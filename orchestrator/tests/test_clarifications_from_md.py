"""`clarifications_from_md.read_sheet` must be the exact inverse of
`md_table.escape_cell` -- a multi-line requirement/question, or one holding
a literal `|`, must round-trip through `build_sheet_md` (and through a
hand-typed client answer in the same table) without losing or corrupting
either character."""

import pytest

from orchestrator.generation.clarification_sheet_writer import build_sheet_md
from orchestrator.models.requirement import DocumentControlMeta
from orchestrator.parsing.clarifications_from_docx import SHEET_COLUMNS
from orchestrator.parsing.clarifications_from_md import read_sheet
from orchestrator.utils.md_table import build_table


def test_build_sheet_md_opens_with_frontmatter_properties_block():
    document_control = DocumentControlMeta(project_id="PRJ-1", document_id="DOC-1")
    content = build_sheet_md([], doc_name="LinkGrid", document_control=document_control)

    assert content.startswith("---\n")
    frontmatter, _, body = content.partition("---\n")[2].partition("---\n")
    assert 'title: "LinkGrid Client Clarification Sheet"' in frontmatter
    assert 'document_type: "Client Clarification Sheet"' in frontmatter
    assert 'project_id: "PRJ-1"' in frontmatter
    assert 'document_id: "DOC-1"' in frontmatter
    # This sheet carries no version of its own -- left blank, not fabricated.
    assert 'version: ""' in frontmatter
    assert 'privacy: "Confidential"' in frontmatter
    assert '  - "clarification-sheet"' in frontmatter
    assert body.startswith("\n# Client Clarification Sheet")


def test_round_trips_build_sheet_md_output(tmp_path):
    rows = [
        (
            "REQ-001",
            "Line one of the requirement.\nLine two, with a | pipe in it.",
            "What about the edge case | involving a pipe?\nAnd a second line?",
        )
    ]
    content = build_sheet_md(rows, doc_name="doc")

    path = tmp_path / "doc-clarifications.md"
    path.write_text(content, encoding="utf-8")

    parsed = read_sheet(path)
    assert len(parsed) == 1
    assert parsed[0]["req_id"] == "REQ-001"
    assert parsed[0]["requirement"] == "Line one of the requirement.\nLine two, with a | pipe in it."
    assert (
        parsed[0]["question"]
        == "What about the edge case | involving a pipe?\nAnd a second line?"
    )
    assert parsed[0]["answer"] == ""


def test_round_trips_a_hand_typed_answer_with_special_characters(tmp_path):
    # build_sheet_md always leaves the Client Response cell blank -- an
    # answer only appears once a client (or QA) types into it directly, so
    # simulate that the same way build_table itself would have rendered it.
    table = build_table(
        SHEET_COLUMNS,
        [
            [
                "REQ-001",
                "Users can reset their password.",
                "How long should the reset link remain valid?",
                "24 hours.\nAlso: the old link | must be invalidated.",
            ]
        ],
    )
    content = "# Client Clarification Sheet\n\n" + table + "\n"

    path = tmp_path / "doc-clarifications.md"
    path.write_text(content, encoding="utf-8")

    parsed = read_sheet(path)
    assert len(parsed) == 1
    assert parsed[0]["answer"] == "24 hours.\nAlso: the old link | must be invalidated."


def test_no_table_raises(tmp_path):
    path = tmp_path / "doc-clarifications.md"
    path.write_text("# Client Clarification Sheet\n\nNo table here.\n", encoding="utf-8")

    with pytest.raises(ValueError):
        read_sheet(path)
