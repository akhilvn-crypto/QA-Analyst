# Test-case export rendering details (maintainer reference)

Not loaded at runtime. `generation/test_case_md_writer.py` and
`generation/zephyr_export.py` render every human-facing artifact
deterministically from the test-case JSON — `zephyr_export.py` never
re-derives content, it only reshapes what the agent already wrote. This file
records how, so the contract survives out of the runtime prompt.

## Why no docx

Deliberate. The always-on Markdown report already serves human review,
Zephyr consumes the CSV directly, and the `.xlsx` already serves human
execution — a fourth, differently-formatted document would be redundant.

## CSV shape (strict Zephyr import)

`COLUMNS`: `Test Case Key | Test Case Name | Objective | Precondition |
Priority | Labels | Folder | Step | Test Data | Expected Result` — one row
**per test step**. `Test Case Key` (the `tc_id`), `Labels` (the `req_id`, so
traceability survives the Zephyr import as a searchable label), and `Folder`
(the doc-name — the meaningful grouping unit within a single-project
workspace) repeat on every step row belonging to that test case. Must not
change without a real Zephyr import requirement driving it.

A raw `.csv` cannot carry any cell formatting at all — wrap text, column
width, and row height are not concepts a plain-text CSV can express;
whatever program opens it applies its own default view. Hard limitation of
the format, not a defect. (There was briefly a second "Zephyr CSV Preview"
sheet in the `.xlsx` mirroring the CSV's content with formatting applied;
removed on request. The `.csv` remains the sole artifact for that shape.)

## XLSX shape (three-sheet controlled-document workbook)

Mirrors the Test Plan's own version-control/release-history structure — a
test-case suite is just as much an ISO-audit-relevant artifact. Written in
this order (the workbook opens on the first sheet, like a Test Plan docx
opens on its cover page):

1. **"Document Version Control"** — a key-value layout of every
   `document_control` field (`DOCUMENT_CONTROL_FIELDS`: Document Title,
   Project ID, Document ID, Description, Version, Prepared By, Prepared
   Date, Approved Date, Master Template ID), with the project logo
   (`Branding/project-logo.png` in the attached folder, via
   `orchestrator.utils.paths.project_logo_path()` — the plugin ships no
   bundled fallback) embedded above it — the same asset the Test Plan cover
   page uses. A missing logo file is a no-op, not a failure.
2. **"Document Release History"** — one row per `release_history` entry:
   `Version | Date | Author | Reviewed By | Reviewed On | Approved By |
   Approved On | Reasons` — identical columns to the Test Plan's own table.
3. **"Test Cases"** (`REVIEW_COLUMNS`): `Requirement ID | Requirement | Test
   Case Key | Test Case Name | Objective | Precondition | Priority | Test
   Type | Steps | Test Data | Expected Result | Actual Result | Execution
   Status` — ordered so the requirement is read first and the test case that
   traces to it follows immediately. One row **per test case**: all of a
   test case's steps merge into a single numbered, newline-joined cell per
   column (`Steps`, `Test Data`, `Expected Result` share the same
   `1.`/`2.`/… numbering so they stay readable in parallel), so a whole test
   case reads as one row instead of scattering across several.
   `Requirement` holds the full `requirement_text` looked up from the
   sibling `-analysis.json` (best-effort — if that file is missing the
   column is left blank, never a fabricated value).

**One `Test Cases` sheet, not one-per-test-type.** Splitting
`Security`/`Database`/`Integration` into separate sheets or files would let
the same data drift out of sync across copies on the next regeneration.
Instead every header cell on every tabular sheet carries a real Excel
AutoFilter (`sheet.auto_filter`), so a reviewer narrows to e.g. `Test Type =
Security` with the column's dropdown, without the data existing in more than
one place.

### Tracking fields

`Execution Status` is a real Excel dropdown (`Pass` / `Fail` / `Not
Executed`, defaulting to `Not Executed`). It and `Actual Result` start blank
on first export and are **not static after that** — but the xlsx is never
where they're recorded. The Markdown report is the one true source; the xlsx
picks the values up the next time `--xlsx` regenerates it, by reading them
back out of the `.md` (`zephyr_export.py` calling
`test_case_md_writer.load_existing_review_tracking`). It is a downstream
render, not a second place these fields live.

This project's own scope ends at test-case generation — there is no
automation flow here to run a suite and write these fields back. All three
tracking fields (`Execution Status`, `Actual Result`, `Linked Issue`) are
QA-typed by hand directly into the Markdown report's bullets, and the xlsx
renders whatever it finds there. A separate automation project consuming
these test cases may populate them the same way (editing the same `.md`
bullets); `test_case_md_writer.write_report`'s `overrides` parameter exists
for exactly that kind of external write-back, but nothing in this project
calls it.

