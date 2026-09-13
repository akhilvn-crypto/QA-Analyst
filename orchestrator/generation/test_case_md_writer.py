"""Writes a *-test-cases.json deliverable as a human-review Markdown report
-- and, since the Markdown report is now this project's one true source of
a test case's execution tracking, also owns reading that tracking back out
of the report's own text.

Usage:
    python -m orchestrator.generation.test_case_md_writer <doc-name>

Reads output/test-cases/<doc-name>-test-cases.json and writes
output/test-cases/<doc-name>-test-cases.md.

This is the deliverable a human actually reviews after a test-case
generation run -- always generated, unlike the Zephyr CSV
(`zephyr_export.py`, opt-in via `--csv`) and the Excel review workbook
(same script, opt-in via `--xlsx`). Once satisfied, the reviewer hands the
approved `.md` off to this project's configured Obsidian destination via
`/handoff-test-cases` (`generation.requirement_handoff`, `--target
test-cases`) -- the exact same always-md/opt-in-extra-format/dedicated-
handoff shape the requirement-analysis report and the Test Plan already
have.

Deliberately generated the same way the Test Plan's Markdown report is:
deterministically, from the test-cases JSON (the single source of truth for
everything *except* execution tracking), never authored by hand a second
time -- so this report can never drift from the JSON, the CSV, or the XLSX
on anything but Execution Status/Actual Result/Linked Issue. Content mirrors
the XLSX "Test Cases" review sheet (see the test-case-output-structure
skill): each test case shows its tracing requirement, type, priority,
objective, preconditions, steps, and its three tracking fields (Execution
Status, Actual Result, Linked Issue). `Requirement` text is looked up from
the sibling `-analysis.json` the same best-effort way `zephyr_export.py`'s
own `load_requirement_texts` does (both share `test_case_tracking.py`).

**This Markdown report is the one true store for Execution Status/Actual
Result/Linked Issue -- not the xlsx, and not the JSON.** `write_report`
carries a test case's already-recorded tracking forward from whatever this
same `.md` file currently holds (`load_existing_review_tracking`, reading
this module's own rendered output back), the same self-referential
carry-forward pattern the xlsx used to do against itself before this
change. `write_report`'s `overrides` parameter exists for a caller outside
this project (e.g. a separate automation project's post-test-run writer)
to patch in Execution Status/Actual Result for whichever `tc_id`s a run
covered -- it never touches the xlsx or the JSON, only this file; nothing
in this project itself calls it that way. `zephyr_export.py`'s xlsx export
reads tracking the same way, via this
module's `load_existing_review_tracking`, so a regenerated xlsx (and a
regenerated Markdown report itself) can never disagree about what's
currently recorded -- both are downstream renders of this one file. A doc
whose `.md` doesn't exist yet, or has no tracking recorded for a given
`tc_id`, just shows Execution Status defaulted to "Not Executed" and blank
Actual Result/Linked Issue -- the same untouched-export defaults the xlsx
itself used to start with.

The report opens with an Obsidian-style YAML frontmatter "Properties" block
(`orchestrator.utils.md_frontmatter`, shared by all four `.md` writers) --
title, document_type, project_id, document_id, version, approved_date,
privacy, tags -- ahead of the `# <document_control.title>` heading, which is
otherwise unchanged.

Before overwriting an existing `.md`, this writer also archives it to a
sibling `history/` folder -- same "preserve every controlled revision"
contract `md_report_writer.py` gives the requirement-analysis report, via
the same shared `orchestrator.utils.md_history` helper (see that module's
docstring). The version an outgoing `.md` carried is recovered from its own
"- **Version:** X" bullet (see `_build_version_control` below), never the
JSON's own already-bumped version.
"""

import re
import sys
from pathlib import Path

from orchestrator.generation.test_case_tracking import DEFAULT_EXECUTION_STATUS, load_requirement_texts
from orchestrator.models.test_case import TestCaseDocument
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.md_frontmatter import build_frontmatter
from orchestrator.utils.md_history import bullet_version_extractor, snapshot_previous_md
from orchestrator.utils.md_table import build_table
from orchestrator.utils.paths import test_cases_json_path, test_cases_md_path
from orchestrator.validation.validate import validate_file

_extract_version = bullet_version_extractor("Version", marker="-")

