"""Sole source for `/analyse-requirement`'s requirement input: combines
every `.md` file found under the attached folder's `Requirements/`
subfolder (`orchestrator.utils.workspace.requirements_path`) into one
staged markdown document at
`output/requirement-analysis/<doc-name>-source.md`, where `<doc-name>` is
the attached folder's own name -- this project analyzes exactly one
combined requirement set per attached folder, not a per-file selection.
There is no `.docx`/`.xlsx` requirement-document handling; a client's
requirement notes live in `Requirements/` as `.md` files.

This is deliberately separate from that same vault's other, pre-existing
use: `knowledge_base.search --source reading` reads the same folder for the
requirement-analyzer's per-requirement mid-analysis fallback queries (see
that agent's step 5), returning only the sections a query matched. This
script takes the whole folder unconditionally -- a plain filesystem read and
concatenation -- and runs at the start of every `/analyse-requirement`
invocation. The two paths don't overlap at runtime.

Every `.md` file found (recursively, skipping any dot-prefixed housekeeping
folder -- Obsidian's own `.obsidian`, and this project's own `.history`
snapshots from `parsing.vault_writeback`) becomes one section of the
combined document, under its own `## Source: <relative path>` heading -- the requirement-analyzer
treats all sections as one combined requirement set, exactly as it already
treats a multi-sheet `.xlsx` workbook's sheets as one combined set (a
holdover convention from before this vault-only redesign, kept because the
same judgment call applies: use discretion on a note that clearly isn't a
requirement itself, e.g. a glossary or meeting-notes page).

The staged file is only rewritten when the combined content actually
differs from what's already there -- otherwise its mtime is left alone.
This is what lets every mtime-based staleness/regeneration check downstream
(`requirement-analyzer`'s docx-only-mode shortcut, `validation.validate`'s
staleness warning, `validation.delta_report`) keep working exactly as they
did against the old docx/xlsx conversion this replaces: re-running this
script when nothing in the vault changed must not itself look like a
change.

Usage:
    python -m orchestrator.parsing.reading_vault_fetch

Prints the resolved doc-name on the first line, then
`source: <vault path> (<n> file(s) combined)` on the second, and exits 0.
Exits 1 if the attached folder has no `Requirements/` subfolder, or it
contains no `.md` files.
"""

import sys
from pathlib import Path

from orchestrator.utils.paths import requirement_source_md_path
from orchestrator.utils.workspace import document_name, requirements_path


def _iter_md_files(vault: Path):
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        # Any dot-prefixed directory is vault housekeeping, never a
        # requirement note -- Obsidian's own `.obsidian`, and this project's
        # `.history` snapshots that parsing.vault_writeback drops next to a
        # note before rewriting it in place. Same convention (and same
        # reason) as knowledge_base.search.find_markdown_files's own
        # dot-directory skip, deliberately -- one rule, not two to keep in
        # sync across the vault's two independent readers.
        if any(part.startswith(".") for part in path.relative_to(vault).parts[:-1]):
            continue
        yield path


def combine(vault: Path) -> tuple[str, int]:
    """Combine every `.md` file under `vault` into one markdown document,
    one `## Source: <relative path>` section per file. Returns
    `(combined_text, file_count)`."""
    files = list(_iter_md_files(vault))
    sections = [
        f"## Source: {path.relative_to(vault)}\n\n{path.read_text(encoding='utf-8').strip()}\n"
        for path in files
    ]
    return "\n".join(sections), len(files)


def main() -> None:
    vault = requirements_path()
    if vault is None:
        print(
            "No Requirements/ folder found in the attached folder -- "
            "there is no requirement source to read. Create a Requirements/ "
            "subfolder holding the requirement .md notes.",
            file=sys.stderr,
        )
        sys.exit(1)

    combined_text, count = combine(vault)
    if count == 0:
        print(f"No .md files found under {vault}", file=sys.stderr)
        sys.exit(1)

    doc_name = document_name()
    dest = requirement_source_md_path(doc_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.read_text(encoding="utf-8") != combined_text:
        dest.write_text(combined_text, encoding="utf-8")

    plural = "" if count == 1 else "s"
    print(doc_name)
    print(f"source: {vault} ({count} file{plural} combined)")
    sys.exit(0)


if __name__ == "__main__":
    main()
