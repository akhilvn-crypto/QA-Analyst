"""Tests for convention-based input discovery inside the attached folder
(`orchestrator.utils.workspace`) -- the replacement for
`config/settings.json`."""

import pytest

from orchestrator.utils import paths, workspace


@pytest.fixture
def root(monkeypatch, tmp_path):
    attached = tmp_path / "LinkGrid"
    attached.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: attached)
    return attached


def test_missing_subfolders_resolve_to_none(root):
    assert workspace.requirements_path() is None
    assert workspace.knowledge_base_path() is None
    assert workspace.branding_path() is None


def test_exact_subfolder_names_resolve(root):
    (root / "Requirements").mkdir()
    (root / "Knowledge Base").mkdir()

    assert workspace.requirements_path() == root / "Requirements"
    assert workspace.knowledge_base_path() == root / "Knowledge Base"


@pytest.mark.parametrize("name", ["knowledge-base", "knowledge_base", "KNOWLEDGE BASE", "KnowledgeBase"])
def test_subfolder_names_match_ignoring_case_spaces_and_separators(root, name):
    (root / name).mkdir()

    assert workspace.knowledge_base_path() == root / name


def test_a_file_never_satisfies_a_folder_lookup(root):
    (root / "Requirements").write_text("not a folder", encoding="utf-8")

    assert workspace.requirements_path() is None


def test_folder_override_resolves_an_exact_top_level_name_regardless_of_convention(root):
    (root / "Specs").mkdir()

    assert workspace.requirements_path("Specs") == root / "Specs"
    assert workspace.knowledge_base_path("Domain Knowledge") is None


def test_folder_override_never_falls_back_to_the_conventional_name(root):
    (root / "Requirements").mkdir()

    assert workspace.requirements_path("Nonexistent") is None


def test_document_name_is_the_attached_folder_name(root):
    assert workspace.document_name() == "LinkGrid"


def test_logos_have_no_bundled_default(root):
    assert paths.header_logo_path() == root / "Branding" / "header-logo.png"
    assert not paths.header_logo_path().exists()
    assert not paths.project_logo_path().exists()


def test_branding_folder_supplies_only_the_logos_it_contains(root):
    (root / "Branding").mkdir()
    (root / "Branding" / "project-logo.png").write_bytes(b"png")

    assert paths.project_logo_path() == root / "Branding" / "project-logo.png"
    assert paths.project_logo_path().is_file()
    assert paths.header_logo_path() == root / "Branding" / "header-logo.png"
    assert not paths.header_logo_path().exists()
