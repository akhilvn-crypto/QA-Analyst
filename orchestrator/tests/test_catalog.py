"""Tests for the Knowledge Catalog build -- the deterministic replacement
for the old Knowledge Base Service. No process, no HTTP, no lifecycle: a
catalog build reads `Knowledge Base/` once and writes one JSON file."""

import json

import pytest

from orchestrator.knowledge_base import catalog
from orchestrator.utils import paths, workspace


@pytest.fixture
def empty_workspace(monkeypatch, tmp_path):
    """An attached folder with no `Knowledge Base/` subfolder."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(paths, "WORKSPACE_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """An attached folder with a `Knowledge Base/` subfolder."""
    kb = tmp_path / "Knowledge Base"
    kb.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(paths, "WORKSPACE_ROOT", tmp_path)
    return kb, tmp_path


# --- build_catalog_entry -----------------------------------------------------


def test_purpose_is_the_first_paragraph_before_any_heading():
    entry = catalog.build_catalog_entry(
        "architecture.md",
        "System architecture, services, components and integrations.\n\n"
        "## Services\ndetails\n## Dependencies\nmore\n",
    )
    assert entry.purpose == "System architecture, services, components and integrations."
    assert entry.description == "Covers: Services, Dependencies."


def test_purpose_is_the_first_headings_own_leading_paragraph_when_no_preamble():
    entry = catalog.build_catalog_entry(
        "workflows.md", "# Workflows\nExisting system and business workflows.\n## Detail\nx\n"
    )
    assert entry.purpose == "Existing system and business workflows."
    assert entry.description == "Covers: Workflows, Detail."


def test_description_uses_the_leaf_of_each_heading_trail_deduplicated():
    entry = catalog.build_catalog_entry(
        "a.md", "# Rules\nintro\n## KYC\nbody\n## KYC\nbody again\n"
    )
    assert entry.description == "Covers: Rules, KYC."


def test_headingless_file_falls_back_to_its_second_paragraph_as_description():
    entry = catalog.build_catalog_entry(
        "flat.md", "Just a flat note with no headings at all.\n\nSecond paragraph with more detail.\n"
    )
    assert entry.purpose == "Just a flat note with no headings at all."
    assert entry.description == "Second paragraph with more detail."


def test_single_paragraph_headingless_file_has_no_description():
    entry = catalog.build_catalog_entry("flat.md", "Just one short paragraph, nothing else.\n")
    assert entry.purpose == "Just one short paragraph, nothing else."
    assert entry.description == ""


# --- build_catalog / main -----------------------------------------------------


def test_build_catalog_covers_every_readable_note(vault):
    folder, _ = vault
    (folder / "business_rules.md").write_text(
        "Business rules and constraints.\n\n## Validation\ndetails\n", encoding="utf-8"
    )
    (folder / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8 \xff")

    entries = catalog.build_catalog(folder)

    assert [e.name for e in entries] == ["business_rules.md"]
    assert entries[0].purpose == "Business rules and constraints."


def test_main_without_a_knowledge_base_folder_exits_1_and_writes_nothing(empty_workspace, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog"])

    with pytest.raises(SystemExit) as exc:
        catalog.main()

    assert exc.value.code == 1
    assert "No Knowledge Base/ folder" in capsys.readouterr().err
    assert not paths.kb_catalog_path().exists()


def test_main_writes_the_catalog_json(vault, monkeypatch, capsys):
    folder, _ = vault
    (folder / "a.md").write_text("Purpose text.\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["prog"])

    with pytest.raises(SystemExit) as exc:
        catalog.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "1 file cataloged" in out

    payload = json.loads(paths.kb_catalog_path().read_text(encoding="utf-8"))
    assert payload["folder"] == str(folder)
    assert payload["files"][0]["name"] == "a.md"
    assert payload["files"][0]["purpose"] == "Purpose text."
    assert "generated_at" in payload


def test_main_folder_override_reads_a_custom_named_folder(empty_workspace, monkeypatch, capsys):
    custom = empty_workspace / "Domain Knowledge"
    custom.mkdir()
    (custom / "a.md").write_text("Custom vault note.\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["prog", "--folder", "Domain Knowledge"])

    with pytest.raises(SystemExit) as exc:
        catalog.main()

    assert exc.value.code == 0
    payload = json.loads(paths.kb_catalog_path().read_text(encoding="utf-8"))
    assert payload["folder"] == str(custom)
    assert payload["files"][0]["name"] == "a.md"


def test_main_rebuild_overwrites_the_previous_catalog(vault, monkeypatch, capsys):
    folder, _ = vault
    (folder / "a.md").write_text("First.\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit):
        catalog.main()

    (folder / "a.md").unlink()
    (folder / "b.md").write_text("Second.\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        catalog.main()

    payload = json.loads(paths.kb_catalog_path().read_text(encoding="utf-8"))
    assert [f["name"] for f in payload["files"]] == ["b.md"]
