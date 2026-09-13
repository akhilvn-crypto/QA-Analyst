---
name: requirement-analysis-framework
description: Domain-aware gap-detection, recommendation, interconnection-detection, and acceptance-criteria framework for business requirement analysis, applicable across any business domain. Used only by the requirement-analyzer agent.
disable-model-invocation: true
---

# Requirement Analysis Framework

Domain-agnostic by design — the same rules apply to an e-commerce checkout,
a healthcare intake system, a banking ledger, or an IoT device. Where
domain-specific judgment is needed, this skill tells you *how to derive it*,
not the answer for any one industry. **Never invent business requirements or
behaviour the document doesn't support or reasonably imply** — domain
reasoning sharpens analysis, it never manufactures facts.

## Domain inference

Infer the business domain from the document's terminology, entities,
workflows, user roles, integrations, and regulatory language. State the
inference explicitly wherever it shapes your analysis (e.g. "this appears to
be a healthcare intake system, so HIPAA-style audit and consent expectations
apply") so a human can verify it rather than have it silently assumed. Don't
work from a predefined list of domains — derive it fresh, and only infer
what the document reasonably supports.

## Domain knowledge reasoning

Then reason internally about the requirement set the way an experienced
practitioner in that domain would: typical workflows, common business rules,
validation rules, user permissions and role boundaries, security
expectations, regulatory expectations, error-handling conventions, state
transitions, external integrations, reporting, audit, industry best
practice.

This sharpens gap detection, recommendations, and Acceptance Criteria — it
is not a deliverable. Surface it only where it materially shapes the
analysis (an assumed default, a flagged gap, a recommendation), never as
running commentary.

## Gap detection

Analyse each requirement independently. Before flagging silence as a gap,
check whether the silent behaviour has a well-established conventional
default *for the inferred domain* (below). Only genuinely undefined,
ambiguous, or contradictory information becomes a candidate — and every
candidate must pass Gap validation before it's finalized.

Flag a requirement as having a gap when it is:

- **Ambiguous** — vague terms, undefined thresholds, unclear actor/action.
- **Contradictory** — conflicts with another requirement. You can only
  *suspect* this while reading one requirement at a time; confirm it in the
  Cross-requirement pass, the only point where both are compared side by
  side. Never finalize a contradiction gap from a single-requirement read.
- **Missing information** — no way to verify "done", or an unstated business
  rule / workflow step / actor.
- **Silent on edge cases** — no stated behaviour for error states,
  concurrency, or expiry/timeout, *and* no well-established convention
  covers it.

Write each gap's `description` in plain language a business stakeholder
understands — no gap IDs, no gap-type labels, no severity scores. Every
genuine gap gets exactly one clarifying `question`.

Judge internally whether each gap is **blocking** — whether it prevents
accurate understanding of the requirement's expected behaviour (see the
Blocked examples below) versus merely minor. This only decides the
requirement's Acceptance Criteria Status; it is never its own output field.

No genuine gaps → exactly:

```
Gap: No significant gaps identified.
Client Question: None.
```

### Conventional defaults vs. genuine gaps

An experienced analyst doesn't treat every silence as unknown. Many
behaviours have one well-established convention *within the document's own
domain* — but that convention differs by domain, so derive it, don't look it
up from a fixed list. When a requirement is silent on something a convention
covers:

- **Do not** raise a gap or generate a client question.
- **Do** state the assumed default explicitly as an assumption, naming both
  the assumption and the domain reasoning: "Not stated in the document;
  standard practice for [inferred domain] assumes [behaviour]. Assumed
  unless the document states otherwise."
- If anything elsewhere in the document contradicts the convention, or the
  product context suggests conventions are deliberately not followed (a
  test/demo system built to exercise edge cases, a legacy system with known
  non-standard behaviour), don't apply it silently — treat it as a genuine
  gap needing confirmation.

**Deriving a domain convention:** ask what an experienced practitioner *in
that specific industry* would consider default, unremarkable behaviour that
wouldn't need stating in a requirements doc. If you can articulate a
specific, well-known convention and justify why it's standard there, treat
it as a default. If you can't name one with confidence, or the domain has no
single clear answer, it's a genuine gap.

**The distinction that matters, independent of domain:** does the silent
behaviour have one broadly-accepted answer within its domain (→ default, no
gap), or is it a parameter, threshold, formula, or business rule that
legitimately varies between implementations even within that domain (→
genuine gap)? Exact numeric thresholds, calculation formulas, specific
compliance standards/versions, and organization-specific business rules are
almost always the latter — there is rarely one universal number, even when
"some threshold must exist" is itself conventional.

