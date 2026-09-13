"""Writes structured test-plan data as a Markdown report.

Usage:
    python -m orchestrator.generation.test_plan_md_writer <doc-name>

Reads output/test-plan/<doc-name>-test-plan.json and writes
output/test-plan/<doc-name>-test-plan.md.

This is the deliverable a human actually reviews after a Test Plan run --
always generated, unlike the Word report (`test_plan_docx_writer.py`,
opt-in via `--docx`). Once satisfied, the reviewer hands the approved `.md`
off to this project's configured Obsidian destination via
`/handoff-test-plan` (`generation.requirement_handoff`, `--target
test-plan`) -- the exact same always-md/opt-in-docx/dedicated-handoff shape
`md_report_writer.py`/`docx_report_writer.py`/`/handoff-requirement`
already have for the requirement-analysis report.

Deliberately generated the same way the docx report is: deterministically,
from the test-plan JSON (the single source of truth), never authored by
hand a second time -- so the two human-facing deliverables can never drift
from each other or from the JSON. Section order and content mirror
`test_plan_docx_writer.py` exactly (see the test-plan-output-structure
skill for the full layout rationale); the container differs only where
Markdown has no docx equivalent (no cover page, page breaks, footers, TOC,
or logos) or where docx keeps a Word-specific affordance (e.g. the
Document Version Control fields render as a table in docx, bullets here --
both are the same "label: value" content, just a different native
container). Every table (Release History, Reference Documents, Team
Members, Roles & Responsibilities, Environment Software/Hardware, Test
Schedule, Test Deliverables document/location pairs, Approval & Sign-off)
uses the same shared `orchestrator.utils.md_table.build_table` helper the
requirement-analysis report and Client Clarification Sheet already use, so
a cell holding a newline or a literal pipe is escaped identically
everywhere in this project's Markdown output.

The report opens with an Obsidian-style YAML frontmatter "Properties" block
(`orchestrator.utils.md_frontmatter`, shared by all four `.md` writers) --
title, document_type, project_id, document_id, version, approved_date,
privacy, tags -- ahead of the `# Test Plan for ...` heading, which is
otherwise unchanged.

Before overwriting an existing `.md`, this writer archives it to a sibling
`history/` folder -- same "preserve every controlled revision" contract
`md_report_writer.py` gives the requirement-analysis report, via the same
shared `orchestrator.utils.md_history` helper (see that module's docstring
for why this lives in Python rather than a hook). Unlike that report, the
Document Version Control section here (see `_build_version_control` below)
has no standalone version bullet -- this section's own convention omits
one, the current version is only ever shown as the last row of "B.
Document Release History" -- so the version an outgoing `.md` carried is
recovered from that table's last row instead of a bullet
(`release_history_version_extractor`).
"""

import sys

from orchestrator.models.test_plan import TestPlan
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.md_frontmatter import build_frontmatter, title_with_project
from orchestrator.utils.md_history import release_history_version_extractor, snapshot_previous_md
from orchestrator.utils.md_table import build_table
from orchestrator.utils.paths import test_plan_json_path, test_plan_md_path
from orchestrator.validation.validate import validate_file

CLIENT_INPUT_TBD = "TBD – Client/Project Input Required"

# Shared verbatim with _build_version_control's own build_table() call below
# so the header line release_history_version_extractor searches for can
# never drift from what's actually rendered.
RELEASE_HISTORY_COLUMNS = [
    "Version", "Date", "Author", "Reviewed By", "Reviewed On", "Approved By", "Approved On", "Reasons",
]
_extract_version = release_history_version_extractor(RELEASE_HISTORY_COLUMNS)


# --------------------------------------------------------------------------
# Generic content helpers
# --------------------------------------------------------------------------


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _nested_bullets(groups) -> str:
    """groups: iterable of objects with .area (top-level bullet) and .items
    (nested sub-bullets) -- the Markdown equivalent of the docx's two-level
    `List Bullet`/`List Bullet 2` nesting."""
    lines = []
    for group in groups:
        lines.append(f"- {group.area}")
        lines.extend(f"  - {item}" for item in group.items)
    return "\n".join(lines)


def _paragraphs(paras: list[str]) -> str:
    return "\n\n".join(paras)


def _kv_bullets(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"- **{key}:** {value}" for key, value in rows)


def _section(heading: str, *body_parts: str) -> str:
    parts = [p for p in body_parts if p and p.strip()]
    return "\n\n".join([heading, *parts]) if parts else heading


