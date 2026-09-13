"""The Knowledge Base Service -- a persistent, in-memory alternative to
`knowledge_base.search`'s per-call disk reads, scoped to exactly one of the
two folders that module knows about: the attached folder's
`Knowledge Base/` subfolder (general domain background). `Requirements/` --
this project's sole requirement-input source, and its own separate
per-requirement reasoning fallback -- is untouched by this module;
`knowledge_base.search --source reading` keeps working exactly as before.

Every other orchestrator module in this project is a fresh, short-lived
`python -m orchestrator.<module>` subprocess (see `scripts/run.sh`) -- this
is the first one that isn't. `start` spawns a **detached** background HTTP
server (stdlib `http.server` only, no new dependency) that holds the loaded
vault and its catalog in memory until `stop` is run, independent of the
session that started it:

    start-kb-service  -> RUNNING, Knowledge Base NOT_LOADED
    load-kb           -> builds a temp KB + temp Catalog, validates, then
                          atomically swaps -- a failed (re)load never
                          exposes a partial KB, and never discards a
                          previously good one just because a later reload
                          failed (see `KnowledgeBaseService.load`)
    kb-status         -> current service/KB state, always answerable,
                          never itself an error
    stop-kb-service   -> graceful shutdown (forced after a short timeout),
                          state files cleaned up, memory released

Deliberately no vector search, no embeddings, no chunking: `get_file`
always returns one complete file exactly as written, and the catalog exists
only so an agent can pick *which* file to retrieve without reading all of
them first.

## Discovery and lifecycle mechanics

The server binds `127.0.0.1:0` (an OS-assigned free port -- no
"port already in use" handling needed, and two different workspaces can run
this service simultaneously with zero collision) and writes the bound port
to `orchestrator.utils.paths.kb_service_port_path()` the instant it binds,
via `os.replace` from a temp file so no reader ever sees a half-written
value. **Liveness is always a network check** (`GET /status`), never a PID
check -- cross-platform PID-liveness is unreliable (nothing on Windows maps
cleanly to POSIX's `os.kill(pid, 0)`), whereas "can I reach the port" is
exactly the property that matters. A PID file is kept only as `stop`'s
force-kill fallback if a graceful `POST /shutdown` doesn't finish in time.

The detached child is spawned with `stdin=DEVNULL` and `stdout`/`stderr`
redirected to `kb_service_log_path()` explicitly -- never left to inherit
the launching CLI call's own streams, which is the classic way a caller
ends up blocked forever on a process that will never produce EOF.

## HTTP API (JSON in, JSON out; loopback only, no auth -- consistent with
the rest of this project's local-file-operations threat model)

    GET  /status    -> current ServiceStatus, always 200
    GET  /catalog    -> catalog entries, or a 409 naming why none are
                        available yet (never loaded / still loading)
    GET  /file?name=<n> -> {"content": "..."} on 200, 404/409 otherwise
    POST /load      -> triggers (re)load synchronously, returns the
                        resulting ServiceStatus
    POST /shutdown  -> schedules `httpd.shutdown()` on a separate thread
                        (calling it inline from the request-handling thread
                        deadlocks ThreadingHTTPServer) and returns 200
                        immediately

## CLI (`python -m orchestrator.knowledge_base.service <verb>`)

`start`, `stop`, `status`, `load`, `catalog`, `file <name>` -- each prints
JSON on stdout (`file` prints the raw file content instead, so a caller
treats it exactly like a file it `Read` directly), plus an internal-only
`_serve`, run only by the detached child `start` spawns; nothing else
should ever invoke it. Exit codes: `0` the request was answered (for
`status`, this includes reporting STOPPED -- an ordinary answer, not a
failure); `1` the service isn't reachable; `2` the KB has never been
loaded; `3` the KB is still loading for the first time (nothing cached
yet); `4` (`file` only) the named file doesn't exist in the loaded KB.
`start`/`stop`/`status` always exit 0 once they've done their own job of
starting/stopping/reporting; `load`/`catalog`/`file` use the fuller
contract above since those three genuinely need the service in a workable
state to do anything.

## Known, accepted limitations

A narrow double-`start` race exists if two callers both observe STOPPED
before either's port file lands -- the later write wins and the other's
spawned child becomes an undiscoverable orphan. Acceptable for a
single-developer local tool; not worth cross-platform advisory-lock code.
Loopback-only with no auth means any other local OS user on a shared
machine could reach the port -- same threat model as every other local file
operation in this project already has. The service outlives the session
that started it by design, so deleting/relocating a workspace without
running `stop` first leaks a harmless orphan process; `kb-status`'s own
output always names the stop command and log file for exactly this reason.
"""

