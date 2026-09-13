"""Per-deliverable audit trail: *who* triggered a controlled revision and
*when* (always IST, regardless of the host machine's own timezone) --
distinct from both `history/` (preserves the outgoing file itself, via this
project's `snapshot-output.sh` hook and `orchestrator.utils.md_history`) and
`meta.changelog`/`release_history` inside the JSON (the content-facing delta
narrative). This module only ever appends -- and only ever the entry for
the file/version transition it's told about; it never inspects content.

Every writer that already archives to a sibling `history/` folder calls
`record` right alongside that archive call, writing to a sibling
`execution-log/` folder instead: `md_history.snapshot_previous_md` for the
four `.md` reports, and `hooks/snapshot-output.sh` for the three JSON
deliverables it snapshots.

"Who" comes from the frontmatter of an optional `Project Info.md` note at
the attached folder's root (`orchestrator.utils.workspace.operator_info`)
-- this is a single-operator tool with no multi-user auth, so there's no
session identity to derive this from; a user fills it in once. Left blank, each field renders as this project's
standard "TBD – Client/Project Input Required" placeholder, same as any
other unset client/project fact -- never fabricated, never silently
defaulted to an OS or git username.

Never raises: a failed read/write here only loses that log entry, the same
never-block contract `md_history.snapshot_previous_md` and
`snapshot-output.sh` already give their own archival copies. Callers don't
need to guard calls to `record`.

The three JSON deliverables don't go through `md_history` -- they're
snapshotted by `hooks/snapshot-output.sh` instead, a separate process with
no view of this module's Python objects. `hooks/execution-log.sh` (a new
PostToolUse Write|Edit hook, run after the write and after
`snapshot-output.sh`'s own PreToolUse snapshot) calls this module as
`python -m orchestrator.utils.execution_log <file_path>`, which is why
`record_json_deliverable`/`main` exist here too -- reusing `record` rather
than re-implementing "append JSON, re-render MD" a second time.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.utils.md_table import build_table
from orchestrator.utils.workspace import operator_info

# A fixed UTC+5:30 offset, not `zoneinfo.ZoneInfo("Asia/Kolkata")` -- IST has
# no DST to track, and Windows Python has no bundled tzdata (importing that
# key raises ZoneInfoNotFoundError unless the `tzdata` package is installed),
# so a fixed offset is both correct and dependency-free.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
LOG_DIRNAME = "execution-log"
LOG_JSON_NAME = "execution-log.json"
LOG_MD_NAME = "execution-log.md"

TBD = "TBD – Client/Project Input Required"

_MD_COLUMNS = [
    "Timestamp (IST)",
    "File",
    "Action",
    "Version",
    "Changed By",
    "Designation",
    "Project",
    "Project ID",
]


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _render_md(entries: list[dict]) -> str:
    rows = []
    for e in entries:
        version = e.get("version") or {}
        rows.append(
            [
                e.get("timestamp_ist", ""),
                e.get("file", ""),
                e.get("action", ""),
                f"{version.get('from') or '—'} → {version.get('to') or '—'}",
                e.get("changed_by", ""),
                e.get("designation", ""),
                e.get("project_name", ""),
                e.get("project_id", ""),
            ]
        )
    return "# Execution Log\n\n" + build_table(_MD_COLUMNS, rows) + "\n"


def record(deliverable_dir: Path, file_name: str, *, from_version: str | None, to_version: str | None) -> None:
    """Append one entry for `file_name` (just written under
    `deliverable_dir`, e.g. `output/requirement-analysis`) to its sibling
    `execution-log/execution-log.json`, then re-render
    `execution-log/execution-log.md` from the full, updated list.

    `from_version=None` means there was nothing on disk before this write
    (first generation) -- recorded as `action: "created"`; any other call is
    `"updated"`. A version this project can't determine (the Client
    Clarification Sheet, which carries none) is passed through as
    `"unversioned"` by the caller, not `None` -- `None` is reserved for
    "nothing existed before"."""
    log_dir = deliverable_dir / LOG_DIRNAME
    json_path = log_dir / LOG_JSON_NAME
    md_path = log_dir / LOG_MD_NAME

    op = operator_info()
    entry = {
        "timestamp_ist": _now_ist(),
        "file": file_name,
        "action": "created" if from_version is None else "updated",
        "version": {"from": from_version, "to": to_version or "unversioned"},
        "changed_by": op.get("name") or TBD,
        "designation": op.get("designation") or TBD,
        "project_name": op.get("projectName") or TBD,
        "project_id": op.get("projectId") or TBD,
    }

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        if json_path.is_file():
            try:
                loaded = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    entries = loaded
            except (json.JSONDecodeError, OSError):
                pass  # a corrupted log starts fresh rather than blocking the run
        entries.append(entry)
        json_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(_render_md(entries), encoding="utf-8")
    except OSError as exc:
        print(f"WARNING: failed to record execution-log entry for {file_name}: {exc}", file=sys.stderr)


def _parse_version(payload) -> str:
    if not isinstance(payload, dict):
        return "unversioned"
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return "unversioned"
    return str(meta.get("version", "")).strip() or "unversioned"


def _version_sort_key(version: str) -> tuple:
    """Sorts this project's dot-decimal versions ("1.0", "1.10", "2.0")
    numerically component-by-component; an unparsable value sorts below
    every real version rather than raising, so one odd `history/` filename
    never breaks `latest_history_version` for the rest."""
    try:
        return (0, tuple(int(p) for p in version.split(".")))
    except ValueError:
        return (-1, version)


def latest_history_version(history_dir: Path, stem: str, suffix: str) -> str | None:
    """The most recently *reached* prior version for `stem` (e.g.
    `LinkGrid-analysis`), recovered from the `history/<stem>-v<version>.json`
    snapshots `hooks/snapshot-output.sh` leaves behind -- the highest version
    present, since this project's versions only ever increase. `None` when
    there's no history yet for this stem (nothing has ever been revised)."""
    if not history_dir.is_dir():
        return None
    prefix = f"{stem}-v"
    versions = [
        candidate.name[len(prefix) : -len(suffix)]
        for candidate in history_dir.glob(f"{prefix}*{suffix}")
        if candidate.name.endswith(suffix) and len(candidate.name) > len(prefix) + len(suffix)
    ]
    return max(versions, key=_version_sort_key) if versions else None