### Gap validation (reduce false positives)

Before a candidate gap is finalized, validate it against three questions:

1. Does the missing information prevent a developer from implementing the
   requirement correctly?
2. Would two experienced developers likely produce materially different
   business behaviour because it's missing?
3. Does it affect business rules, workflow, permissions, calculations,
   compliance, or expected outcomes?

**If all three are No, do not raise a gap.** Instead pick whichever fits:
treat it as a reasonable implementation decision (any competent
implementation converges on the same behaviour anyway); apply an assumed
default; or add an optional recommendation if surfacing the point still adds
value without blocking anything.

Apply this to every candidate, not just borderline ones — a gap survives
only if at least one answer is Yes. A real gap changes what gets built or
how it behaves; a false positive is an implementation detail, a stylistic
choice, or already obvious from context.

### Cross-domain QA instincts (apply in any industry)

- **Negative and boundary paths** — for any input or threshold: zero, the
  maximum, one below/above a limit, invalid input. Not just the happy path.
- **Idempotency of destructive or state-changing actions** — does repeating
  delete/submit/cancel/resend duplicate effects, or is retry safe?
- **State consistency under interruption** — network failure, crash,
  timeout, concurrent edit: is the resulting state well-defined?
- **Auditability of consequential actions** — for anything with legal,
  financial, safety, or compliance weight, is there a record of who did what
  and when?
- **Permission and role boundaries** — who may perform this, and what
  happens when someone without permission tries?
- **Graceful degradation on dependency failure** — if an external system
  this requirement depends on is unavailable, is the fallback defined?
- **Vague qualifiers demand quantification** — "fast", "secure",
  "user-friendly", "reasonable", "appropriate" are never acceptance criteria
  on their own, in any domain.

Apply these alongside domain-specific reasoning, not instead of it — a
domain convention and a cross-domain instinct can both apply to the same
requirement.

## Cross-requirement analysis (second pass)

After the flat requirement list is extracted, do a second pass over the full
set. Both relationship types are properties of a *pair* of requirements, not
of any one read in isolation — which is why this is a distinct pass, not
inline during extraction.

**Interconnections:**
- `depends_on` — this requirement can't be satisfied unless another is.
- `related_to` — shares a workflow, entity, or feature area without strict
  dependency.

**Contradictions:** check every requirement against every other one touching
the same entity, workflow, or business rule — a stated rule, permission,
value, or behaviour in one that cannot both be true alongside another's.
When you find a genuine one:

- Raise it as a gap on **both** affected requirements — each `description`
  naming the other requirement's ID and stating the conflict in plain
  business language.
- Generate one clarifying `question` per affected requirement, asking which
  version is correct or whether both apply under different conditions.
- Treat it as `blocking` — an unresolved contradiction means the expected
  behaviour of *both* requirements isn't yet knowable.

## Question generation

For every genuine gap (assumed defaults are not gaps and get no question),
generate exactly one clarifying question that is specific to the gap (not
generic), phrased so a client/product owner can answer without re-reading
the requirement doc, and actionable (answering it closes the gap).

Two checks before any question is finalized — nothing damages a
clarification sheet's credibility faster than asking something the client
already answered:

1. **Answered elsewhere in the document.** Search the *entire* document —
   every section, including glossary/notes. Requirements docs frequently
   answer one requirement's silence in another section. If found, don't ask:
   cite where it's answered and treat the behaviour as stated.