import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from orchestrator.knowledge_base.search import find_markdown_files, split_sections
from orchestrator.models.knowledge_base_service import (
    ERROR_FILE_NOT_FOUND,
    ERROR_KB_LOADING,
    ERROR_KB_NOT_LOADED,
    ERROR_SERVICE_STOPPED,
    KB_ERROR,
    KB_LOADED,
    KB_LOADING,
    KB_NOT_LOADED,
    SERVICE_RUNNING,
    SERVICE_STOPPED,
    CatalogEntry,
    ServiceStatus,
)
from orchestrator.utils import workspace
from orchestrator.utils.paths import (
    WORKSPACE_ROOT,
    kb_service_dir,
    kb_service_log_path,
    kb_service_pid_path,
    kb_service_port_path,
)

EXIT_OK = 0
EXIT_SERVICE_STOPPED = 1
EXIT_KB_NOT_LOADED = 2
EXIT_KB_LOADING = 3
EXIT_FILE_NOT_FOUND = 4

# Seconds. Deliberately generous relative to a plain status probe: `start`
# has to wait for a brand-new process to import, bind, and write its port
# file; `stop` has to wait for an existing one to unwind its server loop.
_START_TIMEOUT = 5.0
_STOP_TIMEOUT = 5.0
# A short, cheap probe timeout for an ordinary status/catalog/file request
# against an already-running server -- should never legitimately take long.
_REQUEST_TIMEOUT = 2.0
# Loading a whole vault into memory is the one call allowed to take longer.
_LOAD_TIMEOUT = 30.0


# --- catalog generation -----------------------------------------------------


def build_catalog_entry(name: str, text: str) -> CatalogEntry:
    """Purpose + Topics for one file, derived only from what's literally in
    it -- never invented, matching this project's "never fabricate" rule.
    Reuses `search.split_sections`'s heading parser rather than a second
    implementation.

    Purpose is the file's first non-empty paragraph -- the prose before its
    first heading, or that heading's own leading paragraph when the file
    opens with one. Topics are the file's own heading titles (the leaf of
    each heading's trail, not the repeated trail itself), deduplicated, in
    document order."""
    purpose = ""
    topics: list[str] = []
    seen: set[str] = set()

    for section in split_sections(text):
        if section["heading_path"]:
            leaf = section["heading_path"].rsplit(" > ", 1)[-1]
            if leaf not in seen:
                seen.add(leaf)
                topics.append(leaf)

        if not purpose:
            lines = section["text"].splitlines()
            if lines and lines[0].lstrip().startswith("#"):
                lines = lines[1:]  # drop the heading line itself
            remainder = "\n".join(lines).strip()
            if remainder:
                purpose = " ".join(remainder.split("\n\n", 1)[0].split())

    return CatalogEntry(name=name, purpose=purpose, topics=topics)


# --- the plain, network-free service ----------------------------------------


class KnowledgeBaseService:
    """Holds the loaded Knowledge Base + Catalog in memory. No networking
    here at all -- `load`/`status`/`get_catalog`/`get_file` are the whole
    surface, which is what makes this class directly unit-testable. The
    HTTP layer below is a thin wrapper around one instance of it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kb: dict[str, str] = {}
        self._catalog: dict[str, CatalogEntry] = {}
        self._kb_state = KB_NOT_LOADED
        self._loaded_at = ""
        self._error = ""
        self._loading = False
        # True the moment a load has ever succeeded, and never reset --
        # this (not `_kb_state`) is what gates `/catalog`/`/file`: per the
        # spec, a KB currently ERROR (a failed reload) or LOADING (a
        # reload in progress) should still serve the last good content if
        # one exists, rather than pretending nothing is available.
        self._ever_loaded = False

    def _status_locked(self) -> ServiceStatus:
        return ServiceStatus(
            service_state=SERVICE_RUNNING,
            kb_state=self._kb_state,
            files_loaded=len(self._kb),
            catalog_ready=bool(self._catalog),
            loaded_at=self._loaded_at,
            error=self._error,
        )

    def status(self) -> ServiceStatus:
        with self._lock:
            return self._status_locked()

    def has_content(self) -> bool:
        with self._lock:
            return self._ever_loaded

    def load(self) -> ServiceStatus:
        """Build a new KB + Catalog into local temporaries, validate, and
        only then swap the active ones -- readers never see a partial KB
        (the "Atomic Loading Requirement"). A concurrent second call while
        one is already running returns the in-progress status rather than
        racing a second build. A failed (re)load sets `kb_state` to
        `ERROR` with a message, but never clears whatever was already
        loaded -- `get_file`/`get_catalog` keep serving the last good
        content, satisfying "preserve the previously valid Knowledge Base"
        without pretending the failed attempt didn't happen."""
        with self._lock:
            if self._loading:
                return self._status_locked()
            self._loading = True
            self._kb_state = KB_LOADING

        # Resolved on every load (workspace lookups are never cached), so a
        # Knowledge Base/ folder added or renamed mid-session is picked up
        # by the very next load rather than only after a restart.
        folder = workspace.knowledge_base_path()

        if folder is None:
            with self._lock:
                self._kb_state = KB_ERROR
                self._error = (
                    "No Knowledge Base/ folder found in the attached folder."
                )
                self._loading = False
                return self._status_locked()

        try:
            new_kb: dict[str, str] = {}
            new_catalog: dict[str, CatalogEntry] = {}
            for md_file in find_markdown_files(folder):
                rel = md_file.relative_to(folder).as_posix()
                try:
                    text = md_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue  # one unreadable note skips, never fails the whole load
                new_kb[rel] = text
                new_catalog[rel] = build_catalog_entry(rel, text)
        except OSError as exc:
            with self._lock:
                self._kb_state = KB_ERROR
                self._error = f"Knowledge Base load failed: {exc}"
                self._loading = False
                return self._status_locked()

        with self._lock:
            self._kb = new_kb
            self._catalog = new_catalog
            self._kb_state = KB_LOADED
            self._loaded_at = datetime.datetime.now().isoformat(timespec="seconds")
            self._error = ""
            self._loading = False
            self._ever_loaded = True
            return self._status_locked()

    def get_catalog(self) -> list[dict]:
        with self._lock:
            return [entry.to_dict() for entry in self._catalog.values()]

    def get_file(self, name: str) -> str | None:
        with self._lock:
            return self._kb.get(name)


