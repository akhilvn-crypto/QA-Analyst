"""Tests for /handoff-requirement's backing script -- a pure file copy from
the already-reviewed analysis .md to this project's configured Obsidian
destination. No LLM authorship, no JSON reasoning; just a guarded copy."""

import pytest

from orchestrator.generation import requirement_handoff


def test_handoff_raises_when_source_md_missing(tmp_path, monkeypatch):
    missing = tmp_path / "Doc-analysis.md"
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: missing)

    with pytest.raises(FileNotFoundError):
        requirement_handoff.handoff("Doc")


def test_handoff_raises_when_destination_not_configured(tmp_path, monkeypatch):
    source = tmp_path / "Doc-analysis.md"
    source.write_text("# Report\n", encoding="utf-8")
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: None)

    with pytest.raises(RuntimeError):
        requirement_handoff.handoff("Doc")


def test_handoff_copies_file_and_leaves_original_in_place(tmp_path, monkeypatch):
    source = tmp_path / "output" / "requirement-analysis" / "Doc-analysis.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Report\n\nContent.\n", encoding="utf-8")
    destination_dir = tmp_path / "vault" / "Requirements"
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc")

    assert destination == destination_dir / "Doc-analysis.md"
    assert destination.read_text(encoding="utf-8") == "# Report\n\nContent.\n"
    assert source.exists()  # copy, never a move


def test_handoff_creates_destination_dir_if_missing(tmp_path, monkeypatch):
    source = tmp_path / "Doc-analysis.md"
    source.write_text("content", encoding="utf-8")
    destination_dir = tmp_path / "does" / "not" / "exist" / "yet"
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc")

    assert destination.exists()


def test_handoff_refuses_to_overwrite_differing_content_without_force(tmp_path, monkeypatch):
    source = tmp_path / "Doc-analysis.md"
    source.write_text("new content", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    destination_dir.mkdir()
    (destination_dir / "Doc-analysis.md").write_text("edited in obsidian", encoding="utf-8")
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    with pytest.raises(FileExistsError):
        requirement_handoff.handoff("Doc")

    # Refused -- the edited copy must survive untouched.
    assert (destination_dir / "Doc-analysis.md").read_text(encoding="utf-8") == "edited in obsidian"


def test_handoff_force_overwrites_differing_content(tmp_path, monkeypatch):
    source = tmp_path / "Doc-analysis.md"
    source.write_text("new content", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    destination_dir.mkdir()
    (destination_dir / "Doc-analysis.md").write_text("edited in obsidian", encoding="utf-8")
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc", force=True)

    assert destination.read_text(encoding="utf-8") == "new content"


def test_handoff_allows_rewrite_when_destination_content_already_identical(tmp_path, monkeypatch):
    source = tmp_path / "Doc-analysis.md"
    source.write_text("same content", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    destination_dir.mkdir()
    (destination_dir / "Doc-analysis.md").write_text("same content", encoding="utf-8")
    monkeypatch.setattr(requirement_handoff, "analysis_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc")  # no --force needed

    assert destination.read_text(encoding="utf-8") == "same content"


def test_handoff_clarifications_target_copies_the_sheet_md(tmp_path, monkeypatch):
    source = tmp_path / "Doc-clarifications.md"
    source.write_text("| Requirement ID | ... |\n", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    monkeypatch.setattr(requirement_handoff, "clarification_sheet_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc", target="clarifications")

    assert destination == destination_dir / "Doc-clarifications.md"
    assert destination.read_text(encoding="utf-8") == "| Requirement ID | ... |\n"


def test_handoff_clarifications_target_error_hints_at_generate_clarification_sheet(tmp_path, monkeypatch):
    missing = tmp_path / "Doc-clarifications.md"
    monkeypatch.setattr(requirement_handoff, "clarification_sheet_md_path", lambda doc: missing)

    with pytest.raises(FileNotFoundError, match="/generate-clarification-sheet"):
        requirement_handoff.handoff("Doc", target="clarifications")


def test_handoff_test_plan_target_copies_the_plan_md(tmp_path, monkeypatch):
    source = tmp_path / "Doc-test-plan.md"
    source.write_text("# Test Plan for Doc\n", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    monkeypatch.setattr(requirement_handoff, "test_plan_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc", target="test-plan")

    assert destination == destination_dir / "Doc-test-plan.md"
    assert destination.read_text(encoding="utf-8") == "# Test Plan for Doc\n"


def test_handoff_test_plan_target_error_hints_at_generate_test_plan(tmp_path, monkeypatch):
    missing = tmp_path / "Doc-test-plan.md"
    monkeypatch.setattr(requirement_handoff, "test_plan_md_path", lambda doc: missing)

    with pytest.raises(FileNotFoundError, match="/generate-test-plan"):
        requirement_handoff.handoff("Doc", target="test-plan")


def test_handoff_test_cases_target_copies_the_test_cases_md(tmp_path, monkeypatch):
    source = tmp_path / "Doc-test-cases.md"
    source.write_text("# Test Cases for Doc\n", encoding="utf-8")
    destination_dir = tmp_path / "vault"
    monkeypatch.setattr(requirement_handoff, "test_cases_md_path", lambda doc: source)
    monkeypatch.setattr(requirement_handoff, "requirement_handoff_destination_path", lambda: destination_dir)

    destination = requirement_handoff.handoff("Doc", target="test-cases")

    assert destination == destination_dir / "Doc-test-cases.md"
    assert destination.read_text(encoding="utf-8") == "# Test Cases for Doc\n"


def test_handoff_test_cases_target_error_hints_at_generate_test_cases(tmp_path, monkeypatch):
    missing = tmp_path / "Doc-test-cases.md"
    monkeypatch.setattr(requirement_handoff, "test_cases_md_path", lambda doc: missing)

    with pytest.raises(FileNotFoundError, match="/generate-test-cases"):
        requirement_handoff.handoff("Doc", target="test-cases")


def test_handoff_rejects_an_unknown_target(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        requirement_handoff.handoff("Doc", target="bogus")
