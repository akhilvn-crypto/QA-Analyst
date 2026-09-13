"""Reads a Client Clarification Sheet (.docx) back into structured data.

Usage:
    python -m orchestrator.parsing.clarifications_from_docx <path/to/sheet.docx>

Prints a JSON list of every question row in the sheet's table:
    [{"req_id": ..., "requirement": ..., "question": ..., "answer": ...}, ...]

`answer` is whatever the client/QA typed into the Client Response column
(empty string when still unanswered). The /apply-clarifications flow feeds
the answered rows back into the requirement analysis; the clarification
sheet writer uses the same reader to refuse overwriting a sheet that still
holds unprocessed answers.
"""

import json
import sys
from pathlib import Path

from docx import Document

SHEET_COLUMNS = ["Requirement ID", "Requirement", "Client Question", "Client Response"]


def read_sheet(docx_path: Path) -> list[dict]:
    """Return every question row from the clarification sheet's table."""
    document = Document(str(docx_path))

    for table in document.tables:
        header = [cell.text.strip() for cell in table.rows[0].cells]
        if header != SHEET_COLUMNS:
            continue
        rows = []
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(
                {
                    "req_id": cells[0],
                    "requirement": cells[1],
                    "question": cells[2],
                    "answer": cells[3],
                }
            )
        return rows

    raise ValueError(
        f"No clarification table (columns: {SHEET_COLUMNS}) found in {docx_path}"
    )


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.parsing.clarifications_from_docx <path/to/sheet.docx>",
            file=sys.stderr,
        )
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    if not docx_path.exists():
        print(f"File not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    rows = read_sheet(docx_path)
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
