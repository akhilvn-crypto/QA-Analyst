"""Renders the Obsidian-style YAML frontmatter "Properties" block every
generated Markdown deliverable now opens with -- `title`, `document_type`,
`project_id`, `document_id`, `version`, `approved_date`, `privacy`, `tags` --
the same property set Obsidian itself surfaces as a Properties panel when a
note's first lines are a `---`-fenced YAML block.

Shared by all four `.md` writers (`md_report_writer.py`,
`test_plan_md_writer.py`, `test_case_md_writer.py`,
`clarification_sheet_writer.py`) so the shape of this block -- key order,
quoting, tag rendering -- can never drift between them; each writer only
supplies its own `title`/`document_type`/`tags` and whatever
`document_control`/`meta` fields it actually has (a writer with no field for
a given property, e.g. the Clarification Sheet's own version, just passes
`""`).

`privacy` is a fixed "Confidential" document-handling default across all
four -- not a client fact read out of the JSON. Only the requirement
analysis carries anything close (`document_control.classification`, its own
"Classification" body bullet), and that stays exactly where it already was,
untouched by this module. `tags` is a fixed `[<kind>, "qa"]` pair per
deliverable type, supplied by the caller -- deterministic categorisation,
not a claim about the client's requirement or project, so this project's
"never fabricate a client-facing fact" rule (see root CLAUDE.md's
Deliverable shape section) doesn't apply to either property the way it does
to `project_id`/`document_id`/`version`/`approved_date`, which are rendered
verbatim from the deliverable's own document_control/meta -- including
whatever "TBD -- Client/Project Input Required" placeholder is already
sitting in that field, exactly as the body already shows it.
"""

PRIVACY = "Confidential"


def _quote(value: str) -> str:
    """Double-quoted YAML scalar -- safe for any value this project's
    fields can hold (free text that may contain a colon, a quote, a leading
    dash, etc.), unlike a bare scalar which YAML would misparse on those."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_frontmatter(
    *,
    title: str,
    document_type: str,
    tags: list[str],
    project_id: str = "",
    document_id: str = "",
    version: str = "",
    approved_date: str = "",
) -> str:
    """Returns the `---`-fenced YAML block, newline-terminated, ready to
    prepend directly to a report's own Markdown body."""
    lines = [
        "---",
        f"title: {_quote(title)}",
        f"document_type: {_quote(document_type)}",
        f"project_id: {_quote(project_id)}",
        f"document_id: {_quote(document_id)}",
        f"version: {_quote(version)}",
        f"approved_date: {_quote(approved_date)}",
        f"privacy: {_quote(PRIVACY)}",
    ]
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {_quote(tag)}" for tag in tags)
    else:
        lines.append("tags: []")
    lines.append("---")
    return "\n".join(lines) + "\n"


def title_with_project(project_name: str, document_type: str) -> str:
    """"<Project Name> <Document Type>" when a real project name is known
    (present, and not this project's own "TBD -- Client/Project Input
    Required" placeholder), else the bare `document_type` -- the same
    "<Project Name> Release Note" shape the Obsidian Release Note template
    (see `unnamed.webp`) already uses for its own `title` property.

    Only meaningful for a writer whose own project-name field holds the bare
    project name (the requirement analysis's `document_control.title`, the
    Test Plan's `meta.title`, or a doc-name standing in for the Clarification
    Sheet, which has no document_control of its own). The Test Cases
    writer's `document_control.title` already reads as a full composed
    title ("Test Cases for <doc-name>") by that agent's own convention, so
    it's used as-is instead of being passed through this helper."""
    name = (project_name or "").strip()
    if name and not name.upper().startswith("TBD"):
        return f"{name} {document_type}"
    return document_type
