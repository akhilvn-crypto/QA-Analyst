import tempfile
from pathlib import Path

import pytest
from docx import Document

from orchestrator.generation.report_exporter import (
    SEVERITY_STYLES,
    ReportOptions,
    build_document,
    export_report,
    resolve_output_dir,
    severity_of,
)
from orchestrator.utils.paths import exported_reports_dir

SAMPLE_REPORT = """# QA Findings Report — sample-app

## 1. Risk Summary Score

Not Production Ready — Blocking. 1 Critical, 1 High, 0 Medium, 1 Low —
1 Backend, 2 Frontend.

| Severity | Backend (Component A) | Frontend (Component B) |
| --- | --- | --- |
| Critical | 1 | 0 |
| High | 0 | 1 |
| Low | 0 | 1 |

## 2. Backend Infrastructure Findings (Component A)

### Critical

- **Finding** — Debug endpoint left enabled on the production API.
- **Real Impact** — Anyone on the network can attach a debugger.
- **Severity** — Critical
- **How to Fix** — Remove the debug flag from the production config.

## 3. Frontend Compiled Logic Findings (Component B)

### High

- **Finding** — `sk_live_51H…` in `src/payment_service.py`.
- **Real Impact** — An attacker could refund against the merchant account.
- **Severity** — High
- **How to Fix** — Move the key server-side and rotate it.

## 4. Remediation Blueprint

### 4.1 Backend (Infrastructure Owner)

1. Disable the debug endpoint.
2. Add a network security config.

### 4.2 Frontend (Application Developer)

1. Rotate and relocate the payment key.
   - Rebuild with production build flags enabled.
"""


def _paragraph_texts(document: Document) -> list[str]:
    return [paragraph.text for paragraph in document.paragraphs]


def test_severity_of_matches_bare_values_only():
    assert severity_of("Critical") == "critical"
    assert severity_of("**High**") == "high"
    assert severity_of("Medium — needs review") == "medium"
    assert severity_of("Low") == "low"
    # Prose that merely mentions a level must not be colour-coded.
    assert severity_of("This is a high-risk issue that affects every user today") is None
    assert severity_of("3 Critical, 5 High, 4 Medium") is None
    assert severity_of("") is None


def test_every_severity_has_a_style():
    for severity in ("critical", "high", "medium", "low"):
        text_color, fill = SEVERITY_STYLES[severity]
        assert len(text_color) == 6 and len(fill) == 6


def test_headings_are_preserved_as_separate_levels():
    document = build_document(SAMPLE_REPORT)
    styles = {
        paragraph.style.name
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    }
    assert "Title" in styles  # the single H1
    assert "Heading 2" in styles  # the numbered sections
    assert "Heading 3" in styles  # the severity groupings

    texts = _paragraph_texts(document)
    assert "2. Backend Infrastructure Findings (Component A)" in texts
    assert "3. Frontend Compiled Logic Findings (Component B)" in texts


def test_finding_fields_render_as_distinct_labelled_paragraphs():
    """The four fields must never collapse into one paragraph."""
    document = build_document(SAMPLE_REPORT)
    texts = _paragraph_texts(document)

    for label in ("Finding:", "Real Impact:", "Severity:", "How to Fix:"):
        matching = [text for text in texts if text.startswith(label)]
        assert len(matching) == 2, f"expected one {label} per component, got {matching}"

    # Each label is its own bold run, followed by the value run(s).
    finding = next(p for p in document.paragraphs if p.text.startswith("Finding:"))
    assert finding.runs[0].bold is True
    assert finding.runs[0].text == "Finding: "


def test_severity_values_are_colour_coded():
    document = build_document(SAMPLE_REPORT)
    severities = [p for p in document.paragraphs if p.text.startswith("Severity:")]
    assert len(severities) == 2

    colors = {p.runs[-1].font.color.rgb for p in severities}
    expected = {SEVERITY_STYLES["critical"][0], SEVERITY_STYLES["high"][0]}
    assert {str(color) for color in colors} == expected


def test_pipe_table_becomes_a_table_with_shaded_header():
    document = build_document(SAMPLE_REPORT)
    assert len(document.tables) == 1

    table = document.tables[0]
    assert len(table.rows) == 4  # header + 3 severities
    header_cell = table.rows[0].cells[0]
    assert header_cell.text == "Severity"
    # `style_cell` clears the cell first, which leaves an empty leading run —
    # assert against the run actually carrying the text.
    text_runs = [run for run in header_cell.paragraphs[0].runs if run.text]
    assert [run.bold for run in text_runs] == [True]
    # Fixed layout, so Word cannot reflow the table wider than the page.
    assert table.autofit is False


