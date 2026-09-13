import re

from orchestrator.validation.analysis_validator import (
    compare_with_previous,
    validate_analysis,
)
from orchestrator.validation.test_plan_validator import (
    compare_test_plan_with_previous,
    cross_validate_test_plan,
    validate_test_plan,
)


def _req(**overrides) -> dict:
    base = {
        "req_id": "REQ-001",
        "requirement_text": "Users can reset their password via an emailed link.",
        "acceptance_criteria_status": "Generated",
        "acceptance_criteria": "1. A reset link is emailed to the registered address.",
        "gaps": [],
        "recommendations": [],
        "depends_on": [],
        "related_to": [],
    }
    base.update(overrides)
    return base


def _gap(blocking: bool = False) -> dict:
    return {
        "description": "Link expiry is not stated.",
        "question": "How long should the reset link remain valid?",
        "blocking": blocking,
    }


def _meta(**overrides) -> dict:
    base = {
        "source_doc": "doc",
        "domain": "e-commerce checkout",
        "domain_evidence": "cart, payment, order terminology",
        "version": "1.0",
        "generated_date": "2026-07-25",
        "extraction_manifest": {"requirements_extracted": 1},
        "changelog": [{"version": "1.0", "date": "2026-07-25", "changes": "Initial analysis."}],
        "clarification_log": [],
        "nfr_analysis": "Performance (REQ-005): a response-time threshold is stated.",
        "compliance_analysis": "No compliance/regulatory obligations identified as applicable.",
        "executive_summary": "A short summary of what this document covers.",
        "in_scope": "Password reset.",
        "out_of_scope": "Payment processing.",
    }
    base.update(overrides)
    return base


def test_missing_executive_summary_and_scope_warn_only():
    errors, warnings = validate_analysis(
        {
            "meta": _meta(executive_summary="", in_scope="", out_of_scope=""),
            "requirements": [_req()],
            "release_history": [_release_entry()],
        }
    )
    assert errors == []
    assert any("meta.executive_summary is empty" in w for w in warnings)
    assert any("meta.in_scope and meta.out_of_scope are both empty" in w for w in warnings)


def _release_entry(**overrides) -> dict:
    base = {
        "version": "1.0",
        "date": "2026-07-25",
        "author": "Emvigo QA",
        "reviewed_by": "TBD – Client/Project Input Required",
        "reviewed_on": "",
        "approved_by": "TBD – Client/Project Input Required",
        "approved_on": "",
        "reasons": "Initial analysis.",
    }
    base.update(overrides)
    return base


def test_valid_analysis_passes():
    errors, warnings = validate_analysis(
        {"meta": _meta(), "requirements": [_req()], "release_history": [_release_entry()]}
    )
    assert errors == []
    assert warnings == []


def test_missing_release_history_is_warning_not_error_legacy_shape():
    errors, warnings = validate_analysis(
        {"meta": _meta(), "requirements": [_req()], "release_history": []}
    )
    assert errors == []
    assert any("release_history is empty" in w for w in warnings)


def test_release_history_version_mismatch_is_error():
    errors, _ = validate_analysis(
        {
            "meta": _meta(version="1.1", changelog=[{"version": "1.1", "date": "d", "changes": "x"}]),
            "requirements": [_req()],
            "release_history": [_release_entry(version="1.0")],
        }
    )
    assert any("release_history" in e and "1.1" in e for e in errors)


def test_release_history_over_long_reason_is_warning():
    _, warnings = validate_analysis(
        {
            "meta": _meta(),
            "requirements": [_req()],
            "release_history": [_release_entry(reasons="x" * 200)],
        }
    )
    assert any("120" in w for w in warnings)


def test_legacy_list_shape_passes_with_warning():
    errors, warnings = validate_analysis([_req()])
    assert errors == []
    assert any("Legacy shape" in w for w in warnings)


def test_meta_version_changelog_mismatch_is_error():
    errors, _ = validate_analysis(
        {"meta": _meta(version="1.1"), "requirements": [_req()]}
    )
    assert any("changelog" in e for e in errors)


def test_clarification_log_entry_missing_answer_is_error():
    meta = _meta(
        clarification_log=[{"req_id": "REQ-001", "question": "q", "answer": ""}]
    )
    errors, _ = validate_analysis({"meta": meta, "requirements": [_req()]})
    assert any("clarification_log" in e for e in errors)


