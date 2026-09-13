"""Tests for the Test Plan Markdown report -- the always-on human-review
deliverable that mirrors test_plan_docx_writer's own section order and
content, rendered as Markdown instead of docx. See
test_plan_md_writer.py's own docstring for the always-md/opt-in-docx
rationale."""

import json

import pytest

from orchestrator.generation import test_plan_md_writer
from orchestrator.generation.test_plan_md_writer import build_report, write_report
from orchestrator.models.test_plan import TestPlan

MINIMAL_PLAN_DICT = {
    "meta": {
        "title": "LinkGrid",
        "project_id": "TBD – Client/Project Input Required",
        "document_id": "TBD – Client/Project Input Required",
        "description": "Test Plan for LinkGrid.",
        "approved_date": "TBD",
        "master_template_id": "TBD – Client/Project Input Required",
        "prepared_by": "Emvigo Technologies",
        "prepared_date": "2026-08-12",
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
            "reasons": "Initial version.",
        }
    ],
    "introduction": {
        "purpose": "Define the scope and approach for testing LinkGrid.",
        "project_overview": "LinkGrid is a link-sharing platform.",
        "scope_in_areas": [{"area": "Authentication", "items": ["Login", "Logout"], "req_ids": ["REQ-001"]}],
        "scope_in_non_functional": ["Basic performance sanity"],
        "scope_out": ["Payment gateway integration"],
        "reference_documents": [{"process_element": "Requirement Document", "reference": "TBD – To be added by QA"}],
    },
    "resources": {
        "team_members": [{"resource_name": "TBD – Client/Project Input Required", "designation_role": "QA Lead"}],
        "role_assignments": [],
        "orientation_intro": "",
        "orientation_topics": [],
        "inputs_needed": ["Access to staging environment"],
        "environment_software": [],
        "environment_hardware": [],
    },
    "assumptions_dependencies_risks": {
        "assumptions": ["Build is stable at the start of each sprint."],
        "dependencies": ["Staging environment availability."],
        "risks": ["REQ-002 is pending client clarification."],
    },
    "strategy": {
        "overall_strategy": ["Requirement-driven manual test cycle."],
        "integration_strategy": ["Modules are integrated incrementally per sprint."],
        "integration_key_areas": ["Authentication"],
        "integration_sequence": [{"area": "Authentication", "items": ["Login before Logout"]}],
        "entry_criteria": ["Stable build available."],
        "exit_criteria": ["All planned test cases executed."],
        "integration_acceptance_criteria": ["No unresolved high-severity issues."],
    },
    "schedule": [
        {"release": "R1", "sprint": "Sprint 1", "iteration": "1", "start_date": "TBD", "end_date": "TBD"}
    ],
    "deliverables": {
        "test_plan_note": "This document.",
        "test_cases_logs": [{"document": "Test Cases", "location": "TBD – To be added by QA"}],
        "acceptance_exit_note": "Acceptance is based on documented criteria.",
        "acceptance_exit_docs": [],
        "bug_analysis_note": "Bugs are tracked per sprint.",
        "bug_analysis_docs": [],
        "release_notes_note": "Issued at the end of each release.",
        "release_notes_docs": [],
        "non_functional_note": "Basic performance and security sanity.",
        "non_functional_docs": [],
    },
    "closure": {
        "sprint_closure_criteria": ["All sprint test cases executed."],
        "release_closure_criteria": ["No open critical defects."],
    },
}


def test_build_report_opens_with_frontmatter_properties_block():
    plan = TestPlan.from_dict(MINIMAL_PLAN_DICT)
    content = build_report(plan)

    assert content.startswith("---\n")
    frontmatter, _, body = content.partition("---\n")[2].partition("---\n")
    assert 'title: "LinkGrid Test Plan"' in frontmatter
    assert 'document_type: "Test Plan"' in frontmatter
    assert 'version: "1.0"' in frontmatter
    assert 'privacy: "Confidential"' in frontmatter
    assert '  - "test-plan"' in frontmatter
    assert body.startswith("\n# Test Plan for LinkGrid")


