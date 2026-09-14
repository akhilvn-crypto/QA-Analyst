"""Resolves every user-supplied input by *convention*, from the folder the
user attached in Cowork -- there is no `config/settings.json` to fill in.

The attached folder (the session's cwd, `paths.WORKSPACE_ROOT`) is the
whole project: the client's vault of notes, and the home of every
generated deliverable. Inside it, a fixed set of subfolders answers each
question a settings file used to:

    <attached folder>/
      Requirements/      requirement .md notes -- the sole requirement input (required)
      Knowledge Base/    general domain-background notes (optional)
      Branding/          header-logo.png / project-logo.png overrides (optional)
      Project Info.md    operator identity frontmatter (optional)
      output/            generated deliverables (self-creates)

Subfolder names are matched case-insensitively and ignoring spaces, `-`
and `_`, so `Knowledge Base`, `knowledge-base` and `knowledge_base` all
resolve -- a vault's own naming habits never have to change to suit this
plugin, and Cowork's case-sensitive Linux sandbox behaves the same as a
Windows host.

When a client vault names one of these folders something this convention
match can't recognize at all (`Specs/` instead of any spelling of
`Requirements`, say), `requirements_path`/`knowledge_base_path` take an
optional `folder_override` -- an exact top-level folder name -- so an agent
that has already listed the workspace root itself and used its own
judgment to identify the right folder can hand that name straight through,
without this module trying to be clever about it. There is nowhere to
persist that choice (no settings file), so it's re-supplied on whichever
call needs it, same as everything else here being resolved fresh rather
than cached.

There is no handoff destination: deliverables are written straight into
this same folder's `output/`, which is already where the user works.

Nothing is cached -- every call reads the folder as it is right now, so a
subfolder created mid-session (e.g. adding `Knowledge Base/` before
`/build-kb-catalog`) is picked up by the very next call.
"""

import re
from pathlib import Path

REQUIREMENTS_DIRNAME = "Requirements"
KNOWLEDGE_BASE_DIRNAME = "Knowledge Base"
BRANDING_DIRNAME = "Branding"
PROJECT_INFO_FILENAME = "Project Info.md"

OPERATOR_KEYS = ("name", "designation", "projectName", "projectId")


def workspace_root() -> Path:
    from orchestrator.utils import paths

    return paths.WORKSPACE_ROOT


def _normalize(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name).lower()


def _find_child(name: str, *, want_dir: bool) -> Path | None:
    """The direct child of the workspace matching `name` -- exact spelling
    first, then the normalized match described in the module docstring.
    `None` when nothing matches."""
    root = workspace_root()
    exact = root / name
    if (exact.is_dir() if want_dir else exact.is_file()):
        return exact
    target = _normalize(name)
    try:
        children = sorted(root.iterdir())
    except OSError:
        return None
    for child in children:
        if (child.is_dir() if want_dir else child.is_file()) and _normalize(child.name) == target:
            return child
    return None


def requirements_path(folder_override: str | None = None) -> Path | None:
    """The `Requirements/` subfolder -- `None` when the attached folder has
    none, meaning there is no requirement source to analyze.

    `folder_override`, when given, is an exact top-level folder name to use
    instead of matching `Requirements` by convention -- see the module
    docstring's folder-auto-detection note. `None` if that exact name isn't
    a directory of the workspace either."""
    if folder_override:
        candidate = workspace_root() / folder_override
        return candidate if candidate.is_dir() else None
    return _find_child(REQUIREMENTS_DIRNAME, want_dir=True)


def knowledge_base_path(folder_override: str | None = None) -> Path | None:
    """The `Knowledge Base/` subfolder -- `None` when absent. Optional: no
    knowledge base simply means agents reason from the requirement text
    alone. See `requirements_path` for `folder_override`."""
    if folder_override:
        candidate = workspace_root() / folder_override
        return candidate if candidate.is_dir() else None
    return _find_child(KNOWLEDGE_BASE_DIRNAME, want_dir=True)


def branding_path() -> Path | None:
    """The optional `Branding/` subfolder overriding the plugin's bundled
    logos (see `paths.header_logo_path`/`project_logo_path`)."""
    return _find_child(BRANDING_DIRNAME, want_dir=True)


def document_name() -> str:
    """`<doc-name>` for every output path: the attached folder's own name
    (e.g. `LinkGrid`), not the fixed `Requirements` subfolder's, which would
    be identical for every project."""
    return workspace_root().resolve().name


def _parse_frontmatter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def operator_info() -> dict:
    """The human identity execution-log entries attribute a controlled
    revision to -- `name`, `designation`, `projectName`, `projectId`, read
    from `Project Info.md`'s YAML frontmatter at the attached folder's root.
    Each is the empty string when the note or the key is missing; callers
    render a blank field as this project's standard TBD placeholder
    themselves -- never fabricated, never defaulted to an OS/git username."""
    info = dict.fromkeys(OPERATOR_KEYS, "")
    note = _find_child(PROJECT_INFO_FILENAME, want_dir=False)
    if note is None:
        return info
    try:
        frontmatter = _parse_frontmatter(note.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return info
    for key in OPERATOR_KEYS:
        info[key] = str(frontmatter.get(key, "") or "")
    return info
