"""Tests for /apply-clarifications' vault note write-back -- the snapshot
half only (the rewrite itself is authored prose, done by the agent's own
Edit call, not this module). No LLM authorship, no embeddings; a
deterministic archive-before-edit copy, same shape as
test_reading_vault_fetch.py's own tests."""

import pytest

from orchestrator.parsing import vault_writeback


def test_no_requirements_folder_exits_1(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(vault_writeback, "requirements_path", lambda: None)
    monkeypatch.setattr(sys, "argv", ["prog", "snapshot", "Note.md"])

    with pytest.raises(SystemExit) as exc:
        vault_writeback.main()

    assert exc.value.code == 1
    assert "No Requirements/ folder" in capsys.readouterr().err


def test_missing_file_exits_1(monkeypatch, capsys, tmp_path):
    import sys

    vault = tmp_path / "Requirements"
    vault.mkdir()
    monkeypatch.setattr(vault_writeback, "requirements_path", lambda: vault)
    monkeypatch.setattr(sys, "argv", ["prog", "snapshot", "Missing.md"])

    with pytest.raises(SystemExit) as exc:
        vault_writeback.main()

    assert exc.value.code == 1
    assert "No such file" in capsys.readouterr().err


def test_path_traversal_outside_vault_exits_1(monkeypatch, capsys, tmp_path):
    import sys

    vault = tmp_path / "Requirements"
    vault.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Not in the vault.", encoding="utf-8")
    monkeypatch.setattr(vault_writeback, "requirements_path", lambda: vault)
    monkeypatch.setattr(sys, "argv", ["prog", "snapshot", "../outside.md"])

    with pytest.raises(SystemExit) as exc:
        vault_writeback.main()

    assert exc.value.code == 1
    assert "outside the vault" in capsys.readouterr().err


def test_successful_snapshot_copies_content_byte_for_byte(tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    note = vault / "Checkout.md"
    note.write_text("The system shall allow checkout within 3 clicks.", encoding="utf-8")

    dest = vault_writeback.snapshot(vault, "Checkout.md")

    assert dest.is_file()
    assert dest.parent == vault / ".history"
    assert dest.read_text(encoding="utf-8") == note.read_text(encoding="utf-8")


def test_second_snapshot_never_clobbers_the_first(tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    note = vault / "Checkout.md"
    note.write_text("Version A.", encoding="utf-8")

    first = vault_writeback.snapshot(vault, "Checkout.md")
    second = vault_writeback.snapshot(vault, "Checkout.md")

    assert first != second
    assert first.is_file()
    assert second.is_file()
    assert first.read_text(encoding="utf-8") == "Version A."
    assert second.read_text(encoding="utf-8") == "Version A."


def test_nested_relative_path_preserves_subfolder_structure(tmp_path):
    vault = tmp_path / "Requirements"
    (vault / "Checkout").mkdir(parents=True)
    note = vault / "Checkout" / "Payment.md"
    note.write_text("The system shall support card payments.", encoding="utf-8")

    dest = vault_writeback.snapshot(vault, "Checkout/Payment.md")

    assert dest.parent == vault / ".history" / "Checkout"
    assert dest.read_text(encoding="utf-8") == note.read_text(encoding="utf-8")


def test_history_folder_is_dot_prefixed(tmp_path):
    """Deliberate: .history (not history) is what makes
    reading_vault_fetch and knowledge_base.search's existing dot-directory
    exclusion cover it for free."""
    vault = tmp_path / "Requirements"
    vault.mkdir()
    (vault / "Note.md").write_text("Text.", encoding="utf-8")

    dest = vault_writeback.snapshot(vault, "Note.md")

    assert ".history" in dest.parts
