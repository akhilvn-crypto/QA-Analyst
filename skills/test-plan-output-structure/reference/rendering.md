# Test Plan rendering details (maintainer reference)

Not loaded at runtime. `generation/test_plan_md_writer.py` and
`generation/test_plan_docx_writer.py` render both reports deterministically
from the Test Plan JSON; the agent never authors them by hand. This file
records how, so the contract survives out of the runtime prompt.

## md ↔ docx correspondence

Both render the same content from the same JSON — same section order, same
field values. The container differs only where Markdown has no docx
equivalent (no cover page, page breaks, footers, Table of Contents, or
logos). See `test_plan_md_writer.py`'s own docstring for the exact
correspondence to `test_plan_docx_writer.py`'s section builders.

## No automatic PDF export

Deliberate. A freshly generated Test Plan typically still has `TBD` fields
QA fills in by hand, so freezing it as a PDF at generation time would
capture a draft, not a finished document. QA exports a PDF themselves
(Word's Save As) once the document is finalized.

## Section structure origin

Originally derived from an Emvigo client Test Plan template, now fully
encoded in `test_plan_docx_writer.py` — there is no reference file to
consult. Extended with a Table of Contents and a closing Approval &
Sign-off section (both additive, not part of the original template, but
standard for a controlled/audit-ready document).

## Pagination

Sections flow naturally — Word fills each page with as much content as fits
and only starts a new page when content actually overflows. Do **not** add a
blanket "every Heading 1 starts a fresh page" rule, and do not add a forced
break to any *new* section without a specific structural reason: a forced
break reliably leaves a block of wasted empty space on whatever page
precedes it whenever that section's predecessor doesn't happen to fill the
page exactly. (A short "Assumptions, Dependencies & Risks" forced onto its
own page left the rest of the preceding page blank before "Test
Strategy/Methods"; "Approval & Sign-off" forced onto its own page left the
tail of "Test Closure"'s page blank the same way. Both were bugs, not "the
design", and both were fixed by removing the forced break, not by trimming
content.)

Exactly **three** page breaks are explicit, each a one-time structural
necessity — a closed list, not a pattern to extend:

1. cover → Table of Contents
2. Table of Contents → "A. Document Version Control" (the ToC page has no
   natural successor heading to break on)
3. Version Control/Release History front matter → "Introduction" (the
   document-control pair is deliberately isolated on its own page —
   substantive Test Plan content never shares a page with it; this is the
   one place a reader has said the resulting blank space is acceptable,
   precisely because it's front matter, not content)

"A. Document Version Control" and "B. Document Release History" are
back-to-back with no break between them — both are short front-matter tables
that read as one unit. Every other heading, including "Approval &
Sign-off", has no forced break. Every heading level (1–4) carries
`keep_with_next` so natural flow can never strand a heading alone at the
bottom of a page with its content pushed to the next one — that is what
keeps natural flow from looking broken without forcing artificial page
breaks everywhere.

## Cover page and footers

A4 portrait. `config/branding/header-logo.png` right-aligned in
the first-page header (cover page only — interior pages carry no header),
`config/branding/project-logo.png` centered on the cover body, "Test
Plan for `<title>`", Project ID line, left-aligned prepared-by/date block.

Non-cover page footers carry "Confidential – Internal / Client Use Only"
(left-aligned, small italic gray) above `Version <version>    Page <n> of
<N>` (right-aligned) using live Word page-number fields, not literal
numbers. The classification line is fixed regardless of project and is
orthogonal to the `TBD` markers.

## Table of Contents

A real Word `TOC` field (`\o "1-4" \h \z \u`, covering Heading 1–4), not a
hand-built list of section names — it must stay accurate if a heading's text
or page changes. After saving, `write_report()` reopens the file via Word
COM automation (`_bake_live_fields`) and calls `Fields.Update()` /
`TablesOfContents.Update()` before resaving, so the ToC and the
PAGE/NUMPAGES footer fields already carry correct computed values the moment
a client opens the file. This does not depend on the reader's Word having
"update fields on open", and does not depend on the `format-report` hook
(a read-only verification pass against a temp PDF/JPEG render that never
writes back to the delivered `.docx`). Field codes are preserved, so the
document stays live/updateable if edited later.

## Approval & Sign-off

The document's final section: a Role / Name / Signature / Date table
(Prepared By (QA), Reviewed By, Approved By) with blank Signature/Date cells
and `TBD – Client/Project Input Required` Name cells. It cannot be
pre-filled at generation time, but its presence is what makes the document
auditable as a controlled artifact.

## docx formatting

Enforced in `test_plan_docx_writer.py` and the shared helpers in
`orchestrator/utils/docx_helpers.py` — not to be reimplemented ad hoc.

- A4 page size, 0.8in left/right margins, 0.9in top/bottom — narrower than a
  typical prose document on purpose: this document is table-heavy, and the
  reclaimed width is what keeps tables legible rather than cramped.
- Tables use the `Table Grid` style with fixed column widths (every table's
  widths sum to ~6.6in, just under the ~6.67in usable width — never let a
  table exceed the usable width; Word will not auto-shrink a fixed-layout
  table that overflows), bold white-on-navy (`1F3864`) header rows repeated
  on every page, non-zero cell padding via `set_table_cell_margins` (Word's
  default is near zero, which is what makes an unpadded table read as
  "compressed"), and a minimum row height via `set_min_row_height`.
- Every row gets `set_row_cant_split` (a row never divides mid-row across a
  page break — the whole row moves), and header-row cells additionally get
  `paragraph_format.keep_with_next = True` (glues the header to the first
  data row). Without both, a table landing near a page boundary shows what
  looks like a duplicated header — a real, reported defect. Don't drop this
  when touching table-building code.
- Table body text is 10.5pt. The one 8-column table (Document Release
  History) uses 9.5pt with tighter 4pt cell padding instead of the usual 6pt
  — at 8 columns even the widened page can't give every column comfortable
  room at normal size/padding. A header word wrapping mid-word (e.g.
  "Versio-n") is the tell that a column needs more room, smaller text, or
  both.
- Bulleted lists use built-in `List Bullet` / `List Bullet 2` styles for two
  levels of nesting (functional area → sub-item).
- Calibri throughout; Title 18pt, Heading 1 14pt, Heading 2 13pt, Heading 3
  12pt, Heading 4 11pt (all bold, navy `1F3864`), body 11pt. The `Title`
  style's default bottom paragraph border (a python-docx built-in-template
  artifact, not a design choice) is stripped — the cover page must never
  show stray rules under "Test Plan" / the project title.

Any low-level docx helper both `docx_report_writer.py` and
`test_plan_docx_writer.py` need lives in `orchestrator/utils/docx_helpers.py`
— do not duplicate cell-styling/shading/column-width logic between them.

## Why `release_history.reasons` is capped at 120 chars

`MAX_RELEASE_REASON_CHARS` in `orchestrator/models/test_plan.py`. It is the
eighth column of an eight-column table, ~1.5in wide. Past that length the
row grows taller than the page — the cell text overruns the footer and
neighbouring columns are starved until words break mid-word (`Emvigo
Technologie|s`). Observed defect: a 1084-character entry turned a two-row
table into three pages. Validation warns (never blocks — an over-long reason
is an ugly document, not a wrong one). The detail belongs in the sections
that actually changed; QA can expand a specific entry by hand in Word where
a revision genuinely warrants it.

## Render smoke test

Every `test_plan_docx_writer` run is followed by the same automatic
PostToolUse `format-report` hook used for the requirement-analysis report —
converts the `.docx` to PDF/JPEG via Word COM automation to confirm it
paginates cleanly, then discards the temp render. Smoke test only; never
changes formatting.