def test_analysis_top_level_must_be_list():
    errors, _ = validate_analysis({"req_id": "REQ-001"})
    assert errors


def test_duplicate_req_id_is_error():
    errors, _ = validate_analysis([_req(), _req()])
    assert any("duplicate" in e for e in errors)


def test_invalid_status_is_error():
    # Hyphen instead of the required en dash — the most likely slip.
    errors, _ = validate_analysis(
        [_req(acceptance_criteria_status="Not Generated - Client Clarification Required")]
    )
    assert any("acceptance_criteria_status" in e for e in errors)


def test_gap_without_question_is_error():
    gap = _gap()
    gap["question"] = ""
    errors, _ = validate_analysis([_req(gaps=[gap])])
    assert any("client question" in e for e in errors)


def test_blocked_status_requires_blocking_gap():
    errors, _ = validate_analysis(
        [
            _req(
                acceptance_criteria_status="Not Generated – Client Clarification Required",
                acceptance_criteria="Cannot be generated until link expiry is clarified.",
                gaps=[_gap(blocking=False)],
            )
        ]
    )
    assert any("no gap is marked blocking" in e for e in errors)


def test_blocking_gap_requires_blocked_status():
    errors, _ = validate_analysis([_req(gaps=[_gap(blocking=True)])])
    assert any("blocking gap" in e for e in errors)


def test_noncontiguous_ids_warn_only():
    errors, warnings = validate_analysis(
        [_req(), _req(req_id="REQ-003")]
    )
    assert errors == []
    assert any("contiguous" in w for w in warnings)


def test_invalid_category_is_error():
    errors, _ = validate_analysis([_req(category="Security")])
    assert any("category" in e for e in errors)


def test_not_applicable_status_is_valid_for_compliance_category_only():
    # A Compliance item may be "Not Applicable" with no blocking gap.
    errors, _ = validate_analysis(
        [_req(req_id="CMP-REG-001", category="Compliance", acceptance_criteria_status="Not Applicable")]
    )
    assert errors == []

    # The same status on a Functional requirement is rejected.
    errors, _ = validate_analysis([_req(acceptance_criteria_status="Not Applicable")])
    assert any("acceptance_criteria_status" in e for e in errors)


def test_contiguity_is_checked_per_id_prefix():
    """A Compliance item's own "CMP-REG-" numbering starts fresh at 1 and
    must not be flattened into the "REQ-" sequence's own range."""
    errors, warnings = validate_analysis(
        [
            _req(req_id="REQ-001"),
            _req(req_id="REQ-002"),
            _req(req_id="CMP-REG-001", category="Compliance", acceptance_criteria_status="Not Applicable"),
        ]
    )
    assert errors == []
    assert not any("contiguous" in w for w in warnings)


def _minimal_test_plan(version: str = "1.0") -> dict:
    return {
        "meta": {
            "title": "Sample",
            "project_id": "TBD – Client/Project Input Required",
            "document_id": "TBD – Client/Project Input Required",
            "description": "d",
            "approved_date": "TBD",
            "master_template_id": "TBD – Client/Project Input Required",
            "prepared_by": "Emvigo Technologies",
            "prepared_date": "24-Jul-2026",
            "version": version,
        },
        "release_history": [
            {
                "version": "1.0",
                "date": "24-Jul-2026",
                "author": "Emvigo Technologies",
                "reviewed_by": "TBD – Client/Project Input Required",
                "reviewed_on": "TBD – Client/Project Input Required",
                "approved_by": "TBD – Client/Project Input Required",
                "approved_on": "TBD – Client/Project Input Required",
                "reasons": "Initial version.",
            }
        ],
        "introduction": {
            "purpose": "p",
            "project_overview": "o",
            "scope_in_areas": [{"area": "Auth", "items": ["Login"]}],
            "scope_in_non_functional": [],
            "scope_out": [],
            "reference_documents": [
                {"process_element": "Requirement document", "reference": "TBD – To be added by QA"}
            ],
        },
        "resources": {},
        "assumptions_dependencies_risks": {},
        "strategy": {
            "entry_criteria": ["Stable build available."],
            "exit_criteria": ["All planned cases executed."],
        },
        "schedule": [
            {
                "release": "R1",
                "sprint": "S1",
                "iteration": "1",
                "start_date": "TBD – Client/Project Input Required",
                "end_date": "TBD – Client/Project Input Required",
            }
        ],
        "deliverables": {},
        "closure": {},
    }


