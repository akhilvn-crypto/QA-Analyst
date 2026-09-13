---
name: test-case-generation-framework
description: Domain-agnostic framework for turning analyzed requirements' Acceptance Criteria into atomic, traceable test cases — how many a requirement needs, how to write steps, priority derivation, and what never to invent. Used only by the test-case-generator agent.
disable-model-invocation: true
---

# Test Case Generation Framework

*What test cases to write.* The JSON shape and the CSV/XLSX export layout
belong to the test-case-output-structure skill.

Domain-agnostic — the same coverage and step-writing rules apply to a
checkout flow, a clinical intake form, or an internal admin tool.

**Never invent test data or business behaviour** the Acceptance Criteria
doesn't define or reasonably imply — the discipline `requirement-analyzer`
applies to gaps, one level down. A test case that assumes a validation rule,
a numeric limit, or a specific error message the Acceptance Criteria never
stated is testing a requirement that doesn't exist.

## Only test what has Acceptance Criteria

Generate test cases only for `acceptance_criteria_status` of `Generated`,
`Generated with Assumptions`, or — for a `"Compliance"`-category requirement
only — `Not Applicable`. (A compliance framework the domain doesn't
implicate still has real Acceptance Criteria describing what the analysis
confirmed, e.g. "no real PII is collected", so it's testable like any other,
just under a different status label.)

A `Not Generated – Client Clarification Required` requirement has no defined
expected behaviour to test against — a test case for it would invent the
very behaviour the client hasn't confirmed. Record it in `not_covered`, with
`reason` naming the blocking gap(s) from its `acceptance_criteria`
explanation briefly, in plain language (not copied verbatim if long).

For `Generated with Assumptions`, test the behaviour as stated, assumptions
included — they are the requirement's current expected behaviour until a
clarification changes them. Don't caveat the test case about the assumption;
that belongs in the analysis JSON.

## How many test cases a requirement needs

Start from one **happy-path (Positive)** case — the primary successful flow.
Then add the types below *only where the Acceptance Criteria (or, for the
last four, the wider analysis JSON) genuinely supports it*. This is coverage
guidance, not a quota. Most requirements need Positive plus one or two
others; padding a requirement with a type it doesn't call for is exactly the
invented behaviour the rule above forbids.

- **Negative** — one per explicitly stated validation or error rule ("email
  must be a valid format" → a case submitting an invalid format; "cannot
  cancel an order already shipped" → a case attempting exactly that). Never
  for a rule the Acceptance Criteria didn't state.
- **Boundary** — one per stated numeric or length limit, at the values
  genuinely at the edge (a stated "maximum 3 attempts" warrants a case at
  the 3rd and one at the 4th, not an arbitrary "attempt 10").
- **Edge** — a plausible but unusual *state or timing* the normal-case
  wording doesn't narrate, distinct from Boundary (a *stated numeric/length
  threshold*): an empty list feeding a report, two updates arriving for the
  same record in quick succession, an action attempted immediately after a
  dependent one completed, the first or last record in a sequence. Only for
  a genuinely foreseeable state, never a contrived scenario.
