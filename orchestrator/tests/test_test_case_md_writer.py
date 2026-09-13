"""Tests for the Test Cases Markdown report -- the always-on human-review
deliverable that mirrors the XLSX "Test Cases" review sheet's content,
rendered as Markdown instead of a workbook. See test_case_md_writer.py's
own docstring for the always-md/opt-in-csv-xlsx rationale."""

import json

import pytest

from orchestrator.generation import test_case_md_writer
from orchestrator.generation.test_case_md_writer import (
    build_report,
    load_existing_review_tracking,
    write_report,
)
from orchestrator.models.test_case import TestCaseDocument

MINIMAL_DOCUMENT_DICT = {
    "meta": {
        "source_doc": "LinkGrid",
        "version": "1.0",
        "generated_date": "2026-08-12",
        "changelog": [{"version": "1.0", "date": "2026-08-12", "changes": "Initial generation."}],
    },
    "test_cases": [
        {
            "tc_id": "TC-001",
            "req_id": "REQ-001",
            "title": "Successful login",
            "objective": "Verify a registered user can log in.",
            "test_type": "Positive",
            "priority": "High",
            "preconditions": "A registered user account exists.",
            "steps": [
                {
                    "step_number": 1,
                    "action": "Enter a valid username.",
                    "expected_result": "Username field shows the entered value.",
                    "test_data": "validuser",
                },
                {
                    "step_number": 2,
                    "action": "Click Login.",
                    "expected_result": "The dashboard page loads.",
                    "test_data": "",
                },
            ],
        }
    ],
    "not_covered": [{"req_id": "REQ-002", "reason": "Blocked on client clarification about token expiry."}],
    "document_control": {
        "title": "Test Cases for LinkGrid",
        "project_id": "TBD – Client/Project Input Required",
        "document_id": "TBD – Client/Project Input Required",
        "description": "Test cases derived from the LinkGrid requirement analysis.",
        "prepared_by": "Emvigo QA",
        "prepared_date": "2026-08-12",
        "approved_date": "TBD – Client/Project Input Required",
        "master_template_id": "TBD – Client/Project Input Required",
        "version": "1.0",
    },
    "release_history": [
        {
            "version": "1.0",
            "date": "2026-08-12",
            "author": "Emvigo QA",
            "reviewed_by": "TBD – Client/Project Input Required",
            "reviewed_on": "",
            "approved_by": "TBD – Client/Project Input Required",
            "approved_on": "",
            "reasons": "Initial test case generation.",
        }
    ],
}


def test_build_report_opens_with_frontmatter_properties_block():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={"REQ-001": "Users can log in."})

    assert content.startswith("---\n")
    frontmatter, _, body = content.partition("---\n")[2].partition("---\n")
    # document_control.title already reads "Test Cases for LinkGrid" per this
    # agent's own convention -- used verbatim, not composed a second time.
    assert 'title: "Test Cases for LinkGrid"' in frontmatter
    assert 'document_type: "Test Cases"' in frontmatter
    assert 'version: "1.0"' in frontmatter
    assert 'privacy: "Confidential"' in frontmatter
    assert '  - "test-cases"' in frontmatter
    assert body.startswith("\n# Test Cases for LinkGrid")


def test_build_report_contains_every_top_level_section():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={"REQ-001": "Users can log in."})

    assert "# Test Cases for LinkGrid" in content
    assert "## A. Document Version Control" in content
    assert "## B. Document Release History" in content
    assert "## Test Cases" in content
    assert "### TC-001: Successful login" in content
    assert "## Not Covered" in content


def test_build_report_shows_requirement_text_and_test_case_fields():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={"REQ-001": "Users can log in."})

    assert "REQ-001 — Users can log in." in content
    assert "**Test Type:** Positive" in content
    assert "**Priority:** High" in content
    assert "**Objective:** Verify a registered user can log in." in content
    assert "**Preconditions:** A registered user account exists." in content


def test_build_report_renders_steps_table_numbered():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={})

    assert "| Step | Action | Test Data | Expected Result |" in content
    assert "| 1 | Enter a valid username. | validuser | Username field shows the entered value. |" in content
    assert "| 2 | Click Login. |  | The dashboard page loads. |" in content


def test_build_report_renders_not_covered_table():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={})

    assert "REQ-002" in content
    assert "Blocked on client clarification about token expiry." in content


def test_build_report_not_covered_names_the_requirement_beside_its_id():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(
        document,
        requirement_texts={"REQ-002": "Users can reset their password via an emailed link."},
    )

    assert (
        "| REQ-002 | Users can reset their password via an emailed link. "
        "| Blocked on client clarification about token expiry. |"
    ) in content