2. **Answered by this client before.** Read `meta.clarification_log` in
   the existing `<doc-name>-analysis.json` — every answer
   `/apply-clarifications` has applied is recorded there with its question
   and date. Judge the match honestly — same business behaviour, not just
   similar words. On a genuine match, don't re-ask: apply the recorded
   answer as a **client-confirmed default** (stronger than an assumed
   convention — cite it, e.g. "Per the client's earlier clarification on
   REQ-014: …") and close or downgrade the gap. If the current document
   *contradicts* a recorded answer, that is a genuine gap — ask, naming both.

Store the question as `question`. No genuine gaps → the client question is
exactly `None.`

## Recommendations

A **gap** is information the document should have specified but didn't — it
blocks confidence until the client answers. A **recommendation** is a
professional, domain-informed suggestion made *in addition to* a requirement
that is already understandable — it improves the outcome but is never
required to build or test the requirement as written.

Draw them from the domain reasoning above (workflow, security, validation,
reporting, audit, or best-practice considerations the document didn't ask
for but a practitioner would raise).

- Never treated as gaps; never block Acceptance Criteria.
- Only when it genuinely adds value to that specific requirement — do not
  pad every requirement with a generic suggestion. Most requirements having
  none is normal and expected.
- Never require client clarification unless genuinely appropriate (e.g. it
  changes scope or cost) — most need no sign-off.

Capture per recommendation: `recommendation` (specific and concrete),
`reason` (why it matters, grounded in the domain reasoning),
`business_benefit` (concrete value if adopted), and
`client_confirmation_recommended` (`true` when the client should sign off
before it's treated as in-scope, `false` for a low-risk best-practice note).

## Acceptance Criteria generation

Classify each requirement into exactly one status:

**1. Ready** → `acceptance_criteria_status = Generated`. Sufficient
information to define expected behaviour. Includes requirements whose only
silences are covered by a conventional default — assumed defaults don't
block readiness, but still list them in `acceptance_criteria` as stated
assumptions.

**2. Ready with Assumptions** → `Generated with Assumptions`. Only minor
(non-blocking) gaps that don't affect core business behaviour. List all
assumptions *before* the Acceptance Criteria in `acceptance_criteria`, each
marked **Client Confirmation Required**.

**3. Blocked** → `Not Generated – Client Clarification Required`. One or
more blocking gaps prevent accurate understanding: missing business rules,
undefined workflow, undefined user roles or permissions, missing validation
rules, undefined success/failure behaviour, missing approval process, or
conflicting requirements. Do **not** generate Acceptance Criteria — set
`acceptance_criteria` to a brief explanation of why not, referencing the
blocking gap(s) by description (not an ID) and the client question(s)
needed to resolve them.

Classify independently per requirement — one requirement's status never
affects another's.

**Acceptance Criteria standards** (statuses 1 and 2):
- **Plain English** — clear numbered or bulleted statements of expected
  behaviour. No Given/When/Then or other Gherkin syntax.
- Each testable, measurable, traceable to the requirement, free of
  implementation detail.
- Cover, where applicable: happy path, negative scenarios, validation rules,
  error handling, permission checks, business rules, edge cases.
- Never invent behaviour not stated or reasonably implied by the document.

## Title and category

Every requirement — from the main extraction or from the NFR/Compliance
passes — carries:

- `title` — a short plain-English label (e.g. "Initial Login Interface",
  "Performance", "Data Privacy & Protection (GDPR / CCPA)") used as the card
  heading. Derive it from the requirement's own subject; never imply scope
  the text doesn't have.
- `category` — `"Functional"`, `"Non-Functional"`, or `"Compliance"`,
  deciding which report section it groups under. Everything from the main
  extraction pass is `"Functional"` by default. A non-functional or
  compliance requirement is **never backfilled onto an existing Functional
  entry's category** — it's added as its own new itemized requirement by the
  passes below.

## NFR analysis

A synthesis pass over the *whole* document, run once after extraction and
domain inference are both complete.

Identify every requirement that is itself non-functional (performance,
compatibility/browser support, usability, security, session management,
reliability/availability, accessibility, scalability, auditability/logging,
localization, etc. — driven by what the document actually contains, not a
fixed checklist).

- **Already stated in the document** → that requirement's `category` becomes
  `"Non-Functional"` (keeping the `REQ-` ID it was assigned in document
  order) and it goes through the same gap detection / recommendations /
  Acceptance Criteria process as any other. An NFR isn't analyzed
  differently once identified, only grouped separately in the report.
- **Genuinely missing everywhere** (not a per-requirement gap — there's no
  existing requirement it would attach to) and its absence is worth
  surfacing → add a **new** `"Non-Functional"` requirement continuing the
  `REQ-` sequence, whose `requirement_text` plainly states the document is
  silent here, with a genuine gap/question asking for the missing threshold
  or expectation. Judge this like any domain-convention reasoning — only add
  one if the absence is genuinely notable for this kind of system, not as a
  rote checklist. A training/reference/demo application legitimately doesn't
  need the NFR coverage a production financial system does; if that's why a
  category is absent, say so in that requirement's own
  `acceptance_criteria`/gap explanation rather than omitting it silently or
  wrongly implying an oversight.

If the document defines no NFRs and none are worth adding, the report's NFR
section legitimately shows no items — don't fabricate one to fill it. Never
invent an NFR, a threshold, or a category the document doesn't support.

## Compliance analysis

Identify which compliance/regulatory frameworks this document actually
implicates, using the same domain-inference method — derived from the
document's own evidence, never a fixed industry-to-regulation lookup applied
blindly. Each framework worth mentioning becomes its own itemized
`"Compliance"` requirement — **not** a narrative paragraph — on a separate
`CMP-REG-NNN` sequence starting at `CMP-REG-001`, independent of the `REQ-`
sequence (a compliance consideration isn't a requirement the client stated).

- Start from the inferred domain and its concrete evidence. For each
  framework a practitioner would routinely consider (WCAG for accessibility,
  PCI-DSS for payment/card data, GDPR/HIPAA/CCPA for personal or health
  data, SOC 2/ISO 27001 for security/operational controls, financial or
  safety regulation for regulated industries): does this document's actual
  content plausibly implicate it? If yes, add a `CMP-REG-NNN` requirement —
  `title` the framework, `requirement_text` stating what the document's own
  evidence says about it, citing the specific requirement(s) or domain
  evidence that make it relevant (or rule it out, e.g. "no real payment data
  is collected, per Section X / REQ-0NN") in the gap/acceptance-criteria
  text.
- **Implicated** → decide its status like any other requirement (Generated /
  Generated with Assumptions / Blocked) based on whether the document
  addresses it explicitly, partially (a genuine gap and question,
  cross-referencing the relevant REQ-ID's own gap rather than duplicating
  it), or not at all.
- **Not applicable** → still add its `CMP-REG-NNN` item, with
  `acceptance_criteria_status: "Not Applicable"` (the one status that exists
  only for Compliance items) and `acceptance_criteria` naming the concrete
  evidence for why. This mirrors the project-wide "never fabricated" TBD
  convention: an absent compliance concern must be a stated, cited
  conclusion, not a silent omission a reader could mistake for an oversight.
- If nothing implicates any framework, the section legitimately shows no
  items — don't add one to fill it.
- **Never assert** a document is compliant, partially compliant, or
  non-compliant with any named framework — that's a legal/audit judgment
  outside this analysis's scope. State only what the document does or
  doesn't address, and what a client would need to confirm.

## Project Overview & Scope

Once the full requirement set (Functional + Non-Functional + Compliance) is
final, write three short document-level narratives:

- `meta.executive_summary` — a few sentences on what the analyzed document
  covers and what this analysis validates, in plain business language a
  non-technical stakeholder can read before any requirement-by-requirement
  detail.
- `meta.in_scope` / `meta.out_of_scope` — what the document itself states or
  clearly implies is in/out of scope, in the client's own terms where
  possible. Never invent a scope boundary; if the document is silent on
  scope entirely, say so plainly (`"TBD – Client/Project Input Required"`)
  rather than guessing.

## Final consistency review

Before writing the JSON, review your own **drafted output** — not the source
document again — for the self-inconsistency that creeps in when a document
is analyzed requirement-by-requirement rather than all at once:

- Are requirement IDs sequential, with no gaps or duplicates?
- Did every genuine gap get exactly one `question`, and does every
  no-gap requirement read exactly `No significant gaps identified.` /
  `None.` — not a paraphrase?
- Are near-identical requirements (two similar permission checks, two
  similar validation rules) treated consistently — the same convention
  assumed, the same kind of silence judged a gap, in both places or neither?
  An inconsistency here usually means the earlier one was analyzed before
  the pattern was recognized. Reconcile it; don't leave the mismatch.
- Does every `Not Generated – Client Clarification Required` trace to at
  least one gap actually marked `blocking`? Does every `Generated with
  Assumptions` have its assumptions spelled out in `acceptance_criteria`,
  each marked Client Confirmation Required?
- Did every contradiction from the cross-requirement pass land as a gap on
  **both** affected requirements?
- Does any surviving question duplicate something the document answers
  elsewhere, or something already in `meta.clarification_log` / clarification
  memory? (Both checks must have actually happened, not been skipped.)
- On a re-analysis: were unchanged requirements carried forward verbatim (no
  cosmetic re-wording, no re-asking answered questions), and does the
  changelog name the actual delta?
- Were the NFR and Compliance passes actually done (even if the honest
  result is zero items), and does every Non-Functional/Compliance
  requirement cite real evidence rather than read as boilerplate?
- Were `executive_summary`/`in_scope`/`out_of_scope` written, and do they
  reflect the final requirement set (not a stale pre-delta draft)?

Fix whatever this surfaces before writing the JSON. It produces no output of
its own — never a section, note, or field in the deliverable.
