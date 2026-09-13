from orchestrator.validation.test_case_validator import (
    compare_with_previous,
    cross_validate_test_cases,
    validate_test_cases,
)


def _step(n=1, **overrides):
    base = {
        "step_number": n,
        "action": "Click the Submit button.",
        "expected_result": "A confirmation message 'Order placed' is displayed.",
        "test_data": "",
    }
    base.update(overrides)
    return base


def _tc(**overrides):
    base = {
        "tc_id": "TC-001",
        "req_id": "REQ-001",
        "title": "Successful order submission",
        "objective": "Verify an order can be placed with valid details.",
        "test_type": "Positive",
        "priority": "High",
        "preconditions": "User is logged in as a Customer.",
        "steps": [_step()],
    }
    base.update(overrides)
    return base


def _meta(**overrides):
    base = {
        "source_doc": "doc",
        "version": "1.0",
        "generated_date": "2026-07-26",
        "changelog": [{"version": "1.0", "date": "2026-07-26", "changes": "Initial generation."}],
    }
    base.update(overrides)
    return base


def _release_entry(**overrides):
    base = {
        "version": "1.0",
        "date": "2026-07-26",
        "author": "Emvigo QA",
        "reviewed_by": "TBD – Client/Project Input Required",
        "reviewed_on": "",
        "approved_by": "TBD – Client/Project Input Required",
        "approved_on": "",
        "reasons": "Initial test case generation.",
    }
    base.update(overrides)
    return base


def _payload(**overrides):
    """A full, cleanly-valid test-cases payload (meta, test_cases,
    not_covered, release_history) -- individual tests override just the
    field(s) they're exercising."""
    base = {
        "meta": _meta(),
        "test_cases": [_tc()],
        "not_covered": [],
        "release_history": [_release_entry()],
    }
    base.update(overrides)
    return base


def test_valid_document_passes():
    errors, warnings = validate_test_cases(_payload())
    assert errors == []
    assert warnings == []


def test_top_level_must_be_object():
    errors, _ = validate_test_cases([_tc()])
    assert errors


def test_meta_version_changelog_mismatch_is_error():
    errors, _ = validate_test_cases(_payload(meta=_meta(version="1.1")))
    assert any("changelog" in e for e in errors)


def test_empty_changelog_is_error():
    errors, _ = validate_test_cases(_payload(meta=_meta(changelog=[])))
    assert any("changelog" in e for e in errors)


def test_duplicate_tc_id_is_error():
    errors, _ = validate_test_cases(_payload(test_cases=[_tc(), _tc(steps=[_step()])]))
    assert any("duplicate" in e for e in errors)


def test_invalid_priority_is_error():
    errors, _ = validate_test_cases(_payload(test_cases=[_tc(priority="Urgent")]))
    assert any("priority" in e for e in errors)


def test_unknown_test_type_is_warning_not_error():
    errors, warnings = validate_test_cases(_payload(test_cases=[_tc(test_type="Smoke")]))
    assert errors == []
    assert any("test_type" in w for w in warnings)


def test_expanded_known_test_types_do_not_warn():
    for test_type in ("Edge", "Integration", "Security", "Database", "API"):
        errors, warnings = validate_test_cases(_payload(test_cases=[_tc(test_type=test_type)]))
        assert errors == []
        assert warnings == [], f"{test_type} should be a known type, got warnings: {warnings}"


def test_test_case_with_no_steps_is_error():
    errors, _ = validate_test_cases(_payload(test_cases=[_tc(steps=[])]))
    assert any("no steps" in e for e in errors)


def test_non_contiguous_step_numbers_is_error():
    errors, _ = validate_test_cases(_payload(test_cases=[_tc(steps=[_step(1), _step(3)])]))
    assert any("contiguous" in e for e in errors)


def test_empty_action_is_error():
    errors, _ = validate_test_cases(_payload(test_cases=[_tc(steps=[_step(action="")])]))
    assert any("no action" in e for e in errors)


def test_vague_expected_result_is_warning():
    _, warnings = validate_test_cases(
        _payload(test_cases=[_tc(steps=[_step(expected_result="Works correctly")])])
    )
    assert any("vague" in w for w in warnings)


def test_compound_action_is_warning():
    _, warnings = validate_test_cases(
        _payload(test_cases=[_tc(steps=[_step(action="Enter username and click login")])])
    )
    assert any("compound" in w for w in warnings)


def test_not_covered_entry_missing_reason_is_error():
    errors, _ = validate_test_cases(
        _payload(test_cases=[], not_covered=[{"req_id": "REQ-002", "reason": ""}])
    )
    assert any("reason" in e for e in errors)


# --- Document Version Control / Release History (ISO-audit sheet fields) ---

def test_missing_release_history_is_warning_not_error_legacy_shape():
    """A file written before the controlled-document fields existed must
    still validate cleanly (warning only) -- backward compatibility with
    every test-cases.json generated before this feature."""
    errors, warnings = validate_test_cases(_payload(release_history=[]))
    assert errors == []
    assert any("release_history is empty" in w for w in warnings)


