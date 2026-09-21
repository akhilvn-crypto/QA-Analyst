---
name: test-plan-framework
description: Domain-agnostic framework for deriving a Test Plan (scope, strategy, entry/exit criteria, schedule) from analyzed requirements, including the TBD discipline for facts no requirement document can supply. Used only by the test-plan-generator agent.
disable-model-invocation: true
---

# Test Plan Framework

*What content* goes into a Test Plan. The section order and the docx/md
layout belong to the test-plan-output-structure skill; formatting is owned
by `generation/test_plan_docx_writer.py`.

Domain-agnostic — the same rules apply to a mobile app, a backend service,
or an internal tool. Domain inference and domain knowledge reasoning are
**not** duplicated here: read the `requirement-analysis-framework` skill's
sections on both first; everything below assumes the domain is already
inferred that way.

**Never invent project-specific facts** (people, dates, environments, tool
names, document locations) the source material doesn't state. An honest
`TBD – Client/Project Input Required` is more useful and more trustworthy
than a plausible-sounding invented name or date.

## Inputs (in priority order)

1. **The requirement-analysis JSON**
   (`output/requirement-analysis/<doc-name>-analysis.json`) if it exists —
   the vetted, gap-checked requirement set and richest source. Read every
   requirement's `requirement_text`, `acceptance_criteria_status`, `gaps`,
   `recommendations`.
2. **The combined requirement source markdown**
   (`output/requirement-analysis/<doc-name>-source.md`) for scope wording,
   stated timelines/releases, and project context lost in extraction
   (explicit in/out-of-scope statements, sprint plans). Fetch it yourself
   via `bash "$HOME/.qa-analyst/run.sh" parsing.reading_vault_fetch` if absent —
   don't assume it's been run this session.
3. **User-supplied extra instructions** passed with the command (resource
   names, environment details, target dates) — these always beat anything
   you'd otherwise mark TBD.

No analysis JSON yet? Don't block — proceed from the markdown alone and note
in your response that `/analyse-requirement` first would sharpen scope and
surface pending clarifications.

If the analysis JSON has a `meta` block, reuse its recorded
`domain`/`domain_evidence` instead of re-inferring, and read
`meta.clarification_log` — an answered clarification is a confirmed fact,
not an assumption.

**Staleness check:** if the requirement source is newer than the analysis
JSON, the analysis may be out of date — say so to the user *and* reflect it
as a Risk in the plan (validation warns too). Never silently build on an
analysis of an older document version.

### Recommendations are context, not scope

A recommendation from the analysis is optional by that agent's own rules and
was never confirmed by the client. **Never fold an unconfirmed
recommendation into In Scope, Non-functional testing, or any other section**
as if it were accepted — that lets a suggestion quietly become a commitment.
Where one is genuinely relevant to test planning (e.g. it points at a
non-functional risk worth testing regardless of adoption), reflect it in
Assumptions or Risks, named as an open recommendation pending client
confirmation.

Check every recommendation with `client_confirmation_recommended: true` —
that flag is only set when the recommendation could change scope or cost,
which is exactly what makes it worth a client-facing mention. "Don't fold it
into scope" must not become "don't mention it at all": a `true`-flagged
recommendation belongs somewhere in Assumptions (e.g. "Patient SMS-consent
capture has been recommended but not yet confirmed by the client; if
adopted, testing scope would need to include it") even when nothing else
about the plan changes. `false`-flagged ones are lower-stakes — most simply
not appearing is expected.

### Pending clarifications

A requirement with `acceptance_criteria_status: Not Generated – Client
Clarification Required` isn't safe to commit to a schedule. Don't silently
drop it, don't silently include it:

- Name its requirement ID(s) in **Assumptions** or **Risks** (a schedule
  assumption if it should resolve soon, a risk if it threatens the
  timeline), stating it's pending client clarification.
- Write no Test Schedule row or Entry Criterion that assumes its resolution.

## Two kinds of TBD

Not every unknown belongs to the client. Use the marker that names who owns
filling it in:

- **`TBD – Client/Project Input Required`** — a fact only the client or
  project stakeholders can supply: team members, an environment detail, a
  real target date. Use it whenever you'd otherwise invent a name, date, or
  specific tool/vendor.
- **`TBD – To be added by QA`** — a pointer to an artifact QA itself
  produces or locates as the engagement progresses: where a reference
  document lives, where a test-case repository or bug-analysis report will
  be stored.

**Never substitute one of this system's own internal paths** (`output/…`,
`knowledge-base/…`) as a stand-in for a real external reference — they're
meaningless outside this system and have no place in a client-facing
deliverable. Without a real external location, mark it `TBD – To be added by
QA`.

## Scope of Testing

- **In Scope** — group requirements into functional areas the way a QA lead
  would organize a test plan (not necessarily the document's literal
  structure): one `ScopeArea` per area, with concrete capabilities as items,
  drawn only from what the requirements actually describe. Populate each
  area's `req_ids` (JSON-only, not rendered). Every non-blocked requirement
  must land in **exactly one** area — validation checks this mechanically.
  Requirements pending clarification go to Assumptions/Risks instead. The
  analysis JSON's `sprint_or_phase`/`source_ref` often mirror how the client
  already thinks about the system's areas — use them.
- **Non-functional testing** — only the categories (performance, security,
  compatibility, localization…) the requirements or domain reasoning
  actually support. Don't pad with a boilerplate list. If the requirement
  set says nothing, listing only the cross-domain baseline (basic
  performance sanity, basic security sanity) and noting scope is otherwise
  unconfirmed is the right answer.
