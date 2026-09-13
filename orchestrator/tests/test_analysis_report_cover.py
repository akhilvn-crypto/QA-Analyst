"""Tests for the requirement-analysis docx report's cover page, Document
Control & Metadata section, and category-grouped requirement cards."""

from orchestrator.generation.docx_report_writer import build_report
from orchestrator.models.requirement import DocumentControlMeta, Gap, ReleaseHistoryEntry, Requirement


def _requirement(req_id="REQ-001", **overrides) -> Requirement:
    base = dict(
        req_id=req_id,
        requirement_text="The system shall let a user sign in.",
        gaps=[Gap(description="d", question="q", blocking=False)],
        acceptance_criteria_status="Generated",
        acceptance_criteria="1. Users can log in with valid credentials.",
    )
    base.update(overrides)
    return Requirement(**base)


def _document_control(**overrides) -> DocumentControlMeta:
    base = dict(
        title="Requirements",
        project_id="PID-1",
        document_id="DOC-1",
        description="A short description.",
        prepared_by="Emvigo QA",
        prepared_date="2026-07-26",
        approved_date="TBD – Client/Project Input Required",
        master_template_id="TBD – Client/Project Input Required",
        classification="Internal / Highly Confidential",
        version="1.0",
    )
    base.update(overrides)
    return DocumentControlMeta(**base)


def _release_history():
    return [
        ReleaseHistoryEntry(
            version="1.0", date="2026-07-26", author="Emvigo QA",
            reviewed_by="TBD – Client/Project Input Required", reviewed_on="",
            approved_by="TBD – Client/Project Input Required", approved_on="",
            reasons="Initial analysis.",
        )
    ]


def _paragraph_texts(document) -> list[str]:
    return [p.text for p in document.paragraphs]


def test_build_report_without_document_control_does_not_crash():
    """Default (None) document_control/release_history must behave like an
    empty DocumentControlMeta/[] -- a legacy analysis JSON predating these
    fields must still render a report, not fail."""
    document = build_report([_requirement()], doc_name="Requirements")
    assert document is not None


def test_cover_page_shows_title_and_document_title():
    document = build_report(
        [_requirement()], doc_name="Requirements",
        document_control=_document_control(title="My Custom Title"),
    )
    texts = _paragraph_texts(document)
    assert "Requirement Analysis Report" in texts
    assert "My Custom Title" in texts


def test_cover_page_falls_back_to_doc_name_when_title_is_blank():
    document = build_report(
        [_requirement()], doc_name="Requirements",
        document_control=DocumentControlMeta(),  # every field blank
    )
    texts = _paragraph_texts(document)
    assert "Requirements" in texts


def test_document_control_section_has_a_heading_and_every_field():
    document = build_report(
        [_requirement()], doc_name="Requirements",
        document_control=_document_control(), release_history=_release_history(),
    )
    texts = _paragraph_texts(document)
    assert "1. Document Control & Metadata" in texts
    assert "1.1 Revision History" in texts

    # Every DOCUMENT_CONTROL_FIELDS label/value pair renders as its own
    # bold-label-then-value field, same as a requirement card's own fields.
    assert "Project Name" in texts
    assert "Requirements" in texts
    assert "Classification" in texts
    assert "Internal / Highly Confidential" in texts


def test_revision_history_table_has_one_row_per_entry():
    document = build_report(
        [_requirement()], doc_name="Requirements",
        document_control=_document_control(), release_history=_release_history(),
    )
    revision_table = document.tables[0]
    assert revision_table.rows[0].cells[0].text == "Version"  # header
    assert revision_table.rows[1].cells[0].text == "1.0"
    assert revision_table.rows[1].cells[2].text == "Initial analysis."  # Description column


def test_project_overview_and_scope_section_present():
    document = build_report(
        [_requirement()], doc_name="Requirements",
        executive_summary="A short summary.", in_scope="Login.", out_of_scope="Payments.",
    )
    texts = _paragraph_texts(document)
    assert "2. Project Overview & Scope" in texts
    assert "Executive Summary" in texts
    assert "A short summary." in texts


def test_category_sections_and_requirement_cards_present():
    """Requirements render grouped under their own numbered category
    section (3/4/5), each as a full-width labeled-field card, not a table
    row."""
    functional = _requirement("REQ-001", category="Functional")
    nfr = _requirement("REQ-029", category="Non-Functional")
    document = build_report(
        [functional, nfr], doc_name="Requirements",
        document_control=_document_control(), release_history=_release_history(),
    )
    texts = _paragraph_texts(document)
    assert "3. Functional Requirements Analysis & Acceptance Criteria" in texts
    assert "4. Non-Functional Requirements (NFR) Analysis" in texts
    assert "5. Compliance & Regulatory Requirements Analysis" in texts
    # Only the revision-history front-matter table exists -- requirements
    # render as cards, not table rows.
    assert len(document.tables) == 1
    assert "REQ-001" in texts
    assert "REQ-029" in texts
    assert "Requirement" in texts
    assert "The system shall let a user sign in." in texts
