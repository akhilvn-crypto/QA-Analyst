"""Tests for the requirement-analysis Markdown report -- the always-on
human-review deliverable that mirrors docx_report_writer's own content and
section order, rendered as Markdown instead of docx.

The exact structure asserted here (five numbered top-level sections --
1. Document Control & Metadata / 1.1 Revision History, 2. Project Overview
& Scope, 3. Functional Requirements Analysis & Acceptance Criteria, 4.
Non-Functional Requirements (NFR) Analysis, 5. Compliance & Regulatory
Requirements Analysis -- bold bullet-style field labels, requirements
grouped by `category`) is a fixed contract -- see the output-structure
skill and this module's own docstring -- not incidental formatting, so it's
worth pinning down precisely rather than just checking substrings are
present somewhere."""

import json

import pytest

from orchestrator.generation import md_report_writer
from orchestrator.generation.md_report_writer import build_report, write_report
from orchestrator.models.requirement import DocumentControlMeta, Gap, ReleaseHistoryEntry, Requirement


def _requirement(req_id="REQ-001", **overrides) -> Requirement:
    base = dict(
        req_id=req_id,
        requirement_text="The system shall let a user sign in.",
        gaps=[Gap(description="Lockout policy is unstated.", question="After how many failed attempts?", blocking=True)],
        acceptance_criteria_status="Not Generated – Client Clarification Required",
        acceptance_criteria="Blocked by the lockout question.",
    )
    base.update(overrides)
    return Requirement(**base)


def test_build_report_opens_with_frontmatter_properties_block():
    document_control = DocumentControlMeta(
        title="LinkGrid", project_id="PRJ-1", document_id="DOC-1", version="1.0", approved_date="2026-08-12"
    )
    content = build_report([_requirement()], doc_name="Requirements", document_control=document_control)

    assert content.startswith("---\n")
    frontmatter, _, body = content.partition("---\n")[2].partition("---\n")
    assert 'title: "LinkGrid Requirement Analysis"' in frontmatter
    assert 'document_type: "Requirement Analysis"' in frontmatter
    assert 'project_id: "PRJ-1"' in frontmatter
    assert 'document_id: "DOC-1"' in frontmatter
    assert 'version: "1.0"' in frontmatter
    assert 'approved_date: "2026-08-12"' in frontmatter
    assert 'privacy: "Confidential"' in frontmatter
    assert '  - "requirement-analysis"' in frontmatter
    assert body.startswith("\n# Requirement Analysis Report")


def test_build_report_contains_document_control_and_requirement_card():
    document_control = DocumentControlMeta(title="Requirements", version="1.0", prepared_by="Emvigo QA")
    content = build_report([_requirement()], doc_name="Requirements", document_control=document_control)

    assert "# Requirement Analysis Report" in content
    assert "## 1. Document Control & Metadata" in content
    assert "### 1.1 Revision History" in content
    assert "## 2. Project Overview & Scope" in content
    assert "## 3. Functional Requirements Analysis & Acceptance Criteria" in content
    assert "## 4. Non-Functional Requirements (NFR) Analysis" in content
    assert "## 5. Compliance & Regulatory Requirements Analysis" in content
    assert "### REQ-001" in content
    assert "* **Status:** Blocked" in content
    assert "The system shall let a user sign in." in content
    assert "After how many failed attempts?" in content


def test_build_report_uses_bold_bullet_labels_and_section_dividers():
    content = build_report([_requirement()], doc_name="Requirements")

    assert "* **Status:**" in content
    assert "* **Requirement:**" in content
    assert "* **Gap:**" in content
    assert "* **Client Question:**" in content
    assert "* **Acceptance Criteria:**" in content
    assert "* **Recommendations:**" in content
    assert "\n---\n" in content


def test_build_report_groups_requirements_by_category():
    functional = _requirement("REQ-001", category="Functional")
    nfr = _requirement("REQ-029", category="Non-Functional", title="Performance")
    compliance = _requirement("CMP-REG-001", category="Compliance", title="Data Privacy")
    content = build_report([functional, nfr, compliance], doc_name="Requirements")

    functional_section = content.index("## 3. Functional")
    nfr_section = content.index("## 4. Non-Functional")
    compliance_section = content.index("## 5. Compliance")
    req001 = content.index("### REQ-001")
    req029 = content.index("### REQ-029: Performance")
    cmp001 = content.index("### CMP-REG-001: Data Privacy")

    assert functional_section < req001 < nfr_section
    assert nfr_section < req029 < compliance_section
    assert compliance_section < cmp001


def test_build_report_shows_placeholder_text_for_empty_category():
    content = build_report([_requirement(category="Functional")], doc_name="Requirements")

    assert "No non-functional requirements were identified in this document." in content
    assert "No compliance or regulatory considerations were identified as applicable to this document." in content


