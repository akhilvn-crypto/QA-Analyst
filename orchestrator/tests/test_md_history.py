"""Tests for the shared history-archiving helper every plain-text Markdown
report writer in `generation/` uses (see md_history.py's own docstring for
which writers and why)."""

import json

import pytest

from orchestrator.utils import config
from orchestrator.utils.md_history import (
    bullet_version_extractor,
    release_history_version_extractor,
    snapshot_previous_md,
)


@pytest.fixture
def isolated_config(monkeypatch, tmp_path_factory):
    """Points operator_info() (read by execution_log.record, which
    snapshot_previous_md now calls whenever `new_content` is given) at a
    scratch settings file, so these tests never touch this repo's own
    config/settings.json."""
    cfg_path = tmp_path_factory.mktemp("cfg") / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    yield cfg_path
    config.load_config.cache_clear()


def test_bullet_version_extractor_reads_the_labeled_bullet():
    extract = bullet_version_extractor("Document Version", marker="*")
    content = "* **Project Name:** Doc\n* **Document Version:** 3.1\n* **Prepared By:** Emvigo QA\n"
    assert extract(content) == "3.1"


def test_bullet_version_extractor_missing_bullet_returns_none():
    extract = bullet_version_extractor("Document Version", marker="*")
    assert extract("* **Project Name:** Doc\n") is None


def test_bullet_version_extractor_respects_marker_and_label():
    # A "-" marker must not match a "*" bullet, and a "Version" label must
    # not match a "Document Version" one -- both are real distinct
    # conventions used by different reports in this project.
    extract = bullet_version_extractor("Version", marker="-")
    assert extract("* **Document Version:** 1.0\n") is None
    assert extract("- **Version:** 1.0\n") == "1.0"


def test_release_history_version_extractor_reads_the_last_row():
    columns = ["Version", "Date", "Author"]
    extract = release_history_version_extractor(columns)
    content = "\n".join(
        [
            "## B. Document Release History",
            "| Version | Date | Author |",
            "| --- | --- | --- |",
            "| 1.0 | 2026-01-01 | Emvigo QA |",
            "| 1.1 | 2026-02-01 | Emvigo QA |",
            "",
            "## C. Next Section",
        ]
    )
    assert extract(content) == "1.1"


def test_release_history_version_extractor_missing_table_returns_none():
    extract = release_history_version_extractor(["Version", "Date", "Author"])
    assert extract("# Just a title\n\nSome text.\n") is None


def test_snapshot_previous_md_no_op_when_file_missing(tmp_path):
    snapshot_previous_md(tmp_path / "does-not-exist.md", lambda content: "1.0")
    assert not (tmp_path / "history").exists()


def test_snapshot_previous_md_archives_with_extracted_version(tmp_path):
    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content v1", encoding="utf-8")

    snapshot_previous_md(md_path, lambda content: "1.0")

    snapshots = list((tmp_path / "history").glob("Doc-report-v1.0_*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "content v1"


def test_snapshot_previous_md_falls_back_to_unversioned(tmp_path):
    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content", encoding="utf-8")

    snapshot_previous_md(md_path, lambda content: None)

    snapshots = list((tmp_path / "history").glob("Doc-report-vunversioned_*.md"))
    assert len(snapshots) == 1


def test_snapshot_previous_md_never_clobbers_an_existing_snapshot(tmp_path, monkeypatch):
    import orchestrator.utils.md_history as md_history

    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content", encoding="utf-8")

    # Freeze the timestamp so two snapshots in a row would otherwise collide.
    monkeypatch.setattr(md_history.time, "strftime", lambda fmt, t: "20260101-000000")

    snapshot_previous_md(md_path, lambda content: "1.0")
    md_path.write_text("content, edited", encoding="utf-8")
    snapshot_previous_md(md_path, lambda content: "1.0")

    history_dir = tmp_path / "history"
    assert (history_dir / "Doc-report-v1.0_20260101-000000.md").read_text(encoding="utf-8") == "content"
    assert (history_dir / "Doc-report-v1.0_20260101-000000-1.md").read_text(encoding="utf-8") == "content, edited"


def test_snapshot_previous_md_survives_a_failed_copy(tmp_path, monkeypatch, capsys):
    """Snapshotting must never cost a run its actual deliverable -- a
    failure to archive is a warning, never an exception."""
    import orchestrator.utils.md_history as md_history

    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content", encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(md_history.shutil, "copy2", _boom)

    snapshot_previous_md(md_path, lambda content: "1.0")  # must not raise

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "disk full" in captured.err


def test_snapshot_previous_md_logs_created_on_first_generation(tmp_path, isolated_config):
    md_path = tmp_path / "Doc-report.md"

    snapshot_previous_md(md_path, lambda content: "1.0", new_content="content v1")

    entries = json.loads((tmp_path / "execution-log" / "execution-log.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["action"] == "created"
    assert entries[0]["version"] == {"from": None, "to": "1.0"}


def test_snapshot_previous_md_logs_updated_with_old_and_new_version(tmp_path, isolated_config):
    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content v1", encoding="utf-8")

    snapshot_previous_md(md_path, lambda content: "1.0" if "v1" in content else "1.1", new_content="content v2")

    entries = json.loads((tmp_path / "execution-log" / "execution-log.json").read_text(encoding="utf-8"))
    assert entries[-1]["action"] == "updated"
    assert entries[-1]["version"] == {"from": "1.0", "to": "1.1"}


def test_snapshot_previous_md_skips_execution_log_when_new_content_omitted(tmp_path, isolated_config):
    md_path = tmp_path / "Doc-report.md"
    md_path.write_text("content", encoding="utf-8")

    snapshot_previous_md(md_path, lambda content: "1.0")

    assert not (tmp_path / "execution-log").exists()