### Borders and centering — scoped to the two audit sheets only

`Document Version Control` and `Document Release History` both get a thin
border on every cell (`THIN_BORDER`/`_apply_borders()`) and a real blank
margin before the table starts (`AUDIT_LEFT_MARGIN_COLS`,
`AUDIT_TOP_MARGIN_ROWS`) — both headers start well past the A1 corner
(row/column offsets via `_populate_sheet`'s `start_row`/`start_col`, and
equivalent literals in `_write_version_control_sheet`).

**That margin is the actual centering mechanism.** Two earlier attempts
didn't work and were removed: (1) `print_options.horizontalCentered` alone
only affects the printed/PDF page — Excel's default "Normal" view has no
page concept, so nothing changed on screen; (2) adding `sheet_view.view =
"pageLayout"` on top still repositioned nothing, because "centered" content
that already fills the entire print area has no spare width to shift into.
Only real blank rows/columns before a table move it away from the sheet's
corner — which is what "centered" concretely means for a table with no
natural right/bottom edge to balance against.

Short categorical values (`VERSION_CONTROL_CENTER_FIELDS`;
`RELEASE_HISTORY_CENTER_COLUMNS` — every column except `Reasons`) are
horizontal-centered *within their own cells* as a separate, smaller touch;
free text (`Description`, `Reasons`) stays left-aligned. **Every cell in
both sheets wraps** — header, label, and value cells alike
(`RELEASE_HISTORY_WRAP_COLUMNS` covers all eight Release History columns,
not just `Reasons`; every Version Control label and value cell sets
`wrap_text=True`) — so a long name, date, or ID is never clipped.

The working `Test Cases` sheet deliberately keeps none of this (margin,
border, or universal wrap) — this was a request about the two front-matter
sheets specifically, and a 15-column data table with every cell wrapped
would make rows unpredictably tall for columns that are short-text by design
(e.g. `Priority`).

### Logo anchoring

The logo is genuinely centered, not anchored to a fixed cell. Anchoring an
image at a cell string (e.g. `"D2"`) left-aligns it to that cell's corner —
it's a floating object, not cell content, so centering requires computing
where its centered left edge falls across the table's own column span
(wherever `AUDIT_LEFT_MARGIN_COLS` currently places it) and expressing that
as a `(column, pixel-offset)` pair (`_column_width_to_px()` /
`_centered_image_anchor()`, using the standard ECMA-376 width-to-pixel
approximation), then building a `OneCellAnchor` directly rather than passing
a cell-reference string.

### Row height

Computed per row from the tallest wrap-enabled column it holds (estimated
wrapped-line count from both actual `\n` breaks and word-wrap at the
column's width), not just from `Steps` — a long `Requirement`/`Objective`
sentence with no embedded newline still needs the row tall enough to show it
without clipping. Applies to both the `Test Cases` and `Document Release
History` sheets via the shared `_populate_sheet()` helper.

### Test Data line omission

`_merge_steps()` only emits a `Test Data` line (still labelled with that
step's real number, e.g. `"3. Role = Canvasser"`) for steps that actually
specify data; if no step in the test case has any, the whole cell is left
blank. A column reading `"1. \n2. \n3. \n4. "` was a real reported defect —
numbered emptiness that looked like missing data, not the absence of data.

## Markdown report

`test_case_md_writer.py` renders the Document Version Control/Release
History fields, every test case with its requirement, type, priority,
objective, preconditions, and numbered steps, its three tracking fields
(Execution Status, Actual Result, Linked Issue), and the Not Covered list.

Nowhere does it print a requirement ID on its own. A test case's
`Requirement` field reads `<REQ-ID> — <requirement text>`, and the Not
Covered table carries a `Requirement` column between the ID and the Reason
— both fed by `test_case_tracking.load_requirement_texts` (the sibling
`-analysis.json`'s `requirement_text`, falling back to its `title`).
Best-effort as ever: an id that lookup can't resolve degrades to the bare
id / a blank cell rather than failing the report.

A regeneration reads the tracking fields back from this same `.md` via
`load_existing_review_tracking` and merges them forward (`write_report`), so
a regeneration can never silently blank recorded execution data. The xlsx
inherits that protection for free, since `zephyr_export.py` reads its
carried-forward tracking straight from the `.md` rather than from any xlsx
it previously wrote.

Snapshot/validation hook protection is **JSON-only** — the sibling
`.md`/`.csv`/`.xlsx` are never matched by either hook (both key strictly on
`...-test-cases.json`). The `.md`'s merge-preserve logic is its equivalent
protection.

## Legacy tolerance

A `-test-cases.json` written before `document_control`/`release_history`
existed reads back fine (both default empty) — validation warns rather than
errors on the empty case, and the next regeneration populates them for real,
the same tolerance the analysis JSON gives a pre-`meta` bare list.