- **Out of Scope** — what the document explicitly excludes or defers ("Phase
  2", "not in this release"), plus what the requirement set's own boundaries
  reasonably imply. Never invent exclusions; an empty list is fine and
  better than guesses.
- **Reference Documents** — name the `process_element` for each real
  reference category the project material implies (the source requirement
  document, a PRD, a design/Figma reference, a sprint/Jira board, a risk
  register — only those that genuinely exist here, not a fixed list). The
  `reference` value (where it actually lives) is almost never knowable from
  requirement material, so it's `TBD – To be added by QA`.

## Resources, Environment, and Schedule

These are project logistics a requirement document almost never states.
Uniform rule:

1. User supplied it → use it.
2. Source material states it → use it.
3. Domain reasoning gives a well-established convention → state it as a
   reasonable inclusion, not a fabricated specific. ("Android/iOS test
   devices covering the minimum supported OS versions stated in the
   requirements" is fine; a named brand of test device, or a real person's
   name, is not.)
4. Otherwise → literally `TBD – Client/Project Input Required`.

Schedule dates follow the same rule — only dates that are stated or clearly
derivable ("3 sprints of 2 weeks starting <date>"). But **structure is not
dates**: when requirements carry `sprint_or_phase` tags, produce one
schedule row per sprint/phase with its scope attached and only the *date*
columns TBD — a QA lead then fills in dates in minutes instead of rebuilding
the schedule's shape. Only when no timing or phasing information exists
anywhere should the schedule collapse to a single all-TBD row.

## Assumptions, Dependencies, Risks

- **Assumptions** — from domain reasoning applied to what's silent in the
  requirements (the same "conventional defaults" reasoning
  `requirement-analysis-framework` uses at requirement level, applied at
  project level), plus pending-clarification requirements.
- **Dependencies** — what testing genuinely cannot start without: stable
  builds, environment access, external integrations/sandboxes the
  requirements mention, test data. No generic dependencies that don't apply.
- **Risks** — what could plausibly threaten coverage or timeline given this
  domain and requirement set: ambiguity clusters, externally-dependent
  integrations, tight or unstated timelines, pending clarifications. Every
  risk traceable to something specific about *this* project, never
  boilerplate. **Order most severe/likely-to-derail first**, not in source
  order — and when one is clearly more urgent (it could block the schedule,
  versus merely inconvenient), say so explicitly rather than leaving the
  reader to infer priority from list order.

## Test Strategy

- **Overall strategy** — state a methodology only if the source material
  evidences it (sprint/Jira/Agile language implies Scrum-based testing) or
  the user supplied it. If genuinely unstated, describe a straightforward
  requirement-driven manual test cycle rather than asserting an
  Agile/Waterfall methodology nothing supports.
- **Integration strategy / key areas / sequence** — derive directly from the
  `depends_on`/`related_to` interconnections in the analysis JSON; that's
  exactly what those fields are for. Group and sequence by those
  relationships, not guesswork.
- **Never list a bare requirement ID.** Every `integration_sequence` item is
  `<REQ-ID> – <what that requirement is>`, taking the wording from that
  requirement's `title` in the analysis JSON (condense `requirement_text` to
  a short phrase only when there's no usable title). A client reading
  `- REQ-021` learns nothing; `- REQ-021 – Checkout information capture`
  tells them what the stage actually covers. Same rule anywhere else the
  plan's prose enumerates IDs for a reader.
- **Entry / Exit / Acceptance Criteria** (for the overall effort, not
  per-requirement) — standard QA practice as the *shape*, not the content;
  tailor the wording to this domain and requirement set rather than pasting:
  - Entry: stable build, required environment/test data ready, prerequisite
    requirements resolved (no blocking clarifications open).
  - Exit: planned test cases executed, no open critical/high defects,
    requirements' individual Acceptance Criteria satisfied.
  - Acceptance: functionality matches documented business rules, workflows
    stable, no unresolved high-severity issues.

## Test Deliverables and Test Closure

- Deliverables' `location` cells name QA-produced artifacts (test-case
  repositories, execution logs, bug-analysis reports, release notes) QA
  stores somewhere once underway — the client isn't supplying these. Name a
  real location only if already known; otherwise `TBD – To be added by QA`,
  never an internal system path.
- Closure criteria (sprint-level and release-level) restate the Exit/
  Acceptance Criteria above as closure checkpoints — not reinvented.

## Final consistency review

Before writing the JSON, review your own drafted `TestPlan` content — not
the source material again:

- Does every unknown use the correct TBD marker, and does none of them leak
  an internal `output/…` or `knowledge-base/…` path?
- Is every Integration Strategy/Sequence entry traceable to a real
  `depends_on`/`related_to` relationship, not invented to fill the section?
- Does every Integration Sequence item carry its requirement description
  next to the ID, rather than standing as a bare `REQ-0xx`?
- Does every scope area carry its `req_ids`, does every non-blocked
  requirement appear in exactly one area, and does no `req_ids` entry name a
  requirement that doesn't exist in the analysis?
- Does every `Not Generated – Client Clarification Required` requirement
  appear in Assumptions or Risks, and is it excluded from any Entry Criterion
  or Schedule row that assumes it's resolved?
- On a regeneration: does `release_history` still contain every prior entry
  with the new one appended (never replacing), and does its `reasons` name
  the actual delta rather than a vague "updated test plan"?
- Is that `reasons` one short line (**≤120 characters**)? It renders in a
  ~1.5in column of an eight-column table, where a longer value makes the row
  taller than the page and breaks neighbouring columns mid-word. Headline
  only — never an enumerated `(1)… (2)… (3)…` changelog in that cell.
- Did any Recommendation get treated as settled scope? And does every
  `client_confirmation_recommended: true` recommendation actually appear in
  Assumptions — not folded into scope, but not silently dropped either?

Fix whatever this surfaces before writing the JSON. It produces no output of
its own — never a section, note, or field in the deliverable.
