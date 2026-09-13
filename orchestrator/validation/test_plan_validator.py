"""Deterministic consistency checks for a test-plan JSON.

Mechanically enforces the invariants the test-plan-framework skill asks the
agent to self-review: controlled-document version/history coherence, the
two sanctioned TBD marker forms, and the rule that this system's own
internal repository paths never leak into a client-facing deliverable.

Errors block docx generation; warnings are surfaced but never block.
"""

import re

from orchestrator.models.requirement import AnalysisDocument
from orchestrator.models.test_plan import MAX_RELEASE_REASON_CHARS, TestPlan
from orchestrator.validation.analysis_validator import STATUS_BLOCKED

TBD_CLIENT = "TBD – Client/Project Input Required"
TBD_QA = "TBD – To be added by QA"

# This system's own on-disk layout — meaningless to a client and never
# allowed in a deliverable. A plugin install has no `projects/<name>/`
# wrapper anymore (a workspace is exactly one project), so the internal
# folders themselves (output/, knowledge-base/, automation/) are the leak
# signal now. Requirement input comes from the attached folder's
# Requirements/ notes (see orchestrator/utils/workspace.py).
_INTERNAL_PATH = re.compile(r"\b(?:output|knowledge-base|automation)[/\\]\S+")

# An Integration Sequence item that is nothing but an identifier (REQ-021,
# CMP-REG-002) -- the reader has to go fetch the analysis to learn what the
# stage actually covers, so the skill requires the description alongside it.
_BARE_REQ_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+")


def _walk_strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from _walk_strings(value, f"{path}[{idx}]")


def validate_test_plan(data) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed *-test-plan.json payload."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["Top level must be a JSON object matching the TestPlan model."], warnings

    try:
        plan = TestPlan.from_dict(data)
    except (KeyError, TypeError) as exc:
        return [f"Does not match the TestPlan model ({exc!r})."], warnings

    if not plan.meta.version.strip():
        errors.append("meta.version is empty.")
    if not plan.release_history:
        errors.append("release_history is empty — even a first generation has one entry.")
    else:
        latest = plan.release_history[-1]
        if latest.version != plan.meta.version:
            errors.append(
                f"meta.version is {plan.meta.version!r} but the latest release_history "
                f"entry is {latest.version!r} — a regeneration must bump the version "
                "and append a matching history entry."
            )
        if not latest.reasons.strip():
            errors.append("The latest release_history entry has an empty 'reasons'.")
        for entry in plan.release_history:
            length = len(entry.reasons.strip())
            if length > MAX_RELEASE_REASON_CHARS:
                # A warning, not an error: an over-long reason produces an ugly
                # table, not a wrong document, and blocking an otherwise-good
                # regeneration over a formatting issue would be obnoxious. It is
                # still worth flagging every time -- past this length the row
                # grows taller than the page.
                warnings.append(
                    f"release_history entry v{entry.version} has a {length}-character "
                    f"'reasons' (limit {MAX_RELEASE_REASON_CHARS}). The Release History "
                    "table's Reasons column is ~1.5in wide; this long a value makes the "
                    "row taller than the page and squeezes the other columns into "
                    "mid-word breaks. Shorten it to a one-line summary."
                )
        versions = [entry.version for entry in plan.release_history]
        if len(versions) != len(set(versions)):
            warnings.append("release_history contains duplicate version numbers.")

    for path, text in _walk_strings(data):
        if _INTERNAL_PATH.search(text):
            errors.append(
                f"{path}: leaks this system's internal repository path into the "
                f"deliverable: {text[:120]!r} — use the appropriate TBD marker instead."
            )
        if "TBD" in text:
            stripped = text.strip()
            if stripped != "TBD" and TBD_CLIENT not in text and TBD_QA not in text:
                warnings.append(
                    f"{path}: contains a non-standard TBD form ({text[:120]!r}) — use "
                    f"'{TBD_CLIENT}' or '{TBD_QA}' (en dash) so ownership of the "
                    "unknown is explicit."
                )

    if not plan.introduction.scope_in_areas:
        warnings.append("introduction.scope_in_areas is empty — no in-scope functional areas.")
    if not plan.schedule:
        warnings.append(
            "schedule is empty — if no timing is known, one row with "
            f"'{TBD_CLIENT}' dates is the expected shape."
        )
    if not plan.strategy.entry_criteria or not plan.strategy.exit_criteria:
        warnings.append("strategy entry_criteria/exit_criteria should not be empty.")

    for area in plan.strategy.integration_sequence:
        bare = [item for item in area.items if _BARE_REQ_ID.fullmatch(item.strip())]
        if bare:
            warnings.append(
                f"Integration sequence stage {area.area!r} lists bare requirement IDs "
                + ", ".join(bare)
                + " — each item reads '<REQ-ID> – <requirement description>' so a client "
                "can see what the stage covers without cross-referencing the analysis."
            )

    return errors, warnings


