"""Exports a *-test-cases.json deliverable as a Zephyr-import-ready CSV,
and/or a separately-shaped .xlsx for human test execution/review and
ISO-audit traceability. Both are opt-in: `/generate-test-cases` always
produces the JSON and a Markdown report (`test_case_md_writer.py`); this
script only runs, with the matching flag(s), when the user also passed
`--csv` and/or `--xlsx`.

Usage:
    python -m orchestrator.generation.zephyr_export \
        --input output/test-cases/<doc-name>-test-cases.json \
        --output-name <doc-name>-test-cases \
        [--csv] [--xlsx]

(Neither flag given defaults to both, for direct/legacy CLI use.)

The CSV and the XLSX are deliberately **not** the same shape:

- The **CSV** is strict Zephyr import format: one row per test STEP (not one
  row per test case), with the test case's identifying columns (Test Case
  Key, Test Case Name, Objective, Precondition, Priority, Labels, Folder --
  `Folder` holds the doc-name, the meaningful grouping unit within a single-
  project workspace, now that there's no separate project-name string to
  put there) repeated on every one of its step rows, and only Step / Test
  Data / Expected Result varying row to row. `Step` holds the step's actual
  instruction text (e.g. "Click the Submit button."), not a bare step
  number -- real Zephyr CSV templates have no separate numeric step-order
  column; a step's position is implicit in its row order within the same
  Test Case Key. This shape must never change without a real Zephyr import
  requirement driving it.
- The **XLSX** is a three-sheet controlled-document workbook, mirroring the
  Test Plan's own version-control/release-history structure (a test-case
  suite is just as much an ISO-audit-relevant artifact):
    1. "Document Version Control" -- title, project/document IDs, prepared
       by/date, approved date, master template ID, and the project logo.
    2. "Document Release History" -- one row per formal
       author/reviewer/approver sign-off, append-only across regenerations.
    3. "Test Cases" -- the human execution/review shape: one row per test
       case (its steps merged into a single multi-line cell, numbered), the
       full requirement text, and three tracking columns (Execution Status,
       Actual Result, Linked Issue). Execution Status/Actual Result start
       blank on a test case's first export; a regeneration carries forward
       whatever was already recorded for an unchanged tc_id -- by QA typing
       it directly into the sibling `.md` report -- instead of blanking it,
       via `test_case_md_writer.load_existing_review_tracking`. **The xlsx
       is a pure downstream render of that `.md` file for these three
       columns; it is never itself read back.** All three tracking columns
       are QA-typed only in this project (there is no automation flow here
       to run a suite and write results back), but each is carried forward
       across regenerations by the same mechanism.
"""

import argparse
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from orchestrator.generation import test_case_md_writer
from orchestrator.generation.test_case_tracking import (
    DEFAULT_EXECUTION_STATUS,
    EXECUTION_STATUS_OPTIONS,
    has_recorded_tracking_data,
    load_requirement_texts,
)
from orchestrator.models.test_case import DocumentControlMeta, ReleaseHistoryEntry, TestCaseDocument
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.paths import (
    test_cases_csv_path,
    test_cases_md_path,
    test_cases_xlsx_path,
)
# Shared XLSX formatting primitives (docx_helpers.py's openpyxl analogue) --
# see orchestrator/utils/xlsx_helpers.py's module docstring for why these
# moved out of this file. Re-imported under their original private names so
# this module's own public surface (and test_zephyr_export.py's imports of
# it) is unchanged.
from orchestrator.utils.xlsx_helpers import (
    AUDIT_LEFT_MARGIN_COLS,
    AUDIT_TOP_MARGIN_ROWS,
    DEFAULT_COLUMN_WIDTH,
    HEADER_FILL,
    HEADER_FONT_COLOR,
    LOGO_WIDTH_PX,
    POINTS_PER_LINE,
    THIN_BORDER,
    add_logo as _add_logo,
    apply_borders as _apply_borders,
    build_release_history_rows,
    centered_image_anchor as _centered_image_anchor,
    column_width_to_px as _column_width_to_px,
    estimated_line_count as _estimated_line_count,
    populate_sheet as _populate_sheet,
    row_height as _row_height,
    write_release_history_sheet,
    write_version_control_sheet,
)

# --- CSV: strict Zephyr import shape -- do not change without a real
# Zephyr import requirement driving it. ---
COLUMNS = [
    "Test Case Key",
    "Test Case Name",
    "Objective",
    "Precondition",
    "Priority",
    "Labels",
    "Folder",
    "Step",
    "Test Data",
    "Expected Result",
]