def test_ordered_lists_restart_per_section():
    """Word's List Number style would continue 1,2,3,4 across both remediation
    subsections; the markdown's own numbers must be preserved instead."""
    document = build_document(SAMPLE_REPORT)
    numbered = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip().startswith(("1. ", "2. "))
    ]
    assert "1. Disable the debug endpoint." in numbered
    assert "2. Add a network security config." in numbered
    assert "1. Rotate and relocate the payment key." in numbered


def test_code_fences_and_rules_do_not_break_parsing():
    markdown = "# Title\n\n---\n\n```\nliteral --flag\n```\n\nBody text.\n"
    texts = _paragraph_texts(build_document(markdown))
    assert "literal --flag" in texts
    assert "Body text." in texts
    assert "---" not in texts


def test_output_dir_defaults_to_workspace_reports_folder(tmp_path, monkeypatch):
    """Backward compatibility with the standalone /export-report behaviour."""
    import orchestrator.utils.paths as paths_mod

    monkeypatch.setattr(paths_mod, "WORKSPACE_ROOT", tmp_path)
    assert resolve_output_dir(None) == exported_reports_dir()


def test_explicit_output_dir_wins():
    chosen = resolve_output_dir("some/other/dir")
    assert chosen == Path("some/other/dir")


def test_export_report_writes_docx_to_the_requested_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_path = Path(tmp_dir) / "app-report.md"
        md_path.write_text(SAMPLE_REPORT, encoding="utf-8")
        destination = Path(tmp_dir) / "custom-dir"

        output_path = export_report(
            md_path, "app-report", "docx", str(destination)
        )

        assert output_path == destination / "app-report.docx"
        assert output_path.is_file()


def test_export_report_rejects_a_missing_input():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.raises(SystemExit):
            export_report(Path(tmp_dir) / "nope.md", "nope", "docx", tmp_dir)


# --- Controlled-document options (cover page / ToC / classification) ---


WRAPPED_PROSE = """## Executive Summary

This build must not be released. A live payment credential is embedded
in the compiled application and can be extracted by anyone who
downloads the app.

- **A live payment key ships inside the app.** Anyone can recover it
  and move money through the merchant account.
- Second point.
"""


def test_no_options_produces_no_cover_or_toc():
    """The standalone /export-report behaviour must be unchanged."""
    document = build_document(SAMPLE_REPORT)
    texts = _paragraph_texts(document)
    assert "Table of Contents" not in texts
    # The markdown's H1 still becomes the Title block when there is no cover.
    title = next(p for p in document.paragraphs if p.style.name == "Title")
    assert "QA Findings Report" in title.text


def test_cover_page_and_toc_are_added_when_requested():
    options = ReportOptions(
        cover_title="Application Security Assessment",
        cover_subtitle="Acme Wallet",
        classification="Confidential - Client Use Only",
        prepared_by="Emvigo QA",
        toc=True,
    )
    document = build_document(SAMPLE_REPORT, options)
    texts = _paragraph_texts(document)

    assert "Application Security Assessment" in texts
    assert "Acme Wallet" in texts
    assert "CONFIDENTIAL - CLIENT USE ONLY" in texts
    assert "Table of Contents" in texts
    assert any(text.startswith("Prepared by: ") for text in texts)


def test_toc_caption_is_not_a_heading():
    """A real Heading 1 would make the contents page its own first entry."""
    options = ReportOptions(cover_title="Report", toc=True)
    document = build_document(SAMPLE_REPORT, options)
    caption = next(p for p in document.paragraphs if p.text == "Table of Contents")
    assert not caption.style.name.startswith("Heading")


def test_cover_page_suppresses_its_own_footer():
    options = ReportOptions(cover_title="Report", classification="Confidential")
    document = build_document(SAMPLE_REPORT, options)
    assert document.sections[0].different_first_page_header_footer is True


def test_classification_appears_in_the_footer():
    options = ReportOptions(classification="Confidential - Client Use Only")
    document = build_document(SAMPLE_REPORT, options)
    footer_text = " ".join(p.text for p in document.sections[0].footer.paragraphs)
    assert "Confidential - Client Use Only" in footer_text


def test_h1_duplicating_the_cover_title_is_dropped():
    """The cover already carries the title; repeating it as the first section
    heading is duplicated furniture."""
    markdown = "# Application Security Assessment\n\n## 1. Document Control\n\nBody.\n"
    options = ReportOptions(cover_title="Application Security Assessment")
    document = build_document(markdown, options)

    # The title appears exactly once, on the cover (a Title-styled paragraph),
    # and never as a Heading 1 section.
    section_headings = [
        p.text for p in document.paragraphs if p.style.name.startswith("Heading")
    ]
    assert "Application Security Assessment" not in section_headings
    assert "1. Document Control" in section_headings

    all_occurrences = [
        p for p in document.paragraphs if p.text == "Application Security Assessment"
    ]
    assert len(all_occurrences) == 1
    assert all_occurrences[0].style.name == "Title"


