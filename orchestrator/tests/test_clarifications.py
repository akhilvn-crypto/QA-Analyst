import json

import pytest
from docx import Document

from orchestrator.generation.clarification_sheet_writer import write_sheet
from orchestrator.parsing.clarifications_from_docx import read_sheet as read_sheet_docx
from orchestrator.parsing.clarifications_from_md import read_sheet as read_sheet_md
from orchestrator.utils.md_table import build_table

_SHEET_COLUMNS = ["Requirement ID", "Requirement", "Client Question", "Client Response"]


def _analysis(clarification_log=None) -> dict:
    return {
        "meta": {
            "source_doc": "doc",
            "version": "1.0",
            "changelog": [{"version": "1.0", "date": "2026-07-25", "changes": "Initial."}],
            "clarification_log": clarification_log or [],
        },
        "requirements": [
            {
                "req_id": "REQ-001",
                "requirement_text": "Users can reset their password.",
                "acceptance_criteria_status": "Generated with Assumptions",
                "acceptance_criteria": "Assumptions...",
                "gaps": [
                    {
                        "description": "Link expiry is not stated.",
                        "question": "How long should the reset link remain valid?",
                        "blocking": False,
                    }
                ],
                "recommendations": [],
                "depends_on": [],
                "related_to": [],
            },
            {
                "req_id": "REQ-002",
                "requirement_text": "Users can log in.",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "1. Valid credentials log the user in.",
                "gaps": [],
                "recommendations": [],
                "depends_on": [],
                "related_to": [],
            },
            {
                "req_id": "REQ-003",
                "requirement_text": "Users can log out.",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "1. Logging out ends the session.",
                # The real analyzer output represents "no genuine gap" as one
                # Gap entry carrying the sentinel below, not an empty list --
                # this must be excluded from the sheet exactly like REQ-002.
                "gaps": [
                    {
                        "description": "No significant gaps identified.",
                        "question": "None.",
                        "blocking": False,
                    }
                ],
                "recommendations": [],
                "depends_on": [],
                "related_to": [],
            },
        ],
    }


def _answered_row_line(answer: str) -> str:
    """The exact rendered `.md` table line for REQ-001's row once its
    Client Response cell holds `answer` -- built via the same `md_table`
    helper the writer itself uses, so a test that simulates "the client
    typed an answer into the .md copy" edits the file the same way the
    writer would have rendered it, escaping included."""
    rendered = build_table(
        _SHEET_COLUMNS,
        [
            [
                "REQ-001",
                "Users can reset their password.",
                "How long should the reset link remain valid?",
                answer,
            ]
        ],
    )
    return rendered.splitlines()[-1]


def _answer_md_row(md_path, answer: str) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("| REQ-001 |"))
    lines[idx] = _answered_row_line(answer)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _answer_docx_row(docx_path, answer: str) -> None:
    document = Document(str(docx_path))
    document.tables[0].rows[1].cells[3].text = answer
    document.save(str(docx_path))


@pytest.fixture
def sheet_env(tmp_path, monkeypatch):
    json_path = tmp_path / "doc-analysis.json"
    md_path = tmp_path / "doc-clarifications.md"
    docx_path = tmp_path / "doc-clarifications.docx"
    monkeypatch.setattr(
        "orchestrator.generation.clarification_sheet_writer.analysis_json_path",
        lambda doc: json_path,
    )
    monkeypatch.setattr(
        "orchestrator.generation.clarification_sheet_writer.clarification_sheet_md_path",
        lambda doc: md_path,
    )
    monkeypatch.setattr(
        "orchestrator.generation.clarification_sheet_writer.clarification_sheet_docx_path",
        lambda doc: docx_path,
    )
    return json_path, md_path, docx_path


