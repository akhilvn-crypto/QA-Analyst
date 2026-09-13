"""Deterministic consistency checks for a *-test-cases.json deliverable.

Mechanically enforces the invariants the test-case-generation-framework
skill asks the test-case-generator agent to self-review — the mechanical
backstop for that agent's own final consistency review, exactly as
analysis_validator.py is for requirement-analyzer and test_plan_validator.py
is for test-plan-generator.

Errors block the Zephyr CSV/XLSX export; warnings are surfaced but never
block.
"""

import re

from orchestrator.models.test_case import (
    KNOWN_TEST_TYPES,
    MAX_RELEASE_REASON_CHARS,
    TestCase,
    TestCaseDocument,
    VALID_PRIORITIES,
)

_TC_ID_NUM = re.compile(r"(\d+)$")

STATUS_BLOCKED = "Not Generated – Client Clarification Required"
STATUS_GENERATED = "Generated"
STATUS_WITH_ASSUMPTIONS = "Generated with Assumptions"
# "Not Applicable" only ever appears on a Compliance-category requirement
# (see analysis_validator.STATUS_NOT_APPLICABLE) — it still carries real
# Acceptance Criteria (e.g. "no real PII is collected"), so it's coverable
# the same as Generated/Generated with Assumptions, per the
# test-case-generation-framework skill's "Only test what has Acceptance
# Criteria" section.
STATUS_NOT_APPLICABLE = "Not Applicable"
COVERABLE_STATUSES = (STATUS_GENERATED, STATUS_WITH_ASSUMPTIONS, STATUS_NOT_APPLICABLE)


def _as_dict(entry) -> dict:
    return entry if isinstance(entry, dict) else {}


