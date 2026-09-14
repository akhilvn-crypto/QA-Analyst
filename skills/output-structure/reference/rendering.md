# Requirement-analysis rendering details (maintainer reference)

Not loaded at runtime. The agent never authors the `.md`/`.docx` by hand —
`generation/md_report_writer.py` and `generation/docx_report_writer.py`
render both deterministically from the analysis JSON. This file records
*how* they render it, so the contract survives even though the agent
doesn't need it in context.

## Shared rendering

Both writers render the same content from the same JSON via shared helpers
(`docx_report_writer._format_gap_text` / `_format_question_text` /
`_format_recommendations_text` / `_req_sort_key`, imported by
`md_report_writer` rather than reimplemented) — the two human-facing
deliverables can never drift from each other or from the JSON.

`orchestrator/tests/test_md_report_writer.py` and
`orchestrator/tests/test_analysis_report_cover.py` pin every point below
(section headings and numbering, bold bullet field labels, category
grouping, the empty-category placeholder text) — a regression there is the
mechanical backstop for this contract, independent of any reference
`.md`/`.docx` file that may or may not exist on disk at any given time.

## Five numbered top-level sections

Identical in the docx and the Markdown report (content order matches
exactly; only the container differs where Markdown has no docx equivalent —
no cover page, page breaks, footers, or logos):

1. **Document Control & Metadata** (+ **1.1 Revision History**)
2. **Project Overview & Scope** — `meta.executive_summary` / `in_scope` /
   `out_of_scope`
3. **Functional Requirements Analysis & Acceptance Criteria** —
   `category: "Functional"`
4. **Non-Functional Requirements (NFR) Analysis** — `"Non-Functional"`
5. **Compliance & Regulatory Requirements Analysis** — `"Compliance"`

A category section with zero matching requirements still renders its
heading, followed by a plain "No … requirements were identified in this
document." line (`NO_CATEGORY_REQUIREMENTS_TEXT`) — never silently omitted,
the same "never omit, always say so" convention used project-wide. Sections
3/4/5 sort by Requirement ID ascending (`_req_sort_key` — numeric, not
lexicographic, so `REQ-2` sorts before `REQ-10`).

## Section 1 / 1.1

`docx_report_writer.py`'s `_build_document_control_section`, not to be
reimplemented ad hoc:

- Docx: Heading 1 "1. Document Control & Metadata", then every
  `DOCUMENT_CONTROL_FIELDS` pair as a row in a bold-key/plain-value table
  (`docx_helpers.add_key_value_table()` — the same shared helper the Test
  Plan's own Document Version Control section uses, so a controlled-document
  identification block reads as a table everywhere in this project, not as
  loose paragraphs): **Project Name** (`document_control.title`),
  **Project ID**, **Document ID**, **Description**, **Document Version**,
  **Prepared By**, **Date** (`prepared_date`), **Approved Date**,
  **Master Template ID**, **Classification**. `_add_field()` (bold-label
  paragraph + plain-value paragraph) is reserved for the Project Overview &
  Scope narrative and each requirement card's own fields — free-flowing
  prose fields, not a fixed controlled-document schema. Markdown renders the
  Document Control fields as a bullet list (`* **Label:** value`) — same
  content, no docx table equivalent needed for a flat key/value list.
- "1.1 Revision History" (Heading 2 in docx, `###` in Markdown) is a
  **six-column condensed view** of `release_history` — Version, Date,
  Description (`reasons`), Author, Reviewed By, Approved By — dropping
  Reviewed On/Approved On from this table only; the full eight-field entry
  is still what `release_history` stores in the JSON (see
  `ReleaseHistoryEntry` in `orchestrator/models/requirement.py`), nothing is
  lost from the source of truth. A real table in both reports
  (`docx_helpers.add_header_table()` / `md_table.build_table()`).