def test_a_differing_h1_is_kept_as_a_heading():
    markdown = "# Appendix Pack\n\nBody.\n"
    options = ReportOptions(cover_title="Application Security Assessment")
    document = build_document(markdown, options)
    assert "Appendix Pack" in _paragraph_texts(document)


def test_wrapped_prose_joins_into_one_paragraph():
    """Markdown hard-wraps prose. Rendering each source line as its own Word
    paragraph is what made wrapped text come out loosely spaced, and turned a
    bullet's continuation line into a stray unbulleted paragraph."""
    document = build_document(WRAPPED_PROSE)
    texts = [text for text in _paragraph_texts(document) if text.strip()]

    body = next(text for text in texts if text.startswith("This build must not"))
    assert body.endswith("downloads the app.")
    assert "  " not in body  # joined with single spaces

    bullets = [p for p in document.paragraphs if p.style.name.startswith("List Bullet")]
    assert len(bullets) == 2
    assert bullets[0].text.endswith("through the merchant account.")
    # No orphan paragraph carrying the bullet's continuation.
    assert not any(text.startswith("and move money") for text in texts)


def test_metadata_never_names_python_docx_or_a_windows_account():
    """python-docx stamps author='python-docx' and a 'generated by python-docx'
    comment into every file. On a client-facing report -- readable in File >
    Info -- that discloses the toolchain, and Word's save additionally stamps
    the Windows account name into last_modified_by."""
    options = ReportOptions(
        cover_title="Application Security Assessment",
        cover_subtitle="Acme Wallet",
        prepared_by="Emvigo QA — Application Security",
    )
    properties = build_document(SAMPLE_REPORT, options).core_properties

    assert properties.author == "Emvigo QA — Application Security"
    assert properties.last_modified_by == "Emvigo QA — Application Security"
    assert properties.comments == ""
    assert "python-docx" not in f"{properties.author}{properties.comments}"
    assert properties.title == "Application Security Assessment"
    assert properties.subject == "Acme Wallet"


def test_metadata_author_falls_back_when_no_prepared_by():
    properties = build_document(SAMPLE_REPORT, ReportOptions()).core_properties
    assert properties.author == "Emvigo QA"
    assert properties.comments == ""


def test_document_author_never_empty():
    assert ReportOptions().document_author
    assert ReportOptions(prepared_by="Someone").document_author == "Someone"


def test_no_absolute_or_internal_paths_are_embedded(tmp_path):
    """The input markdown lives under an internal workspace path the client
    must never see, and the PDF path builds via a temp directory. Neither may
    end up inside the rendered file."""
    md_path = tmp_path / "workspace" / "output" / "reports" / "rep.md"
    md_path.parent.mkdir(parents=True)
    md_path.write_text(SAMPLE_REPORT, encoding="utf-8")

    output = export_report(md_path, "rep", "docx", str(tmp_path / "out"), ReportOptions())

    import zipfile

    with zipfile.ZipFile(output) as archive:
        blob = b"".join(archive.read(name) for name in archive.namelist())
    text = blob.decode("utf-8", "ignore")

    assert str(tmp_path) not in text
    assert "report-exporter-" not in text  # the temp dir used by the pdf path


def test_word_com_helpers_absolutise_their_paths():
    """Word resolves a relative path against *its own* working directory, so a
    path that is valid here fails with "Sorry, we couldn't find your file"."""
    import inspect

    from orchestrator.generation import report_exporter
    from orchestrator.utils import docx_helpers

    bake = inspect.getsource(docx_helpers.bake_live_fields)
    assert ".resolve()" in bake, "bake_live_fields must absolutise before COM"
    # The resolve must happen before the file is handed to Word.
    assert bake.index(".resolve()") < bake.index("Documents.Open")

    convert = inspect.getsource(report_exporter._convert_to_pdf)
    assert convert.count(".resolve()") >= 2, "both docx and pdf paths need it"
    assert convert.index(".resolve()") < convert.index("Documents.Open")


def test_export_report_accepts_a_relative_output_dir(tmp_path, monkeypatch):
    """End-to-end guard for the same bug, without needing Word: a relative
    --output-dir must produce a file where the caller expects it."""
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "report.md"
    md.write_text(SAMPLE_REPORT, encoding="utf-8")

    output = export_report(Path("report.md"), "report", "docx", "out/custom-dir/")

    assert output == Path("out/custom-dir/report.docx")
    assert (tmp_path / "out" / "custom-dir" / "report.docx").is_file()


def test_needs_field_baking_only_with_a_toc():
    assert ReportOptions(toc=True).needs_field_baking is True
    assert ReportOptions(cover_title="Report").needs_field_baking is False
    assert ReportOptions().needs_field_baking is False
