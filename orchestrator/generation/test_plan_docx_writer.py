"""Writes structured test-plan data as a formatted Word document, following
Emvigo's Test Plan structure and branding (see the test-plan-output-structure
skill for the authoritative section order/formatting spec, and
`paths.header_logo_path`/`project_logo_path` for the logo assets used on the cover page).

Usage:
    python -m orchestrator.generation.test_plan_docx_writer <doc-name>

Reads output/test-plan/<doc-name>-test-plan.json and writes
output/test-plan/<doc-name>-test-plan.docx
"""

import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Mm, Pt, RGBColor

from orchestrator.models.test_plan import TestPlan
from orchestrator.utils.docx_helpers import (
    FONT_NAME,
    add_key_value_table,
    bake_live_fields,
    scrub_authorship,
    set_authorship,
    add_page_field,
    clear_paragraph_border,
    repeat_header_row,
    save_document,
    set_fixed_column_widths,
    set_min_row_height,
    set_row_cant_split,
    set_table_cell_margins,
    set_update_fields_on_open,
    shade_cell,
    style_cell,
)
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.paths import (
    header_logo_path,
    project_logo_path,
    test_plan_docx_path,
    test_plan_json_path,
)
from orchestrator.validation.validate import validate_file

ACCENT_COLOR = "1F3864"  # dark navy -- matches the requirement-analysis report's header fill
TABLE_FONT_SIZE_PT = 10.5
DENSE_TABLE_FONT_SIZE_PT = 9.5  # for wide tables (8+ columns) where 10.5pt would overflow
BODY_FONT_SIZE_PT = 11
MIN_ROW_HEIGHT_PT = 22
CLASSIFICATION_TEXT = "Confidential – Internal / Client Use Only"
CLIENT_INPUT_TBD = "TBD – Client/Project Input Required"


# --------------------------------------------------------------------------
# Page / style setup
# --------------------------------------------------------------------------


def _set_a4_portrait(document: Document) -> None:
    for section in document.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.header_distance = Inches(0.32)
        section.footer_distance = Inches(0.6)


