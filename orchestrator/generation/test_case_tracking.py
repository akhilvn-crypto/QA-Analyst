"""Shared execution-tracking primitives for the test-cases deliverable --
Execution Status/Actual Result/Linked Issue defaults, and the sibling
requirement-text lookup both the Markdown report (`test_case_md_writer.py`)
and the CSV/XLSX export (`zephyr_export.py`) need.

Pulled out into its own module for the same reason `xlsx_helpers.py` was
already pulled out of `zephyr_export.py` (see that module's own docstring):
avoiding an import cycle. The Markdown report is now the one true source of
these three tracking fields -- `test_case_md_writer.load_existing_review_
tracking` reads them straight from the `.md` file itself -- and
`zephyr_export.py` imports that function to carry tracking forward into a
regenerated xlsx (see its own module docstring). That's a one-directional
dependency (`zephyr_export.py` -> `test_case_md_writer.py`); putting the
constants/helpers both modules *also* need here, instead of in either of
them, means neither has to import the other's whole module just for these.
"""

from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.paths import analysis_json_path

EXECUTION_STATUS_OPTIONS = ("Pass", "Fail", "Not Executed")
DEFAULT_EXECUTION_STATUS = "Not Executed"


def requirement_display_text(requirement: dict) -> str:
    """What a deliverable shows next to a requirement's id: its
    `requirement_text`, falling back to its `title` when that's blank.

    Every deliverable that prints a req_id prints this beside it -- the
    test-cases report's `Requirement` field and Not Covered table, the
    Zephyr/xlsx exports, and the traceability matrix's own `Requirement`
    column -- so a reader is never handed a bare `REQ-021` to go look up.
    One rule in one place so those renderings can't drift apart."""
    if not isinstance(requirement, dict):
        return ""
    return (
        str(requirement.get("requirement_text") or "").strip()
        or str(requirement.get("title") or "").strip()
    )


def load_requirement_texts(doc_name: str) -> dict[str, str]:
    """req_id -> its display text (`requirement_display_text`), read from the
    sibling requirement-analysis JSON (best-effort: if it's missing or
    unreadable, the Requirement column/field is just left blank rather than
    failing the whole report/export -- the analysis JSON isn't either of
    these writers' own deliverable to guarantee)."""
    path = analysis_json_path(doc_name)
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception:
        return {}
    items = data.get("requirements", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("req_id", "")): requirement_display_text(item)
        for item in items
        if isinstance(item, dict)
    }


def has_recorded_tracking_data(tracking: dict[str, str]) -> bool:
    """True when `tracking` holds more than the untouched-export defaults --
    used to decide whether a dropped tc_id is worth naming in a "discarded
    tracking data" note (every never-executed test case already carries the
    default Execution Status, so that alone shouldn't trigger the note)."""
    if tracking.get("Actual Result") or tracking.get("Linked Issue"):
        return True
    status = tracking.get("Execution Status", "")
    return bool(status) and status != DEFAULT_EXECUTION_STATUS
