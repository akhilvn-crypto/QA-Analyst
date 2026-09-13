---
name: test-plan-output-structure
description: Output file/section-structure conventions for the Test Plan deliverable (JSON + Markdown report + optional Word document). Used only by the test-plan-generator agent.
disable-model-invocation: true
---

# Test Plan output structure

You author the **JSON only** (`TestPlan` in
`orchestrator/models/test_plan.py`). The `.md`/`.docx` are rendered from it
by deterministic scripts — never hand-write or edit them. Layout,
pagination, and docx formatting details live in `reference/rendering.md`;
read that only if you're debugging a writer.

## Files (under `output/test-plan/`)

| File | When |
|---|---|
| `<doc-name>-test-plan.json` | always — source of truth, you write it |
| `<doc-name>-test-plan.md` | always — `generation.test_plan_md_writer` |
| `<doc-name>-test-plan.docx` | opt-in `--docx` — `generation.test_plan_docx_writer` |

The `.md` is what a reviewer reads before `/handoff-test-plan` copies it
unchanged to `requirementHandoff.obsidianDestinationPath`.

## Section order (fixed)

cover page → Table of Contents → **A. Document Version Control** → **B.
Document Release History** → **Introduction** (Purpose, Project Overview,
Scope of testing, Reference Documents) → **Resource Requirement for Tests**
(Team Members, Roles & Responsibilities Matrix, Orientation/Training Plan,
Inputs Needed, Test Environment Needed) → **Assumptions, Dependencies &
Risks** → **Test Strategy/Methods** (Overall Strategy, Integration Strategy,
Sequence & Criteria, Entry/Exit/Acceptance Criteria) → **Test Schedule** →
**Test Deliverables** → **Test Closure** → **Approval & Sign-off**.

Never reorder, rename, or drop a top-level section. A section with no
content for a given project still renders its heading with an honest
`TBD – Client/Project Input Required` or an empty table — never an
omission, so every generated Test Plan has a predictable, comparable shape
across projects.

## Never invent

Resource names, dates, environment specifics, and document locations the
source material doesn't support are `TBD` — see the test-plan-framework
skill's "Two kinds of TBD" (`TBD – Client/Project Input Required` for
client-owed facts, `TBD – To be added by QA` for QA-owned artifact
locations, e.g. Reference Documents and Test Deliverables). A field left as
one of these is correct output, not a missing feature. Neither is ever this
system's own workspace-relative path (`output/...`, `knowledge-base/...`) —
that means nothing to a client reading the deliverable.

## Revision control

Running against a document that already has a `-test-plan.json` is a
revision, not a fresh document: bump `meta.version` and **append** a
`release_history` entry naming what changed (never replace prior entries).
`release_history.reasons` is a one-line headline capped at 120 characters
(`MAX_RELEASE_REASON_CHARS`) — validation warns past that; detail belongs in
the sections that actually changed.

The `snapshot-output` PreToolUse hook preserves the previous JSON to
`history/<name>-v<version>.json` before overwrite, and validation diffs new
against previous: `release_history` is append-only (losing an entry is an
error) and `meta.version` never goes backwards. `history/` is internal audit
trail, never a client deliverable.
