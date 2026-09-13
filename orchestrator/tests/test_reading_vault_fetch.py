"""Tests for /analyse-requirement's requirement input source -- combining
every .md file under the configured requirementReading vault into one
staged markdown document. No LLM authorship, no embeddings; just a
deterministic read-and-concatenate, same shape as requirement_handoff's
own tests."""

import pytest

from orchestrator.parsing import reading_vault_fetch


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    output_dir = tmp_path / "output" / "requirement-analysis"
    monkeypatch.setattr(
        reading_vault_fetch, "requirement_source_md_path", lambda doc_name: output_dir / f"{doc_name}-source.md"
    )
    return output_dir


def test_no_vault_configured_exits_1(isolated, monkeypatch, capsys):
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: None)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 1
    assert "not configured" in capsys.readouterr().err


def test_configured_vault_missing_on_disk_exits_1(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "does-not-exist"
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 1
    assert "does not exist" in capsys.readouterr().err


def test_no_md_files_exits_1(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "notes.txt").write_text("x", encoding="utf-8")  # not a candidate suffix
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 1
    assert "No .md files found" in capsys.readouterr().err


def test_single_md_file_is_staged_with_doc_name_from_vault_folder(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    (vault / "Checkout.md").write_text("The system shall allow checkout.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Requirements"
    assert f"source: {vault} (1 file combined)" in out

    staged = isolated / "Requirements-source.md"
    assert staged.exists()
    assert "## Source: Checkout.md" in staged.read_text(encoding="utf-8")
    assert "The system shall allow checkout." in staged.read_text(encoding="utf-8")


def test_multiple_md_files_are_combined_into_one_document(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    (vault / "Alpha.md").write_text("Alpha requirement text.", encoding="utf-8")
    (vault / "Beta.md").write_text("Beta requirement text.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "source: " in out and "(2 files combined)" in out

    combined = (isolated / "Requirements-source.md").read_text(encoding="utf-8")
    assert "## Source: Alpha.md" in combined
    assert "Alpha requirement text." in combined
    assert "## Source: Beta.md" in combined
    assert "Beta requirement text." in combined


def test_unchanged_content_does_not_rewrite_or_touch_mtime(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    (vault / "Alpha.md").write_text("Alpha requirement text.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit):
        reading_vault_fetch.main()
    staged = isolated / "Requirements-source.md"
    first_mtime = staged.stat().st_mtime_ns

    with pytest.raises(SystemExit):
        reading_vault_fetch.main()

    assert staged.stat().st_mtime_ns == first_mtime


def test_changed_content_rewrites_the_staged_file(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "Requirements"
    vault.mkdir()
    source = vault / "Alpha.md"
    source.write_text("Original text.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit):
        reading_vault_fetch.main()

    source.write_text("Revised text.", encoding="utf-8")
    with pytest.raises(SystemExit):
        reading_vault_fetch.main()

    staged = isolated / "Requirements-source.md"
    assert "Revised text." in staged.read_text(encoding="utf-8")
    assert "Original text." not in staged.read_text(encoding="utf-8")


def test_obsidian_bookkeeping_folder_is_excluded(isolated, monkeypatch, capsys, tmp_path):
    vault = tmp_path / "Requirements"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "config.md").write_text("x", encoding="utf-8")
    (vault / "Real.md").write_text("Real requirement.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "(1 file combined)" in out
    combined = (isolated / "Requirements-source.md").read_text(encoding="utf-8")
    assert "Real.md" in combined
    assert "config.md" not in combined


def test_any_dot_prefixed_folder_is_excluded(isolated, monkeypatch, capsys, tmp_path):
    """Same exclusion as .obsidian, generalized -- covers
    parsing.vault_writeback's own .history snapshot folder, which must
    never be re-ingested as fresh requirement content on the next run."""
    vault = tmp_path / "Requirements"
    (vault / ".history" / "Real.md").parent.mkdir(parents=True)
    (vault / ".history" / "Real.md").write_text("Stale pre-edit snapshot.", encoding="utf-8")
    (vault / "Real.md").write_text("Real requirement.", encoding="utf-8")
    monkeypatch.setattr(reading_vault_fetch, "requirement_reading_vault_path", lambda: vault)

    with pytest.raises(SystemExit) as exc:
        reading_vault_fetch.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "(1 file combined)" in out
    combined = (isolated / "Requirements-source.md").read_text(encoding="utf-8")
    assert "Real requirement." in combined
    assert "Stale pre-edit snapshot." not in combined
