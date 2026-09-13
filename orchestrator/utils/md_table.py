"""Shared Markdown table-rendering (and round-tripping) helpers.

Several writers need to render a table whose cells may hold a literal
newline or unescaped pipe -- `md_report_writer.py` (Document Version
Control / Document Release History tables), `clarification_sheet_writer.py`'s
`build_sheet_md` (the Client Clarification Sheet's own table),
`test_case_md_writer.py`, and `test_plan_md_writer.py`. Pulled out here
rather than left duplicated so none of them can ever drift on how a cell
gets escaped -- or, for a reader that round-trips a QA-typed column back
out of its own rendered table (`clarifications_from_md.read_sheet`), on how
a row gets split back apart.
"""

import re

# Splits a pipe-table row on `|` that isn't escaped with a backslash -- the
# exact inverse of `escape_cell`'s `\\|` escaping.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def escape_cell(value: str) -> str:
    """Markdown table cells can't contain a literal newline or unescaped
    pipe -- both appear in real data here (a multi-gap `Gap` field, a
    `Reasons` string, a free-text client answer). Newlines become `<br>`
    (renders as a line break in every Markdown viewer that matters here,
    including Obsidian); pipes are escaped so they never get mistaken for
    a column boundary."""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def unescape_cell(value: str) -> str:
    """The exact inverse of `escape_cell`: `<br>` becomes a literal newline
    again, `\\|` becomes a literal `|` again."""
    return value.strip().replace("<br>", "\n").replace("\\|", "|")


def split_row(line: str) -> list[str]:
    """Splits one rendered pipe-table row back into its cells, unescaping
    each with `unescape_cell`. A well-formed row is "| a | b | c |" -- the
    leading/trailing "|" is stripped first so splitting doesn't yield empty
    leading/trailing cells."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [unescape_cell(cell) for cell in _UNESCAPED_PIPE.split(inner)]


def build_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines)
