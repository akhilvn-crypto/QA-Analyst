"""Tests for the shared YAML frontmatter "Properties" block every
Markdown deliverable writer in `generation/` now prepends to its output --
see md_frontmatter.py's own docstring for which writers and why."""

from orchestrator.utils.md_frontmatter import build_frontmatter, title_with_project


def test_build_frontmatter_renders_all_properties_in_order():
    content = build_frontmatter(
        title="LinkGrid Requirement Analysis",
        document_type="Requirement Analysis",
        tags=["requirement-analysis", "qa"],
        project_id="PRJ-1",
        document_id="DOC-1",
        version="1.0",
        approved_date="2026-08-12",
    )
    lines = content.splitlines()

    assert lines[0] == "---"
    assert lines[-1] == "---"
    assert lines.index('title: "LinkGrid Requirement Analysis"') < lines.index(
        'document_type: "Requirement Analysis"'
    )
    assert 'project_id: "PRJ-1"' in lines
    assert 'document_id: "DOC-1"' in lines
    assert 'version: "1.0"' in lines
    assert 'approved_date: "2026-08-12"' in lines
    assert 'privacy: "Confidential"' in lines
    assert "tags:" in lines
    assert '  - "requirement-analysis"' in lines
    assert '  - "qa"' in lines


def test_build_frontmatter_blank_fields_render_as_empty_quoted_strings():
    content = build_frontmatter(title="Doc", document_type="Test Plan", tags=["test-plan", "qa"])

    assert 'project_id: ""' in content.splitlines()
    assert 'document_id: ""' in content.splitlines()
    assert 'version: ""' in content.splitlines()
    assert 'approved_date: ""' in content.splitlines()


def test_build_frontmatter_no_tags_renders_empty_list():
    content = build_frontmatter(title="Doc", document_type="Test Plan", tags=[])

    assert "tags: []" in content.splitlines()
    assert "tags:\n" not in content


def test_build_frontmatter_escapes_embedded_quotes_and_backslashes():
    content = build_frontmatter(title='A "quoted" title', document_type="Test Plan", tags=[])

    assert 'title: "A \\"quoted\\" title"' in content.splitlines()


def test_title_with_project_prefixes_a_real_project_name():
    assert title_with_project("LinkGrid", "Test Plan") == "LinkGrid Test Plan"


def test_title_with_project_falls_back_to_bare_type_when_blank():
    assert title_with_project("", "Test Plan") == "Test Plan"


def test_title_with_project_falls_back_to_bare_type_for_tbd_placeholder():
    assert title_with_project("TBD – Client/Project Input Required", "Test Plan") == "Test Plan"
