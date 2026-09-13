---
name: output-structure
description: Output file/JSON-shape conventions for the requirement-analysis deliverable (JSON, Markdown report, Word report, Client Clarification Sheet). Used only by the requirement-analyzer agent.
disable-model-invocation: true
---

# Requirement-analysis output structure

You author the **JSON only**. The `.md`/`.docx` reports and the
clarification sheet are rendered from it by deterministic scripts — never
hand-write or edit them. Layout/formatting details live in
`reference/rendering.md`; read that only if you're debugging a writer.

## Files (under `output/`)

| File | When |
|---|---|
| `requirement-analysis/<doc-name>-analysis.json` | always — source of truth, you write it |
| `requirement-analysis/<doc-name>-analysis.md` | always — `generation.md_report_writer` |
| `requirement-analysis/<doc-name>-analysis.docx` | opt-in `--docx` — `generation.docx_report_writer` |
| `client-clarifications/<doc-name>-clarifications.md` | always, but only from `/generate-clarification-sheet` |
| `client-clarifications/<doc-name>-clarifications.docx` | that command's opt-in `--docx` |

The clarification sheet is **not** a requirement-analyzer write-time
deliverable. Only `/apply-clarifications` regenerates an already-existing
sheet after applying answers.

## JSON shape

`{"meta": {...}, "requirements": [...], "document_control": {...}, "release_history": [...]}`

**`meta`** — `source_doc`, `domain` + `domain_evidence` (your stated
inference, carried forward so the test-plan agent doesn't re-derive it),
`version`, `generated_date`, `extraction_manifest` (sections processed,
requirements extracted, deliberate skips — the reviewer's proof nothing was
silently dropped), `changelog` (one entry per run, naming the actual delta),
`clarification_log` (`req_id`, `question`, `answer`, `date` per applied
answer — append-only, never deleted), and `executive_summary` / `in_scope` /
`out_of_scope` (plain narrative strings, may hold their own numbered
sub-points; never fabricated — `"TBD – To be added by QA"` if unpopulated).
Leave `nfr_analysis`/`compliance_analysis` empty — that content is now
itemized `requirements` entries.

**`requirements[]`** — `req_id`, `title` (short plain-English card heading,
e.g. `"Initial Login Interface"`), `category` (`"Functional"` |
`"Non-Functional"` | `"Compliance"` — decides which report section it renders
under), `requirement_text`, `source_ref` / `priority` / `sprint_or_phase`
(lifted from the document when stated, empty otherwise — never invented;
JSON-only, consumed by the test-plan agent), `source_file` (the vault-relative
path, from the enclosing `## Source: <relative path>` heading, this
requirement was extracted from — JSON-only, consumed by
`/apply-clarifications`' vault write-back to find which note to edit; empty
when unknown), `gaps[]` (`description`, `question`, `blocking`,
`source_excerpt` — the verbatim passage in `source_file` this gap's ambiguity
came from, character-for-character so it literal-matches later; empty for a
"missing information" gap with nothing to quote), `recommendations[]`
(`recommendation`, `reason`, `business_benefit`,
`client_confirmation_recommended`), `acceptance_criteria_status`,
`acceptance_criteria`, `depends_on`, `related_to`.

**`document_control`** (`DocumentControlMeta` in
`orchestrator/models/requirement.py`) — `title`, `project_id`, `document_id`,
`description`, `prepared_by`, `prepared_date`, `approved_date`,
`master_template_id`, `version`. Any field without a real value is
`"TBD – Client/Project Input Required"`, never invented.

**`release_history[]`** — `{version, date, author, reviewed_by, reviewed_on,
approved_by, approved_on, reasons}`, the audit-facing sign-off record
(distinct from `meta.changelog`, the informal content-delta narrative).
`reasons` is a ≤120-character headline (`MAX_RELEASE_REASON_CHARS`), not a
changelog.

## Exact strings

- No genuine gaps → `Gap: No significant gaps identified.` /
  `Client Question: None.` — verbatim, not a paraphrase.
- Unknown client/project fact → `"TBD – Client/Project Input Required"`.
- Unwritten QA narrative → `"TBD – To be added by QA"`.
- Statuses: `Generated` / `Generated with Assumptions` /
  `Not Generated – Client Clarification Required` / `Not Applicable`
  (Compliance-only). Never rename these — downstream agents key off the
  exact string.
- Never emit Gap IDs, Gap Types, Risk Scores, Business Impact, or Complexity
  anywhere. Retired.

## Revision control (mechanical, not trusted)

Re-analysis is a controlled revision: unchanged requirements carry forward
verbatim (no re-wording, no re-asking answered questions), `meta.version` is
bumped, and the changelog names what actually changed.

Before any output JSON is overwritten, the `snapshot-output` PreToolUse hook
copies it to a sibling `history/<name>-v<version>.json` (first capture of a
version wins). Validation then diffs your new file against that snapshot and
**errors** on: lost `changelog`/`clarification_log`/`release_history`
entries (all three are append-only), a version going backwards, a
carried-forward requirement churning without cause, a changelog that doesn't
name the real added/removed/changed IDs, and a gap question that re-asks
what `clarification_log` already answers. Same-version rewrites count as
in-run iteration — only the append-only invariants apply. `history/` is
internal audit trail, never a client deliverable.

`bash ./.qa-orchestrator validation.delta_report <doc-name>` gives an
advisory changed/missing/new signal before a delta re-analysis — advisory
only; you judge.

## Client Clarification Sheet contract

Columns: **Requirement ID | Requirement | Client Question | Client
Response** — one row per *open* question (two gaps → two rows; a requirement
with no gaps doesn't appear). Client Response is left blank for the client
to type into.

Round trip: the client (or QA) fills in Client Response →
`/apply-clarifications` ingests via `parsing.clarifications_from_md`,
falling back to `parsing.clarifications_from_docx` only when the `.md` has
zero answered rows and a `.docx` exists → answered gaps close, Acceptance
Criteria/status update, every answer is logged to `meta.clarification_log`
and remembered in clarification memory, then the report plus a fresh sheet
(holding only still-open questions) are regenerated. Where a gap carries a
`source_excerpt`, its originating vault note (`requirements[].source_file`)
is also rewritten in place — snapshotted first via
`parsing.vault_writeback snapshot` — so the requirement text itself, not
just the analysis, stops reading as ambiguous once the client answers.

The writer refuses to regenerate **either** file if an existing `.md` or
`.docx` holds client responses not yet in `meta.clarification_log`, so typed
answers can't be silently lost. `--force` overrides, on explicit user
request only.