def test_build_report_omits_not_covered_section_when_empty():
    data = json.loads(json.dumps(MINIMAL_DOCUMENT_DICT))
    data["not_covered"] = []
    document = TestCaseDocument.from_dict(data)
    content = build_report(document, requirement_texts={})

    assert "## Not Covered" not in content


def test_build_report_defaults_execution_status_and_omits_blank_tracking_fields():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={})

    # No tracking supplied at all (no sibling xlsx) -- Execution Status
    # still shows the same untouched-export default the xlsx itself would
    # start with; Actual Result/Linked Issue have nothing recorded, so they
    # don't appear rather than rendering as an empty line.
    assert "**Execution Status:** Not Executed" in content
    assert "**Actual Result:**" not in content
    assert "**Linked Issue:**" not in content


def test_build_report_shows_recorded_tracking_fields():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    tracking = {
        "TC-001": {
            "Execution Status": "Fail",
            "Actual Result": "Login button did not respond.",
            "Linked Issue": "JIRA-123",
        }
    }
    content = build_report(document, requirement_texts={}, tracking=tracking)

    assert "**Execution Status:** Fail" in content
    assert "**Actual Result:** Login button did not respond." in content
    assert "**Linked Issue:** JIRA-123" in content


def test_build_report_falls_back_to_blank_requirement_text_without_crashing():
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={})

    # No requirement text supplied -- just the bare req_id, no crash, no
    # fabricated text.
    assert "**Requirement:** REQ-001" in content


def test_write_report_writes_md_file_from_json(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})

    write_report("Doc")

    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "### TC-001: Successful login" in content


def test_write_report_carries_tracking_forward_from_its_own_prior_content(tmp_path, monkeypatch):
    """The Markdown report is the one true source of tracking now -- a
    regeneration must read whatever it already recorded back out of its own
    current content before overwriting it, the same self-referential
    carry-forward the xlsx used to do against itself."""
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})
    monkeypatch.setattr(
        test_case_md_writer,
        "load_existing_review_tracking",
        lambda path: {"TC-001": {"Execution Status": "Pass", "Actual Result": "OK.", "Linked Issue": "JIRA-9"}},
    )

    write_report("Doc")

    content = md_path.read_text(encoding="utf-8")
    assert "**Execution Status:** Pass" in content
    assert "**Actual Result:** OK." in content
    assert "**Linked Issue:** JIRA-9" in content


def test_write_report_applies_overrides_on_top_of_carried_forward_tracking(tmp_path, monkeypatch):
    """`overrides` (as an external caller might pass after a test run)
    patches Execution Status/Actual Result for the given tc_id without
    touching a Linked Issue already carried forward from the report's own
    prior content."""
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})
    monkeypatch.setattr(
        test_case_md_writer,
        "load_existing_review_tracking",
        lambda path: {"TC-001": {"Execution Status": "Not Executed", "Linked Issue": "JIRA-9"}},
    )

    matched = write_report(
        "Doc", overrides={"TC-001": {"Execution Status": "Fail", "Actual Result": "Login button unresponsive."}}
    )

    assert matched == 1
    content = md_path.read_text(encoding="utf-8")
    assert "**Execution Status:** Fail" in content
    assert "**Actual Result:** Login button unresponsive." in content
    assert "**Linked Issue:** JIRA-9" in content  # untouched by the override


def test_write_report_overrides_for_a_tc_id_no_longer_in_the_json_are_not_counted(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})
    monkeypatch.setattr(test_case_md_writer, "load_existing_review_tracking", lambda path: {})

    matched = write_report("Doc", overrides={"TC-999": {"Execution Status": "Pass"}})

    assert matched == 0


def test_write_report_exits_on_validation_errors(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-cases.json"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: (["bad test cases"], []))

    with pytest.raises(SystemExit) as exc_info:
        write_report("Doc")

    assert exc_info.value.code == 1


def test_write_report_first_run_does_not_create_history(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})

    write_report("Doc")

    assert not (tmp_path / "history").exists()