def compare_test_plan_with_previous(new_data, old_data) -> tuple[list[str], list[str]]:
    """Mechanical revision checks between a test-plan JSON and its latest
    history/ snapshot: release_history is append-only, version never goes
    backwards. Same-version comparisons are in-run iteration and only the
    append-only invariant applies."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        new = TestPlan.from_dict(new_data)
        old = TestPlan.from_dict(old_data)
    except (KeyError, TypeError) as exc:
        return [], [f"History comparison skipped: could not parse both versions ({exc!r})."]

    def entry_key(entry):
        return f"{entry.version}|{entry.date}|{entry.reasons}"

    new_history = {entry_key(e) for e in new.release_history}
    lost = [e for e in old.release_history if entry_key(e) not in new_history]
    if lost:
        errors.append(
            "release_history lost entries present in the previous version "
            f"(versions: {', '.join(e.version for e in lost)}) — release history "
            "is append-only and must never be replaced."
        )

    def version_tuple(version: str):
        parts = re.findall(r"\d+", version)
        return tuple(int(p) for p in parts) if parts else None

    old_tuple, new_tuple = version_tuple(old.meta.version), version_tuple(new.meta.version)
    if old_tuple and new_tuple and new_tuple < old_tuple:
        errors.append(
            f"meta.version went backwards ({old.meta.version} → {new.meta.version})."
        )

    return errors, warnings


def cross_validate_test_plan(plan_data, analysis_data) -> tuple[list[str], list[str]]:
    """Consistency checks between a test plan and the requirement analysis it
    was derived from. Run only when both JSONs exist for the same document.

    Enforces the test-plan-framework skill's cross-agent rules mechanically:
    scope traceability/coverage via the scope areas' `req_ids`, and blocked
    requirements being surfaced rather than silently dropped.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        plan = TestPlan.from_dict(plan_data)
        analysis = AnalysisDocument.from_any(analysis_data)
    except (KeyError, TypeError) as exc:
        return [f"Cross-validation skipped: could not parse both JSONs ({exc!r})."], warnings

    analysis_ids = {req.req_id for req in analysis.requirements}
    blocked_ids = {
        req.req_id
        for req in analysis.requirements
        if req.acceptance_criteria_status == STATUS_BLOCKED
    }

    scope_ids: set[str] = set()
    any_traced = False
    for area in plan.introduction.scope_in_areas:
        if area.req_ids:
            any_traced = True
        for rid in area.req_ids:
            if rid in scope_ids:
                warnings.append(
                    f"{rid} appears in more than one scope area — each requirement "
                    "should land in exactly one."
                )
            scope_ids.add(rid)
            if rid not in analysis_ids:
                errors.append(
                    f"Scope area {area.area!r} references {rid}, which does not "
                    "exist in the requirement analysis."
                )

    if any_traced:
        untraced = sorted(analysis_ids - scope_ids)
        missing_unblocked = [rid for rid in untraced if rid not in blocked_ids]
        if missing_unblocked:
            warnings.append(
                "Requirements not covered by any scope area: "
                + ", ".join(missing_unblocked)
                + " — every non-blocked requirement should appear in exactly one "
                "scope area (or be explicitly out of scope)."
            )
    else:
        warnings.append(
            "No scope area carries req_ids — requirement coverage cannot be "
            "verified. Populate each scope area's req_ids for traceability."
        )

    adr = plan.assumptions_dependencies_risks
    adr_text = " ".join(adr.assumptions + adr.dependencies + adr.risks)
    unsurfaced = sorted(rid for rid in blocked_ids if rid not in adr_text)
    if unsurfaced:
        warnings.append(
            "Requirements pending client clarification not mentioned in "
            "Assumptions/Dependencies/Risks: " + ", ".join(unsurfaced)
            + " — they must be surfaced, not silently included or dropped. "
            "(If they're referenced as a range like 'REQ-020–024', name them "
            "individually so this check can see them.)"
        )

    return errors, warnings
