import csv
import json
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from orchestrator.generation import test_case_md_writer
from orchestrator.generation.test_case_tracking import has_recorded_tracking_data
from orchestrator.generation.zephyr_export import (
    AUDIT_LEFT_MARGIN_COLS,
    AUDIT_TOP_MARGIN_ROWS,
    COLUMNS,
    DEFAULT_EXECUTION_STATUS,
    DOCUMENT_CONTROL_FIELDS,
    EXECUTION_STATUS_OPTIONS,
    RELEASE_HISTORY_CENTER_COLUMNS,
    RELEASE_HISTORY_COLUMNS,
    REVIEW_COLUMN_WIDTHS,
    REVIEW_COLUMNS,
    REVIEW_WRAP_COLUMNS,
    VERSION_CONTROL_CENTER_FIELDS,
    VERSION_CONTROL_COLUMN_WIDTHS,
    _centered_image_anchor,
    _column_width_to_px,
    _doc_name_from_input,
    _estimated_line_count,
    _merge_steps,
    _row_height,
    build_release_history_rows,
    build_review_rows,
    build_rows,
    export,
    load_requirement_texts,
    write_csv,
    write_xlsx,
)
# Aliased on import: pytest's default collection matches any module-level
# name starting with "Test", and these are data models, not test classes.
from orchestrator.models.test_case import (
    DocumentControlMeta,
    ReleaseHistoryEntry,
    TestCase as CaseModel,
    TestCaseDocument as CaseDocumentModel,
    TestCaseMeta as CaseMetaModel,
    TestStep as StepModel,
)


def _document():
    tc1 = CaseModel(
        tc_id="TC-001",
        req_id="REQ-001",
        title="Successful login",
        objective="Verify a registered user can log in.",
        test_type="Positive",
        priority="High",
        preconditions="A registered user account exists.",
        steps=[
            StepModel(1, "Enter a valid username.", "Username field shows the entered value.", "validuser"),
            StepModel(2, "Click Login.", "The dashboard page loads.", ""),
        ],
    )
    tc2 = CaseModel(
        tc_id="TC-002",
        req_id="REQ-002",
        title="Reject expired token",
        objective="Verify an expired reset link is rejected.",
        test_type="Negative",
        priority="Medium",
        preconditions="A reset link older than the stated expiry exists.",
        steps=[
            StepModel(1, "Open the expired reset link.", "An 'This link has expired' message is shown.", ""),
        ],
    )
    return CaseDocumentModel(
        meta=CaseMetaModel(source_doc="doc", version="1.0"),
        test_cases=[tc1, tc2],
        not_covered=[],
    )


def _document_control(**overrides):
    base = dict(
        title="Test Cases for LinkGrid",
        project_id="TBD – Client/Project Input Required",
        document_id="TBD – Client/Project Input Required",
        description="Test cases derived from the LinkGrid requirement analysis.",
        prepared_by="Emvigo QA",
        prepared_date="2026-07-26",
        approved_date="TBD – Client/Project Input Required",
        master_template_id="TBD – Client/Project Input Required",
        version="1.0",
    )
    base.update(overrides)
    return DocumentControlMeta(**base)


def _release_history():
    return [
        ReleaseHistoryEntry(
            version="1.0",
            date="2026-07-26",
            author="Emvigo QA",
            reviewed_by="TBD – Client/Project Input Required",
            reviewed_on="",
            approved_by="TBD – Client/Project Input Required",
            approved_on="",
            reasons="Initial test case generation.",
        )
    ]


# --- CSV: strict Zephyr shape, one row per step (unchanged behaviour) ---

def test_build_rows_one_row_per_step_with_repeated_identifying_columns():
    rows = build_rows(_document(), folder="acme")
    assert len(rows) == 3  # 2 steps for TC-001 + 1 step for TC-002

    tc1_rows = [r for r in rows if r[0] == "TC-001"]
    assert len(tc1_rows) == 2
    # Identifying columns repeat on every step row of the same test case.
    assert tc1_rows[0][1] == tc1_rows[1][1] == "Successful login"
    assert tc1_rows[0][5] == tc1_rows[1][5] == "REQ-001"
    assert tc1_rows[0][6] == tc1_rows[1][6] == "acme"
    # Step-specific columns vary: Step carries the actual instruction text
    # (not the bare step_number), in step order.
    assert tc1_rows[0][7] == "Enter a valid username."
    assert tc1_rows[1][7] == "Click Login."
    assert tc1_rows[0][8] == "validuser"