def _set_base_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = Pt(BODY_FONT_SIZE_PT)

    sizes = {"Title": 18, "Heading 1": 14, "Heading 2": 13, "Heading 3": 12, "Heading 4": 11}
    for style_name, size_pt in sizes.items():
        style = document.styles[style_name]
        style.font.name = FONT_NAME
        style.font.size = Pt(size_pt)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(ACCENT_COLOR)

    # python-docx's built-in Title style ships with a bottom paragraph
    # border -- strip it so the cover page doesn't show stray rules under
    # "Test Plan" / the project title.
    clear_paragraph_border(document.styles["Title"])

    # Never let a heading sit alone at the bottom of a page with its content
    # pushed to the next one -- every heading level stays glued to whatever
    # follows it. Which specific sections force a fresh page is decided
    # explicitly per call site (each _build_* function's `page_break=`
    # argument to _add_heading), not blanket per style, so front-matter
    # sections can share a page deliberately.
    for style_name in ("Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        document.styles[style_name].paragraph_format.keep_with_next = True


# --------------------------------------------------------------------------
# Generic content helpers
# --------------------------------------------------------------------------


def _add_heading(document: Document, text: str, level: int, *, page_break: bool = False):
    """Add a heading. `page_break=True` starts this section on a fresh page --
    used deliberately per top-level section (see each _build_* function),
    not as a blanket per-style rule, so front-matter sections can be made to
    share a page on purpose (e.g. Document Version Control + Release History)."""
    heading = document.add_heading(text, level=level)
    if page_break:
        heading.paragraph_format.page_break_before = True
    return heading


def _add_paragraph(document: Document, text: str, *, bold: bool = False, italic: bool = False):
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.name = FONT_NAME
    run.font.size = Pt(BODY_FONT_SIZE_PT)
    run.font.bold = bold
    run.font.italic = italic
    return paragraph


def _add_bullets(document: Document, items: list[str], level: int = 0) -> None:
    style_name = "List Bullet" if level == 0 else "List Bullet 2"
    for item in items:
        paragraph = document.add_paragraph(style=style_name)
        run = paragraph.add_run(item)
        run.font.name = FONT_NAME
        run.font.size = Pt(BODY_FONT_SIZE_PT)


def _add_nested_bullets(document: Document, groups) -> None:
    """groups: iterable of objects with .area (level-0 bullet) and .items (level-1 bullets)."""
    for group in groups:
        _add_bullets(document, [group.area], level=0)
        _add_bullets(document, list(group.items), level=1)


def _add_table(
    document: Document,
    headers: list[str],
    rows: list[list[str]],
    widths_in: list[float],
    *,
    font_size_pt: float = TABLE_FONT_SIZE_PT,
    cell_padding_pt: float = 6,
):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    header_row = table.rows[0]
    repeat_header_row(header_row)
    set_min_row_height(header_row, MIN_ROW_HEIGHT_PT)
    set_row_cant_split(header_row)
    for idx, header in enumerate(headers):
        cell = header_row.cells[idx]
        style_cell(cell, header, bold=True, color="FFFFFF", size_pt=font_size_pt)
        shade_cell(cell, ACCENT_COLOR)
        # Glue the header row to the first data row so Word never strands the
        # header alone at the bottom of a page with its data pushed to the
        # next one -- which is what makes the repeating header look like a
        # duplicate. Word honors keep-with-next set on a table cell's own
        # paragraph as a row-pagination hint, the same as it does for a
        # heading kept with its following paragraph.
        cell.paragraphs[0].paragraph_format.keep_with_next = True

    for row in rows:
        table_row = table.add_row()
        set_min_row_height(table_row, MIN_ROW_HEIGHT_PT)
        set_row_cant_split(table_row)
        cells = table_row.cells
        for idx, value in enumerate(row):
            style_cell(cells[idx], value, size_pt=font_size_pt)

    set_fixed_column_widths(table, widths_in)
    set_table_cell_margins(table, left_pt=cell_padding_pt, right_pt=cell_padding_pt)
    document.add_paragraph()
    return table


def _doc_location_table(document: Document, entries) -> None:
    if not entries:
        return
    _add_table(
        document,
        ["Document", "Location"],
        [[entry.document, entry.location] for entry in entries],
        widths_in=[2.3, 4.3],
    )


# --------------------------------------------------------------------------
# Cover page
# --------------------------------------------------------------------------


def _spacer(document: Document, *, before_pt: int = 0, after_pt: int = 0):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(before_pt)
    paragraph.paragraph_format.space_after = Pt(after_pt)
    return paragraph


def _build_cover_page(document: Document, plan: TestPlan) -> None:
    section = document.sections[0]
    section.different_first_page_header_footer = True

    header_logo = header_logo_path()
    if header_logo.exists():
        header_paragraph = section.first_page_header.paragraphs[0]
        header_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        header_paragraph.add_run().add_picture(str(header_logo), width=Inches(1.3))

    _spacer(document, after_pt=72)

    project_logo = project_logo_path()
    if project_logo.exists():
        logo_paragraph = document.add_paragraph()
        logo_paragraph.paragraph_format.space_after = Pt(18)
        logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logo_paragraph.add_run().add_picture(str(project_logo), width=Inches(2.0))

    title1 = document.add_paragraph(style="Title")
    title1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title1.add_run("Test Plan")

    for_p = document.add_paragraph()
    for_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for_p.add_run("for")

    title2 = document.add_paragraph(style="Title")
    title2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title2.add_run(plan.meta.title)

    project_id_p = document.add_paragraph()
    project_id_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    project_id_p.add_run(f"Project ID: {plan.meta.project_id}")

    footer_p = _spacer(document, before_pt=260)
    footer_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    footer_p.add_run(f"{plan.meta.prepared_by}\n{plan.meta.prepared_date}")

    document.add_page_break()
    _build_table_of_contents(document)

    classification_p = section.footer.paragraphs[0]
    classification_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    classification_run = classification_p.add_run(CLASSIFICATION_TEXT)
    classification_run.font.name = FONT_NAME
    classification_run.font.size = Pt(8)
    classification_run.font.italic = True
    classification_run.font.color.rgb = RGBColor.from_string("595959")

    default_footer_p = section.footer.add_paragraph()
    default_footer_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = default_footer_p.add_run(f"Version {plan.meta.version}\tPage ")
    run.font.name = FONT_NAME
    run.font.size = Pt(9)
    add_page_field(default_footer_p, "PAGE")
    run2 = default_footer_p.add_run(" of ")
    run2.font.name = FONT_NAME
    run2.font.size = Pt(9)
    add_page_field(default_footer_p, "NUMPAGES")


def _build_table_of_contents(document: Document) -> None:
    # Deliberately not the "Heading 1" style -- that style now carries
    # page-break-before, and a heading-styled ToC title would list itself
    # as an entry in its own table of contents.
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run("Table of Contents")
    run.font.name = FONT_NAME
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor.from_string(ACCENT_COLOR)
    title.paragraph_format.space_after = Pt(12)

    toc_paragraph = document.add_paragraph()
    add_page_field(
        toc_paragraph,
        'TOC \\o "1-4" \\h \\z \\u',
        placeholder_text="Right-click here and choose \"Update Field\" to generate the Table of Contents.",
    )


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------


def _build_version_control(document: Document, plan: TestPlan) -> None:
    _add_heading(document, "A. Document Version Control", level=1, page_break=True)
    add_key_value_table(
        document,
        [
            ("Title", plan.meta.title),
            ("Project ID", plan.meta.project_id),
            ("Document ID", plan.meta.document_id),
            ("Description", plan.meta.description),
            ("Approved date", plan.meta.approved_date),
            ("Master Template ID", plan.meta.master_template_id),
        ],
    )

    _add_heading(document, "B. Document Release History", level=1)
    _add_table(
        document,
        ["Version", "Date", "Author", "Reviewed By", "Reviewed On", "Approved By", "Approved On", "Reasons"],
        [
            [e.version, e.date, e.author, e.reviewed_by, e.reviewed_on, e.approved_by, e.approved_on, e.reasons]
            for e in plan.release_history
        ],
        # Reasons is the only genuinely free-text column, so it gets the most
        # room. Every other width is the minimum that keeps its own *header*
        # on one line -- a header breaking mid-word ("Versio-n") is the tell
        # that a column is starved, so Version cannot go below ~0.68in however
        # short its values are. Date fits "25-Jul-2026" unwrapped; Author fits
        # a company name wrapping between words.
        #
        # The four Reviewed/Approved columns still break "TBD -
        # Client/Project Input Required" mid-word. That is unavoidable at
        # eight columns: giving each the ~0.95in that string needs would leave
        # Reasons under half an inch. Accepted deliberately -- those cells are
        # placeholders QA overwrites with real names and dates, which wrap
        # fine.
        #
        # Must still sum to ~6.6in -- Word will not shrink a fixed-layout
        # table that overflows the page.
        widths_in=[0.68, 0.8, 0.85, 0.75, 0.7, 0.75, 0.7, 1.37],
        font_size_pt=DENSE_TABLE_FONT_SIZE_PT,
        cell_padding_pt=4,
    )


def _build_introduction(document: Document, plan: TestPlan) -> None:
    intro = plan.introduction
    _add_heading(document, "Introduction", level=1, page_break=True)

    _add_heading(document, "Purpose", level=2)
    _add_paragraph(document, intro.purpose)

    _add_heading(document, "Project Overview", level=2)
    _add_paragraph(document, intro.project_overview)

    _add_heading(document, "Scope of testing", level=2)
    _add_heading(document, "In Scope", level=3)
    if intro.scope_in_areas:
        _add_heading(document, "Core Functional Areas", level=4)
        _add_nested_bullets(document, intro.scope_in_areas)
    if intro.scope_in_non_functional:
        _add_heading(document, "Non-Functional Testing", level=4)
        _add_bullets(document, intro.scope_in_non_functional)

    _add_heading(document, "Out of Scope", level=3)
    _add_bullets(document, intro.scope_out)

    if intro.reference_documents:
        _add_heading(document, "Reference Documents", level=2)
        _add_table(
            document,
            ["Process Element", "Reference"],
            [[d.process_element, d.reference] for d in intro.reference_documents],
            widths_in=[2.6, 4.0],
        )


def _build_resources(document: Document, plan: TestPlan) -> None:
    res = plan.resources
    _add_heading(document, "Resource Requirement for Tests", level=1)

    if res.team_members:
        _add_heading(document, "Team Members", level=2)
        _add_table(
            document,
            ["Resource Name", "Designation/Role"],
            [[m.resource_name, m.designation_role] for m in res.team_members],
            widths_in=[3.3, 3.3],
        )

    if res.role_assignments:
        _add_heading(document, "Roles & Responsibilities Matrix", level=2)
        _add_table(
            document,
            ["Element", "Resource Name", "Designation/Role"],
            [[r.element, r.resource_name, r.designation_role] for r in res.role_assignments],
            widths_in=[2.3, 2.2, 2.1],
        )

    _add_heading(document, "Orientation/Training Plan", level=2)
    if res.orientation_intro:
        _add_paragraph(document, res.orientation_intro)
    _add_bullets(document, res.orientation_topics)

    _add_heading(document, "Inputs/Documents needed from Project Team", level=2)
    _add_bullets(document, res.inputs_needed)

    _add_heading(document, "Test Environment Needed", level=2)
    if res.environment_software:
        _add_heading(document, "Software", level=3)
        _add_table(
            document,
            ["S. No", "Software", "Purpose"],
            [[i.sno, i.name, i.purpose] for i in res.environment_software],
            widths_in=[0.6, 2.5, 3.5],
        )
    if res.environment_hardware:
        _add_heading(document, "Hardware", level=3)
        _add_table(
            document,
            ["S. No", "Hardware", "Purpose"],
            [[i.sno, i.name, i.purpose] for i in res.environment_hardware],
            widths_in=[0.6, 2.5, 3.5],
        )


def _build_assumptions_dependencies_risks(document: Document, plan: TestPlan) -> None:
    adr = plan.assumptions_dependencies_risks
    _add_heading(document, "Assumptions, Dependencies & Risks", level=1)

    _add_heading(document, "Assumptions", level=2)
    _add_bullets(document, adr.assumptions)

    _add_heading(document, "Dependencies", level=2)
    _add_bullets(document, adr.dependencies)

    _add_heading(document, "Risks", level=2)
    _add_bullets(document, adr.risks)


def _build_strategy(document: Document, plan: TestPlan) -> None:
    strategy = plan.strategy
    _add_heading(document, "Test Strategy/Methods", level=1)

    _add_heading(document, "Overall Test Strategy", level=2)
    for para in strategy.overall_strategy:
        _add_paragraph(document, para)

    _add_heading(document, "Strategy for Integration of Product Modules", level=2)
    for para in strategy.integration_strategy:
        _add_paragraph(document, para)
    if strategy.integration_key_areas:
        _add_bullets(document, strategy.integration_key_areas)

    if strategy.integration_sequence:
        _add_heading(document, "Sequence & Criteria for Integration Testing", level=2)
        _add_nested_bullets(document, strategy.integration_sequence)

    if strategy.entry_criteria:
        _add_heading(document, "Entry Criteria for Integration Testing", level=3)
        _add_bullets(document, strategy.entry_criteria)

    if strategy.exit_criteria:
        _add_heading(document, "Exit Criteria for Integration Testing", level=3)
        _add_bullets(document, strategy.exit_criteria)

    if strategy.integration_acceptance_criteria:
        _add_heading(document, "Acceptance Criteria", level=3)
        _add_bullets(document, strategy.integration_acceptance_criteria)


def _build_schedule(document: Document, plan: TestPlan) -> None:
    _add_heading(document, "Test Schedule", level=1)
    _add_table(
        document,
        ["Release", "Sprint", "Iteration", "Start Date", "End Date"],
        [[e.release, e.sprint, e.iteration, e.start_date, e.end_date] for e in plan.schedule],
        widths_in=[1.4, 1.2, 1.1, 1.4, 1.5],
    )


def _build_deliverables(document: Document, plan: TestPlan) -> None:
    deliv = plan.deliverables
    _add_heading(document, "Test Deliverables", level=1)
    _add_paragraph(
        document, "All the Test deliverables should be shared to the customer at the end of project"
    )

    _add_heading(document, "Test Plan", level=2)
    _add_paragraph(document, deliv.test_plan_note)

    _add_heading(document, "Test Cases & Test Logs", level=2)
    _doc_location_table(document, deliv.test_cases_logs)

    _add_heading(document, "Acceptance/Exit Criteria", level=2)
    _add_paragraph(document, deliv.acceptance_exit_note)
    _doc_location_table(document, deliv.acceptance_exit_docs)

    _add_heading(document, "Bug Analysis", level=2)
    _add_paragraph(document, deliv.bug_analysis_note)
    _doc_location_table(document, deliv.bug_analysis_docs)

    _add_heading(document, "Release Notes", level=2)
    _add_paragraph(document, deliv.release_notes_note)
    _doc_location_table(document, deliv.release_notes_docs)

    _add_heading(document, "Non Functional Testing", level=2)
    _add_paragraph(document, deliv.non_functional_note)
    _doc_location_table(document, deliv.non_functional_docs)


def _build_closure(document: Document, plan: TestPlan) -> None:
    closure = plan.closure
    _add_heading(document, "Test Closure", level=1)
    _add_paragraph(
        document,
        "Test closure activities are performed at the completion of each sprint and at the "
        "final release milestone, based on requirement completion and acceptance.",
    )
    if closure.sprint_closure_criteria:
        _add_paragraph(document, "A sprint is considered test-closed when:")
        _add_bullets(document, closure.sprint_closure_criteria)
    if closure.release_closure_criteria:
        _add_paragraph(document, "At the end of the release:")
        _add_bullets(document, closure.release_closure_criteria)


def _build_approval_signoff(document: Document) -> None:
    _add_heading(document, "Approval & Sign-off", level=1)
    _add_paragraph(
        document,
        "This Test Plan is considered approved once each role below has "
        "reviewed and signed off on its content.",
    )
    _add_table(
        document,
        ["Role", "Name", "Signature", "Date"],
        [
            ["Prepared By (QA)", CLIENT_INPUT_TBD, "", ""],
            ["Reviewed By", CLIENT_INPUT_TBD, "", ""],
            ["Approved By", CLIENT_INPUT_TBD, "", ""],
        ],
        widths_in=[1.7, 2.3, 1.4, 1.2],
    )


# --------------------------------------------------------------------------
# Top-level build / write
# --------------------------------------------------------------------------


def _document_author(plan: TestPlan) -> str:
    """Who the file's metadata names as author.

    Prefers the plan's own prepared-by value, but never a `TBD` placeholder --
    "TBD - To be added by QA" is honest inside the document, where a reader
    understands it as an unfilled field, and meaningless as a file author.
    """
    prepared_by = (plan.meta.prepared_by or "").strip()
    if prepared_by and not prepared_by.upper().startswith("TBD"):
        return prepared_by
    return "Emvigo QA"


def build_report(plan: TestPlan) -> Document:
    document = Document()
    _set_a4_portrait(document)
    _set_base_styles(document)
    # Never ship python-docx's default author, and never the Windows account
    # name Word stamps in during _bake_live_fields -- this document goes to a
    # client, who can read both in File > Info.
    set_authorship(
        document,
        author=_document_author(plan),
        title=f"Test Plan for {plan.meta.title}" if plan.meta.title else "Test Plan",
        subject=plan.meta.project_id or "",
    )

    _build_cover_page(document, plan)
    _build_version_control(document, plan)
    _build_introduction(document, plan)
    _build_resources(document, plan)
    _build_assumptions_dependencies_risks(document, plan)
    _build_strategy(document, plan)
    _build_schedule(document, plan)
    _build_deliverables(document, plan)
    _build_closure(document, plan)
    _build_approval_signoff(document)

    # PAGE/NUMPAGES in the footer and the Table of Contents are live fields
    # with no cached value -- without this, Word shows them blank until the
    # user manually right-clicks each one and chooses "Update Field".
    set_update_fields_on_open(document)

    return document


def _bake_live_fields(docx_path) -> None:
    """Compute and cache this document's TOC/PAGE/NUMPAGES field values.

    The implementation is shared with `report_exporter.py` (which needs the
    identical Word COM pass for its own Table of Contents), so it lives in
    `orchestrator/utils/docx_helpers.py` per that module's no-duplication rule.
    """
    bake_live_fields(docx_path)


def write_report(doc_name: str) -> None:
    json_path = test_plan_json_path(doc_name)
    data = read_json(json_path)

    errors, warnings = validate_file(json_path)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Refusing to generate the Test Plan: {json_path.name} failed validation. "
            "Fix the JSON and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    plan = TestPlan.from_dict(data)

    document = build_report(plan)

    docx_path = test_plan_docx_path(doc_name)
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    save_document(document, docx_path)
    _bake_live_fields(docx_path)
    # Word's save during field baking overwrote last_modified_by with the
    # Windows account name; reset it before the file goes to a client.
    scrub_authorship(docx_path, author=_document_author(plan))
    print(str(docx_path))


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.generation.test_plan_docx_writer <doc-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    _, doc_name = sys.argv
    write_report(doc_name)


if __name__ == "__main__":
    main()
