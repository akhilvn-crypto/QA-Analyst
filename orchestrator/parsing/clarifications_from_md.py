"""Reads a Client Clarification Sheet (.md) back into structured data.

Usage:
    python -m orchestrator.parsing.clarifications_from_md <path/to/sheet.md>

Prints a JSON list of every question row in the sheet's table:
    [{"req_id": ..., "requirement": ..., "question": ..., "answer": ...}, ...]

The `.md` sheet is `clarification_sheet_writer.build_sheet_md`'s own output
-- the same four-column table `clarifications_from_docx.read_sheet` reads
from the `.docx` copy, rendered as a Markdown pipe table via
`orchestrator.utils.md_table` instead of a Word table. This is now the
primary ingest path for `/apply-clarifications` (the `.docx` reader is only
a fallback, for when the client/QA typed answers into the Word copy
instead) -- both round-trip the identical row shape, so downstream code
never needs to care which format an answer arrived in.

`answer` is whatever the client/QA typed into the table's Client Response
column (empty string when still unanswered). Cells are unescaped the exact
inverse of `md_table.escape_cell`: `<br>` becomes a literal newline again,
`\\|` becomes a literal `|` again.
"""

import json
import sys
from pathlib import Path

from orchestrator.parsing.clarifications_from_docx import SHEET_COLUMNS
from orchestrator.utils.md_table import split_row

_HEADER_LINE = "| " + " | ".join(SHEET_COLUMNS) + " |"


def read_sheet(md_path: Path) -> list[dict]:
    """Return every question row from the clarification sheet's table."""
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()

    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == _HEADER_LINE), None
    )
    if header_idx is None:
        raise ValueError(
            f"No clarification table (columns: {SHEET_COLUMNS}) found in {md_path}"
        )

    rows = []
    # header_idx + 1 is the "| --- | --- | ... |" separator line; data rows
    # follow immediately and run until the first line that isn't a table row
    # (a blank line, since build_sheet_md never puts anything else there).
    for line in lines[header_idx + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_row(line)
        if len(cells) != len(SHEET_COLUMNS):
            continue
        rows.append(
            {
                "req_id": cells[0],
                "requirement": cells[1],
                "question": cells[2],
                "answer": cells[3],
            }
        )
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.parsing.clarifications_from_md <path/to/sheet.md>",
            file=sys.stderr,
        )
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"File not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    rows = read_sheet(md_path)
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