def test_build_rows_handles_test_case_with_no_steps():
    doc = CaseDocumentModel(
        meta=CaseMetaModel(source_doc="doc"),
        test_cases=[
            CaseModel(
                tc_id="TC-001",
                req_id="REQ-001",
                title="Edge case",
                objective="obj",
                test_type="Positive",
                priority="Low",
                steps=[],
            )
        ],
    )
    rows = build_rows(doc, folder="acme")
    assert len(rows) == 1
    assert rows[0][7] == ""


def test_write_csv_round_trip(tmp_path):
    path = tmp_path / "out" / "cases.csv"
    write_csv(build_rows(_document(), folder="acme"), path)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert rows[0] == COLUMNS
    assert len(rows) == 4  # header + 3 step rows
    assert rows[1][0] == "TC-001"


# --- XLSX "Test Cases" sheet: human execution/review shape, one row per
# test case ---

def test_merge_steps_numbers_each_line_and_keeps_columns_aligned():
    tc = _document().test_cases[0]  # TC-001, 2 steps
    steps_text, data_text, expected_text = _merge_steps(tc)
    assert steps_text == "1. Enter a valid username.\n2. Click Login."
    # Step 2 has no test data -- it's dropped entirely, not left as a bare
    # "2. " placeholder (this was a real reported bug: "1. \n2. " read as
    # noise, not information).
    assert data_text == "1. validuser"
    assert expected_text == (
        "1. Username field shows the entered value.\n2. The dashboard page loads."
    )


def test_merge_steps_test_data_is_blank_when_no_step_has_any():
    tc = CaseModel(
        tc_id="TC-004", req_id="REQ-004", title="t", objective="o",
        test_type="Positive", priority="Low",
        steps=[
            StepModel(1, "Do a thing.", "It happens.", ""),
            StepModel(2, "Do another thing.", "It also happens.", ""),
        ],
    )
    _, data_text, _ = _merge_steps(tc)
    assert data_text == ""


def test_merge_steps_keeps_real_step_number_when_some_steps_have_no_data():
    tc = CaseModel(
        tc_id="TC-005", req_id="REQ-005", title="t", objective="o",
        test_type="Positive", priority="Low",
        steps=[
            StepModel(1, "Step one.", "Result one.", ""),
            StepModel(2, "Step two.", "Result two.", "Role = Canvasser"),
            StepModel(3, "Step three.", "Result three.", ""),
        ],
    )
    _, data_text, _ = _merge_steps(tc)
    assert data_text == "2. Role = Canvasser"


def test_merge_steps_handles_no_steps():
    tc = CaseModel(
        tc_id="TC-999", req_id="REQ-001", title="t", objective="o",
        test_type="Positive", priority="Low", steps=[],
    )
    assert _merge_steps(tc) == ("", "", "")


def test_build_review_rows_one_row_per_test_case():
    rows = build_review_rows(_document(), requirement_texts={"REQ-001": "Users can log in."})
    assert len(rows) == 2  # one row per test case, not per step

    tc1 = rows[0]
    assert tc1[REVIEW_COLUMNS.index("Test Case Key")] == "TC-001"
    assert tc1[REVIEW_COLUMNS.index("Requirement ID")] == "REQ-001"
    assert tc1[REVIEW_COLUMNS.index("Requirement")] == "Users can log in."
    assert "1. Enter a valid username." in tc1[REVIEW_COLUMNS.index("Steps")]
    assert tc1[REVIEW_COLUMNS.index("Execution Status")] == DEFAULT_EXECUTION_STATUS
    # Actual Result is QA/test-run-filled at execution time, not generated
    # -- blank by construction.
    assert tc1[REVIEW_COLUMNS.index("Actual Result")] == ""
    # Linked Issue is QA-typed only -- blank by construction too.
    assert tc1[REVIEW_COLUMNS.index("Linked Issue")] == ""

    tc2 = rows[1]
    # No requirement text supplied for REQ-002 -- blank, not a crash.
    assert tc2[REVIEW_COLUMNS.index("Requirement")] == ""


