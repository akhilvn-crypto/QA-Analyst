"""Deterministic consistency checks for a requirement-analysis JSON.

Mechanically enforces the invariants the requirement-analysis-framework
skill asks the agent to self-review — so a slip in the agent's own "final
consistency review" is caught before the JSON becomes the source of truth
for the docx report or any downstream agent.

Errors block docx generation; warnings are surfaced but never block.
"""

import re
from difflib import SequenceMatcher

from orchestrator.models.requirement import (
    AnalysisDocument,
    MAX_RELEASE_REASON_CHARS,
    Requirement,
)

STATUS_GENERATED = "Generated"
STATUS_WITH_ASSUMPTIONS = "Generated with Assumptions"
STATUS_BLOCKED = "Not Generated – Client Clarification Required"
# Only legal on a Compliance-category requirement (see CATEGORY_COMPLIANCE
# below) — the report displays it verbatim as "Not Applicable" (unlike
# STATUS_BLOCKED, which the report displays as the shorter "Blocked"; see
# md_report_writer/docx_report_writer's `_display_status`). A compliance
# consideration the inferred domain doesn't actually implicate is this
# status, not STATUS_GENERATED, so it stays distinguishable in the JSON.
STATUS_NOT_APPLICABLE = "Not Applicable"

VALID_STATUSES = (STATUS_GENERATED, STATUS_WITH_ASSUMPTIONS, STATUS_BLOCKED)

CATEGORY_FUNCTIONAL = "Functional"
CATEGORY_NON_FUNCTIONAL = "Non-Functional"
CATEGORY_COMPLIANCE = "Compliance"
VALID_CATEGORIES = (CATEGORY_FUNCTIONAL, CATEGORY_NON_FUNCTIONAL, CATEGORY_COMPLIANCE)

_REQ_ID_NUM = re.compile(r"(\d+)$")

# Similarity thresholds for re-ask detection (normalized question text).
_REASK_ERROR = 0.90
_REASK_WARNING = 0.70


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _as_dict(entry) -> dict:
    """Malformed log/changelog entries must degrade to reportable problems,
    never crash the validator."""
    return entry if isinstance(entry, dict) else {}


def _clarification_key(entry) -> str:
    entry = _as_dict(entry)
    return "|".join(str(entry.get(k, "")) for k in ("req_id", "question", "answer"))


def _question_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _check_reasked_questions(
    requirements: list[Requirement],
    clarification_log: list,
    errors: list[str],
    warnings: list[str],
) -> None:
    """A question the client already answered (it's in clarification_log)
    must never reappear as an open gap question — not even reworded."""
    answered = [
        (str(_as_dict(entry).get("req_id", "")), str(_as_dict(entry).get("question", "")))
        for entry in clarification_log
        if str(_as_dict(entry).get("question", "")).strip()
    ]
    if not answered:
        return

    for req in requirements:
        for gap in req.gaps:
            for ans_req_id, ans_question in answered:
                score = _question_similarity(gap.question, ans_question)
                if score >= _REASK_ERROR:
                    errors.append(
                        f"{req.req_id}: gap question re-asks what the client already "
                        f"answered for {ans_req_id} ({ans_question[:80]!r}, "
                        f"similarity {score:.2f}) — apply the recorded answer from "
                        "clarification_log instead of re-asking."
                    )
                elif score >= _REASK_WARNING:
                    warnings.append(
                        f"{req.req_id}: gap question looks similar to one already "
                        f"answered for {ans_req_id} (similarity {score:.2f}) — "
                        "verify it genuinely asks something new."
                    )


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
            "meta.changelog is empty — even a first analysis records one entry "
            "('Initial analysis...')."
        )
    elif not isinstance(changelog[-1], dict):
        errors.append("meta.changelog entries must be JSON objects.")
    elif version and str(changelog[-1].get("version", "")) != version:
        errors.append(
            f"meta.version is {version!r} but the latest changelog entry is "
            f"{changelog[-1].get('version')!r} — a re-analysis must bump the version "
            "and append a matching changelog entry."
        )

    if not str(meta.get("source_doc", "")).strip():
        warnings.append("meta.source_doc is empty.")
    if not str(meta.get("domain", "")).strip():
        warnings.append("meta.domain is empty — the domain inference should be recorded.")
    if not str(meta.get("executive_summary", "")).strip():
        warnings.append(
            "meta.executive_summary is empty — the Project Overview & Scope report "
            "section needs a short summary of what the document covers."
        )
    if not str(meta.get("in_scope", "")).strip() and not str(meta.get("out_of_scope", "")).strip():
        warnings.append(
            "meta.in_scope and meta.out_of_scope are both empty — the Project "
            "Overview & Scope report section has nothing to show for either."
        )
    # meta.nfr_analysis/meta.compliance_analysis emptiness is no longer
    # checked here — NFR/Compliance coverage is now judged from itemized
    # Non-Functional/Compliance-category requirements (see the category
    # checks below, once the requirement list is parsed), not from these two
    # legacy narrative fields.

    log = meta.get("clarification_log", [])
    if not isinstance(log, list):
        errors.append("meta.clarification_log must be a JSON list.")
        log = []
    for idx, entry in enumerate(log, start=1):
        if not all(
            str(_as_dict(entry).get(k, "")).strip()
            for k in ("req_id", "question", "answer")
        ):
            errors.append(
                f"meta.clarification_log entry {idx} is missing req_id, question, "
                "or answer."
            )


