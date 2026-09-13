"""Tells the requirement-analyzer whether a full/delta re-analysis run
would find anything new to do.

Usage:
    python -m orchestrator.validation.analysis_currency <doc-name>

Compares `output/requirement-analysis/<doc-name>-source.md`'s mtime
(staged fresh by every `/analyse-requirement` run via
`parsing.reading_vault_fetch`, which only rewrites -- and only then
touches the mtime of -- that file when the vault's combined content
actually changed) against `<doc-name>-analysis.json`'s mtime. This is the
same "source not newer than analysis" comparison Docx-only mode and
`validate.py`'s own staleness warning (`_staleness_warnings`) already rely
on, just applied here as its own reusable, testable check rather than
prose the agent re-derives ad hoc.

Exit 0, prints "changed: ...": no prior analysis exists, or the source is
newer than it -- something to (re-)analyze, or this is the first run.

Exit 1, prints "unchanged: ..." (to stderr) naming the current version and
when it was prepared: the source is not newer than the existing analysis
-- nothing in the requirement vault has changed since that run. This is
the guard that stops a plain re-run of `/analyse-requirement` from
silently re-reasoning and re-versioning an analysis nothing actually
changed for; see requirement-analyzer.md's Mode selection section for how
the two exit codes route to Docx-only mode vs. the no-op guard.
"""

import sys

from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.paths import analysis_json_path, requirement_source_md_path


def check(doc_name: str) -> tuple[bool, str]:
    """Returns `(changed, message)`. `changed` is True when a full/delta
    re-analysis has real work to do (first analysis, or the source is
    newer than the existing one); False when the existing analysis is
    already current with the vault's combined content."""
    json_path = analysis_json_path(doc_name)
    source_path = requirement_source_md_path(doc_name)

    if not json_path.is_file():
        return True, f"changed: no prior analysis at {json_path.name} -- this is a first analysis."
    if not source_path.is_file():
        # Shouldn't happen -- parsing.reading_vault_fetch always writes this
        # first -- but a missing comparison point must never block a real
        # run on this script's own confusion.
        return True, f"changed: no staged source found at {source_path.name} to compare against."
    if source_path.stat().st_mtime > json_path.stat().st_mtime:
        return True, "changed: the requirement source is newer than the existing analysis."

    version = "unknown"
    prepared_date = "unknown"
    try:
        data = read_json(json_path)
        if isinstance(data, dict):
            meta = data.get("meta") or {}
            document_control = data.get("document_control") or {}
            version = meta.get("version", version)
            prepared_date = document_control.get("prepared_date", prepared_date)
    except Exception:
        pass

    return False, (
        f"unchanged: {json_path.name} is already current (version {version}, "
        f"prepared {prepared_date}) -- no requirement content changed since "
        "that run. Nothing to re-analyze; pass --docx if you want the Word "
        "copy and don't already have a current one."
    )


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m orchestrator.validation.analysis_currency <doc-name>", file=sys.stderr)
        sys.exit(2)

    _, doc_name = sys.argv
    changed, message = check(doc_name)
    if changed:
        print(message)
        sys.exit(0)
    print(message, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