def record_json_deliverable(file_path: Path) -> None:
    """Entry point for `hooks/execution-log.sh` (PostToolUse Write|Edit):
    given a JSON deliverable just written to disk, records who/when this
    revision happened.

    Runs after the fact, from a separate hook process with no direct view of
    the file's prior content, so both ends of the version transition are
    recovered rather than passed in: `to_version` is read straight off the
    file now on disk; `from_version` is the highest version already
    snapshotted to `history/` for this stem, or `None` when there is none
    (first generation).

    Skips silently -- no duplicate entry -- when the last logged entry for
    this file already names this exact (from, to) pair: an in-run redraft
    that doesn't change `meta.version` (`snapshot-output.sh` skips
    snapshotting those too) would otherwise get logged again on every
    intermediate rewrite, since `history/` itself doesn't change across
    them."""
    if not file_path.is_file():
        return
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    to_version = _parse_version(payload)

    history_dir = file_path.parent / "history"
    from_version = latest_history_version(history_dir, file_path.stem, file_path.suffix)

    log_json_path = file_path.parent / LOG_DIRNAME / LOG_JSON_NAME
    if log_json_path.is_file():
        try:
            entries = json.loads(log_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []
        if isinstance(entries, list):
            for e in reversed(entries):
                if e.get("file") == file_path.name:
                    last_version = e.get("version") or {}
                    if last_version.get("from") == from_version and last_version.get("to") == to_version:
                        return  # nothing changed since the last logged entry
                    break

    record(file_path.parent, file_path.name, from_version=from_version, to_version=to_version)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m orchestrator.utils.execution_log <file_path>", file=sys.stderr)
        sys.exit(1)
    record_json_deliverable(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