def _validate_release_history(
    release_history, meta_version: str, errors: list[str], warnings: list[str]
) -> None:
    """Coherence rules for the Document Release History section, mirroring
    test_case_validator's own `_validate_release_history` — tolerant of a
    file written before these controlled-document fields existed: an
    entirely empty release_history is a warning (legacy shape, the next
    analysis run will adopt it), not an error. Once it has at least one
    entry, the same strict rules as the Test Plan/Test Case deliverables
    apply."""
    if not isinstance(release_history, list):
        errors.append("release_history must be a JSON list.")
        return

    if not release_history:
        warnings.append(
            "release_history is empty — this file predates the controlled-document "
            "fields (Document Version Control / Release History); the next analysis "
            "run will populate them."
        )
        return

    latest = _as_dict(release_history[-1])
    if meta_version and str(latest.get("version", "")) != meta_version:
        errors.append(
            f"meta.version is {meta_version!r} but the latest release_history entry "
            f"is {latest.get('version')!r} — a re-analysis must bump the version and "
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
                "The Release History table's Reasons column is narrow; shorten it "
                "to a one-line summary."
            )

    versions = [str(_as_dict(e).get("version", "")) for e in release_history]
    if len(versions) != len(set(versions)):
        warnings.append("release_history contains duplicate version numbers.")


