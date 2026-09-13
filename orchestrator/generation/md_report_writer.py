"""Writes structured requirement-analysis data as a Markdown report.

Usage:
    python -m orchestrator.generation.md_report_writer <doc-name>

Reads output/requirement-analysis/<doc-name>-analysis.json and writes
output/requirement-analysis/<doc-name>-analysis.md.

This is the deliverable a human actually reviews after an analysis run --
always generated, unlike the Word report (`docx_report_writer.py`, opt-in
via `--docx`). Once satisfied, the reviewer hands the approved `.md` off to
this project's configured Obsidian destination via `/handoff-requirement`
(`generation.requirement_handoff`).

Before overwriting an existing `.md`, this writer archives it to a sibling
`history/` folder as `<doc-name>-analysis-v<version>_<timestamp>.md` --
the same "preserve every controlled revision" contract
`hooks/snapshot-output.sh` already gives `<doc-name>-analysis.json`,
applied here in Python instead of a hook because this file is produced by
a Bash-invoked script, not `Write`/`Edit`, so that PreToolUse hook never
sees it. `orchestrator.utils.md_history` holds the actual archiving logic
-- shared by every other deliverable's own `.md` writer for the identical
reason (see that module's docstring) -- this file only supplies where its
own version lives in its rendered text (the "* **Document Version:**"
bullet). A run that finds nothing to archive (first analysis) or nothing
to overwrite differently is unaffected; the requirement-analyzer's own
no-op guard (`validation.analysis_currency`) is what stops a genuinely
unchanged re-run from reaching this writer at all.

Deliberately generated the same way the docx report is: deterministically,
from the analysis JSON (the single source of truth), never authored by hand
a second time -- so the two human-facing deliverables can never drift from
each other or from the JSON. Content order mirrors `docx_report_writer.py`
exactly (see the output-structure skill for the full layout rationale); the
container differs only where Markdown has no docx equivalent (no cover
page, page breaks, footers, or logos) or where docx keeps a Word-specific
affordance (e.g. the Document Control fields render as a table in docx,
bullets here -- both are the same "label: value" content, just a different
native container for it).

The report opens with an Obsidian-style YAML frontmatter "Properties" block
(`orchestrator.utils.md_frontmatter`, shared by all four `.md` writers) --
title, document_type, project_id, document_id, version, approved_date,
privacy, tags -- ahead of the numbered sections below, which are otherwise
unchanged.

The five numbered top-level sections below -- 1. Document Control &
Metadata (+ 1.1 Revision History), 2. Project Overview & Scope, 3.
Functional Requirements Analysis & Acceptance Criteria, 4. Non-Functional
Requirements (NFR) Analysis, 5. Compliance & Regulatory Requirements
Analysis -- are a fixed structural contract, not incidental Markdown
styling -- see the output-structure skill's "Markdown report" section for
why, and keep this file in sync with it if either changes. The per-
requirement text helpers (`_format_gap_text`/`_format_question_text`/
`_format_recommendations_text`/`_display_status`) and requirement sort
order (`_req_sort_key`) are imported from `docx_report_writer.py` rather
than reimplemented, so both reports render identical text for identical
input.
"""

import re
import sys

from orchestrator.generation.docx_report_writer import (
    NO_CATEGORY_REQUIREMENTS_TEXT,
    NO_REQUIREMENTS_TEXT,
    SECTION_TITLES,
    _build_summary_line,
    _display_status,
    _format_gap_text,
    _format_question_text,
    _format_recommendations_text,
    _req_sort_key,
)
from orchestrator.models.requirement import AnalysisDocument, DocumentControlMeta, ReleaseHistoryEntry, Requirement
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.md_frontmatter import build_frontmatter, title_with_project
from orchestrator.utils.md_history import bullet_version_extractor, snapshot_previous_md
from orchestrator.utils.md_table import build_table
from orchestrator.utils.paths import analysis_json_path, analysis_md_path
from orchestrator.validation.analysis_validator import CATEGORY_COMPLIANCE, CATEGORY_FUNCTIONAL, CATEGORY_NON_FUNCTIONAL
from orchestrator.validation.validate import validate_file

# (label, DocumentControlMeta attribute) pairs, bullet order for the
# "1. Document Control & Metadata" section -- "Project Name"/"Date" are the
# report-facing labels for `title`/`prepared_date`; the JSON field names
# underneath are unchanged (see DocumentControlMeta).
DOCUMENT_CONTROL_FIELDS = [
    ("Project Name", "title"),
    ("Project ID", "project_id"),
    ("Document ID", "document_id"),
    ("Description", "description"),
    ("Document Version", "version"),
    ("Prepared By", "prepared_by"),
    ("Date", "prepared_date"),
    ("Approved Date", "approved_date"),
    ("Master Template ID", "master_template_id"),
    ("Classification", "classification"),
]

# "1.1 Revision History" is a condensed view of `release_history` -- Version/
# Date/Description(=reasons)/Author/Reviewed By/Approved By -- dropping
# Reviewed On/Approved On from this table only; the full eight-field entry
# is still what's stored in the JSON (see ReleaseHistoryEntry) and what the
# opt-in docx report's own Revision History table shows.
REVISION_HISTORY_COLUMNS = ["Version", "Date", "Description", "Author", "Reviewed By", "Approved By"]

_LEADING_MARKER = re.compile(r"^(?:[-*]|\d+\.)\s+")