- **Permission** — one per stated role or access-control rule ("only an
  Admin can approve" → Admin succeeding, non-Admin denied).
- **Integration** — when the Acceptance Criteria describes, or
  `depends_on`/`related_to` shows, an interaction with another system,
  service, or requirement's workflow (calendar sync, payment gateway
  callback, webhook, downstream system that must receive an update). Verify
  the observable outcome on **both** sides, not just the triggering side
  ("the local status updates *and* the external calendar event is created
  with the right participants").
- **Security** — when the requirement touches authentication, an
  authorization boundary beyond a simple role check (already Permission),
  sensitive data (PII, financial, health), or an input surface with real
  exploit potential (session/token expiry; a financial-value field rejecting
  a negative injected value; one user unable to reach another's record by
  guessing an ID). Ground it in what *this* requirement exposes — never a
  generic "test for SQL injection" bolted onto a requirement with no stated
  input surface.
- **Database** — when the expected behaviour implies a persistence or
  data-integrity guarantee beyond the UI-level criteria: a record surviving
  a refresh, a foreign-key or attribution relationship staying consistent
  after an update (reassigning a lead's capturing-Canvasser ID correctly
  repoints financial-value attribution), a value that must never end up null
  or orphaned after a status transition. Only when the data model is
  actually inferable from the Acceptance Criteria — never invent schema.
- **API** — when the requirement describes or clearly implies a
  system/service contract: a status code, a request/response field, an error
  payload shape ("the system re-validates availability at confirmation and
  rejects the second attempt" implies a specific conflict response, not just
  a UI message). Test the contract, not implementation internals.

A requirement whose Acceptance Criteria packs in several distinct rules gets
one test case per rule plus the happy path — not one sprawling case
exercising everything. Atomicity applies at the test-case level, not just
the step level: each case should verify one behaviour clearly enough that a
failure immediately says which expectation broke.

## Writing steps

- **One action per step.** "Enter username and click login" is two steps — a
  compound step hides which half failed.
- **One specific, verifiable expected result per step.** Never "works
  correctly", "functions as expected", or "success" — state what a tester
  actually observes (a specific message, field value, state change,
  redirect).
- **Preconditions** go in `preconditions`, not as a numbered step. "User is
  logged in as a Customer" is a precondition, not step 1.
- **Test data** goes on the step that uses it (`test_data`), not folded into
  the action text — so the exported Test Data column carries the actual
  value a tester types, separately from the instruction to type it.
- Number steps `1..N` contiguously — no gaps, no restarts.

## Never invent test data or business behaviour

If the Acceptance Criteria says "a valid email address" with no format
example, the test data says "a valid registered email address" — not a
specific invented address, regex, or domain the source never stated (unless
surrounding project material genuinely supplies one). If the criteria don't
state what happens on an error path, don't write a negative case guessing at
it: that gap was `requirement-analyzer`'s job to surface, and it isn't this
agent's job to silently fill in a guess.

Before falling back to a generic placeholder, check whether this project's
ingested knowledge base can supply the missing specific — see the agent's
own "Resolve genuine doubts against the knowledge base" step. A `[]` or
irrelevant result is not an answer; only then does the generic fallback
apply.

## Priority derivation

There is no risk-rating field anywhere in this system's output — risk scores
were retired. Test-case `priority` derives from the requirement's own stated
`priority`, so the signal the client actually gave drives it:

| Requirement priority | Test case priority |
|---|---|
| `Must Have` / `P1` / explicit "Critical"/"High" | **High** |
| `Should Have` / `P2` | **Medium** |
| `Could Have` / `Won't Have` / `P3` / `P4` / explicit "Low" | **Low** |
| unstated or unrecognized | **Medium** (neutral default, not a guess) |

Apply once per requirement — every test case from the same requirement
inherits the same priority. A negative-path or boundary case does *not* get
a different priority just because it's "less common".

## Final consistency review

Before writing the JSON, review your own drafted test cases — not the source
analysis again:

- Is every `tc_id` sequential with no gaps or duplicates, and does every
  `req_id` exist in the source analysis JSON?
- Does every `Generated` / `Generated with Assumptions` / (Compliance-only)
  `Not Applicable` requirement have at least one test case, and does every
  `Not Generated – Client Clarification Required` one appear in
  `not_covered` instead — never both, never neither?
- Is every step's action atomic, with a specific (never vague) expected
  result?
- Does every `priority` match its requirement's stated priority per the
  table above — not a re-guessed value?
- Did any test case assume test data, a format, or a business rule the
  Acceptance Criteria never stated?
- Does every Integration/Security/Database/API case trace to something the
  Acceptance Criteria (or `depends_on`/`related_to`) genuinely states or
  implies — not a type added reflexively to "round out" coverage?

Fix whatever this surfaces before writing the JSON. It produces no output of
its own — never a field or note in the deliverable.