# --- XLSX "Test Cases" sheet: human execution/review shape -- one row per
# test case. Requirement columns come first, then the test case that traces
# to it -- matching how a reviewer actually reads the sheet (requirement,
# then its test case), not an arbitrary order. The last two columns are
# execution-tracking fields, blank until QA types them into the sibling
# `.md` report (see this module's own docstring), not generated content. ---
REVIEW_COLUMNS = [
    "Requirement ID",
    "Requirement",
    "Test Case Key",
    "Test Case Name",
    "Objective",
    "Precondition",
    "Priority",
    "Test Type",
    "Steps",
    "Test Data",
    "Expected Result",
    "Actual Result",
    "Execution Status",
    "Linked Issue",
]
REVIEW_WRAP_COLUMNS = {
    "Test Case Name",
    "Requirement",
    "Objective",
    "Precondition",
    "Steps",
    "Test Data",
    "Expected Result",
    "Actual Result",
    "Linked Issue",
}
REVIEW_COLUMN_WIDTHS = {
    "Requirement ID": 12,
    "Requirement": 36,
    "Test Case Key": 12,
    "Test Case Name": 26,
    "Objective": 28,
    "Precondition": 20,
    "Priority": 10,
    "Test Type": 12,
    "Steps": 36,
    "Test Data": 20,
    "Expected Result": 32,
    "Actual Result": 32,
    "Execution Status": 15,
    "Linked Issue": 18,
}

# EXECUTION_STATUS_OPTIONS/DEFAULT_EXECUTION_STATUS live in
# test_case_tracking.py now (imported above) -- shared with
# test_case_md_writer.py, which is this project's one true source of these
# values (see this module's own docstring). The three QA/execution-tracking
# columns are the tail of REVIEW_COLUMNS ("Actual Result", "Execution
# Status", "Linked Issue") -- all three are QA-typed directly into the
# sibling `.md` report in this project (there is no automation flow here to
# run a suite and write results back).

# --- XLSX "Document Version Control" sheet: (label, DocumentControlMeta
# attribute) pairs, in display order -- mirrors the fields
# test_plan_docx_writer._build_version_control shows for the Test Plan's own
# equivalent section, plus Prepared By/Date (shown on the Test Plan's cover
# page instead, since Excel has no separate cover). ---
DOCUMENT_CONTROL_FIELDS = [
    ("Document Title", "title"),
    ("Project ID", "project_id"),
    ("Document ID", "document_id"),
    ("Description", "description"),
    ("Version", "version"),
    ("Prepared By", "prepared_by"),
    ("Prepared Date", "prepared_date"),
    ("Approved Date", "approved_date"),
    ("Master Template ID", "master_template_id"),
]

# --- XLSX "Document Release History" sheet: same eight columns as the Test
# Plan's own Document Release History table. ---
RELEASE_HISTORY_COLUMNS = [
    "Version",
    "Date",
    "Author",
    "Reviewed By",
    "Reviewed On",
    "Approved By",
    "Approved On",
    "Reasons",
]
# Every column wraps -- even the short categorical ones, so a long name/
# date/version that doesn't fit the column width is never clipped.
RELEASE_HISTORY_WRAP_COLUMNS = set(RELEASE_HISTORY_COLUMNS)
# Short categorical columns read cleanly centered in a bordered table;
# Reasons is free text and stays left-aligned (still wrapped) for readability.
RELEASE_HISTORY_CENTER_COLUMNS = {
    "Version", "Date", "Author", "Reviewed By", "Reviewed On", "Approved By", "Approved On",
}
RELEASE_HISTORY_COLUMN_WIDTHS = {
    "Version": 10,
    "Date": 14,
    "Author": 18,
    "Reviewed By": 22,
    "Reviewed On": 14,
    "Approved By": 22,
    "Approved On": 14,
    "Reasons": 40,
}

_VERSION_CONTROL_LABEL_COL = AUDIT_LEFT_MARGIN_COLS + 1
_VERSION_CONTROL_VALUE_COL = _VERSION_CONTROL_LABEL_COL + 1
_VERSION_CONTROL_LABEL_LETTER = get_column_letter(_VERSION_CONTROL_LABEL_COL)
_VERSION_CONTROL_VALUE_LETTER = get_column_letter(_VERSION_CONTROL_VALUE_COL)

VERSION_CONTROL_COLUMN_WIDTHS = {
    _VERSION_CONTROL_LABEL_LETTER: 22,
    _VERSION_CONTROL_VALUE_LETTER: 55,
}
# Short, single-line values read cleanly centered in a bordered form;
# Description is the one field expected to be a full sentence, so it stays
# left-aligned for readability even though it also gets a border.
VERSION_CONTROL_CENTER_FIELDS = {
    "Document Title", "Project ID", "Document ID", "Version",
    "Prepared By", "Prepared Date", "Approved Date", "Master Template ID",
}