# Recovers the version an existing .md was written at, from its own "*
# **Document Version:** X" bullet (see DOCUMENT_CONTROL_FIELDS above) --
# never the JSON's own release_history, which by the time this runs has
# already been advanced to the *new* version (step 15 of
# requirement-analyzer.md writes the JSON first; this writer runs after, at
# step 16). See orchestrator.utils.md_history for the shared archiving logic
# this feeds into.
_extract_version = bullet_version_extractor("Document Version", marker="*")


def _bullet_field(label: str, text: str) -> str:
    """Render one "Label: value" field as a bullet -- inline on the same
    bullet line when the value is a single line (the common case: `Gap:
    None.`, `Status: Generated`), or as its own bullet holding nested
    sub-bullets when the value has multiple lines (a multi-gap Gap/Client
    Question, a multi-line Acceptance Criteria, several Recommendations).
    Any leading "- "/"1. " marker already in the source text is stripped
    since the nested bullet marker enumerates it instead."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 1:
        return f"* **{label}:** {text}"
    sub_items = "\n".join(f"  * {_LEADING_MARKER.sub('', ln.strip())}" for ln in lines)
    return f"* **{label}:**\n{sub_items}"


def _requirement_heading(requirement: Requirement) -> str:
    return f"### {requirement.req_id}: {requirement.title}" if requirement.title else f"### {requirement.req_id}"


def _build_requirement_card(requirement: Requirement) -> str:
    return "\n".join(
        [
            _requirement_heading(requirement),
            f"* **Status:** {_display_status(requirement.acceptance_criteria_status)}",
            _bullet_field("Requirement", requirement.requirement_text),
            _bullet_field("Gap", _format_gap_text(requirement)),
            _bullet_field("Client Question", _format_question_text(requirement)),
            _bullet_field("Acceptance Criteria", requirement.acceptance_criteria),
            _bullet_field("Recommendations", _format_recommendations_text(requirement)),
        ]
    )


def _build_category_section(category: str, requirements: list[Requirement]) -> str:
    items = sorted(
        (r for r in requirements if r.category == category),
        key=lambda r: _req_sort_key(r.req_id),
    )
    parts = [f"## {SECTION_TITLES[category]}"]
    if not items:
        parts.append(NO_CATEGORY_REQUIREMENTS_TEXT[category])
    else:
        parts.extend(_build_requirement_card(req) for req in items)
    return "\n\n".join(parts)


def build_report(
    requirements: list[Requirement],
    *,
    doc_name: str,
    document_control: DocumentControlMeta | None = None,
    release_history: list[ReleaseHistoryEntry] | None = None,
    executive_summary: str = "",
    in_scope: str = "",
    out_of_scope: str = "",
) -> str:
    document_control = document_control or DocumentControlMeta()
    release_history = release_history or []

    frontmatter = build_frontmatter(
        title=title_with_project(document_control.title, "Requirement Analysis"),
        document_type="Requirement Analysis",
        tags=["requirement-analysis", "qa"],
        project_id=document_control.project_id,
        document_id=document_control.document_id,
        version=document_control.version,
        approved_date=document_control.approved_date,
    )

    sections = ["# Requirement Analysis Report"]

    # 1. Document Control & Metadata -- bullet fields (not a table), one
    # per DOCUMENT_CONTROL_FIELDS entry.
    sections.append("## 1. Document Control & Metadata")
    sections.append(
        "\n".join(f"* **{label}:** {getattr(document_control, attr)}" for label, attr in DOCUMENT_CONTROL_FIELDS)
    )

    sections.append("### 1.1 Revision History")
    revision_rows = [[e.version, e.date, e.reasons, e.author, e.reviewed_by, e.approved_by] for e in release_history]
    sections.append(build_table(REVISION_HISTORY_COLUMNS, revision_rows))
    sections.append(f"*{_build_summary_line(doc_name, requirements)}*")

    sections.append("---")

    # 2. Project Overview & Scope
    sections.append("## 2. Project Overview & Scope")
    sections.append(
        "\n".join(
            [
                f"* **Executive Summary:** {executive_summary}",
                f"* **In-Scope:** {in_scope}",
                f"* **Out-of-Scope:** {out_of_scope}",
            ]
        )
    )

    sections.append("---")

    if not requirements:
        sections.append(f"## {SECTION_TITLES[CATEGORY_FUNCTIONAL]}")
        sections.append(NO_REQUIREMENTS_TEXT)
    else:
        sections.append(_build_category_section(CATEGORY_FUNCTIONAL, requirements))
        sections.append("---")
        sections.append(_build_category_section(CATEGORY_NON_FUNCTIONAL, requirements))
        sections.append("---")
        sections.append(_build_category_section(CATEGORY_COMPLIANCE, requirements))

    return frontmatter + "\n" + "\n\n".join(sections) + "\n"


def write_report(doc_name: str) -> None:
    json_path = analysis_json_path(doc_name)
    data = read_json(json_path)

    errors, warnings = validate_file(json_path)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Refusing to generate the report: {json_path.name} failed validation. "
            "Fix the JSON and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    analysis = AnalysisDocument.from_any(data)

    content = build_report(
        analysis.requirements,
        doc_name=doc_name,
        document_control=analysis.document_control,
        release_history=analysis.release_history,
        executive_summary=analysis.meta.executive_summary,
        in_scope=analysis.meta.in_scope,
        out_of_scope=analysis.meta.out_of_scope,
    )

    md_path = analysis_md_path(doc_name)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_previous_md(md_path, _extract_version, new_content=content)
    md_path.write_text(content, encoding="utf-8")
    print(str(md_path))


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.generation.md_report_writer <doc-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    _, doc_name = sys.argv
    write_report(doc_name)


if __name__ == "__main__":
    main()