# Matches this report's own "### TC-001: Title" heading (see
# `_build_test_case`) -- the section boundary `load_existing_review_tracking`
# splits on to isolate one test case's tracking lines from the next.
_TC_HEADING_RE = re.compile(r"^### (TC-\S+):", re.MULTILINE)
# The three tracking bullets this report renders, in the same
# "- **<label>:** <value>" shape every other field on a test case uses (see
# `_build_test_case`) -- single-line by construction (`_flatten_tracking_
# value` collapses any embedded newline before it's ever written), so a
# straight to-end-of-line capture is always correct, never truncating a
# wrapped value.
_TRACKING_FIELD_RES = {
    field: re.compile(rf"^- \*\*{field}:\*\* (.+)$", re.MULTILINE)
    for field in ("Execution Status", "Actual Result", "Linked Issue")
}


def _flatten_tracking_value(value: str) -> str:
    """Collapses a tracking value to one line. Actual Result in particular
    can be a genuine multi-line Playwright error message (a stack trace, a
    multi-line assertion diff) -- rendering it as-is would break this
    report's own line-based bullet format (each subsequent physical line
    would no longer start with "- **", so `load_existing_review_tracking`
    could never read it back). Collapsing internal whitespace runs
    (including newlines) to a single space keeps the report both readable
    and losslessly round-trippable."""
    return " ".join(value.split())


def load_existing_review_tracking(md_path: Path) -> dict[str, dict[str, str]]:
    """Best-effort read of an already-written test-cases Markdown report's
    own Execution Status/Actual Result/Linked Issue bullets, keyed by
    `tc_id` -- lets a regeneration (by this module itself, or by an
    external caller's `overrides`, see `write_report`) carry forward
    whatever's already recorded instead of silently blanking it. A missing
    file, or a `tc_id` section with none of the three bullets present, is a
    no-op (empty dict/entry) -- the same tolerance the old xlsx-based
    lookup gave a missing file/sheet/column, never treated as an error."""
    if not md_path.is_file():
        return {}
    try:
        content = md_path.read_text(encoding="utf-8")
    except Exception:
        return {}

    headings = list(_TC_HEADING_RE.finditer(content))
    tracking: dict[str, dict[str, str]] = {}
    for idx, heading in enumerate(headings):
        tc_id = heading.group(1)
        start = heading.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(content)
        block = content[start:end]
        values = {
            field: match.group(1).strip()
            for field, pattern in _TRACKING_FIELD_RES.items()
            if (match := pattern.search(block))
        }
        if values:
            tracking[tc_id] = values
    return tracking


def _build_version_control(document: TestCaseDocument) -> str:
    control = document.document_control
    parts = [
        "## A. Document Version Control",
        "\n".join(
            f"- **{label}:** {value}"
            for label, value in [
                ("Title", control.title),
                ("Project ID", control.project_id),
                ("Document ID", control.document_id),
                ("Description", control.description),
                ("Prepared By", control.prepared_by),
                ("Prepared Date", control.prepared_date),
                ("Approved Date", control.approved_date),
                ("Master Template ID", control.master_template_id),
                ("Version", control.version),
            ]
        ),
        "## B. Document Release History",
        build_table(
            ["Version", "Date", "Author", "Reviewed By", "Reviewed On", "Approved By", "Approved On", "Reasons"],
            [
                [e.version, e.date, e.author, e.reviewed_by, e.reviewed_on, e.approved_by, e.approved_on, e.reasons]
                for e in document.release_history
            ],
        ),
    ]
    return "\n\n".join(parts)


def _build_test_case(tc, requirement_text: str, tracking: dict[str, str]) -> str:
    parts = [
        f"### {tc.tc_id}: {tc.title}",
        "\n".join(
            f"- **{label}:** {value}"
            for label, value in [
                ("Requirement", f"{tc.req_id} — {requirement_text}" if requirement_text else tc.req_id),
                ("Test Type", tc.test_type),
                ("Priority", tc.priority),
                ("Objective", tc.objective),
                ("Preconditions", tc.preconditions),
                # Execution Status always has a value (defaults the same way
                # the xlsx's own untouched export used to); Actual Result/
                # Linked Issue only appear once something's actually been
                # recorded -- see load_existing_review_tracking. Flattened
                # to one line each so this report stays losslessly
                # round-trippable (see _flatten_tracking_value).
                (
                    "Execution Status",
                    _flatten_tracking_value(tracking.get("Execution Status") or DEFAULT_EXECUTION_STATUS),
                ),
                ("Actual Result", _flatten_tracking_value(tracking.get("Actual Result", ""))),
                ("Linked Issue", _flatten_tracking_value(tracking.get("Linked Issue", ""))),
            ]
            if value
        ),
    ]
    if tc.steps:
        parts.append(
            build_table(
                ["Step", "Action", "Test Data", "Expected Result"],
                [[str(s.step_number), s.action, s.test_data, s.expected_result] for s in tc.steps],
            )
        )
    return "\n\n".join(p for p in parts if p and p.strip())


