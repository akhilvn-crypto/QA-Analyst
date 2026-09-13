"""Tests for the per-deliverable execution-log audit trail
(`orchestrator.utils.execution_log`) -- who/when a controlled revision
happened, distinct from `history/`'s own file-copy archive."""

import json

import pytest

from orchestrator.utils import config, execution_log


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Same isolation `test_config.py` uses -- point config_path() at a
    scratch file so `operator_info()` never reads this repo's own
    config/settings.json."""
    cfg_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    yield cfg_path
    config.load_config.cache_clear()


def _entries(deliverable_dir):
    return json.loads((deliverable_dir / "execution-log" / "execution-log.json").read_text(encoding="utf-8"))


def test_record_first_generation_is_action_created(tmp_path, isolated_config):
    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")

    entries = _entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["action"] == "created"
    assert entries[0]["version"] == {"from": None, "to": "1.0"}
    assert entries[0]["timestamp_ist"].endswith("IST")


def test_record_revision_is_action_updated_and_appends(tmp_path, isolated_config):
    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")
    execution_log.record(tmp_path, "Doc-analysis.md", from_version="1.0", to_version="1.1")

    entries = _entries(tmp_path)
    assert len(entries) == 2
    assert entries[1]["action"] == "updated"
    assert entries[1]["version"] == {"from": "1.0", "to": "1.1"}


def test_record_uses_tbd_placeholder_when_operator_unconfigured(tmp_path, isolated_config):
    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")

    entry = _entries(tmp_path)[0]
    assert entry["changed_by"] == execution_log.TBD
    assert entry["designation"] == execution_log.TBD
    assert entry["project_name"] == execution_log.TBD
    assert entry["project_id"] == execution_log.TBD


def test_record_uses_configured_operator_identity(tmp_path, isolated_config):
    isolated_config.write_text(
        json.dumps(
            {
                "operator": {
                    "name": "Akhil VN",
                    "designation": "QA Lead",
                    "projectName": "LinkGrid",
                    "projectId": "LG-001",
                }
            }
        ),
        encoding="utf-8",
    )

    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")

    entry = _entries(tmp_path)[0]
    assert entry["changed_by"] == "Akhil VN"
    assert entry["designation"] == "QA Lead"
    assert entry["project_name"] == "LinkGrid"
    assert entry["project_id"] == "LG-001"


def test_record_renders_md_table_alongside_json(tmp_path, isolated_config):
    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")

    md = (tmp_path / "execution-log" / "execution-log.md").read_text(encoding="utf-8")
    assert "# Execution Log" in md
    assert "Doc-analysis.md" in md
    assert "created" in md


def test_record_survives_a_corrupt_existing_log(tmp_path, isolated_config):
    log_dir = tmp_path / "execution-log"
    log_dir.mkdir()
    (log_dir / "execution-log.json").write_text("not valid json", encoding="utf-8")

    execution_log.record(tmp_path, "Doc-analysis.md", from_version=None, to_version="1.0")

    assert len(_entries(tmp_path)) == 1


def test_latest_history_version_none_when_no_history(tmp_path):
    assert execution_log.latest_history_version(tmp_path / "history", "Doc-analysis", ".json") is None


def test_latest_history_version_picks_highest(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "Doc-analysis-v1.0.json").write_text("{}", encoding="utf-8")
    (history_dir / "Doc-analysis-v1.9.json").write_text("{}", encoding="utf-8")
    (history_dir / "Doc-analysis-v1.10.json").write_text("{}", encoding="utf-8")

    # Numeric compare, not lexicographic -- "1.10" outranks "1.9".
    assert execution_log.latest_history_version(history_dir, "Doc-analysis", ".json") == "1.10"


def test_record_json_deliverable_first_generation(tmp_path, isolated_config):
    json_path = tmp_path / "Doc-analysis.json"
    json_path.write_text(json.dumps({"meta": {"version": "1.0"}}), encoding="utf-8")

    execution_log.record_json_deliverable(json_path)

    entries = _entries(tmp_path)
    assert len(entries) == 1
    assert entries[0]["version"] == {"from": None, "to": "1.0"}
    assert entries[0]["action"] == "created"


def test_record_json_deliverable_reads_from_version_from_history(tmp_path, isolated_config):
    json_path = tmp_path / "Doc-analysis.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "Doc-analysis-v1.0.json").write_text("{}", encoding="utf-8")
    json_path.write_text(json.dumps({"meta": {"version": "1.1"}}), encoding="utf-8")

    execution_log.record_json_deliverable(json_path)

    entries = _entries(tmp_path)
    assert entries[0]["version"] == {"from": "1.0", "to": "1.1"}
    assert entries[0]["action"] == "updated"


def test_record_json_deliverable_skips_duplicate_same_version_redraft(tmp_path, isolated_config):
    json_path = tmp_path / "Doc-analysis.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "Doc-analysis-v1.0.json").write_text("{}", encoding="utf-8")
    json_path.write_text(json.dumps({"meta": {"version": "1.1"}}), encoding="utf-8")

    execution_log.record_json_deliverable(json_path)
    # An in-run redraft that leaves meta.version unchanged and doesn't touch
    # history/ (snapshot-output.sh skips those) must not log a second time.
    json_path.write_text(json.dumps({"meta": {"version": "1.1"}, "extra": "fix"}), encoding="utf-8")
    execution_log.record_json_deliverable(json_path)

    assert len(_entries(tmp_path)) == 1


def test_record_json_deliverable_missing_file_is_noop(tmp_path, isolated_config):
    execution_log.record_json_deliverable(tmp_path / "does-not-exist.json")

    assert not (tmp_path / "execution-log").exists()