- A single italic summary line (`_build_summary_line()` — "Document: … |
  Generated: … | Total requirements: N | Total gaps identified: N |
  Acceptance Criteria: …") closes out section 1, right after the Revision
  History table. This replaced the old standalone "Analysis Summary"
  heading — the five-section layout has no room for a sixth top-level
  section just for counters.

## Section 2

A Heading 1, then three bold-label/plain-value (or bullet, in Markdown)
fields — **Executive Summary**, **In-Scope**, **Out-of-Scope** — holding
`meta.executive_summary`/`in_scope`/`out_of_scope` verbatim.

## Requirement cards (sections 3/4/5)

One full-width "card" per requirement, **not a table row**. Originally a
seven-column table, one row per requirement — reported as hard to read,
since seven columns on even a landscape page left free-text columns only
~1.5–2in wide, forcing heavy wrapping. Each requirement gets its own
section instead:

- A Heading 2/`###` holding `req_id: title` (e.g. `REQ-001: Initial Login
  Interface`) — falls back to the bare `req_id` when `title` is empty (a
  legacy analysis JSON predating that field).
- A **Status: `<display status>`** line directly under the heading, bold and
  color-coded green/amber/red/grey (`STATUS_COLORS`) — the *display* status
  (`_display_status()`), not the raw JSON value: `Generated` / `Generated
  with Assumptions` pass through unchanged, the JSON's longer `Not Generated
  – Client Clarification Required` displays as `Blocked`, and a
  Compliance-only `Not Applicable` displays unchanged. This is a
  **display-only mapping** — `acceptance_criteria_status` in the JSON is
  never renamed, so every other agent/validator keying off its exact string
  (e.g. `test-case-generation-framework`'s "only test what has Acceptance
  Criteria" rule) is unaffected.
- Then, as full-width labeled fields (bold label, value below it in docx via
  `_add_field()`; a bold Markdown bullet, inline for a single-line value or
  with nested sub-bullets for a multi-line one via `_bullet_field()`), in
  this order: **Requirement** → **Gap** → **Client Question** → **Acceptance
  Criteria** → **Recommendations**.
- Multiple gaps consolidate into one list inside the single Gap field rather
  than exploding into repeated sections — a requirement is one card, not one
  card per gap.
- Docx cards are separated by a thin horizontal rule (`add_bottom_border()`
  on an empty paragraph); Markdown cards need no separator beyond the next
  `###` heading (a new heading is the only card-boundary marker there — the
  same reasoning the docx's rule exists to replace; Markdown just has no
  equivalent primitive to reuse).
- **No forced page break per requirement (docx).** Cards flow naturally like
  the Test Plan's own sections — Word only starts a new page when content
  actually overflows. The label-before-value `keep_with_next` chaining
  (heading → status line → each field's label) is what prevents a label or
  heading from being stranded alone at the bottom of a page with its content
  pushed to the next one; it is *not* trying to keep an entire card
  together, since a card's own content (e.g. a long Acceptance Criteria) can
  legitimately run longer than one page and should keep flowing like
  ordinary document text.
- Word-wrap is automatic for a normal paragraph (nothing to configure);
  Calibri 12pt throughout. The footer's `Page n of N` text is 11pt.

## Docx-only affordances

**Portrait Letter, not landscape** — a single-column card layout reads more
naturally in portrait, and it's what the Test Plan already uses for the same
reason. Margins are a plain 1in on every side.

**Front matter, mirroring the Test Plan's own controlled-document
structure**: cover page (project logo centered, header logo top-right if
present, "Requirement Analysis Report" / "for" / the document title,
prepared by/date, pushed near the bottom of the page — see
`_build_cover_page()`'s own measured-not-estimated spacing note in the
source) → page break → section 1 → page break → section 2 → page break →
sections 3/4/5. Every page except the cover carries a `Page n of N` footer.

Markdown has no cover page (title is just `# Requirement Analysis Report`
immediately followed by section 1 — the document's own title/project ID live
inside section 1's "Project Name"/"Project ID" fields, not a separate
front-matter block) and uses a bare `---` between sections 1/2/3/4/5 instead
of a page break.

## Client Clarification Sheet rendering

`orchestrator/generation/clarification_sheet_writer.py`.

- The `.md` table mirrors the `.docx` table exactly — same four columns,
  same row order, and, like `md_report_writer`'s own tables, always rendered
  even with zero data rows (header-only) so it stays machine-readable for
  `clarifications_from_md` regardless of how many questions are currently
  open. Built via the shared `orchestrator.utils.md_table` helpers
  (`escape_cell`/`build_table`, also used by `md_report_writer`) — a cell's
  embedded newline becomes `<br>` and an embedded `|` is escaped to `\|`, so
  a free-text client answer can never be mistaken for a row/column boundary;
  `clarifications_from_md` reverses both escapes when reading a row back.
- The `.docx` table is landscape, fixed-width, with a repeating navy header
  and `cantSplit` rows, Calibri 12pt — deliberately kept as a table (unlike
  the analysis report above): four short, comparably-sized columns fit a
  landscape page without the many-narrow-columns problem the seven-column
  analysis table had, and a fillable grid is the natural shape for a form
  the client types answers into.

## Legacy tolerance

- Legacy bare-list JSONs (pre-`meta`) are still readable everywhere; the next
  analysis run upgrades them to the meta shape.
- A `-analysis.json` written before `document_control`/`release_history`
  existed reads back fine (both default empty) — validation warns rather
  than errors on the empty case, and the next analysis run populates them.
- A legacy JSON predating `category` reads back with every requirement
  defaulting to `"Functional"`.
- `meta.nfr_analysis` / `meta.compliance_analysis` were once single
  document-level narratives naming which NFR categories / compliance
  frameworks a document addressed. That content now lives as individual
  categorized `requirements` entries. Both fields are still read tolerantly
  (a legacy analysis JSON with narrative text there but no categorized
  requirements continues to validate); a current run leaves them empty.

## Render smoke test

Every run of `docx_report_writer` is followed by an automatic PostToolUse
render check (the `format-report` hook) that converts the `.docx` to
PDF/JPEG via Word COM automation (this system only runs on Windows machines
with Word installed) to confirm it paginates cleanly, then discards the temp
render. Smoke test only — it never changes formatting.