def test_build_report_contains_every_top_level_section():
    plan = TestPlan.from_dict(MINIMAL_PLAN_DICT)
    content = build_report(plan)

    assert "# Test Plan for LinkGrid" in content
    assert "## A. Document Version Control" in content
    assert "## B. Document Release History" in content
    assert "## Introduction" in content
    assert "## Resource Requirement for Tests" in content
    assert "## Assumptions, Dependencies & Risks" in content
    assert "## Test Strategy/Methods" in content
    assert "## Test Schedule" in content
    assert "## Test Deliverables" in content
    assert "## Test Closure" in content
    assert "## Approval & Sign-off" in content


def test_build_report_renders_scope_areas_and_traceability_ids_only_in_json():
    plan = TestPlan.from_dict(MINIMAL_PLAN_DICT)
    content = build_report(plan)

    assert "- Authentication" in content
    assert "  - Login" in content
    assert "  - Logout" in content
    # req_ids are JSON-only traceability, never rendered in a human-facing
    # deliverable -- same rule the docx writer follows.
    assert "REQ-001" not in content


def test_build_report_renders_tables_with_escaped_cells():
    data = json.loads(json.dumps(MINIMAL_PLAN_DICT))
    data["release_history"][0]["reasons"] = "Line one\nLine two | still one cell"
    plan = TestPlan.from_dict(data)
    content = build_report(plan)

    assert "Line one<br>Line two \\| still one cell" in content


def test_build_report_uses_tbd_markers_verbatim():
    plan = TestPlan.from_dict(MINIMAL_PLAN_DICT)
    content = build_report(plan)

    assert "TBD – Client/Project Input Required" in content
    assert "TBD – To be added by QA" in content


def test_write_report_writes_md_file_from_json(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-plan.json"
    md_path = tmp_path / "Doc-test-plan.md"
    json_path.write_text(json.dumps(MINIMAL_PLAN_DICT), encoding="utf-8")

    monkeypatch.setattr(test_plan_md_writer, "test_plan_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_plan_md_writer, "test_plan_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_plan_md_writer, "validate_file", lambda path: ([], []))

    write_report("Doc")

    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "# Test Plan for LinkGrid" in content


def test_write_report_exits_on_validation_errors(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-plan.json"
    json_path.write_text(json.dumps(MINIMAL_PLAN_DICT), encoding="utf-8")

    monkeypatch.setattr(test_plan_md_writer, "test_plan_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_plan_md_writer, "validate_file", lambda path: (["bad test plan"], []))

    with pytest.raises(SystemExit) as exc_info:
        write_report("Doc")

    assert exc_info.value.code == 1


def test_write_report_first_run_does_not_create_history(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-test-plan.json"
    md_path = tmp_path / "Doc-test-plan.md"
    json_path.write_text(json.dumps(MINIMAL_PLAN_DICT), encoding="utf-8")

    monkeypatch.setattr(test_plan_md_writer, "test_plan_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_plan_md_writer, "test_plan_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_plan_md_writer, "validate_file", lambda path: ([], []))

    write_report("Doc")

    assert not (tmp_path / "history").exists()


def test_write_report_archives_previous_md_with_version_from_release_history(tmp_path, monkeypatch):
    """The Test Plan's Document Version Control section has no standalone
    version bullet -- the archived filename's version must come from the
    last row of its own Document Release History table instead."""
    json_path = tmp_path / "Doc-test-plan.json"
    md_path = tmp_path / "Doc-test-plan.md"

    monkeypatch.setattr(test_plan_md_writer, "test_plan_json_path", lambda doc: json_path)
    monkeypatch.setattr(test_plan_md_writer, "test_plan_md_path", lambda doc: md_path)
    monkeypatch.setattr(test_plan_md_writer, "validate_file", lambda path: ([], []))

    json_path.write_text(json.dumps(MINIMAL_PLAN_DICT), encoding="utf-8")
    write_report("Doc")
    first_content = md_path.read_text(encoding="utf-8")

    data = json.loads(json.dumps(MINIMAL_PLAN_DICT))
    data["meta"]["version"] = "2.0"
    data["release_history"].append(
        {
            "version": "2.0", "date": "2026-08-13", "author": "Emvigo QA",
            "reviewed_by": "TBD", "reviewed_on": "", "approved_by": "TBD", "approved_on": "",
            "reasons": "Schedule revised.",
        }
    )
    json_path.write_text(json.dumps(data), encoding="utf-8")
    write_report("Doc")

    history_dir = tmp_path / "history"
    snapshots = list(history_dir.glob("Doc-test-plan-v1.0_*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == first_content