def _write_version_control_sheet(workbook: Workbook, document_control: DocumentControlMeta) -> None:
    write_version_control_sheet(
        workbook,
        document_control,
        fields=DOCUMENT_CONTROL_FIELDS,
        center_fields=VERSION_CONTROL_CENTER_FIELDS,
        label_width=VERSION_CONTROL_COLUMN_WIDTHS[_VERSION_CONTROL_LABEL_LETTER],
        value_width=VERSION_CONTROL_COLUMN_WIDTHS[_VERSION_CONTROL_VALUE_LETTER],
    )


def _write_release_history_sheet(
    workbook: Workbook, release_history: list[ReleaseHistoryEntry]
) -> None:
    write_release_history_sheet(
        workbook,
        build_release_history_rows(release_history),
        columns=RELEASE_HISTORY_COLUMNS,
        wrap_columns=RELEASE_HISTORY_WRAP_COLUMNS,
        column_widths=RELEASE_HISTORY_COLUMN_WIDTHS,
        center_columns=RELEASE_HISTORY_CENTER_COLUMNS,
    )


def _doc_name_from_input(input_path: Path) -> str:
    """`<doc-name>-test-cases.json` -> `<doc-name>`, per the
    test-case-output-structure skill's naming convention."""
    stem = input_path.stem
    return stem[: -len("-test-cases")] if stem.endswith("-test-cases") else stem


def build_rows(document: TestCaseDocument, *, folder: str) -> list[list[str]]:
    """CSV rows: one per test step -- see module docstring's Zephyr shape.
    `folder` is the doc-name (see module docstring's Folder column note)."""
    rows = []
    for tc in document.test_cases:
        steps = tc.steps or [None]
        for step in steps:
            rows.append(
                [
                    tc.tc_id,
                    tc.title,
                    tc.objective,
                    tc.preconditions,
                    tc.priority,
                    tc.req_id,
                    folder,
                    step.action if step else "",
                    step.test_data if step else "",
                    step.expected_result if step else "",
                ]
            )
    return rows


def _merge_steps(tc) -> tuple[str, str, str]:
    """Combine a test case's steps into three strings (Steps / Test Data /
    Expected Result), each line numbered with its real step_number so the
    three columns stay correlated when read side by side.

    `Steps` and `Expected Result` always carry one numbered line per step --
    every step has an action and an expected result by construction (the
    validator requires both non-empty). `Test Data` only includes a line for
    steps that actually specify data, still labelled with that step's real
    number (e.g. just "3. Role = Canvasser") -- a step without data
    contributes nothing, rather than a bare "4. " placeholder. If no step in
    the test case has any test data at all, the whole cell is left empty
    rather than a column of noise like "1. \\n2. \\n3. \\n4. ".
    """
    if not tc.steps:
        return "", "", ""
    steps_lines, expected_lines, data_lines = [], [], []
    for step in tc.steps:
        steps_lines.append(f"{step.step_number}. {step.action}")
        expected_lines.append(f"{step.step_number}. {step.expected_result}")
        if step.test_data.strip():
            data_lines.append(f"{step.step_number}. {step.test_data}")
    return "\n".join(steps_lines), "\n".join(data_lines), "\n".join(expected_lines)


def build_review_rows(
    document: TestCaseDocument,
    *,
    requirement_texts: dict[str, str],
    existing_tracking: dict[str, dict[str, str]] | None = None,
) -> list[list[str]]:
    """XLSX "Test Cases" rows: one per test case, steps merged -- see module
    docstring's human execution/review shape. Actual Result/Execution
    Status/Linked Issue are carried forward from `existing_tracking` (keyed
    by tc_id, read from the sibling `.md` report -- see
    `test_case_md_writer.load_existing_review_tracking`) when it already has
    them recorded -- either QA's own typed-in values, or (for Actual
    Result/Execution Status only) the post-test-run `execution_result_
    writer.py` patch -- so a regeneration never silently blanks execution
    history. A tc_id with no prior entry (brand new test case) gets today's
    untouched defaults."""
    existing_tracking = existing_tracking or {}
    rows = []
    for tc in document.test_cases:
        steps_text, data_text, expected_text = _merge_steps(tc)
        prior = existing_tracking.get(tc.tc_id, {})
        rows.append(
            [
                tc.req_id,
                requirement_texts.get(tc.req_id, ""),
                tc.tc_id,
                tc.title,
                tc.objective,
                tc.preconditions,
                tc.priority,
                tc.test_type,
                steps_text,
                data_text,
                expected_text,
                prior.get("Actual Result", ""),
                prior.get("Execution Status") or DEFAULT_EXECUTION_STATUS,
                prior.get("Linked Issue", ""),
            ]
        )
    return rows