def test_write_sheet_always_writes_md_but_docx_only_when_requested(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    write_sheet("doc")
    assert md_path.exists()
    assert not docx_path.exists()

    write_sheet("doc", docx=True, force=True)
    assert docx_path.exists()


def test_md_sheet_round_trip(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    write_sheet("doc")
    rows = read_sheet_md(md_path)

    # Only the requirement with a genuine open question appears -- neither
    # REQ-002 (empty gaps list) nor REQ-003 (a "None." sentinel gap) shows up.
    assert len(rows) == 1
    assert rows[0]["req_id"] == "REQ-001"
    assert rows[0]["question"] == "How long should the reset link remain valid?"
    assert rows[0]["answer"] == ""


def test_docx_sheet_round_trip(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    write_sheet("doc", docx=True)
    rows = read_sheet_docx(docx_path)

    assert len(rows) == 1
    assert rows[0]["req_id"] == "REQ-001"
    assert rows[0]["question"] == "How long should the reset link remain valid?"
    assert rows[0]["answer"] == ""


def test_empty_sheet_still_renders_header_only_table(sheet_env):
    """A requirement set with no open questions still needs a machine-
    readable (header-only) table, both formats -- validated against the
    read-back parsers, not just visual inspection."""
    json_path, md_path, docx_path = sheet_env
    analysis = _analysis()
    analysis["requirements"] = analysis["requirements"][1:]  # drop REQ-001
    json_path.write_text(json.dumps(analysis), encoding="utf-8")

    write_sheet("doc", docx=True)

    assert read_sheet_md(md_path) == []
    assert read_sheet_docx(docx_path) == []


def test_overwrite_guard_protects_unprocessed_answers_in_md(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")
    write_sheet("doc")

    # Simulate the client typing an answer directly into the .md table.
    _answer_md_row(md_path, "24 hours")

    with pytest.raises(SystemExit):
        write_sheet("doc")

    # --force overrides on explicit request.
    write_sheet("doc", force=True)
    assert read_sheet_md(md_path)[0]["answer"] == ""


def test_overwrite_guard_protects_unprocessed_answers_in_docx(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")
    write_sheet("doc", docx=True)

    # Simulate the client typing an answer into the Word copy instead.
    _answer_docx_row(docx_path, "24 hours")

    with pytest.raises(SystemExit):
        write_sheet("doc")

    write_sheet("doc", docx=True, force=True)
    assert read_sheet_docx(docx_path)[0]["answer"] == ""


def test_overwrite_guard_checks_docx_even_when_only_md_is_being_regenerated(sheet_env):
    """The guard is a union across whichever files exist -- regenerating
    just the .md (no --docx this run) must not silently blow away an
    unprocessed answer sitting only in a previously-produced .docx."""
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")
    write_sheet("doc", docx=True)

    _answer_docx_row(docx_path, "24 hours")

    with pytest.raises(SystemExit):
        write_sheet("doc")

    # force lets the (md-only) regeneration through without touching the
    # still-answered .docx, which --docx wasn't asked for this run.
    write_sheet("doc", force=True)
    assert read_sheet_md(md_path)[0]["answer"] == ""


def test_write_sheet_first_run_does_not_create_history(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    write_sheet("doc")

    assert not (md_path.parent / "history").exists()


def test_write_sheet_archives_previous_md_as_unversioned(sheet_env):
    """The sheet carries no version of its own -- its snapshots are always
    named "unversioned", distinguished from each other only by timestamp."""
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    write_sheet("doc")
    first_content = md_path.read_text(encoding="utf-8")

    write_sheet("doc")  # no pending answers -- no --force needed

    history_dir = md_path.parent / "history"
    snapshots = list(history_dir.glob("doc-clarifications-vunversioned_*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == first_content


def test_overwrite_allowed_once_answer_is_logged(sheet_env):
    json_path, md_path, docx_path = sheet_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")
    write_sheet("doc")

    _answer_md_row(md_path, "24 hours")

    # After /apply-clarifications the answer is in the log (and the gap
    # would be closed) — regeneration must then proceed without --force.
    ingested = _analysis(
        clarification_log=[
            {
                "req_id": "REQ-001",
                "question": "How long should the reset link remain valid?",
                "answer": "24 hours",
                "date": "2026-07-25",
            }
        ]
    )
    ingested["requirements"][0]["gaps"] = []
    ingested["requirements"][0]["acceptance_criteria_status"] = "Generated"
    json_path.write_text(json.dumps(ingested), encoding="utf-8")

    write_sheet("doc")
    assert read_sheet_md(md_path) == []