def test_build_report_renders_provided_project_overview_and_scope():
    content = build_report(
        [_requirement()],
        doc_name="Requirements",
        executive_summary="A short summary of the analyzed document.",
        in_scope="Login and checkout.",
        out_of_scope="Payment gateway integration.",
    )

    assert "* **Executive Summary:** A short summary of the analyzed document." in content
    assert "* **In-Scope:** Login and checkout." in content
    assert "* **Out-of-Scope:** Payment gateway integration." in content


def test_build_report_no_gaps_and_no_recommendations_text():
    requirement = _requirement(gaps=[], acceptance_criteria_status="Generated", acceptance_criteria="OK.")
    content = build_report([requirement], doc_name="Doc")

    assert "No significant gaps identified." in content
    assert "None." in content
    assert "No recommendations." in content


def test_build_report_sorts_requirements_numerically_within_category():
    reqs = [_requirement("REQ-10"), _requirement("REQ-2"), _requirement("REQ-1")]
    content = build_report(reqs, doc_name="Doc")

    assert content.index("### REQ-1\n") < content.index("### REQ-2\n") < content.index("### REQ-10\n")


def test_build_report_with_no_requirements_shows_empty_message():
    content = build_report([], doc_name="Doc")

    assert "No requirements were extracted from this document." in content


def test_build_report_escapes_pipes_and_newlines_in_revision_history_table():
    document_control = DocumentControlMeta(title="A | B", version="1.0")
    release_history = [
        ReleaseHistoryEntry(
            version="1.0", date="2026-08-10", author="Emvigo QA",
            reviewed_by="TBD", reviewed_on="", approved_by="TBD", approved_on="",
            reasons="Line one\nLine two | still one cell",
        )
    ]
    content = build_report(
        [_requirement()], doc_name="Doc", document_control=document_control, release_history=release_history
    )

    assert "* **Project Name:** A | B" in content
    assert "Line one<br>Line two \\| still one cell" in content
    # No stray literal newline inside the revision-history row itself.
    for line in content.splitlines():
        assert line.count("|") % 2 == 0 or not line.startswith("| 1.0")


def test_write_report_writes_md_file_from_json(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    md_path = tmp_path / "Doc-analysis.md"
    analysis = {
        "meta": {"source_doc": "Doc", "version": "1.0"},
        "requirements": [
            {
                "req_id": "REQ-001",
                "requirement_text": "Users must be able to reset their password.",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "1. Users can request a reset link.",
                "gaps": [],
                "recommendations": [],
            }
        ],
        "document_control": {"title": "Doc", "version": "1.0"},
        "release_history": [],
    }
    json_path.write_text(json.dumps(analysis), encoding="utf-8")

    monkeypatch.setattr(md_report_writer, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(md_report_writer, "analysis_md_path", lambda doc: md_path)
    monkeypatch.setattr(md_report_writer, "validate_file", lambda path: ([], []))

    write_report("Doc")

    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "### REQ-001" in content
    assert "Users must be able to reset their password." in content


def _analysis(version="1.0"):
    return {
        "meta": {"source_doc": "Doc", "version": version},
        "requirements": [
            {
                "req_id": "REQ-001",
                "requirement_text": "Users must be able to reset their password.",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "1. Users can request a reset link.",
                "gaps": [],
                "recommendations": [],
            }
        ],
        "document_control": {"title": "Doc", "version": version},
        "release_history": [],
    }


def test_write_report_first_run_does_not_create_history(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    md_path = tmp_path / "Doc-analysis.md"
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")

    monkeypatch.setattr(md_report_writer, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(md_report_writer, "analysis_md_path", lambda doc: md_path)
    monkeypatch.setattr(md_report_writer, "validate_file", lambda path: ([], []))

    write_report("Doc")

    assert not (tmp_path / "history").exists()


def test_write_report_archives_previous_md_with_version_and_timestamp(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    md_path = tmp_path / "Doc-analysis.md"

    monkeypatch.setattr(md_report_writer, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(md_report_writer, "analysis_md_path", lambda doc: md_path)
    monkeypatch.setattr(md_report_writer, "validate_file", lambda path: ([], []))

    json_path.write_text(json.dumps(_analysis("1.0")), encoding="utf-8")
    write_report("Doc")
    first_content = md_path.read_text(encoding="utf-8")

    json_path.write_text(json.dumps(_analysis("2.0")), encoding="utf-8")
    write_report("Doc")

    history_dir = tmp_path / "history"
    snapshots = list(history_dir.glob("Doc-analysis-v1.0_*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == first_content
    # The live file now reflects the new version, not the archived one.
    assert "* **Document Version:** 2.0" in md_path.read_text(encoding="utf-8")


def test_write_report_exits_on_validation_errors(tmp_path, monkeypatch, capsys):
    json_path = tmp_path / "Doc-analysis.json"
    json_path.write_text(json.dumps({"meta": {"source_doc": "Doc"}, "requirements": []}), encoding="utf-8")

    monkeypatch.setattr(md_report_writer, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(md_report_writer, "validate_file", lambda path: (["bad requirement"], []))

    with pytest.raises(SystemExit) as exc_info:
        write_report("Doc")

    assert exc_info.value.code == 1