def _doc_location_table(entries) -> str:
    if not entries:
        return ""
    return build_table(["Document", "Location"], [[e.document, e.location] for e in entries])


# --------------------------------------------------------------------------
# Section builders (mirror test_plan_docx_writer.py's _build_* functions,
# same order, same content -- see this module's own docstring)
# --------------------------------------------------------------------------


def _build_version_control(plan: TestPlan) -> str:
    parts = [
        "## A. Document Version Control",
        _kv_bullets(
            [
                ("Title", plan.meta.title),
                ("Project ID", plan.meta.project_id),
                ("Document ID", plan.meta.document_id),
                ("Description", plan.meta.description),
                ("Approved date", plan.meta.approved_date),
                ("Master Template ID", plan.meta.master_template_id),
            ]
        ),
        "## B. Document Release History",
        build_table(
            RELEASE_HISTORY_COLUMNS,
            [
                [e.version, e.date, e.author, e.reviewed_by, e.reviewed_on, e.approved_by, e.approved_on, e.reasons]
                for e in plan.release_history
            ],
        ),
    ]
    return "\n\n".join(parts)


def _build_introduction(plan: TestPlan) -> str:
    intro = plan.introduction
    parts = [
        "## Introduction",
        "### Purpose",
        intro.purpose,
        "### Project Overview",
        intro.project_overview,
        "### Scope of testing",
        "#### In Scope",
    ]
    if intro.scope_in_areas:
        parts.append("##### Core Functional Areas")
        parts.append(_nested_bullets(intro.scope_in_areas))
    if intro.scope_in_non_functional:
        parts.append("##### Non-Functional Testing")
        parts.append(_bullets(intro.scope_in_non_functional))
    parts.append("#### Out of Scope")
    parts.append(_bullets(intro.scope_out))
    if intro.reference_documents:
        parts.append("### Reference Documents")
        parts.append(
            build_table(
                ["Process Element", "Reference"],
                [[d.process_element, d.reference] for d in intro.reference_documents],
            )
        )
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_resources(plan: TestPlan) -> str:
    res = plan.resources
    parts = ["## Resource Requirement for Tests"]

    if res.team_members:
        parts.append("### Team Members")
        parts.append(
            build_table(
                ["Resource Name", "Designation/Role"],
                [[m.resource_name, m.designation_role] for m in res.team_members],
            )
        )

    if res.role_assignments:
        parts.append("### Roles & Responsibilities Matrix")
        parts.append(
            build_table(
                ["Element", "Resource Name", "Designation/Role"],
                [[r.element, r.resource_name, r.designation_role] for r in res.role_assignments],
            )
        )

    parts.append("### Orientation/Training Plan")
    if res.orientation_intro:
        parts.append(res.orientation_intro)
    if res.orientation_topics:
        parts.append(_bullets(res.orientation_topics))

    parts.append("### Inputs/Documents needed from Project Team")
    parts.append(_bullets(res.inputs_needed))

    parts.append("### Test Environment Needed")
    if res.environment_software:
        parts.append("#### Software")
        parts.append(
            build_table(
                ["S. No", "Software", "Purpose"],
                [[i.sno, i.name, i.purpose] for i in res.environment_software],
            )
        )
    if res.environment_hardware:
        parts.append("#### Hardware")
        parts.append(
            build_table(
                ["S. No", "Hardware", "Purpose"],
                [[i.sno, i.name, i.purpose] for i in res.environment_hardware],
            )
        )

    return "\n\n".join(p for p in parts if p and p.strip())


def _build_assumptions_dependencies_risks(plan: TestPlan) -> str:
    adr = plan.assumptions_dependencies_risks
    return "\n\n".join(
        p
        for p in [
            "## Assumptions, Dependencies & Risks",
            "### Assumptions",
            _bullets(adr.assumptions),
            "### Dependencies",
            _bullets(adr.dependencies),
            "### Risks",
            _bullets(adr.risks),
        ]
        if p and p.strip()
    )