def test_valid_test_plan_passes():
    errors, warnings = validate_test_plan(_minimal_test_plan())
    assert errors == []
    assert warnings == []


def test_version_history_mismatch_is_error():
    errors, _ = validate_test_plan(_minimal_test_plan(version="2.0"))
    assert any("release_history" in e for e in errors)


def test_internal_path_leak_is_error():
    plan = _minimal_test_plan()
    plan["introduction"]["reference_documents"][0]["reference"] = (
        "output/requirement-analysis/doc-analysis.json"
    )
    errors, _ = validate_test_plan(plan)
    assert any("internal repository path" in e for e in errors)


def test_bare_requirement_ids_in_integration_sequence_warn():
    plan = _minimal_test_plan()
    plan["strategy"]["integration_sequence"] = [
        {"area": "Stage 1 — Authentication", "items": ["REQ-001", "CMP-REG-002"]}
    ]
    errors, warnings = validate_test_plan(plan)
    assert errors == []
    assert any("bare requirement IDs REQ-001, CMP-REG-002" in w for w in warnings)


def test_described_integration_sequence_items_do_not_warn():
    plan = _minimal_test_plan()
    plan["strategy"]["integration_sequence"] = [
        {
            "area": "Stage 1 — Authentication",
            "items": ["REQ-001 – Initial login interface", "Login before Logout"],
        }
    ]
    errors, warnings = validate_test_plan(plan)
    assert errors == []
    assert warnings == []


def test_nonstandard_tbd_marker_warns():
    plan = _minimal_test_plan()
    plan["introduction"]["purpose"] = "TBD - to be decided"
    errors, warnings = validate_test_plan(plan)
    assert errors == []
    assert any("non-standard TBD" in w for w in warnings)


def test_malformed_meta_structures_report_errors_not_crash():
    # meta as a list, changelog entries as strings, log entries as strings —
    # every one must surface as an ERROR line, never an exception.
    errors, _ = validate_analysis({"meta": [], "requirements": [_req()]})
    assert any("meta must be a JSON object" in e for e in errors)

    errors, _ = validate_analysis(
        {"meta": _meta(changelog=["not-a-dict"]), "requirements": [_req()]}
    )
    assert any("changelog entries must be JSON objects" in e for e in errors)

    errors, _ = validate_analysis(
        {"meta": _meta(clarification_log=["not-a-dict"]), "requirements": [_req()]}
    )
    assert any("clarification_log entry 1" in e for e in errors)

    errors, warnings = compare_with_previous(
        {"meta": _meta(changelog=["junk"]), "requirements": [_req()]},
        {"meta": _meta(clarification_log=["junk"]), "requirements": [_req()]},
    )
    assert isinstance(errors, list) and isinstance(warnings, list)


def test_reasked_question_is_error():
    meta = _meta(
        clarification_log=[
            {
                "req_id": "REQ-001",
                "question": "How long should the reset link remain valid?",
                "answer": "24 hours",
                "date": "2026-07-25",
            }
        ]
    )
    gap = {
        "description": "Link validity not stated.",
        "question": "How long should the reset link stay valid?",
        "blocking": False,
    }
    errors, _ = validate_analysis(
        {
            "meta": meta,
            "requirements": [
                _req(
                    acceptance_criteria_status="Generated with Assumptions",
                    acceptance_criteria="Assumptions...",
                    gaps=[gap],
                )
            ],
        }
    )
    assert any("re-asks" in e for e in errors)


def _versioned_analysis(version, changelog, requirements, clarification_log=None, release_history=None):
    return {
        "meta": _meta(
            version=version, changelog=changelog, clarification_log=clarification_log or []
        ),
        "requirements": requirements,
        "release_history": release_history if release_history is not None else [],
    }


def test_history_changelog_append_only():
    old = _versioned_analysis(
        "1.0", [{"version": "1.0", "date": "d", "changes": "Initial."}], [_req()]
    )
    new = _versioned_analysis(
        "1.1", [{"version": "1.1", "date": "d", "changes": "Rewrote."}], [_req()]
    )
    errors, _ = compare_with_previous(new, old)
    assert any("changelog lost entries" in e for e in errors)


