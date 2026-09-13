"""Shared archival helper every plain-text Markdown report writer in
`generation/` uses to preserve its own controlled-revision history:
`md_report_writer.py` (requirement analysis), `test_plan_md_writer.py`,
`test_case_md_writer.py`, and `clarification_sheet_writer.py`.

Every one of those reports is produced by a Bash-invoked script, never
`Write`/`Edit`, so `hooks/snapshot-output.sh`'s PreToolUse hook -- which
matches only `Write|Edit` -- never sees any of them. This module is the
Python-side equivalent of that same "preserve every controlled revision"
contract, applied uniformly across all four instead of four independent
copies of the same archive-before-overwrite logic.

Each writer supplies its own `extract_version` -- a function reading the
*outgoing* content, never the on-disk JSON, which by the time any of these
writers runs has already been advanced to the *new* version (every agent
writes the JSON via `Write`/`Edit` first, then calls the deterministic `.md`
writer) -- because where a report's current version lives in its own
rendered text differs writer to writer:

- a labeled bullet, e.g. `* **Document Version:** 1.0` or
  `- **Version:** 1.0` (`bullet_version_extractor`)
- the last row of a Document Release History table, for a report (the Test
  Plan) whose Document Version Control section has no standalone version
  bullet of its own (`release_history_version_extractor`)
- nothing at all -- the Client Clarification Sheet carries no version of
  its own; pass a function that always returns `None`, which snapshots
  under the literal "unversioned" label like any other report whose
  version can't be determined.

`snapshot_previous_md`, given the outgoing report's replacement text via
`new_content`, also records who/when this revision happened to a sibling
`execution-log/` folder (`orchestrator.utils.execution_log`) -- a distinct
audit trail from this module's own `history/` file copies.
"""

import re
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

from orchestrator.utils import execution_log
from orchestrator.utils.md_table import split_row

VersionExtractor = Callable[[str], "str | None"]


def bullet_version_extractor(label: str, marker: str = "*") -> VersionExtractor:
    """Matches this project's "<marker> **<label>:** <value>" bullet
    convention (single-line by construction -- a version string is never
    multi-line)."""
    pattern = re.compile(rf"^{re.escape(marker)}\s+\*\*{re.escape(label)}:\*\*\s*(.+)$", re.MULTILINE)

    def extract(content: str) -> str | None:
        match = pattern.search(content)
        return match.group(1).strip() if match else None

    return extract


def release_history_version_extractor(columns: list[str]) -> VersionExtractor:
    """For a report whose Document Version Control section has no
    standalone version bullet (the Test Plan) -- its current version is
    only recoverable from the last row of its own Document Release History
    table, first column."""
    header_line = "| " + " | ".join(columns) + " |"

    def extract(content: str) -> str | None:
        lines = content.splitlines()
        try:
            header_idx = lines.index(header_line)
        except ValueError:
            return None
        version = None
        # header_idx + 1 is the "| --- | ... |" separator line; data rows
        # follow immediately and run until the first line that isn't one.
        for line in lines[header_idx + 2 :]:
            if not line.strip().startswith("|"):
                break
            cells = split_row(line)
            if cells and cells[0].strip():
                version = cells[0].strip()
        return version

    return extract


def snapshot_previous_md(md_path: Path, extract_version: VersionExtractor, new_content: str | None = None) -> None:
    """Archive the `.md` this run is about to overwrite into a sibling
    `history/` folder before it's gone, named with the version it carried
    (via `extract_version`) and the timestamp it was actually written at --
    not "now", since "now" is essentially the new version's own timestamp.
    No-op when there's nothing on disk yet (first run for this doc) -- except
    for the execution-log entry below, which still records the first
    generation as `action: "created"`.

    Snapshotting must never cost a run its actual deliverable -- same
    contract `snapshot-output.sh` gives the JSON's own history/ copies (it
    always exits 0/allow even on a failed copy). A permissions issue, full
    disk, or a file locked by another process (an editor, a sync client)
    here only loses the archival copy, never the new report.

    `new_content`, when given, is the report text this same call site is
    about to `write_text` right after -- already built, at every one of this
    project's four `.md` writer call sites, before the archive-then-overwrite
    happens. Passing it lets this one call also record the who/when
    execution-log entry (`orchestrator.utils.execution_log`) for both the
    "created" and "updated" case, using the same `extract_version` to read
    the *new* version out of it. Omitted, no execution-log entry is written
    -- a caller that only wants the `history/` archive can still get it."""
    history_dir = md_path.parent / "history"
    existed = md_path.is_file()
    old_version: str | None = None

    if existed:
        try:
            content = md_path.read_text(encoding="utf-8")
            old_version = extract_version(content) or "unversioned"
            timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(md_path.stat().st_mtime))

            history_dir.mkdir(parents=True, exist_ok=True)
            snapshot = history_dir / f"{md_path.stem}-v{old_version}_{timestamp}{md_path.suffix}"
            # Never clobber an existing snapshot -- same never-clobber
            # contract snapshot-output.sh applies to the JSON's own history/
            # copies.
            suffix = 1
            while snapshot.exists():
                snapshot = history_dir / f"{md_path.stem}-v{old_version}_{timestamp}-{suffix}{md_path.suffix}"
                suffix += 1
            shutil.copy2(md_path, snapshot)
        except OSError as exc:
            print(f"WARNING: failed to archive previous {md_path.name} to history/: {exc}", file=sys.stderr)

    if new_content is not None:
        new_version = extract_version(new_content) or "unversioned"
        execution_log.record(
            md_path.parent,
            md_path.name,
            from_version=old_version,
            to_version=new_version,
        )
