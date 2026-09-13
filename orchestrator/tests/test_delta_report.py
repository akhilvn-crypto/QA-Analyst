import json

import pytest

from orchestrator.validation.delta_report import build_report


@pytest.fixture
def delta_env(tmp_path, monkeypatch):
    json_path = tmp_path / "doc-analysis.json"
    md_path = tmp_path / "doc-source.md"
    monkeypatch.setattr(
        "orchestrator.validation.delta_report.analysis_json_path",
        lambda doc: json_path,
    )
    monkeypatch.setattr(
        "orchestrator.validation.delta_report.requirement_source_md_path",
        lambda doc: md_path,
    )
    return json_path, md_path


def _analysis() -> dict:
    return {
        "meta": {"source_doc": "doc", "version": "1.0"},
        "requirements": [
            {
                "req_id": "REQ-001",
                "requirement_text": "As an Admin, I want to add Canvassers and assign permissions.",
                "source_ref": "US-001",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "x",
            },
            {
                "req_id": "REQ-002",
                "requirement_text": "Surveyors can upload roof photos from the mobile app.",
                "source_ref": "US-002",
                "acceptance_criteria_status": "Generated",
                "acceptance_criteria": "x",
            },
        ],
    }


def test_delta_report_statuses(delta_env):
    json_path, md_path = delta_env
    json_path.write_text(json.dumps(_analysis()), encoding="utf-8")
    # New revision: US-001 still present, US-002 gone, US-003 is new.
    md_path.write_text(
        "| US-001 | As an Admin, I want to add Canvassers and assign permissions. |\n"
        "| US-003 | Admins can export weekly lead reports. |\n",
        encoding="utf-8",
    )

    report = build_report("doc")
    by_id = {entry["req_id"]: entry for entry in report["requirements"]}

    assert by_id["REQ-001"]["status"] == "matched"
    assert by_id["REQ-001"]["source_ref_found"] is True
    assert by_id["REQ-002"]["status"] == "missing"
    assert "US-003" in report["unmatched_source_refs"]
    assert report["previous_version"] == "1.0"


def test_delta_report_requires_previous_analysis(delta_env):
    json_path, md_path = delta_env
    md_path.write_text("content", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        build_report("doc")