def validate_analysis(data) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed *-analysis.json payload.

    Accepts both shapes: `{"meta": {...}, "requirements": [...]}` (current)
    and the legacy bare list of requirements (validated with a warning).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if isinstance(data, dict):
        meta = data.get("meta", {})
        _validate_meta(meta, errors, warnings)
        meta_version = str(_as_dict(meta).get("version", ""))
        _validate_release_history(data.get("release_history", []), meta_version, errors, warnings)
        items = data.get("requirements", [])
        if not isinstance(items, list):
            errors.append("'requirements' must be a JSON list.")
            return errors, warnings
    elif isinstance(data, list):
        items = data
        warnings.append(
            "Legacy shape (bare list, no meta block) — the next analysis run will "
            "add the meta block (domain, version, extraction manifest)."
        )
    else:
        return [
            "Top level must be {'meta': ..., 'requirements': [...]} or a legacy "
            "list of requirements."
        ], warnings

    if not items:
        return errors + ["Requirement list is empty."], warnings

    requirements: list[Requirement] = []
    for idx, item in enumerate(items):
        try:
            requirements.append(Requirement.from_dict(item))
        except (KeyError, TypeError) as exc:
            label = item.get("req_id", f"item #{idx + 1}") if isinstance(item, dict) else f"item #{idx + 1}"
            errors.append(f"{label}: does not match the Requirement model ({exc!r}).")
    if errors:
        return errors, warnings

    seen_ids: set[str] = set()
    for req in requirements:
        rid = req.req_id
        if not rid or not rid.strip():
            errors.append("A requirement has an empty req_id.")
            continue
        if rid in seen_ids:
            errors.append(f"{rid}: duplicate requirement ID.")
        seen_ids.add(rid)

        if not req.requirement_text.strip():
            errors.append(f"{rid}: requirement_text is empty.")

        for g_idx, gap in enumerate(req.gaps, start=1):
            if not gap.description.strip():
                errors.append(f"{rid}: gap {g_idx} has an empty description.")
            if not gap.question.strip():
                errors.append(
                    f"{rid}: gap {g_idx} has no client question — every genuine gap "
                    "gets exactly one."
                )

        if req.category not in VALID_CATEGORIES:
            errors.append(
                f"{rid}: category {req.category!r} is not one of {list(VALID_CATEGORIES)}."
            )
            continue

        # Not Applicable is only meaningful for a Compliance-category item
        # (a framework the inferred domain doesn't actually implicate) — a
        # Functional/Non-Functional requirement must still resolve to one of
        # the three original statuses.
        allowed_statuses = VALID_STATUSES
        if req.category == CATEGORY_COMPLIANCE:
            allowed_statuses = VALID_STATUSES + (STATUS_NOT_APPLICABLE,)

        if req.acceptance_criteria_status not in allowed_statuses:
            errors.append(
                f"{rid}: acceptance_criteria_status {req.acceptance_criteria_status!r} "
                f"is not one of {list(allowed_statuses)} (note the en dash in "
                f"'{STATUS_BLOCKED}')."
            )
            continue

        if not req.acceptance_criteria.strip():
            errors.append(
                f"{rid}: acceptance_criteria is empty — it must hold the criteria, "
                "or the clarification-needed explanation when status is "
                f"'{STATUS_BLOCKED}'."
            )

        has_blocking = any(gap.blocking for gap in req.gaps)
        # The blocking<->STATUS_BLOCKED linkage doesn't apply to a Not
        # Applicable compliance item — "not implicated by this domain" isn't
        # a blocking gap, so it has none to trace to.
        if req.acceptance_criteria_status != STATUS_NOT_APPLICABLE:
            if req.acceptance_criteria_status == STATUS_BLOCKED and not has_blocking:
                errors.append(
                    f"{rid}: status is '{STATUS_BLOCKED}' but no gap is marked blocking — "
                    "a Blocked status must trace to at least one blocking gap."
                )
            if has_blocking and req.acceptance_criteria_status != STATUS_BLOCKED:
                errors.append(
                    f"{rid}: has a blocking gap but status is "
                    f"'{req.acceptance_criteria_status}' — a blocking gap means "
                    f"Acceptance Criteria cannot be generated ('{STATUS_BLOCKED}')."
                )

        if (
            req.acceptance_criteria_status == STATUS_WITH_ASSUMPTIONS
            and "ssumption" not in req.acceptance_criteria
        ):
            warnings.append(
                f"{rid}: status is '{STATUS_WITH_ASSUMPTIONS}' but acceptance_criteria "
                "doesn't appear to spell out any assumptions."
            )

        for dep in req.depends_on:
            if dep == rid:
                errors.append(f"{rid}: depends_on itself.")
        for rec_idx, rec in enumerate(req.recommendations, start=1):
            if not rec.recommendation.strip() or not rec.reason.strip():
                errors.append(
                    f"{rid}: recommendation {rec_idx} is missing its recommendation "
                    "or reason text."
                )

    all_ids = {req.req_id for req in requirements}
    for req in requirements:
        for dep in req.depends_on:
            if dep not in all_ids:
                warnings.append(
                    f"{req.req_id}: depends_on {dep!r}, which is not a requirement in "
                    "this document — dependencies should be intra-document."
                )

    # Contiguity is checked per ID prefix, not across the whole document —
    # Compliance items intentionally use their own "CMP-REG-" numbering
    # rather than continuing the "REQ-" sequence Functional/Non-Functional
    # requirements share (see the category field), so the two shouldn't be
    # flattened into one range.
    numbers_by_prefix: dict[str, list[int]] = {}
    for req in requirements:
        match = _REQ_ID_NUM.search(req.req_id)
        if match:
            prefix = req.req_id[: match.start()]
            numbers_by_prefix.setdefault(prefix, []).append(int(match.group(1)))
    for prefix, numbers in numbers_by_prefix.items():
        expected = list(range(min(numbers), min(numbers) + len(numbers)))
        if sorted(numbers) != expected:
            warnings.append(
                f"Requirement IDs with prefix {prefix!r} are not a contiguous "
                "sequence — check for a skipped or misnumbered ID."
            )

    if isinstance(data, dict):
        meta = data.get("meta")
        log = meta.get("clarification_log", []) if isinstance(meta, dict) else []
        _check_reasked_questions(
            requirements,
            log if isinstance(log, list) else [],
            errors,
            warnings,
        )

    return errors, warnings


