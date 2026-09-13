"""Entry point for manual/CLI invocation of the requirement-analysis pipeline.

The primary trigger for analysis is the /analyse-requirement slash command,
which invokes the requirement-analyzer agent directly. This entry point exists
for running the fetch step manually, outside of the agent.

Usage:
    python -m orchestrator.main
"""

import sys

from orchestrator.parsing.reading_vault_fetch import combine
from orchestrator.utils.config import requirement_reading_vault_path
from orchestrator.utils.paths import requirement_source_md_path


def main() -> None:
    vault = requirement_reading_vault_path()
    if vault is None:
        print(
            "requirementReading.obsidianPath is not configured in "
            "config/settings.json -- there is no requirement source to read.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not vault.is_dir():
        print(f"Configured requirementReading.obsidianPath does not exist: {vault}", file=sys.stderr)
        sys.exit(1)

    combined_text, count = combine(vault)
    if count == 0:
        print(f"No .md files found under {vault}", file=sys.stderr)
        sys.exit(1)

    doc_name = vault.name
    dest = requirement_source_md_path(doc_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.read_text(encoding="utf-8") != combined_text:
        dest.write_text(combined_text, encoding="utf-8")

    print(f"Combined {count} file(s) into: {dest}")
    print(
        "Run the requirement-analyzer agent (via /analyse-requirement) "
        "to complete extraction and report generation."
    )


if __name__ == "__main__":
    main()
