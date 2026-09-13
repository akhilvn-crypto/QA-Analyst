"""CLI gate for the JSON deliverables.

Usage:
    python -m orchestrator.validation.validate <path-to-json>

The file kind is detected from its name: *-analysis.json is validated as a
requirement analysis, *-test-plan.json as a test plan, *-test-cases.json as
a test-case set. Prints ERROR/WARNING lines; exits 1 if any errors were
found (warnings alone exit 0).

Run automatically by the validate-output PostToolUse hook whenever an
output JSON is written, and again by the docx writers / zephyr_export
before rendering.
"""

import json
import sys
from pathlib import Path

from orchestrator.validation.analysis_validator import (
    compare_with_previous,
    validate_analysis,
)
from orchestrator.validation.test_plan_validator import (
    compare_test_plan_with_previous,
    cross_validate_test_plan,
    validate_test_plan,
)
from orchestrator.validation.test_case_validator import (
    compare_with_previous as compare_test_cases_with_previous,
    cross_validate_test_cases,
    validate_test_cases,
)


def _load(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _source_file(workspace_root: Path, doc_name: str) -> Path | None:
    """The combined requirement source for a doc-name — the markdown
    `parsing.reading_vault_fetch` stages from every `.md` file under the
    configured requirementReading vault. `None` if it hasn't been
    generated (or the doc-name doesn't match one that has)."""
    source_path = (
        workspace_root / "output" / "requirement-analysis" / f"{doc_name}-source.md"
    )
    return source_path if source_path.exists() else None


def _staleness_warnings(path: Path, doc_name: str) -> list[str]:
    """Warn when the artifact chain is out of date: requirement source newer
    than the analysis it was derived from."""
    workspace_root = path.parents[2]
    analysis_path = (
        workspace_root / "output" / "requirement-analysis" / f"{doc_name}-analysis.json"
    )
    if not analysis_path.exists():
        return []

    warnings = []
    source = _source_file(workspace_root, doc_name)
    if source and source.stat().st_mtime > analysis_path.stat().st_mtime:
        warnings.append(
            f"The requirement source ({source.name}) was modified after the "
            "analysis was generated — the analysis may be stale; consider "
            "re-running /analyse-requirement."
        )
    return warnings


def _latest_snapshot(path: Path):
    """The most recent history/ snapshot of this deliverable, or None.
    Snapshots are written by the snapshot-output PreToolUse hook as
    history/<stem>-v<version>.json before every overwrite."""
    history_dir = path.parent / "history"
    if not history_dir.is_dir():
        return None
    snapshots = sorted(
        history_dir.glob(f"{path.stem}-v*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return snapshots[-1] if snapshots else None


def _history_checks(path: Path, data, compare) -> tuple[list[str], list[str]]:
    snapshot = _latest_snapshot(path)
    if snapshot is None:
        return [], []
    try:
        old_data = _load(snapshot)
    except json.JSONDecodeError:
        return [], [f"History comparison skipped: {snapshot.name} is not valid JSON."]
    errors, warnings = compare(data, old_data)
    return errors, warnings


def validate_file(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the JSON deliverable at `path`,
    including cross-artifact and staleness checks when the sibling
    artifacts exist on disk."""
    path = path.resolve()
    name = path.name

    try:
        data = _load(path)
    except json.JSONDecodeError as exc:
        return [f"{name}: not valid JSON ({exc})."], []

    if name.endswith("-analysis.json"):
        doc_name = name[: -len("-analysis.json")]
        errors, warnings = validate_analysis(data)
        hist_errors, hist_warnings = _history_checks(path, data, compare_with_previous)
        errors += hist_errors
        warnings += hist_warnings
        warnings += _staleness_warnings(path, doc_name)
        return errors, warnings

    if name.endswith("-test-plan.json"):
        doc_name = name[: -len("-test-plan.json")]
        errors, warnings = validate_test_plan(data)

        analysis_path = (
            path.parents[2]
            / "output"
            / "requirement-analysis"
            / f"{doc_name}-analysis.json"
        )
        if not errors and analysis_path.exists():
            try:
                analysis_data = _load(analysis_path)
            except json.JSONDecodeError:
                warnings.append(
                    f"Cross-validation skipped: {analysis_path.name} is not valid JSON."
                )
            else:
                cross_errors, cross_warnings = cross_validate_test_plan(data, analysis_data)
                errors += cross_errors
                warnings += cross_warnings
        hist_errors, hist_warnings = _history_checks(
            path, data, compare_test_plan_with_previous
        )
        errors += hist_errors
        warnings += hist_warnings
        warnings += _staleness_warnings(path, doc_name)
        return errors, warnings

    if name.endswith("-test-cases.json"):
        doc_name = name[: -len("-test-cases.json")]
        errors, warnings = validate_test_cases(data)

        analysis_path = (
            path.parents[2]
            / "output"
            / "requirement-analysis"
            / f"{doc_name}-analysis.json"
        )
        if not errors and analysis_path.exists():
            try:
                analysis_data = _load(analysis_path)
            except json.JSONDecodeError:
                warnings.append(
                    f"Cross-validation skipped: {analysis_path.name} is not valid JSON."
                )
            else:
                cross_errors, cross_warnings = cross_validate_test_cases(data, analysis_data)
                errors += cross_errors
                warnings += cross_warnings
                if analysis_path.stat().st_mtime > path.stat().st_mtime:
                    warnings.append(
                        f"{analysis_path.name} was regenerated after these test cases "
                        "were generated — coverage may be stale; consider re-running "
                        "/generate-test-cases."
                    )
        hist_errors, hist_warnings = _history_checks(
            path, data, compare_test_cases_with_previous
        )
        errors += hist_errors
        warnings += hist_warnings
        warnings += _staleness_warnings(path, doc_name)
        return errors, warnings

    return (
        [
            f"{name}: unknown deliverable kind (expected *-analysis.json, "
            "*-test-plan.json, or *-test-cases.json)."
        ],
        [],
    )


def report(errors: list[str], warnings: list[str], *, label: str) -> None:
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"{label}: FAILED — {len(errors)} error(s), {len(warnings)} warning(s).")
    else:
        print(f"{label}: OK — 0 errors, {len(warnings)} warning(s).")


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.validation.validate <path-to-json>",
            file=sys.stderr,
        )
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(2)

    errors, warnings = validate_file(path)
    report(errors, warnings, label=path.name)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