def _version_tuple(version: str):
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else None


def compare_with_previous(new_data, old_data) -> tuple[list[str], list[str]]:
    """Mechanical revision checks between an analysis JSON and its latest
    history/ snapshot: append-only logs, version discipline, carried-forward
    stability, and a changelog that names the real delta.

    A same-version comparison is treated as in-run iteration (the agent
    fixing its own draft), so only the append-only invariants apply there.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        new = AnalysisDocument.from_any(new_data)
        old = AnalysisDocument.from_any(old_data)
    except (KeyError, TypeError) as exc:
        return [], [f"History comparison skipped: could not parse both versions ({exc!r})."]

    # Append-only invariants hold regardless of version.
    if not new.legacy and not old.legacy:
        new_log = {_clarification_key(e) for e in new.meta.clarification_log}
        lost = [
            e
            for e in old.meta.clarification_log
            if _clarification_key(e) not in new_log
        ]
        if lost:
            errors.append(
                "clarification_log lost entries present in the previous version "
                f"({', '.join(str(_as_dict(e).get('req_id', '?')) for e in lost)}) — "
                "client answers are append-only and must never be dropped."
            )

    if old.legacy or new.legacy:
        return errors, warnings

    old_version, new_version = old.meta.version, new.meta.version
    old_tuple, new_tuple = _version_tuple(old_version), _version_tuple(new_version)
    if old_tuple and new_tuple and new_tuple < old_tuple:
        errors.append(
            f"meta.version went backwards ({old_version} → {new_version})."
        )

    if new_version == old_version:
        return errors, warnings  # in-run iteration — revision checks don't apply

    # This is a real revision: previous changelog entries must survive.
    def changelog_key(entry) -> str:
        entry = _as_dict(entry)
        return f"{entry.get('version', '')}|{entry.get('changes', '')}"

    new_changes = {changelog_key(e) for e in new.meta.changelog}
    lost_changelog = [
        e for e in old.meta.changelog if changelog_key(e) not in new_changes
    ]
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

    old_reqs = {req.req_id: req for req in old.requirements}
    new_reqs = {req.req_id: req for req in new.requirements}

    added = sorted(set(new_reqs) - set(old_reqs))
    removed = sorted(set(old_reqs) - set(new_reqs))
    changed_text = sorted(
        rid
        for rid in set(old_reqs) & set(new_reqs)
        if old_reqs[rid].requirement_text != new_reqs[rid].requirement_text
    )

    # Carried-forward stability: same requirement text should mean the same
    # analysis, unless a clarification landed for that requirement between
    # the two versions.
    old_log_keys = {_clarification_key(e) for e in old.meta.clarification_log}
    newly_clarified = {
        str(_as_dict(e).get("req_id", ""))
        for e in new.meta.clarification_log
        if _clarification_key(e) not in old_log_keys
    }
    def analysis_body(req: Requirement) -> dict:
        # depends_on/related_to legitimately shift when other requirements
        # are added/removed, so they don't count as churn.
        body = req.to_dict()
        body.pop("depends_on", None)
        body.pop("related_to", None)
        return body

    churned = [
        rid
        for rid in set(old_reqs) & set(new_reqs)
        if old_reqs[rid].requirement_text == new_reqs[rid].requirement_text
        and rid not in newly_clarified
        and analysis_body(old_reqs[rid]) != analysis_body(new_reqs[rid])
    ]
    if churned:
        warnings.append(
            "Carried-forward requirements changed without their text changing or a "
            f"new clarification landing: {', '.join(sorted(churned))} — unchanged "
            "requirements should be carried forward verbatim, not re-worded."
        )

    latest_entry_text = (
        str(_as_dict(new.meta.changelog[-1]).get("changes", ""))
        if new.meta.changelog
        else ""
    )
    unmentioned = [
        rid for rid in (added + removed + changed_text) if rid not in latest_entry_text
    ]
    if unmentioned:
        warnings.append(
            "The latest changelog entry doesn't mention these actually "
            f"added/removed/changed requirements: {', '.join(unmentioned)} — the "
            "changelog should name the real delta."
        )

    return errors, warnings