def test_release_history_version_mismatch_is_error():
    errors, _ = validate_test_cases(
        _payload(meta=_meta(version="1.1"), release_history=[_release_entry(version="1.0")])
    )
    assert any("release_history" in e and "1.1" in e for e in errors)


def test_release_history_empty_reasons_is_error():
    errors, _ = validate_test_cases(_payload(release_history=[_release_entry(reasons="")]))
    assert any("empty" in e and "reasons" in e for e in errors)


def test_release_history_over_long_reason_is_warning():
    _, warnings = validate_test_cases(
        _payload(release_history=[_release_entry(reasons="x" * 200)])
    )
    assert any("120" in w for w in warnings)


def test_release_history_duplicate_versions_is_warning():
    _, warnings = validate_test_cases(
        _payload(
            release_history=[
                _release_entry(version="1.0"),
                _release_entry(version="1.0", date="2026-07-27"),
            ]
        )
    )
    assert any("duplicate" in w for w in warnings)


# --- cross-validation against the sibling analysis JSON ---

def _analysis_req(req_id="REQ-001", status="Generated"):
    return {
        "req_id": req_id,
        "requirement_text": "Some requirement.",
        "acceptance_criteria_status": status,
        "acceptance_criteria": "Some criteria.",
        "gaps": [],
        "recommendations": [],
        "depends_on": [],
        "related_to": [],
    }


def test_cross_validate_flags_test_case_for_unknown_requirement():
    data = {"test_cases": [_tc(req_id="REQ-999")], "not_covered": []}
    analysis = {"requirements": [_analysis_req()]}
    errors, _ = cross_validate_test_cases(data, analysis)
    assert any("REQ-999" in e for e in errors)


def test_cross_validate_warns_on_missing_coverage():
    data = {"test_cases": [], "not_covered": []}
    analysis = {"requirements": [_analysis_req(status="Generated")]}
    _, warnings = cross_validate_test_cases(data, analysis)
    assert any("coverage gap" in w for w in warnings)


def test_cross_validate_warns_when_blocked_requirement_missing_from_not_covered():
    data = {"test_cases": [], "not_covered": []}
    analysis = {
        "requirements": [
            _analysis_req(status="Not Generated – Client Clarification Required")
        ]
    }
    _, warnings = cross_validate_test_cases(data, analysis)
    assert any("Blocked" in w for w in warnings)


def test_cross_validate_errors_when_blocked_requirement_has_test_case():
    data = {"test_cases": [_tc(req_id="REQ-001")], "not_covered": []}
    analysis = {
        "requirements": [
            _analysis_req(status="Not Generated – Client Clarification Required")
        ]
    }
    errors, _ = cross_validate_test_cases(data, analysis)
    assert any("Blocked" in e for e in errors)


def test_cross_validate_passes_when_coverage_is_complete():
    data = {"test_cases": [_tc(req_id="REQ-001")], "not_covered": [{"req_id": "REQ-002", "reason": "Blocked."}]}
    analysis = {
        "requirements": [
            _analysis_req("REQ-001", "Generated"),
            _analysis_req("REQ-002", "Not Generated – Client Clarification Required"),
        ]
    }
    errors, warnings = cross_validate_test_cases(data, analysis)
    assert errors == []
    assert warnings == []


# --- version history ---

def test_version_regression_is_error():
    old = {"meta": _meta(version="1.1", changelog=[{"version": "1.1", "date": "d", "changes": "x"}]), "test_cases": [], "not_covered": []}
    new = {"meta": _meta(version="1.0"), "test_cases": [], "not_covered": []}
    errors, _ = compare_with_previous(new, old)
    assert any("backwards" in e for e in errors)


def test_lost_changelog_entry_is_error():
    old = {
        "meta": _meta(
            version="1.0",
            changelog=[
                {"version": "1.0", "date": "d", "changes": "Initial generation."},
            ],
        ),
        "test_cases": [],
        "not_covered": [],
    }
    new = {
        "meta": _meta(
            version="1.1",
            changelog=[{"version": "1.1", "date": "d2", "changes": "Regenerated for new scope."}],
        ),
        "test_cases": [],
        "not_covered": [],
    }
    errors, _ = compare_with_previous(new, old)
    assert any("append-only" in e for e in errors)


def test_same_version_iteration_skips_revision_checks():
    old = {"meta": _meta(version="1.0"), "test_cases": [], "not_covered": []}
    new = {"meta": _meta(version="1.0", changelog=[]), "test_cases": [], "not_covered": []}
    # Same version = in-run iteration; changelog-append-only check doesn't apply.
    errors, _ = compare_with_previous(new, old)
    assert errors == []


def test_lost_release_history_entry_is_error():
    old = {
        "meta": _meta(version="1.0"),
        "test_cases": [],
        "not_covered": [],
        "release_history": [_release_entry(version="1.0")],
    }
    new = {
        "meta": _meta(version="1.1", changelog=[{"version": "1.1", "date": "d", "changes": "x"}]),
        "test_cases": [],
        "not_covered": [],
        "release_history": [_release_entry(version="1.1", reasons="Regenerated.")],
    }
    errors, _ = compare_with_previous(new, old)
    assert any("release_history" in e and "append-only" in e for e in errors)
