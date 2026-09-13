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


def test_document_name_is_the_attached_folder_name(root):
    assert workspace.document_name() == "LinkGrid"


def test_operator_info_is_blank_without_a_project_info_note(root):
    assert workspace.operator_info() == dict.fromkeys(workspace.OPERATOR_KEYS, "")


def test_operator_info_reads_project_info_frontmatter(root):
    (root / "Project Info.md").write_text(
        "---\n"
        "name: Akhil VN\n"
        "designation: 'QA Lead'\n"
        'projectName: "LinkGrid"\n'
        "projectId: LG-001\n"
        "---\n\n# Project Info\nBody text is ignored.\n",
        encoding="utf-8",
    )

    assert workspace.operator_info() == {
        "name": "Akhil VN",
        "designation": "QA Lead",
        "projectName": "LinkGrid",
        "projectId": "LG-001",
    }


def test_operator_info_partial_frontmatter_leaves_other_fields_blank(root):
    (root / "project-info.md").write_text("---\nname: Akhil VN\n---\n", encoding="utf-8")

    info = workspace.operator_info()
    assert info["name"] == "Akhil VN"
    assert info["projectId"] == ""


def test_operator_info_ignores_a_note_without_frontmatter(root):
    (root / "Project Info.md").write_text("name: not frontmatter\n", encoding="utf-8")

    assert workspace.operator_info()["name"] == ""


def test_logos_fall_back_to_the_bundled_defaults(root):
    assert paths.header_logo_path() == paths.BRANDING_ASSETS_ROOT / "header-logo.png"
    assert paths.project_logo_path().is_file()


def test_branding_folder_overrides_only_the_logos_it_contains(root):
    (root / "Branding").mkdir()
    (root / "Branding" / "project-logo.png").write_bytes(b"png")

    assert paths.project_logo_path() == root / "Branding" / "project-logo.png"
    assert paths.header_logo_path() == paths.BRANDING_ASSETS_ROOT / "header-logo.png"
