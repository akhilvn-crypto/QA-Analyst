"""`/build-kb-catalog` -- the whole Knowledge Base mechanism, replacing the
former Knowledge Base Service (a persistent background HTTP process with a
start/load/status/stop lifecycle, atomic hot-swap, and its own client). That
turned out to be a lot of machinery for what agents actually need: a small
map of what's in `Knowledge Base/` so they can decide *which* file, if any,
is worth reading in full, without reading all of them first for every
requirement/plan/test-case doubt.

This is a single deterministic pass, run once by the user whenever they add
or edit notes:

    python -m orchestrator.knowledge_base.catalog [--folder <name>]

It scans every `.md` file under the attached folder's `Knowledge Base/`
subfolder (`orchestrator.utils.workspace.knowledge_base_path`, or an exact
top-level folder name via `--folder` when a client vault's folder isn't
named anything the usual convention match recognizes -- see
`workspace.py`'s folder-auto-detection note), derives one `CatalogEntry`
per file (name/purpose/description, never the file's content), and writes
the whole thing as one JSON file: `orchestrator.utils.paths.kb_catalog_path()`
(`output/knowledge-base/catalog.json`). That JSON also carries the
Knowledge Base folder's own resolved absolute path, so an agent that judges
an entry relevant can `Read` it directly -- `<catalog's "folder">/<entry's
"name">` -- with its own `Read` tool. No service to query, no HTTP, no
lifecycle: reading the catalog file and then reading a named file are both
just filesystem reads, exactly like every other input in this project.

Deliberately no self-heal, no staleness check, and no vector
search/embeddings/chunking anywhere in this path: a generator agent reads
whatever catalog currently exists (or none at all, treated exactly like an
unconfigured Knowledge Base always has been -- reason from the requirement
text alone) and never rebuilds it itself. Rebuilding is this command's job
alone, run again by the user after editing notes -- deliberate and visible,
not something happening silently mid-analysis.

Exits 0 having written the catalog, printing `<n> file(s) cataloged from
<folder>` plus the output path. Exits 1 -- with the reason on stderr, and
writes nothing -- when no Knowledge Base folder is found (by convention or
the given `--folder`); that's an ordinary "nothing to catalog" outcome, not
a crash.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from orchestrator.knowledge_base.search import find_markdown_files, split_sections
from orchestrator.models.knowledge_base_catalog import CatalogEntry
from orchestrator.utils import workspace
from orchestrator.utils.paths import kb_catalog_path


def build_catalog_entry(name: str, text: str) -> CatalogEntry:
    """Purpose + description for one file, derived only from what's
    literally in it -- never invented, matching this project's "never
    fabricate" rule. Reuses `search.split_sections`'s heading parser rather
    than a second implementation.

    `purpose` is the file's first non-empty paragraph -- the prose before
    its first heading, or that heading's own leading paragraph when the
    file opens with one. `description` is a short, still-literal summary an
    agent can judge relevance from without reading the whole file: the
    file's own heading titles ("Covers: A, B, C.") when it has any,
    otherwise its second paragraph (there's nothing else to summarize
    with), otherwise empty for a file that's genuinely just one short
    paragraph."""
    purpose = ""
    extra_paragraph = ""
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
                paragraphs = remainder.split("\n\n", 1)
                purpose = " ".join(paragraphs[0].split())
                if len(paragraphs) > 1:
                    extra_paragraph = " ".join(paragraphs[1].split())

    if topics:
        description = "Covers: " + ", ".join(topics) + "."
    else:
        description = extra_paragraph

    return CatalogEntry(name=name, purpose=purpose, description=description)


def build_catalog(folder: Path) -> list[CatalogEntry]:
    """One `CatalogEntry` per readable `.md` file under `folder`, in the
    same sorted order `find_markdown_files` already guarantees -- so two
    builds over unchanged notes always produce the same file order."""
    entries = []
    for md_file in find_markdown_files(folder):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # one unreadable note skips, never fails the whole build
        rel = md_file.relative_to(folder).as_posix()
        entries.append(build_catalog_entry(rel, text))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.knowledge_base.catalog",
        description="Build the Knowledge Catalog from the attached folder's Knowledge Base/ notes.",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help=(
            "Exact top-level folder name to catalog instead of matching 'Knowledge Base' by "
            "convention -- for a client vault that names it something else entirely."
        ),
    )
    args = parser.parse_args()

    folder = workspace.knowledge_base_path(args.folder) if args.folder else workspace.knowledge_base_path()
    if folder is None:
        print(
            "No Knowledge Base/ folder found in the attached folder -- there is nothing to "
            "catalog. Add a Knowledge Base/ subfolder of domain-background .md notes, or pass "
            "--folder \"<name>\" if it's named something else.",
            file=sys.stderr,
        )
        sys.exit(1)

    entries = build_catalog(folder)
    payload = {
        "folder": str(folder),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": [entry.to_dict() for entry in entries],
    }

    dest = kb_catalog_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    plural = "" if len(entries) == 1 else "s"
    print(f"{len(entries)} file{plural} cataloged from {folder}")
    print(dest)
    sys.exit(0)


if __name__ == "__main__":
    main()