def _build_strategy(plan: TestPlan) -> str:
    strategy = plan.strategy
    parts = [
        "## Test Strategy/Methods",
        "### Overall Test Strategy",
        _paragraphs(strategy.overall_strategy),
        "### Strategy for Integration of Product Modules",
        _paragraphs(strategy.integration_strategy),
    ]
    if strategy.integration_key_areas:
        parts.append(_bullets(strategy.integration_key_areas))
    if strategy.integration_sequence:
        parts.append("### Sequence & Criteria for Integration Testing")
        parts.append(_nested_bullets(strategy.integration_sequence))
    if strategy.entry_criteria:
        parts.append("#### Entry Criteria for Integration Testing")
        parts.append(_bullets(strategy.entry_criteria))
    if strategy.exit_criteria:
        parts.append("#### Exit Criteria for Integration Testing")
        parts.append(_bullets(strategy.exit_criteria))
    if strategy.integration_acceptance_criteria:
        parts.append("#### Acceptance Criteria")
        parts.append(_bullets(strategy.integration_acceptance_criteria))
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_schedule(plan: TestPlan) -> str:
    return "\n\n".join(
        [
            "## Test Schedule",
            build_table(
                ["Release", "Sprint", "Iteration", "Start Date", "End Date"],
                [[e.release, e.sprint, e.iteration, e.start_date, e.end_date] for e in plan.schedule],
            ),
        ]
    )


def _build_deliverables(plan: TestPlan) -> str:
    deliv = plan.deliverables
    parts = [
        "## Test Deliverables",
        "All the Test deliverables should be shared to the customer at the end of project",
        "### Test Plan",
        deliv.test_plan_note,
        "### Test Cases & Test Logs",
        _doc_location_table(deliv.test_cases_logs),
        "### Acceptance/Exit Criteria",
        deliv.acceptance_exit_note,
        _doc_location_table(deliv.acceptance_exit_docs),
        "### Bug Analysis",
        deliv.bug_analysis_note,
        _doc_location_table(deliv.bug_analysis_docs),
        "### Release Notes",
        deliv.release_notes_note,
        _doc_location_table(deliv.release_notes_docs),
        "### Non Functional Testing",
        deliv.non_functional_note,
        _doc_location_table(deliv.non_functional_docs),
    ]
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_closure(plan: TestPlan) -> str:
    closure = plan.closure
    parts = [
        "## Test Closure",
        "Test closure activities are performed at the completion of each sprint and at the "
        "final release milestone, based on requirement completion and acceptance.",
    ]
    if closure.sprint_closure_criteria:
        parts.append("A sprint is considered test-closed when:")
        parts.append(_bullets(closure.sprint_closure_criteria))
    if closure.release_closure_criteria:
        parts.append("At the end of the release:")
        parts.append(_bullets(closure.release_closure_criteria))
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_approval_signoff() -> str:
    return "\n\n".join(
        [
            "## Approval & Sign-off",
            "This Test Plan is considered approved once each role below has "
            "reviewed and signed off on its content.",
            build_table(
                ["Role", "Name", "Signature", "Date"],
                [
                    ["Prepared By (QA)", CLIENT_INPUT_TBD, "", ""],
                    ["Reviewed By", CLIENT_INPUT_TBD, "", ""],
                    ["Approved By", CLIENT_INPUT_TBD, "", ""],
                ],
            ),
        ]
    )


# --------------------------------------------------------------------------
# Top-level build / write
# --------------------------------------------------------------------------


def build_report(plan: TestPlan) -> str:
    title = f"# Test Plan for {plan.meta.title}" if plan.meta.title else "# Test Plan"
    frontmatter = build_frontmatter(
        title=title_with_project(plan.meta.title, "Test Plan"),
        document_type="Test Plan",
        tags=["test-plan", "qa"],
        project_id=plan.meta.project_id,
        document_id=plan.meta.document_id,
        version=plan.meta.version,
        approved_date=plan.meta.approved_date,
    )
    sections = [
        title,
        _build_version_control(plan),
        _build_introduction(plan),
        _build_resources(plan),
        _build_assumptions_dependencies_risks(plan),
        _build_strategy(plan),
        _build_schedule(plan),
        _build_deliverables(plan),
        _build_closure(plan),
        _build_approval_signoff(),
    ]
    return frontmatter + "\n" + "\n\n---\n\n".join(sections) + "\n"


def write_report(doc_name: str) -> None:
    json_path = test_plan_json_path(doc_name)
    data = read_json(json_path)

    errors, warnings = validate_file(json_path)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Refusing to generate the Test Plan report: {json_path.name} failed validation. "
            "Fix the JSON and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    plan = TestPlan.from_dict(data)
    content = build_report(plan)

    md_path = test_plan_md_path(doc_name)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_previous_md(md_path, _extract_version, new_content=content)
    md_path.write_text(content, encoding="utf-8")
    print(str(md_path))


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.generation.test_plan_md_writer <doc-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    _, doc_name = sys.argv
    write_report(doc_name)


if __name__ == "__main__":
    main()