def _build_test_cases(
    document: TestCaseDocument,
    requirement_texts: dict[str, str],
    tracking: dict[str, dict[str, str]],
) -> str:
    if not document.test_cases:
        return "## Test Cases\n\nNo test cases were generated for this run."
    entries = [
        _build_test_case(tc, requirement_texts.get(tc.req_id, ""), tracking.get(tc.tc_id, {}))
        for tc in document.test_cases
    ]
    # Dividers separate individual test cases from each other, not the
    # section heading from the first one.
    return "## Test Cases\n\n" + "\n\n---\n\n".join(entries)


def _build_not_covered(document: TestCaseDocument, requirement_texts: dict[str, str]) -> str:
    """The Requirement column carries the same sibling-analysis lookup each
    test case's own `Requirement` field uses (`load_requirement_texts`) --
    a bare `REQ-021` tells a reviewer nothing about what's going untested,
    and the whole point of this section is that they can weigh the gap
    without opening the analysis report. Best-effort like everywhere else
    that lookup is used: an id the analysis doesn't carry just leaves the
    cell blank rather than failing the report."""
    if not document.not_covered:
        return ""
    return "\n\n".join(
        [
            "## Not Covered",
            "Requirements still blocked on client clarification -- no test cases "
            "were generated for these; see the requirement-analysis report for "
            "the underlying gap.",
            build_table(
                ["Requirement ID", "Requirement", "Reason"],
                [
                    [entry.req_id, requirement_texts.get(entry.req_id, ""), entry.reason]
                    for entry in document.not_covered
                ],
            ),
        ]
    )


def build_report(
    document: TestCaseDocument,
    requirement_texts: dict[str, str],
    tracking: dict[str, dict[str, str]] | None = None,
) -> str:
    # `document_control.title` already reads "Test Cases for <doc-name>" per
    # the test-case-generator agent's own convention for this field (see
    # test-case-output-structure skill) -- used verbatim as the heading
    # rather than prefixed a second time.
    control = document.document_control
    title = f"# {control.title}" if control.title else "# Test Cases"
    frontmatter = build_frontmatter(
        title=control.title or "Test Cases",
        document_type="Test Cases",
        tags=["test-cases", "qa"],
        project_id=control.project_id,
        document_id=control.document_id,
        version=control.version,
        approved_date=control.approved_date,
    )
    sections = [
        title,
        _build_version_control(document),
        _build_test_cases(document, requirement_texts, tracking or {}),
        _build_not_covered(document, requirement_texts),
    ]
    return frontmatter + "\n" + "\n\n---\n\n".join(p for p in sections if p and p.strip()) + "\n"


def write_report(doc_name: str, overrides: dict[str, dict[str, str]] | None = None) -> int:
    """Regenerates `<doc-name>-test-cases.md` from the JSON, carrying
    forward whatever tracking this same `.md` file already has recorded
    (`load_existing_review_tracking`, reading its own current content
    before it's overwritten). `overrides` layers fresh values for specific
    `tc_id`s on top of that carried-forward tracking -- this project itself
    never passes it (there is no automation flow here to run a suite and
    write results back); it exists for an external caller, such as a
    separate automation project's own post-test-run writer, to patch in
    Execution Status/Actual Result without touching the xlsx or the JSON.
    Any of the three tracking fields may be overridden by such a caller.
    Returns how many of `overrides`'s `tc_id`s actually matched a test
    case in the current JSON -- 0 when called with no
    overrides at all (a plain regeneration)."""
    json_path = test_cases_json_path(doc_name)
    data = read_json(json_path)

    errors, warnings = validate_file(json_path)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Refusing to generate the Test Cases report: {json_path.name} failed validation. "
            "Fix the JSON and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    document = TestCaseDocument.from_dict(data)
    requirement_texts = load_requirement_texts(doc_name)

    md_path = test_cases_md_path(doc_name)
    tracking = load_existing_review_tracking(md_path)
    matched = 0
    if overrides:
        current_tc_ids = {tc.tc_id for tc in document.test_cases}
        for tc_id, values in overrides.items():
            tracking.setdefault(tc_id, {}).update(values)
            if tc_id in current_tc_ids:
                matched += 1

    content = build_report(document, requirement_texts, tracking)

    md_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_previous_md(md_path, _extract_version, new_content=content)
    md_path.write_text(content, encoding="utf-8")
    print(str(md_path))
    return matched


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.generation.test_case_md_writer <doc-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    _, doc_name = sys.argv
    write_report(doc_name)


if __name__ == "__main__":
    main()