def test_build_review_rows_carries_forward_existing_tracking():
    existing_tracking = {
        "TC-001": {
            "Actual Result": "All steps executed as expected; no failures reported.",
            "Execution Status": "Pass",
            "Linked Issue": "JIRA-123",
        }
    }
    rows = build_review_rows(
        _document(), requirement_texts={}, existing_tracking=existing_tracking
    )
    tc1 = rows[0]
    assert tc1[REVIEW_COLUMNS.index("Execution Status")] == "Pass"
    assert tc1[REVIEW_COLUMNS.index("Actual Result")] == (
        "All steps executed as expected; no failures reported."
    )
    assert tc1[REVIEW_COLUMNS.index("Linked Issue")] == "JIRA-123"

    # TC-002 has no prior entry -- untouched defaults, not a crash.
    tc2 = rows[1]
    assert tc2[REVIEW_COLUMNS.index("Execution Status")] == DEFAULT_EXECUTION_STATUS
    assert tc2[REVIEW_COLUMNS.index("Actual Result")] == ""
    assert tc2[REVIEW_COLUMNS.index("Linked Issue")] == ""


def test_write_xlsx_writes_review_shape_with_one_row_per_test_case(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    review_rows = build_review_rows(_document(), requirement_texts={"REQ-001": "Users can log in."})
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Test Cases"]
    header = [cell.value for cell in sheet[1]]
    assert header == REVIEW_COLUMNS
    assert sheet.max_row == 3  # header + 2 test cases (not 4 steps)
    assert sheet.cell(row=2, column=REVIEW_COLUMNS.index("Test Case Key") + 1).value == "TC-001"
    assert sheet.cell(row=2, column=REVIEW_COLUMNS.index("Requirement ID") + 1).value == "REQ-001"
    assert sheet.cell(row=2, column=REVIEW_COLUMNS.index("Execution Status") + 1).value == "Not Executed"
    # Requirement columns are read before the test case that traces to them.
    assert REVIEW_COLUMNS.index("Requirement ID") < REVIEW_COLUMNS.index("Test Case Key")
    assert REVIEW_COLUMNS.index("Requirement") < REVIEW_COLUMNS.index("Test Case Name")


def test_write_xlsx_adds_execution_status_dropdown(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    review_rows = build_review_rows(_document(), requirement_texts={})
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Test Cases"]
    validations = list(sheet.data_validations.dataValidation)
    assert len(validations) == 1
    dv = validations[0]
    assert dv.type == "list"
    for option in EXECUTION_STATUS_OPTIONS:
        assert option in dv.formula1


def test_write_xlsx_adds_autofilter_across_the_full_header(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    review_rows = build_review_rows(_document(), requirement_texts={})
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Test Cases"]
    last_col = get_column_letter(len(REVIEW_COLUMNS))
    assert sheet.auto_filter.ref == f"A1:{last_col}{sheet.max_row}"


# --- XLSX: three-sheet controlled-document workbook ---

def test_write_xlsx_creates_three_sheets_in_iso_audit_order(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    review_rows = build_review_rows(_document(), requirement_texts={})
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    assert workbook.sheetnames == [
        "Document Version Control",
        "Document Release History",
        "Test Cases",
    ]
    # Opens on the front-matter sheet first, like a cover page.
    assert workbook.active.title == "Document Version Control"


def test_version_control_sheet_shows_every_document_control_field(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    control = _document_control(title="My Title", project_id="PID-1")
    write_xlsx([], control, _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Version Control"]
    values = {cell.value for row in sheet.iter_rows() for cell in row if cell.value is not None}
    assert "My Title" in values
    assert "PID-1" in values
    for label, _ in DOCUMENT_CONTROL_FIELDS:
        assert label in values


def test_version_control_sheet_embeds_the_project_logo(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Version Control"]
    assert len(sheet._images) == 1


def test_build_release_history_rows_matches_columns():
    rows = build_release_history_rows(_release_history())
    assert len(rows) == 1
    assert len(rows[0]) == len(RELEASE_HISTORY_COLUMNS)
    assert rows[0][RELEASE_HISTORY_COLUMNS.index("Version")] == "1.0"
    assert rows[0][RELEASE_HISTORY_COLUMNS.index("Reasons")] == "Initial test case generation."


RELEASE_HISTORY_HEADER_ROW = AUDIT_TOP_MARGIN_ROWS + 1
RELEASE_HISTORY_START_COL = AUDIT_LEFT_MARGIN_COLS + 1


def test_release_history_sheet_has_one_row_per_entry(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    history = _release_history() + [
        ReleaseHistoryEntry(
            version="1.1", date="2026-07-27", author="Emvigo QA",
            reviewed_by="", reviewed_on="", approved_by="", approved_on="",
            reasons="Added new test cases.",
        )
    ]
    write_xlsx([], _document_control(), history, path)

    workbook = load_workbook(path)
    sheet = workbook["Document Release History"]
    header = [
        sheet.cell(row=RELEASE_HISTORY_HEADER_ROW, column=RELEASE_HISTORY_START_COL + i).value
        for i in range(len(RELEASE_HISTORY_COLUMNS))
    ]
    assert header == RELEASE_HISTORY_COLUMNS
    assert sheet.max_row == RELEASE_HISTORY_HEADER_ROW + 2  # header + 2 entries


def test_release_history_sheet_handles_empty_history(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), [], path)

    workbook = load_workbook(path)
    sheet = workbook["Document Release History"]
    assert sheet.max_row == RELEASE_HISTORY_HEADER_ROW  # header only, no rows, no crash


def test_release_history_sheet_does_not_start_at_the_sheet_corner(tmp_path):
    """The actual "centering" fix: the table starts well past A1, not
    flush against it -- a real blank margin, not a print/view setting."""
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Release History"]
    assert sheet.cell(row=1, column=1).value is None
    assert RELEASE_HISTORY_HEADER_ROW > 1
    assert RELEASE_HISTORY_START_COL > 1
    assert sheet.cell(row=RELEASE_HISTORY_HEADER_ROW, column=RELEASE_HISTORY_START_COL).value == "Version"


# --- alignment/borders/centering (the "make it look right" review round) ---

def test_column_width_to_px_is_reasonable():
    # A wider column must produce a larger pixel width, monotonically.
    assert _column_width_to_px(10) < _column_width_to_px(50)
    assert _column_width_to_px(0) > 0


def test_centered_image_anchor_centers_within_the_given_span():
    # A span of two equal-width columns: a narrower-than-span image should
    # land with a non-zero offset into (or before) the second column,
    # roughly at the span's midpoint, not flush against its left edge.
    anchor = _centered_image_anchor(
        ["B", "C"], {"B": 20, "C": 20}, row_idx=1, width_px=50, height_px=50
    )
    # Total span ~= 2 * (20*7+5) = 2*145 = 290px; centered offset = (290-50)/2 = 120px,
    # which exceeds column B's own 145px only partially -- so it should land
    # inside column B itself (index 1) with an offset, not at column C (index 2).
    assert anchor._from.col in (1, 2)
    assert anchor._from.colOff >= 0
    assert anchor.ext.cx > 0 and anchor.ext.cy > 0


def test_centered_image_anchor_is_not_flush_left():
    # A logo much narrower than its span must NOT anchor at column-offset 0
    # of the span's first column -- that would just be a left-aligned
    # anchor wearing a "centered" label.
    anchor = _centered_image_anchor(
        ["B", "C"], VERSION_CONTROL_COLUMN_WIDTHS, row_idx=1, width_px=150, height_px=140
    )
    at_flush_left = anchor._from.col == 1 and anchor._from.colOff == 0
    assert not at_flush_left


def test_version_control_sheet_has_borders_and_centered_short_fields(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Version Control"]

    # Locate the "Document Title" label row dynamically rather than
    # hardcoding a row number, so this test survives layout tweaks.
    label_col = AUDIT_LEFT_MARGIN_COLS + 1
    value_col = label_col + 1
    label_row = next(
        r for r in range(1, sheet.max_row + 1)
        if sheet.cell(row=r, column=label_col).value == "Document Title"
    )
    label_cell = sheet.cell(row=label_row, column=label_col)
    value_cell = sheet.cell(row=label_row, column=value_col)

    assert label_cell.border.left.style == "thin"
    assert value_cell.border.left.style == "thin"
    assert value_cell.alignment.horizontal == "center"  # a VERSION_CONTROL_CENTER_FIELDS field

    description_row = next(
        r for r in range(1, sheet.max_row + 1)
        if sheet.cell(row=r, column=label_col).value == "Description"
    )
    description_value = sheet.cell(row=description_row, column=value_col)
    assert description_value.border.left.style == "thin"  # bordered
    assert description_value.alignment.horizontal is None  # but not centered (long text)


def test_version_control_sheet_does_not_start_at_the_sheet_corner(tmp_path):
    """The actual "centering" fix: the table starts well past A1, not
    flush against it -- a real blank margin, not a print/view setting."""
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Version Control"]
    label_col = AUDIT_LEFT_MARGIN_COLS + 1
    assert sheet.cell(row=1, column=1).value is None
    assert label_col > 1  # real blank columns to the left, not just column A
    assert any(
        sheet.cell(row=r, column=label_col).value == "Document Title"
        for r in range(1, sheet.max_row + 1)
    )


def test_release_history_sheet_has_borders_and_centered_short_columns(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Release History"]

    header_row = RELEASE_HISTORY_HEADER_ROW
    start_col = RELEASE_HISTORY_START_COL
    version_col = start_col + RELEASE_HISTORY_COLUMNS.index("Version")
    reasons_col = start_col + RELEASE_HISTORY_COLUMNS.index("Reasons")

    header_cell = sheet.cell(row=header_row, column=version_col)
    data_cell = sheet.cell(row=header_row + 1, column=version_col)
    reasons_cell = sheet.cell(row=header_row + 1, column=reasons_col)

    assert header_cell.border.left.style == "thin"
    assert data_cell.border.left.style == "thin"
    assert data_cell.alignment.horizontal == "center"
    assert reasons_cell.border.left.style == "thin"  # bordered
    assert reasons_cell.alignment.horizontal is None  # but left/wrapped, not centered
    assert reasons_cell.alignment.wrap_text is True
    # Wrap applies to every column, not just Reasons -- a long Author name
    # or Reviewed By value must never clip either.
    assert data_cell.alignment.wrap_text is True
    assert header_cell.alignment.wrap_text is True


def test_version_control_sheet_wraps_every_cell(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    write_xlsx([], _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Document Version Control"]
    label_col = AUDIT_LEFT_MARGIN_COLS + 1
    value_col = label_col + 1

    title_row = next(
        r for r in range(1, sheet.max_row + 1)
        if sheet.cell(row=r, column=label_col).value == "Document Title"
    )
    assert sheet.cell(row=title_row, column=label_col).alignment.wrap_text is True
    assert sheet.cell(row=title_row, column=value_col).alignment.wrap_text is True


def test_test_cases_sheet_is_not_bordered_or_offset(tmp_path):
    """Regression guard: the border/centering request was scoped to the two
    audit sheets only -- the working Test Cases sheet must be unaffected,
    still starting at A1 exactly like before."""
    path = tmp_path / "out" / "cases.xlsx"
    review_rows = build_review_rows(_document(), requirement_texts={})
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Test Cases"]
    assert sheet.cell(row=1, column=1).value == REVIEW_COLUMNS[0]
    data_cell = sheet.cell(row=2, column=1)
    assert data_cell.border.left.style is None


# --- row height: must account for wrapping in EVERY wrap column, not just
# Steps (this was a real bug -- a long Requirement/Objective sentence with
# no embedded newline still wraps within its column width and needs a tall
# enough row, or it renders clipped) ---

def test_estimated_line_count_single_short_line_is_one():
    assert _estimated_line_count("Short text.", column_width=30) == 1


def test_estimated_line_count_wraps_long_line_with_no_newlines():
    # 80 chars in a 20-wide column must wrap onto multiple visual lines,
    # even though there isn't a single '\n' in the text.
    long_line = "A" * 80
    assert _estimated_line_count(long_line, column_width=20) > 1


def test_estimated_line_count_counts_newlines_and_wrapping_together():
    text = "1. Short.\n2. " + ("B" * 80)
    lines = _estimated_line_count(text, column_width=20)
    assert lines > 2  # line 1 is one visual line, line 2 wraps into several


def test_row_height_driven_by_long_requirement_not_short_steps():
    columns = ["Requirement", "Steps"]
    short_steps_row = ["A" * 300, "1. Ok."]  # long Requirement, trivial Steps
    tall_height = _row_height(short_steps_row, columns, REVIEW_WRAP_COLUMNS, REVIEW_COLUMN_WIDTHS)

    baseline_row = ["Short.", "1. Ok."]
    short_height = _row_height(baseline_row, columns, REVIEW_WRAP_COLUMNS, REVIEW_COLUMN_WIDTHS)

    assert tall_height > short_height


def test_row_height_respects_the_columns_and_widths_passed_in():
    # Same text, two different column-width configs -> a narrower column
    # needs more wrapped lines, so a taller (or equal) row height.
    columns = ["Step"]
    row = ["A" * 100]
    wide_height = _row_height(row, columns, {"Step"}, {"Step": 40})
    narrow_height = _row_height(row, columns, {"Step"}, {"Step": 10})
    assert narrow_height >= wide_height


def test_write_xlsx_sizes_row_for_the_tallest_wrap_column(tmp_path):
    path = tmp_path / "out" / "cases.xlsx"
    long_requirement = "A" * 400  # far longer than the Requirement column's width
    review_rows = [
        [
            "REQ-001", long_requirement, "TC-001", "Short name", "obj", "precond",
            "High", "Positive", "1. One step.", "1. ", "1. Result.", "",
            "Not Executed",
        ]
    ]
    write_xlsx(review_rows, _document_control(), _release_history(), path)

    workbook = load_workbook(path)
    sheet = workbook["Test Cases"]
    # A single-step test case would previously get the single-line minimum
    # height, clipping the long Requirement text -- it must now be tall.
    assert sheet.row_dimensions[2].height > 15 * 3


# --- requirement-text lookup and path helpers ---

def test_load_requirement_texts_reads_sibling_analysis_json(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod

    analysis_dir = tmp_path / "output" / "requirement-analysis"
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "doc-analysis.json").write_text(
        json.dumps({"requirements": [{"req_id": "REQ-001", "requirement_text": "Users can log in."}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)

    texts = load_requirement_texts("doc")
    assert texts == {"REQ-001": "Users can log in."}


def test_load_requirement_texts_falls_back_to_title_when_text_is_blank(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod

    analysis_dir = tmp_path / "output" / "requirement-analysis"
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "doc-analysis.json").write_text(
        json.dumps(
            {
                "requirements": [
                    {"req_id": "REQ-001", "requirement_text": "  ", "title": "Initial Login Interface"},
                    {"req_id": "REQ-002", "requirement_text": None, "title": "Credential Authentication"},
                    {"req_id": "REQ-003"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)

    assert load_requirement_texts("doc") == {
        "REQ-001": "Initial Login Interface",
        "REQ-002": "Credential Authentication",
        "REQ-003": "",
    }


def test_load_requirement_texts_missing_file_returns_empty(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod
    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)
    assert load_requirement_texts("doc-that-does-not-exist") == {}


def test_doc_name_from_input_strips_test_cases_suffix():
    assert _doc_name_from_input(Path("LinkGrid-test-cases.json")) == "LinkGrid"
    assert _doc_name_from_input(Path("Rental Supplier-test-cases.json")) == "Rental Supplier"


# --- execution-tracking merge-preserve (regression coverage for the
# "regeneration silently wipes QA-recorded execution data" bug). The xlsx's
# own tracking columns are sourced from the sibling `.md` report now (see
# zephyr_export.py's module docstring) -- test_test_case_md_writer.py covers
# `load_existing_review_tracking` itself; these tests cover `export()`'s use
# of it. ---

def test_has_recorded_tracking_data_true_for_non_default_status():
    assert has_recorded_tracking_data({"Execution Status": "Pass"}) is True
    assert has_recorded_tracking_data({"Execution Status": "Fail"}) is True


def test_has_recorded_tracking_data_true_for_actual_result():
    assert has_recorded_tracking_data({"Actual Result": "Login succeeded."}) is True


def test_has_recorded_tracking_data_true_for_linked_issue():
    assert has_recorded_tracking_data({"Linked Issue": "JIRA-123"}) is True


def test_has_recorded_tracking_data_false_for_untouched_defaults():
    assert has_recorded_tracking_data({"Execution Status": DEFAULT_EXECUTION_STATUS}) is False
    assert has_recorded_tracking_data({}) is False


def _write_test_cases_json(workspace_root: Path, doc_name: str, tc_ids: list[str]) -> Path:
    tc_dir = workspace_root / "output" / "test-cases"
    tc_dir.mkdir(parents=True, exist_ok=True)
    document = CaseDocumentModel(
        meta=CaseMetaModel(
            source_doc="doc",
            version="1.0",
            changelog=[{"version": "1.0", "date": "2026-07-26", "changes": "Initial generation."}],
        ),
        test_cases=[
            CaseModel(
                tc_id=tc_id, req_id="REQ-001", title=f"Case {tc_id}", objective="obj",
                test_type="Positive", priority="High",
                steps=[StepModel(1, "Do a thing.", "It happens.", "")],
            )
            for tc_id in tc_ids
        ],
        not_covered=[],
        document_control=_document_control(),
        release_history=_release_history(),
    )
    path = tc_dir / f"{doc_name}-test-cases.json"
    path.write_text(json.dumps(document.to_dict()), encoding="utf-8")
    return path


def test_export_round_trip_preserves_execution_status_on_regeneration(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)

    input_path = _write_test_cases_json(tmp_path, "doc", ["TC-001", "TC-002"])

    csv_path, xlsx_path = export(input_path, "doc-test-cases")
    workbook = load_workbook(xlsx_path)
    sheet = workbook["Test Cases"]
    header = {cell.value: idx for idx, cell in enumerate(sheet[1], start=1)}
    assert sheet.cell(row=2, column=header["Execution Status"]).value == DEFAULT_EXECUTION_STATUS

    # Simulate QA typing a real result directly into the report -- the
    # xlsx is never the place this is recorded, only the sibling .md.
    test_case_md_writer.write_report(
        "doc", overrides={"TC-001": {"Execution Status": "Pass", "Actual Result": "All steps executed as expected."}}
    )

    # Regenerate from the same JSON -- this used to silently wipe the above
    # (back when the xlsx carried tracking forward from itself).
    export(input_path, "doc-test-cases")

    reloaded = load_workbook(xlsx_path)
    reloaded_sheet = reloaded["Test Cases"]
    reloaded_header = {cell.value: idx for idx, cell in enumerate(reloaded_sheet[1], start=1)}
    assert reloaded_sheet.cell(row=2, column=reloaded_header["Execution Status"]).value == "Pass"
    assert reloaded_sheet.cell(row=2, column=reloaded_header["Actual Result"]).value == (
        "All steps executed as expected."
    )
    # Formatting survives the round trip too.
    validations = list(reloaded_sheet.data_validations.dataValidation)
    assert len(validations) == 1
    for option in EXECUTION_STATUS_OPTIONS:
        assert option in validations[0].formula1
    assert len(reloaded["Document Version Control"]._images) == 1


def test_export_prints_note_for_dropped_tc_id_with_real_tracking_data(tmp_path, monkeypatch, capsys):
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)

    input_path = _write_test_cases_json(tmp_path, "doc", ["TC-001", "TC-002"])
    export(input_path, "doc-test-cases")

    test_case_md_writer.write_report("doc", overrides={"TC-001": {"Execution Status": "Pass"}})

    # Regenerate with TC-001 removed.
    _write_test_cases_json(tmp_path, "doc", ["TC-002"])
    export(input_path, "doc-test-cases")

    captured = capsys.readouterr()
    assert "TC-001" in captured.out
    assert "discarded" in captured.out


def test_export_csv_only_does_not_write_xlsx(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)
    input_path = _write_test_cases_json(tmp_path, "doc", ["TC-001"])

    csv_path, xlsx_path = export(input_path, "doc-test-cases", want_csv=True, want_xlsx=False)

    assert csv_path is not None and csv_path.is_file()
    assert xlsx_path is None
    assert not (tmp_path / "output" / "test-cases" / "doc-test-cases.xlsx").exists()


def test_export_xlsx_only_does_not_write_csv(tmp_path, monkeypatch):
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)
    input_path = _write_test_cases_json(tmp_path, "doc", ["TC-001"])

    csv_path, xlsx_path = export(input_path, "doc-test-cases", want_csv=False, want_xlsx=True)

    assert xlsx_path is not None and xlsx_path.is_file()
    assert csv_path is None
    assert not (tmp_path / "output" / "test-cases" / "doc-test-cases.csv").exists()


def test_export_does_not_flag_dropped_tc_id_with_only_untouched_defaults(tmp_path, monkeypatch, capsys):
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)

    input_path = _write_test_cases_json(tmp_path, "doc", ["TC-001", "TC-002"])
    export(input_path, "doc-test-cases")
    # Seed the .md with TC-001/TC-002 both left at untouched defaults --
    # the same state a plain, never-run `/generate-test-cases` leaves them
    # in.
    test_case_md_writer.write_report("doc")

    _write_test_cases_json(tmp_path, "doc", ["TC-002"])  # TC-001 dropped, never executed
    export(input_path, "doc-test-cases")

    captured = capsys.readouterr()
    assert "discarded" not in captured.out