def test_history_version_backwards_is_error():
    old = _versioned_analysis(
        "1.1",
        [
            {"version": "1.0", "date": "d", "changes": "Initial."},
            {"version": "1.1", "date": "d", "changes": "Rev."},
        ],
        [_req()],
    )
    new = _versioned_analysis(
        "1.0", [{"version": "1.0", "date": "d", "changes": "Initial."}], [_req()]
    )
    errors, _ = compare_with_previous(new, old)
    assert any("backwards" in e for e in errors)


def test_history_lost_clarification_answer_is_error():
    log = [{"req_id": "REQ-001", "question": "q", "answer": "a", "date": "d"}]
    old = _versioned_analysis(
        "1.0",
        [{"version": "1.0", "date": "d", "changes": "Initial."}],
        [_req()],
        clarification_log=log,
    )
    new = _versioned_analysis(
        "1.1",
        [
            {"version": "1.0", "date": "d", "changes": "Initial."},
            {"version": "1.1", "date": "d", "changes": "Rev."},
        ],
        [_req()],
    )
    errors, _ = compare_with_previous(new, old)
    assert any("clarification_log lost" in e for e in errors)


def test_history_churn_and_unnamed_delta_warn():
    changelog_v1 = [{"version": "1.0", "date": "d", "changes": "Initial."}]
    old = _versioned_analysis("1.0", changelog_v1, [_req()])
    # Same requirement text, reworded analysis; REQ-002 added but changelog
    # doesn't mention either.
    new = _versioned_analysis(
        "1.1",
        changelog_v1 + [{"version": "1.1", "date": "d", "changes": "Minor updates."}],
        [
            _req(acceptance_criteria="1. Reworded criteria."),
            _req(req_id="REQ-002"),
        ],
    )
    errors, warnings = compare_with_previous(new, old)
    assert errors == []
    assert any("carried-forward" in w.lower() for w in warnings)
    assert any("REQ-002" in w and "changelog" in w for w in warnings)


def test_history_same_version_is_in_run_iteration():
    changelog = [{"version": "1.0", "date": "d", "changes": "Initial."}]
    old = _versioned_analysis("1.0", changelog, [_req()])
    new = _versioned_analysis(
        "1.0", changelog, [_req(acceptance_criteria="1. Fixed wording.")]
    )
    errors, warnings = compare_with_previous(new, old)
    assert errors == []
    assert warnings == []


def test_release_history_lost_entry_is_error():
    changelog_v1 = [{"version": "1.0", "date": "d", "changes": "Initial."}]
    old = _versioned_analysis(
        "1.0", changelog_v1, [_req()], release_history=[_release_entry(version="1.0")]
    )
    new = _versioned_analysis(
        "1.1",
        changelog_v1 + [{"version": "1.1", "date": "d", "changes": "Rev."}],
        [_req()],
        release_history=[_release_entry(version="1.1", reasons="Regenerated.")],
    )
    errors, _ = compare_with_previous(new, old)
    assert any("release_history lost" in e for e in errors)


def test_test_plan_history_release_history_append_only():
    old = _minimal_test_plan()
    new = _minimal_test_plan(version="1.1")
    new["release_history"] = [
        {**old["release_history"][0], "version": "1.1", "reasons": "Rewritten."}
    ]
    errors, _ = compare_test_plan_with_previous(new, old)
    assert any("release_history lost entries" in e for e in errors)


def _analysis_for_cross(statuses: dict[str, str]) -> dict:
    return {
        "meta": _meta(),
        "requirements": [
            _req(
                req_id=rid,
                acceptance_criteria_status=status,
                acceptance_criteria=(
                    "Pending clarification."
                    if status.startswith("Not Generated")
                    else "1. Behaviour as stated."
                ),
                gaps=[_gap(blocking=True)] if status.startswith("Not Generated") else [],
            )
            for rid, status in statuses.items()
        ],
    }


def test_cross_validation_scope_coverage():
    plan = _minimal_test_plan()
    plan["introduction"]["scope_in_areas"] = [
        {"area": "Auth", "items": ["Login"], "req_ids": ["REQ-001"]}
    ]
    analysis = _analysis_for_cross(
        {"REQ-001": "Generated", "REQ-002": "Generated"}
    )
    errors, warnings = cross_validate_test_plan(plan, analysis)
    assert errors == []
    assert any("REQ-002" in w and "not covered" in w for w in warnings)


