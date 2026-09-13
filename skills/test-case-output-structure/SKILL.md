---
name: test-case-output-structure
description: Output file/JSON-shape conventions for the test-cases deliverable (JSON, Markdown report, Zephyr CSV, XLSX review workbook). Used only by the test-case-generator agent.
disable-model-invocation: true
---

# Test-case output structure

You author the **JSON only** (`TestCaseDocument` in
`orchestrator/models/test_case.py`). The `.md`, `.csv`, and `.xlsx` are
rendered from it by deterministic scripts — never hand-write or edit them.
Column layouts and formatting details live in `reference/rendering.md`; read
that only if you're debugging an export.

## Files (under `output/test-cases/`)

| File | When | Written by |
|---|---|---|
| `<doc-name>-test-cases.json` | always — source of truth | you |
| `<doc-name>-test-cases.md` | always — the human-review report | `generation.test_case_md_writer` |
| `<doc-name>-test-cases.csv` | opt-in `--csv` — strict Zephyr import, one row per step | `generation.zephyr_export` |
| `<doc-name>-test-cases.xlsx` | opt-in `--xlsx` — three-sheet human execution workbook | `generation.zephyr_export` |

The CSV and XLSX are **differently shaped**, not two copies of the same
table. There is deliberately no docx.

**Export-only mode**: re-running with only `--csv`/`--xlsx` when the JSON is
already current relative to the source analysis skips straight to
`zephyr_export`, passing only the flag(s) given — it never regenerates the
JSON or the Markdown report just because an extra format was requested. See
the agent's Mode selection for the mtime rule.

## JSON shape

`{"meta": {...}, "test_cases": [...], "not_covered": [...], "document_control": {...}, "release_history": [...]}`

- **`meta`** — `source_doc`, `version`, `generated_date`, `changelog` (one
  entry per run, naming the actual delta).
- **`test_cases[]`** — `tc_id` (`TC-001`, sequential), `req_id` (the
  requirement it traces to), `title`, `objective`, `test_type`, `priority`,
  `preconditions`, `steps[]` (`{step_number, action, expected_result,
  test_data}`, numbered `1..N` contiguously).
- **`not_covered[]`** — `{req_id, reason}` for every requirement whose
  `acceptance_criteria_status` is `Not Generated – Client Clarification
  Required`. A requirement never appears in both lists.
- **`document_control`** (`DocumentControlMeta` in `models/test_case.py`) —
  `title`, `project_id`, `document_id`, `description`, `prepared_by`,
  `prepared_date`, `approved_date`, `master_template_id`, `version`. Any
  field without a real value is `"TBD – Client/Project Input Required"`,
  never invented.
- **`release_history[]`** — `{version, date, author, reviewed_by,
  reviewed_on, approved_by, approved_on, reasons}`, the audit-facing
  sign-off record (distinct from `meta.changelog`, the informal delta
  narrative). `reasons` is a ≤120-character headline
  (`MAX_RELEASE_REASON_CHARS`), not a changelog.

## Content rules

- **`test_type`** is one of `Positive`, `Negative`, `Boundary`, `Edge`,
  `Permission`, `Integration`, `Security`, `Database`, `API` (see the
  framework skill). The first five apply to most requirements; the last four
  are conditional — only when the Acceptance Criteria (or
  `depends_on`/`related_to`) genuinely calls for that check, never padded on
  to cover the full list. Validation warns (never blocks) on other values,
  since a genuinely domain-specific type may be warranted.
- **`priority`** (`High`/`Medium`/`Low`) is *derived* from the requirement's
  stated `priority` (MoSCoW / P1–P4 / etc.) per the framework skill's
  Priority derivation section. There is no `overall_risk` field anywhere in
  this system — risk ratings were retired. Never fabricate one.
- **Never fabricate test data or business behaviour.** If the Acceptance
  Criteria didn't define a value, format, or rule, keep the wording general
  ("a valid registered email address") rather than inventing a concrete
  value the source never stated.
- **Atomic steps.** One user action paired with one specific, verifiable
  expected result. "Enter username and click login" is two steps. "Works
  correctly" is never an expected result.

## Cross-validation against the analysis JSON

- Every test case's `req_id` must exist in the sibling `-analysis.json`.
- Every requirement with status `Generated` or `Generated with Assumptions`
  needs at least one test case or an explicit `not_covered` entry.
- Every `Blocked` requirement appears in `not_covered`, never in
  `test_cases`.
- `validation.validate` also warns when the analysis JSON is newer than the
  test cases (stale coverage — consider re-running).

## Regeneration

Re-running on a document that already has a `-test-cases.json` is a
regeneration, not an overwrite: bump `meta.version` and **append** a
changelog entry naming what actually changed (typically that the underlying
analysis JSON changed). The `snapshot-output` PreToolUse hook preserves the
previous version to `history/<name>-v<version>.json`, and
`validate-output` / `validation.validate` enforce append-only changelog and
no-version-regression. `history/` is internal audit trail, never a client
deliverable.

The Markdown report is always regenerated alongside, carrying forward
whatever **Execution Status / Actual Result / Linked Issue** it already
records — **the `.md` is the one true source of those three fields**, not
the xlsx (which reads them back out of it). Never hand-edit the `.md` to
set them.

If a regenerated JSON drops a `tc_id` that had real (non-default) tracking
data, that data is discarded from the xlsx export with a printed note naming
exactly which `tc_id`(s) — never silently. Relay that note in your final
report when it appears.