# --- pure route handlers (no socket involved -- unit-testable directly) ----


def handle_status(service: KnowledgeBaseService) -> tuple[int, dict]:
    return 200, service.status().to_dict()


def handle_catalog(service: KnowledgeBaseService) -> tuple[int, object]:
    if not service.has_content():
        status = service.status()
        message = ERROR_KB_LOADING if status.kb_state == KB_LOADING else ERROR_KB_NOT_LOADED
        return 409, {"error": message}
    return 200, service.get_catalog()


def handle_file(service: KnowledgeBaseService, name: str) -> tuple[int, object]:
    if not service.has_content():
        status = service.status()
        message = ERROR_KB_LOADING if status.kb_state == KB_LOADING else ERROR_KB_NOT_LOADED
        return 409, {"error": message}
    content = service.get_file(name)
    if content is None:
        return 404, {"error": ERROR_FILE_NOT_FOUND}
    return 200, {"content": content}


# --- HTTP layer --------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def _write_json(self, status_code: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib-mandated name
        service: KnowledgeBaseService = self.server.kb_service  # type: ignore[attr-defined]
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            self._write_json(*handle_status(service))
        elif parsed.path == "/catalog":
            self._write_json(*handle_catalog(service))
        elif parsed.path == "/file":
            name = (parse_qs(parsed.query).get("name") or [""])[0]
            self._write_json(*handle_file(service, name))
        else:
            self._write_json(404, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802 - stdlib-mandated name
        service: KnowledgeBaseService = self.server.kb_service  # type: ignore[attr-defined]
        if self.path == "/load":
            self._write_json(200, service.load().to_dict())
        elif self.path == "/shutdown":
            self._write_json(200, {"ok": True})
            # Must run on a different thread than this request-handling
            # one -- calling shutdown() inline here deadlocks
            # ThreadingHTTPServer (it joins the very thread calling it).
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._write_json(404, {"error": "Not found."})


def _serve() -> None:
    """The actual server loop. Run **only** by the detached child process
    `start` spawns -- never call this directly."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.kb_service = KnowledgeBaseService()  # type: ignore[attr-defined]

    port_path = kb_service_port_path()
    port_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = port_path.with_name(port_path.name + ".tmp")
    tmp_path.write_text(str(server.server_address[1]), encoding="utf-8")
    os.replace(tmp_path, port_path)  # atomic -- a reader never sees a half-written port

    try:
        server.serve_forever()
    finally:
        server.server_close()
        for path in (kb_service_port_path(), kb_service_pid_path()):
            try:
                path.unlink()
            except OSError:
                pass


# --- CLI-side HTTP client + verbs --------------------------------------------


def _read_port() -> int | None:
    try:
        return int(kb_service_port_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_pid() -> int | None:
    try:
        return int(kb_service_pid_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _cleanup_stale_files() -> None:
    for path in (kb_service_port_path(), kb_service_pid_path()):
        try:
            path.unlink()
        except OSError:
            pass


def _http_call(method: str, path: str, timeout: float = _REQUEST_TIMEOUT):
    """`(status_code, json_payload)` on any response the server actually
    sent (2xx included via urlopen, 4xx/5xx via the HTTPError branch --
    both are "the service answered"), or `None` when it couldn't be
    reached at all (nothing listening / connection refused / timed out) --
    `None` is this module's one signal for "treat as STOPPED"."""
    port = _read_port()
    if port is None:
        return None
    url = f"http://127.0.0.1:{port}{path}"
    request = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            payload = {"error": str(exc)}
        return exc.code, payload
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def verb_start() -> int:
    already_running = _http_call("GET", "/status")
    if already_running is not None:
        print(json.dumps(already_running[1], indent=2))
        return EXIT_OK

    kb_service_dir().mkdir(parents=True, exist_ok=True)
    log_path = kb_service_log_path()
    with open(log_path, "ab") as log_fh:
        popen_kwargs: dict = dict(
            args=[sys.executable, "-m", "orchestrator.knowledge_base.service", "_serve"],
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            cwd=str(WORKSPACE_ROOT),
            env=os.environ.copy(),
        )
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(**popen_kwargs)

    kb_service_pid_path().write_text(str(process.pid), encoding="utf-8")

    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        result = _http_call("GET", "/status")
        if result is not None:
            print(json.dumps(result[1], indent=2))
            return EXIT_OK
        time.sleep(0.1)

    print(
        f"Knowledge Base Service failed to start within {_START_TIMEOUT:.0f}s -- "
        f"see {log_path} for details.",
        file=sys.stderr,
    )
    return EXIT_SERVICE_STOPPED


def verb_stop() -> int:
    pid = _read_pid()
    _http_call("POST", "/shutdown")  # best-effort; a stopped service has nothing to answer

    deadline = time.monotonic() + _STOP_TIMEOUT
    while time.monotonic() < deadline and _http_call("GET", "/status") is not None:
        time.sleep(0.1)

    if _http_call("GET", "/status") is not None and pid is not None:
        # Graceful shutdown didn't finish in time -- force it. `os.kill`
        # with SIGTERM maps to TerminateProcess on Windows, so this one
        # call is already cross-platform without shelling out to taskkill.
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass  # already gone

    _cleanup_stale_files()
    print(json.dumps(ServiceStatus(service_state=SERVICE_STOPPED).to_dict(), indent=2))
    return EXIT_OK


def verb_status() -> int:
    result = _http_call("GET", "/status")
    if result is None:
        _cleanup_stale_files()
        print(json.dumps(ServiceStatus(service_state=SERVICE_STOPPED).to_dict(), indent=2))
        return EXIT_OK
    print(json.dumps(result[1], indent=2))
    return EXIT_OK


def verb_load() -> int:
    result = _http_call("POST", "/load", timeout=_LOAD_TIMEOUT)
    if result is None:
        print(ERROR_SERVICE_STOPPED, file=sys.stderr)
        return EXIT_SERVICE_STOPPED
    print(json.dumps(result[1], indent=2))
    return EXIT_OK


def verb_catalog() -> int:
    result = _http_call("GET", "/catalog")
    if result is None:
        print(ERROR_SERVICE_STOPPED, file=sys.stderr)
        return EXIT_SERVICE_STOPPED
    status_code, payload = result
    if status_code == 200:
        print(json.dumps(payload, indent=2))
        return EXIT_OK
    message = payload.get("error", "") if isinstance(payload, dict) else ""
    print(message, file=sys.stderr)
    return EXIT_KB_LOADING if message == ERROR_KB_LOADING else EXIT_KB_NOT_LOADED


def verb_file(name: str) -> int:
    result = _http_call("GET", f"/file?name={quote(name)}")
    if result is None:
        print(ERROR_SERVICE_STOPPED, file=sys.stderr)
        return EXIT_SERVICE_STOPPED
    status_code, payload = result
    if status_code == 200 and isinstance(payload, dict):
        sys.stdout.write(payload.get("content", ""))
        return EXIT_OK
    message = payload.get("error", "") if isinstance(payload, dict) else ""
    print(message, file=sys.stderr)
    if message == ERROR_FILE_NOT_FOUND:
        return EXIT_FILE_NOT_FOUND
    if message == ERROR_KB_LOADING:
        return EXIT_KB_LOADING
    return EXIT_KB_NOT_LOADED


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.knowledge_base.service",
        description="Lifecycle and query commands for the Knowledge Base Service.",
    )
    subparsers = parser.add_subparsers(dest="verb", required=True)
    subparsers.add_parser("start")
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    subparsers.add_parser("load")
    subparsers.add_parser("catalog")
    file_parser = subparsers.add_parser("file")
    file_parser.add_argument("name")
    subparsers.add_parser("_serve")  # internal only -- the detached child, never called directly

    args = parser.parse_args()

    if args.verb == "_serve":
        _serve()
        return

    verbs = {
        "start": verb_start,
        "stop": verb_stop,
        "status": verb_status,
        "load": verb_load,
        "catalog": verb_catalog,
    }
    if args.verb == "file":
        sys.exit(verb_file(args.name))
    sys.exit(verbs[args.verb]())


if __name__ == "__main__":
    main()
