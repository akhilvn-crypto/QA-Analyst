"""Single place that resolves every workspace path.

No other script should hardcode a workspace path string -- import and use
these helpers instead, so the on-disk layout only has to change in one
place.

A plugin install maps to exactly one project: `WORKSPACE_ROOT` is the user's
own project directory (the session's `cwd`), and every deliverable lives
directly under it -- there is no `projects/<name>/` subfolder to select
between, unlike this system's pre-plugin, multi-project-per-repo form.

`REPO_ROOT` is a different thing entirely: it's this *plugin's own* install
directory, resolved via `__file__` (so it's correct regardless of the
caller's `cwd`), used only for bundled, read-only assets shipped with the
plugin itself (`orchestrator/templates/`, and the default logos under
`assets/branding/` -- see `header_logo_path`/`project_logo_path` below) --
never for anything workspace/project-specific.

User inputs inside the workspace (`Requirements/`, `Knowledge Base/`,
`Branding/`, `Project Info.md`) are resolved by convention in
`orchestrator.utils.workspace` -- there is no settings file.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANDING_ASSETS_ROOT = REPO_ROOT / "assets" / "branding"
WORKSPACE_ROOT = Path.cwd()


def requirement_source_md_path(doc_name: str) -> Path:
    """The combined markdown staged from every `.md` file under the
    attached folder's `Requirements/` subfolder -- produced fresh by
    `parsing.reading_vault_fetch` on every `/analyse-requirement` run.
    `<doc_name>` is always the attached folder's own name, since every
    `.md` file found under `Requirements/` is combined into one requirement
    set rather than selected individually."""
    return output_dir() / f"{doc_name}-source.md"


def output_dir(purpose: str = "requirement-analysis") -> Path:
    return WORKSPACE_ROOT / "output" / purpose


def analysis_json_path(doc_name: str) -> Path:
    return output_dir() / f"{doc_name}-analysis.json"


def analysis_docx_path(doc_name: str) -> Path:
    return output_dir() / f"{doc_name}-analysis.docx"


def analysis_md_path(doc_name: str) -> Path:
    """The human-review Markdown report -- always generated, unlike the
    docx (opt-in via `--docx`). This is the file a reviewer reads."""
    return output_dir() / f"{doc_name}-analysis.md"


def clarification_sheet_docx_path(doc_name: str) -> Path:
    return output_dir("client-clarifications") / f"{doc_name}-clarifications.docx"


def clarification_sheet_md_path(doc_name: str) -> Path:
    """The round-trip source for the Client Clarification Sheet -- always
    written (unlike the docx, opt-in via `--docx`), and the file
    `parsing.clarifications_from_md` reads back to ingest client answers.
    Same doc-name-first, docx-opt-in relationship the analysis report's
    `analysis_md_path`/`analysis_docx_path` pair already has."""
    return output_dir("client-clarifications") / f"{doc_name}-clarifications.md"


def test_plan_json_path(doc_name: str) -> Path:
    return output_dir("test-plan") / f"{doc_name}-test-plan.json"


def test_plan_md_path(doc_name: str) -> Path:
    """The human-review Markdown Test Plan -- always generated, unlike the
    docx (opt-in via `--docx`). This is the file a reviewer reads. Same
    doc-name-first, docx-opt-in
    relationship `analysis_md_path`/`analysis_docx_path` already have."""
    return output_dir("test-plan") / f"{doc_name}-test-plan.md"


def test_plan_docx_path(doc_name: str) -> Path:
    return output_dir("test-plan") / f"{doc_name}-test-plan.docx"


def test_cases_json_path(doc_name: str) -> Path:
    return output_dir("test-cases") / f"{doc_name}-test-cases.json"


def test_cases_md_path(doc_name: str) -> Path:
    """The human-review Markdown test-case report -- always generated,
    unlike the CSV/XLSX exports (opt-in via `--csv`/`--xlsx`). This is the
    file a reviewer reads. Same
    doc-name-first, opt-in-extra-format relationship
    `analysis_md_path`/`analysis_docx_path` and
    `test_plan_md_path`/`test_plan_docx_path` already have."""
    return output_dir("test-cases") / f"{doc_name}-test-cases.md"


def test_cases_csv_path(output_name: str) -> Path:
    return output_dir("test-cases") / f"{output_name}.csv"


def test_cases_xlsx_path(output_name: str) -> Path:
    return output_dir("test-cases") / f"{output_name}.xlsx"


def exported_reports_dir() -> Path:
    """Default destination for `report_exporter` when no --output-dir is given."""
    return output_dir("reports")


def kb_catalog_path() -> Path:
    """The Knowledge Catalog `/build-kb-catalog` writes and every generator
    agent reads directly with `Read` -- name/purpose/description per note
    under the attached folder's `Knowledge Base/` subfolder, plus that
    folder's own resolved path so a reader knows where to `Read` a named
    file from. Not a client deliverable (no `meta`/`document_control`
    shape, never snapshotted, validated, or logged) -- an internal working
    file, same tier as the staged `<doc-name>-source.md`, which is why it
    lives under `output/` without a per-document name: there is exactly one
    Knowledge Base per workspace, same singular assumption as
    `Requirements/`."""
    return WORKSPACE_ROOT / "output" / "knowledge-base" / "catalog.json"


def _logo_path(filename: str) -> Path:
    from orchestrator.utils.workspace import branding_path

    override_dir = branding_path()
    if override_dir is not None and (override_dir / filename).is_file():
        return override_dir / filename
    return BRANDING_ASSETS_ROOT / filename


def header_logo_path() -> Path:
    """The attached folder's `Branding/header-logo.png` when present, else
    the plugin's bundled default -- nothing needs to exist in the workspace
    for reports to render."""
    return _logo_path("header-logo.png")


def project_logo_path() -> Path:
    """See `header_logo_path` -- same override-first, bundled-fallback
    resolution, for the project logo asset."""
    return _logo_path("project-logo.png")