def _validate_meta(meta, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(meta, dict):
        errors.append("meta must be a JSON object.")
        return

    version = str(meta.get("version", "")).strip()
    if not version:
        errors.append("meta.version is empty.")

    changelog = meta.get("changelog", [])
    if not isinstance(changelog, list) or not changelog:
        errors.append(
            "meta.changelog is empty — even a first generation records one entry "
            "('Initial generation...')."
        )
    elif not isinstance(changelog[-1], dict):
        errors.append("meta.changelog entries must be JSON objects.")
    elif version and str(changelog[-1].get("version", "")) != version:
        errors.append(
            f"meta.version is {version!r} but the latest changelog entry is "
            f"{changelog[-1].get('version')!r} — a regeneration must bump the "
            "version and append a matching changelog entry."
        )

    if not str(meta.get("source_doc", "")).strip():
        warnings.append("meta.source_doc is empty.")


def _validate_release_history(
    release_history, meta_version: str, errors: list[str], warnings: list[str]
) -> None:
    """Same coherence rules as test_plan_validator's for TestPlan.release_history
    — but tolerant of a file written before these controlled-document fields
    existed: an entirely empty release_history is a warning (legacy shape,
    the next regeneration will adopt it), not an error. Once it has at least
    one entry, the same strict rules as the Test Plan apply."""
    if not isinstance(release_history, list):
        errors.append("release_history must be a JSON list.")
        return

    if not release_history:
        warnings.append(
            "release_history is empty — this file predates the controlled-document "
            "fields (Document Version Control / Release History); the next "
            "regeneration will populate them."
        )
        return

    latest = _as_dict(release_history[-1])
    if meta_version and str(latest.get("version", "")) != meta_version:
        errors.append(
            f"meta.version is {meta_version!r} but the latest release_history entry "
            f"is {latest.get('version')!r} — a regeneration must bump the version and "
            "append a matching history entry."
        )
    if not str(latest.get("reasons", "")).strip():
        errors.append("The latest release_history entry has an empty 'reasons'.")

    for entry in release_history:
        entry = _as_dict(entry)
        length = len(str(entry.get("reasons", "")).strip())
        if length > MAX_RELEASE_REASON_CHARS:
            warnings.append(
                f"release_history entry v{entry.get('version', '?')} has a "
                f"{length}-character 'reasons' (limit {MAX_RELEASE_REASON_CHARS}). "
                "The Release History sheet's Reasons column is narrow; shorten it to "
                "a one-line summary."
            )

    versions = [str(_as_dict(e).get("version", "")) for e in release_history]
    if len(versions) != len(set(versions)):
        warnings.append("release_history contains duplicate version numbers.")


def validate_test_cases(data) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed *-test-cases.json payload."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["Top level must be {'meta': ..., 'test_cases': [...], 'not_covered': [...]}."], warnings

    meta = data.get("meta", {})
    _validate_meta(meta, errors, warnings)
    meta_version = str(_as_dict(meta).get("version", ""))
    _validate_release_history(data.get("release_history", []), meta_version, errors, warnings)

    items = data.get("test_cases", [])
    if not isinstance(items, list):
        errors.append("'test_cases' must be a JSON list.")
        return errors, warnings

    not_covered = data.get("not_covered", [])
    if not isinstance(not_covered, list):
        errors.append("'not_covered' must be a JSON list.")
        not_covered = []
    for idx, entry in enumerate(not_covered, start=1):
        entry = _as_dict(entry)
        if not str(entry.get("req_id", "")).strip():
            errors.append(f"not_covered entry {idx} is missing req_id.")
        if not str(entry.get("reason", "")).strip():
            errors.append(f"not_covered entry {idx} is missing reason.")

    if not items and not not_covered:
        warnings.append(
            "No test cases and no not_covered entries — nothing was generated at all."
        )

    test_cases: list[TestCase] = []
    for idx, item in enumerate(items):
        try:
            test_cases.append(TestCase.from_dict(item))
        except (KeyError, TypeError) as exc:
            label = item.get("tc_id", f"item #{idx + 1}") if isinstance(item, dict) else f"item #{idx + 1}"
            errors.append(f"{label}: does not match the TestCase model ({exc!r}).")
    if errors:
        return errors, warnings

    seen_ids: set[str] = set()
    for tc in test_cases:
        tcid = tc.tc_id
        if not tcid or not tcid.strip():
            errors.append("A test case has an empty tc_id.")
            continue
        if tcid in seen_ids:
            errors.append(f"{tcid}: duplicate test case ID.")
        seen_ids.add(tcid)

        if not tc.req_id.strip():
            errors.append(f"{tcid}: req_id is empty — every test case must trace to a requirement.")
        if not tc.title.strip():
            errors.append(f"{tcid}: title is empty.")
        if tc.priority not in VALID_PRIORITIES:
            errors.append(
                f"{tcid}: priority {tc.priority!r} is not one of {list(VALID_PRIORITIES)}."
            )
        if tc.test_type and tc.test_type not in KNOWN_TEST_TYPES:
            warnings.append(
                f"{tcid}: test_type {tc.test_type!r} is not one of the framework's "
                f"known types {list(KNOWN_TEST_TYPES)} — verify this is deliberate, "
                "not a typo."
            )
        elif not tc.test_type:
            warnings.append(f"{tcid}: test_type is empty.")

        if not tc.steps:
            errors.append(f"{tcid}: has no steps — every test case needs at least one.")
            continue

        expected_step_numbers = list(range(1, len(tc.steps) + 1))
        actual_step_numbers = [step.step_number for step in tc.steps]
        if actual_step_numbers != expected_step_numbers:
            errors.append(
                f"{tcid}: step numbers {actual_step_numbers} are not a contiguous "
                f"1..N sequence."
            )

        for step in tc.steps:
            if not step.action.strip():
                errors.append(f"{tcid}: step {step.step_number} has no action.")
            elif re.search(r"\band\b", step.action, re.IGNORECASE):
                warnings.append(
                    f"{tcid}: step {step.step_number} action ({step.action!r}) reads as "
                    "compound (joined by 'and') — each step should be a single atomic action."
                )
            if not step.expected_result.strip():
                errors.append(
                    f"{tcid}: step {step.step_number} has no expected_result — every "
                    "step needs a specific, verifiable expected result."
                )
            elif step.expected_result.strip().lower() in (
                "works correctly",
                "works as expected",
                "success",
                "it works",
            ):
                warnings.append(
                    f"{tcid}: step {step.step_number} expected_result ({step.expected_result!r}) "
                    "is vague — state the specific, verifiable outcome."
                )

    numbers = []
    for tc in test_cases:
        match = _TC_ID_NUM.search(tc.tc_id)
        if match:
            numbers.append(int(match.group(1)))
    if numbers:
        expected = list(range(min(numbers), min(numbers) + len(numbers)))
        if sorted(numbers) != expected:
            warnings.append(
                "Test case IDs are not a contiguous sequence — check for a skipped "
                "or misnumbered TC-ID."
            )

    return errors, warnings


def cross_validate_test_cases(data, analysis_data) -> tuple[list[str], list[str]]:
    """Check a test-cases payload against its sibling requirement-analysis
    JSON: every test case traces to a real requirement, every coverable
    requirement (Generated / Generated with Assumptions) has test cases or
    is explicitly accounted for, and every blocked requirement is actually
    in not_covered rather than silently missing from both."""
    errors: list[str] = []
    warnings: list[str] = []

    analysis_items = (
        analysis_data.get("requirements", []) if isinstance(analysis_data, dict) else analysis_data
    )
    if not isinstance(analysis_items, list):
        return errors, warnings

    status_by_id = {
        str(_as_dict(item).get("req_id", "")): str(
            _as_dict(item).get("acceptance_criteria_status", "")
        )
        for item in analysis_items
        if isinstance(item, dict)
    }
    all_req_ids = set(status_by_id)

    tc_req_ids = {
        str(_as_dict(item).get("req_id", "")) for item in data.get("test_cases", [])
    }
    not_covered_ids = {
        str(_as_dict(item).get("req_id", "")) for item in data.get("not_covered", [])
    }

    for req_id in tc_req_ids:
        if req_id and all_req_ids and req_id not in all_req_ids:
            errors.append(
                f"A test case traces to {req_id!r}, which is not a requirement in the "
                "sibling analysis JSON."
            )

    for req_id, status in status_by_id.items():
        if status in COVERABLE_STATUSES:
            if req_id not in tc_req_ids and req_id not in not_covered_ids:
                warnings.append(
                    f"{req_id}: status is {status!r} (Acceptance Criteria available) "
                    "but has no test case and isn't in not_covered — coverage gap."
                )
        elif status == STATUS_BLOCKED:
            if req_id not in not_covered_ids:
                warnings.append(
                    f"{req_id}: status is Blocked but doesn't appear in not_covered — "
                    "a blocked requirement should be explicitly accounted for, not "
                    "silently absent."
                )
            if req_id in tc_req_ids:
                errors.append(
                    f"{req_id}: has test cases but its Acceptance Criteria status is "
                    "Blocked — test cases must never be fabricated for a requirement "
                    "with no generated Acceptance Criteria."
                )

    return errors, warnings


def _version_tuple(version: str):
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else None


def compare_with_previous(new_data, old_data) -> tuple[list[str], list[str]]:
    """Mechanical revision checks between a test-cases JSON and its latest
    history/ snapshot: append-only changelog, version discipline."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        new = TestCaseDocument.from_dict(new_data)
        old = TestCaseDocument.from_dict(old_data)
    except (KeyError, TypeError) as exc:
        return [], [f"History comparison skipped: could not parse both versions ({exc!r})."]

    old_version, new_version = old.meta.version, new.meta.version
    old_tuple, new_tuple = _version_tuple(old_version), _version_tuple(new_version)
    if old_tuple and new_tuple and new_tuple < old_tuple:
        errors.append(f"meta.version went backwards ({old_version} → {new_version}).")

    if new_version == old_version:
        return errors, warnings  # in-run iteration — revision checks don't apply

    def changelog_key(entry) -> str:
        entry = _as_dict(entry)
        return f"{entry.get('version', '')}|{entry.get('changes', '')}"

    new_changes = {changelog_key(e) for e in new.meta.changelog}
    lost_changelog = [e for e in old.meta.changelog if changelog_key(e) not in new_changes]
    if lost_changelog:
        errors.append(
            "changelog lost entries present in the previous version "
            f"(versions: {', '.join(str(_as_dict(e).get('version', '?')) for e in lost_changelog)}) "
            "— the changelog is append-only."
        )

    def release_key(entry) -> str:
        return f"{entry.version}|{entry.date}|{entry.reasons}"

    new_history = {release_key(e) for e in new.release_history}
    lost_history = [e for e in old.release_history if release_key(e) not in new_history]
    if lost_history:
        errors.append(
            "release_history lost entries present in the previous version "
            f"(versions: {', '.join(e.version for e in lost_history)}) — release "
            "history is append-only and must never be replaced."
        )

    return errors, warnings