def test_cross_validation_unknown_req_id_is_error():
    plan = _minimal_test_plan()
    plan["introduction"]["scope_in_areas"] = [
        {"area": "Auth", "items": ["Login"], "req_ids": ["REQ-099"]}
    ]
    analysis = _analysis_for_cross({"REQ-001": "Generated"})
    errors, _ = cross_validate_test_plan(plan, analysis)
    assert any("REQ-099" in e for e in errors)


def test_cross_validation_blocked_req_must_be_surfaced():
    plan = _minimal_test_plan()
    plan["introduction"]["scope_in_areas"] = [
        {"area": "Auth", "items": ["Login"], "req_ids": ["REQ-001"]}
    ]
    analysis = _analysis_for_cross(
        {
            "REQ-001": "Generated",
            "REQ-002": "Not Generated – Client Clarification Required",
        }
    )
    errors, warnings = cross_validate_test_plan(plan, analysis)
    assert errors == []
    assert any("REQ-002" in w and "pending client clarification" in w for w in warnings)

    plan["assumptions_dependencies_risks"] = {
        "assumptions": ["REQ-002 is pending client clarification."],
        "dependencies": [],
        "risks": [],
    }
    _, warnings = cross_validate_test_plan(plan, analysis)
    assert not any("pending client clarification not mentioned" in w for w in warnings)


# --- release_history 'reasons' length ---------------------------------------


def test_long_release_reason_warns_but_does_not_block():
    """A 1084-character reason made a two-row table span three pages, with the
    cell text running over the footer. It is a formatting defect, not a
    correctness one, so it warns rather than blocking an otherwise-good
    regeneration."""
    from orchestrator.models.test_plan import MAX_RELEASE_REASON_CHARS

    plan = _minimal_test_plan()
    plan["release_history"][0]["reasons"] = "x" * (MAX_RELEASE_REASON_CHARS + 1)

    errors, warnings = validate_test_plan(plan)

    assert not any("reasons" in e for e in errors), "must not block generation"
    assert any(
        "'reasons'" in w and str(MAX_RELEASE_REASON_CHARS) in w for w in warnings
    ), warnings


def test_reason_at_the_limit_is_accepted_silently():
    from orchestrator.models.test_plan import MAX_RELEASE_REASON_CHARS

    plan = _minimal_test_plan()
    plan["release_history"][0]["reasons"] = "x" * MAX_RELEASE_REASON_CHARS

    _, warnings = validate_test_plan(plan)

    assert not any("'reasons'" in w for w in warnings)


def test_every_history_entry_is_checked_not_just_the_latest():
    from orchestrator.models.test_plan import MAX_RELEASE_REASON_CHARS

    plan = _minimal_test_plan(version="1.1")
    plan["release_history"][0]["reasons"] = "y" * (MAX_RELEASE_REASON_CHARS + 50)
    plan["release_history"].append(
        {**plan["release_history"][0], "version": "1.1", "reasons": "Short and concise."}
    )

    _, warnings = validate_test_plan(plan)

    assert any("v1.0" in w and "'reasons'" in w for w in warnings), warnings


def test_empty_reason_is_still_an_error_not_a_warning():
    """Shortening the field must not weaken the existing "must say something"
    rule at the other end."""
    plan = _minimal_test_plan()
    plan["release_history"][0]["reasons"] = "   "

    errors, _ = validate_test_plan(plan)

    assert any("empty 'reasons'" in e for e in errors)


def test_release_history_column_widths_fit_the_page():
    """Word will not shrink a fixed-layout table that overflows, so the widths
    must stay inside the usable page width."""
    import inspect

    from orchestrator.generation import test_plan_docx_writer as writer

    source = inspect.getsource(writer._build_version_control)
    match = re.search(r"widths_in=\[([0-9., ]+)\]", source)
    assert match, "could not locate the release-history column widths"
    widths = [float(v) for v in match.group(1).split(",") if v.strip()]

    assert len(widths) == 8, "the Release History table has eight columns"
    assert sum(widths) <= 6.67, f"widths sum to {sum(widths)}in, wider than the page"
    # Version must stay wide enough that its own header doesn't break mid-word.
    assert widths[0] >= 0.65, "Version column too narrow — its header will wrap"
    # Reasons is the only free-text column and must remain the widest.
    assert widths[-1] == max(widths), "Reasons should be the widest column"
