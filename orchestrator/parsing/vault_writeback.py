"""Companion to `parsing.reading_vault_fetch`, in the opposite direction:
once `/apply-clarifications` has a client's confirmed answer to a gap, this
module snapshots the *originating* note under the attached folder's
`Requirements/` subfolder before the requirement-analyzer agent
rewrites the gap's `source_excerpt` passage in it via `Edit`.

Only the snapshot step lives here -- the actual rewrite is authored prose
(folding a confirmed answer into a note's own voice, as if the ambiguity
was never there), which is the agent's job, not a deterministic script's.
This module's entire contract is: preserve the pre-edit version somewhere
recoverable, or refuse loudly so the agent doesn't edit an unrecoverable
copy. This project isn't a git repository, so there is no other undo path
for a vault note than what this script keeps.

Snapshots land in `<vault>/.history/<relative-dir>/<stem>_<timestamp>.md`,
mirroring the note's own subfolder layout. `.history` is deliberately
dot-prefixed: `parsing.reading_vault_fetch._iter_md_files` and
`knowledge_base.search.find_markdown_files` both already skip any
dot-prefixed directory (Obsidian's own `.obsidian` folder is the reason
that convention exists), so snapshots never get re-ingested as fresh
requirement content or knowledge-base notes -- no separate exclusion rule
to keep in sync.

Usage:
    python -m orchestrator.parsing.vault_writeback snapshot "<relative-file-path>" [--folder <name>]

`--folder` is an exact top-level folder name to use instead of matching
`Requirements` by convention -- for a client vault that names it something
else entirely (see `orchestrator.utils.workspace`'s folder-auto-detection
note). Not cached anywhere; supply it again on every run that needs it.

Prints the absolute snapshot path on success and exits 0. Exits 1 -- with
the reason on stderr -- when the attached folder has no `Requirements/`
subfolder (nor the given `--folder`), the target file doesn't exist under
it (or the given path resolves outside the vault entirely), or the copy
itself fails. Any exit 1 here means: do not edit the note -- the caller
falls back to recording the clarification in the analysis JSON only.
"""

import argparse
import sys
import time
from pathlib import Path

from orchestrator.utils.workspace import requirements_path


def snapshot(vault: Path, relative_file_path: str) -> Path:
    """Copy `vault / relative_file_path`'s current content into
    `<vault>/.history/...`, never clobbering an existing snapshot. Returns
    the snapshot path. Raises `ValueError`/`OSError` on any failure --
    the caller decides how to report it; this function never partially
    writes a snapshot it doesn't return."""
    target = (vault / relative_file_path).resolve()
    vault_resolved = vault.resolve()
    if vault_resolved not in target.parents and target != vault_resolved:
        raise ValueError(f"'{relative_file_path}' resolves outside the vault ({vault}).")
    if not target.is_file():
        raise ValueError(f"No such file under the vault: {relative_file_path}")

    rel = target.relative_to(vault_resolved)
    history_dir = vault_resolved / ".history" / rel.parent
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(target.stat().st_mtime))
    dest = history_dir / f"{target.stem}_{timestamp}{target.suffix}"
    suffix = 1
    while dest.exists():
        dest = history_dir / f"{target.stem}_{timestamp}-{suffix}{target.suffix}"
        suffix += 1

    dest.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.parsing.vault_writeback",
        description="Snapshot a requirement-reading vault note before /apply-clarifications edits it in place.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_snapshot = sub.add_parser(
        "snapshot", help="Archive a vault note's current content to .history/ before editing it."
    )
    p_snapshot.add_argument(
        "relative_file_path", help="Path to the note, relative to the Requirements/ folder."
    )
    p_snapshot.add_argument(
        "--folder",
        default=None,
        help=(
            "Exact top-level folder name to use instead of matching 'Requirements' by "
            "convention -- for a client vault that names it something else entirely."
        ),
    )

    args = parser.parse_args()

    vault = requirements_path(args.folder) if args.folder else requirements_path()
    if vault is None:
        print(
            "No Requirements/ folder found in the attached folder -- "
            "there is no requirement note to snapshot.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        dest = snapshot(vault, args.relative_file_path)
    except (ValueError, OSError) as exc:
        print(f"Failed to snapshot '{args.relative_file_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    print(dest)
    sys.exit(0)


if __name__ == "__main__":
    main()