def write_csv(rows: list[list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def write_xlsx(
    review_rows: list[list[str]],
    document_control: DocumentControlMeta,
    release_history: list[ReleaseHistoryEntry],
    path: Path,
) -> None:
    """Writes the three-sheet controlled-document workbook: "Document
    Version Control", "Document Release History", "Test Cases" (in that
    order -- opening the file shows the front matter first, the same as
    opening the Test Plan docx shows its cover page first)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)  # default blank sheet; we create our own three

    _write_version_control_sheet(workbook, document_control)
    _write_release_history_sheet(workbook, release_history)

    sheet = workbook.create_sheet("Test Cases")
    _populate_sheet(
        sheet,
        REVIEW_COLUMNS,
        review_rows,
        wrap_columns=REVIEW_WRAP_COLUMNS,
        column_widths=REVIEW_COLUMN_WIDTHS,
    )

    # Execution Status: a real dropdown, not just a text convention -- QA
    # ticks through Pass/Fail/Not Executed while running the test case.
    status_col = get_column_letter(REVIEW_COLUMNS.index("Execution Status") + 1)
    last_row = sheet.max_row
    if last_row >= 2:
        validation = DataValidation(
            type="list",
            formula1=f'"{",".join(EXECUTION_STATUS_OPTIONS)}"',
            allow_blank=True,
            showDropDown=False,  # openpyxl quirk: False is what actually shows the arrow.
        )
        sheet.add_data_validation(validation)
        validation.add(f"{status_col}2:{status_col}{last_row}")

    workbook.active = 0  # "Document Version Control" opens first, like a cover page
    workbook.save(path)


def export(
    input_path: Path,
    output_name: str,
    *,
    want_csv: bool = True,
    want_xlsx: bool = True,
) -> tuple[Path | None, Path | None]:
    """Generates whichever of the CSV/XLSX outputs `want_csv`/`want_xlsx`
    request (both by default, for backward compatibility with direct
    callers -- e.g. tests -- that don't care about the distinction). The
    `test-case-generator` agent calls this with only the flag(s) the user
    actually passed to `/generate-test-cases` (`--csv`, `--xlsx`, or both),
    since neither export is generated by default anymore -- only the JSON
    and the Markdown report (`test_case_md_writer.py`) always are. Returns
    `(csv_path, xlsx_path)`, with whichever wasn't requested left `None`."""
    if not input_path.is_file():
        raise SystemExit(f"Input test-cases JSON not found: {input_path}")

    doc_name = _doc_name_from_input(input_path)
    document = TestCaseDocument.from_dict(read_json(input_path))

    csv_path = None
    if want_csv:
        csv_rows = build_rows(document, folder=doc_name)
        csv_path = test_cases_csv_path(output_name)
        write_csv(csv_rows, csv_path)

    xlsx_path = None
    if want_xlsx:
        requirement_texts = load_requirement_texts(doc_name)
        xlsx_path = test_cases_xlsx_path(output_name)
        # Tracking's one true source is the sibling `.md` report, never the
        # xlsx itself -- see this module's own docstring.
        existing_tracking = test_case_md_writer.load_existing_review_tracking(test_cases_md_path(doc_name))
        review_rows = build_review_rows(
            document, requirement_texts=requirement_texts, existing_tracking=existing_tracking
        )

        current_tc_ids = {tc.tc_id for tc in document.test_cases}
        dropped = sorted(
            tc_id
            for tc_id, tracking in existing_tracking.items()
            if tc_id not in current_tc_ids and has_recorded_tracking_data(tracking)
        )
        if dropped:
            print(
                "Note: execution/QA tracking data (Actual Result/Execution "
                "Status/Linked Issue) for these test cases was discarded "
                "because they no longer exist in the regenerated test-cases "
                f"JSON: {', '.join(dropped)}"
            )

        write_xlsx(review_rows, document.document_control, document.release_history, xlsx_path)

    return csv_path, xlsx_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a test-cases JSON as a Zephyr-import-ready CSV and/or an Excel execution workbook."
    )
    parser.add_argument("--input", required=True, help="Path to the source *-test-cases.json file.")
    parser.add_argument(
        "--output-name", required=True, help="Output filename without extension (e.g. LinkGrid-test-cases)."
    )
    parser.add_argument("--csv", action="store_true", help="Generate the Zephyr-import CSV.")
    parser.add_argument("--xlsx", action="store_true", help="Generate the Excel execution workbook.")
    args = parser.parse_args()

    # Neither flag given -- direct/legacy CLI use, default to both (the same
    # default the `export()` function itself has for programmatic callers).
    want_csv, want_xlsx = (args.csv, args.xlsx) if (args.csv or args.xlsx) else (True, True)

    csv_path, xlsx_path = export(Path(args.input), args.output_name, want_csv=want_csv, want_xlsx=want_xlsx)
    if csv_path:
        print(str(csv_path))
    if xlsx_path:
        print(str(xlsx_path))


if __name__ == "__main__":
    main()