def test_write_report_archives_previous_md_with_version_and_timestamp(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})

    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")
    write_report("Doc")
    first_content = md_path.read_text(encoding="utf-8")

    data = json.loads(json.dumps(MINIMAL_DOCUMENT_DICT))
    data["meta"]["version"] = "2.0"
    data["document_control"]["version"] = "2.0"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    write_report("Doc")

    history_dir = tmp_path / "history"
    snapshots = list(history_dir.glob("Doc-test-cases-v1.0_*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == first_content
    assert "- **Version:** 2.0" in md_path.read_text(encoding="utf-8")


# --- load_existing_review_tracking: parses this report's own rendered
# output back out -- the mechanism the Markdown report's self-referential
# carry-forward (and zephyr_export.py's xlsx export) both depend on. ---

def test_load_existing_review_tracking_missing_file_returns_empty(tmp_path):
    assert load_existing_review_tracking(tmp_path / "does-not-exist.md") == {}


def test_load_existing_review_tracking_round_trips_build_report_output(tmp_path):
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    tracking = {
        "TC-001": {
            "Execution Status": "Fail",
            "Actual Result": "Login button did not respond.",
            "Linked Issue": "JIRA-123",
        }
    }
    content = build_report(document, requirement_texts={}, tracking=tracking)
    md_path = tmp_path / "Doc-test-cases.md"
    md_path.write_text(content, encoding="utf-8")

    reloaded = load_existing_review_tracking(md_path)
    assert reloaded == {"TC-001": tracking["TC-001"]}


def test_load_existing_review_tracking_untouched_test_case_only_has_execution_status(tmp_path):
    # No Actual Result/Linked Issue ever recorded -- build_report omits
    # those two bullets entirely for an untouched test case (see
    # test_build_report_defaults_execution_status_and_omits_blank_tracking_
    # fields above), so only Execution Status should come back.
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    content = build_report(document, requirement_texts={})
    md_path = tmp_path / "Doc-test-cases.md"
    md_path.write_text(content, encoding="utf-8")

    tracking = load_existing_review_tracking(md_path)
    assert tracking == {"TC-001": {"Execution Status": "Not Executed"}}


def test_load_existing_review_tracking_multiple_test_cases_stay_isolated(tmp_path):
    data = json.loads(json.dumps(MINIMAL_DOCUMENT_DICT))
    data["test_cases"].append(
        {
            "tc_id": "TC-002",
            "req_id": "REQ-002",
            "title": "Second case",
            "objective": "obj",
            "test_type": "Positive",
            "priority": "Low",
            "steps": [],
        }
    )
    document = TestCaseDocument.from_dict(data)
    content = build_report(
        document,
        requirement_texts={},
        tracking={"TC-001": {"Execution Status": "Pass"}, "TC-002": {"Execution Status": "Fail"}},
    )
    md_path = tmp_path / "Doc-test-cases.md"
    md_path.write_text(content, encoding="utf-8")

    tracking = load_existing_review_tracking(md_path)
    assert tracking["TC-001"]["Execution Status"] == "Pass"
    assert tracking["TC-002"]["Execution Status"] == "Fail"


def test_write_report_end_to_end_carries_tracking_forward_without_mocking(tmp_path, monkeypatch):
    """No mocked `load_existing_review_tracking` here -- a real prior `.md`
    on disk, regenerated by the real `write_report`, must still show what
    it already recorded."""
    json_path = tmp_path / "Doc-test-cases.json"
    md_path = tmp_path / "Doc-test-cases.md"
    json_path.write_text(json.dumps(MINIMAL_DOCUMENT_DICT), encoding="utf-8")

    monkeypatch.setattr(test_case_md_writer, "test_cases_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_case_md_writer, "test_cases_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_case_md_writer, "validate_file", lambda path: ([], []))
    monkeypatch.setattr(test_case_md_writer, "load_requirement_texts", lambda doc: {})

    write_report("Doc", overrides={"TC-001": {"Execution Status": "Pass", "Actual Result": "All good."}})
    # Regenerate again, with no overrides this time -- must still show the
    # previous run's recorded values, not blank them.
    write_report("Doc")

    content = md_path.read_text(encoding="utf-8")
    assert "**Execution Status:** Pass" in content
    assert "**Actual Result:** All good." in content


def test_build_test_case_flattens_multiline_actual_result():
    """A real Playwright error message is often multi-line -- rendering it
    verbatim would break this report's own line-based bullet format (see
    load_existing_review_tracking). It must collapse to one line."""
    document = TestCaseDocument.from_dict(MINIMAL_DOCUMENT_DICT)
    tracking = {"TC-001": {"Actual Result": "Error: expect(locator).toBeVisible()\n\nLocator: button\nExpected: visible"}}
    content = build_report(document, requirement_texts={}, tracking=tracking)

    assert "**Actual Result:** Error: expect(locator).toBeVisible() Locator: button Expected: visible" in content
