"""Resolves every user-supplied input from the project root -- there is no
`config/settings.json` to fill in.

The project root open in the editor (the session's cwd,
`paths.WORKSPACE_ROOT`) is the whole project: the client's notes, and the
home of every generated deliverable. The two input folders are normally
named on the command itself (`--req "<folder>"`/`--kb "<folder>"`, which
each agent passes down as this module's `folder_override`); when a flag is
omitted, a fixed set of subfolder names answers the same question a
settings file used to:

    <project root>/
      Requirements/      requirement .md notes -- the sole requirement input (required)
      Knowledge Base/    general domain-background notes (optional)
      Branding/          header-logo.png / project-logo.png (optional; no bundled default)
      output/            generated deliverables (self-creates)

Subfolder names are matched case-insensitively and ignoring spaces, `-`
and `_`, so `Knowledge Base`, `knowledge-base` and `knowledge_base` all
resolve -- a vault's own naming habits never have to change to suit this
plugin, and Cowork's case-sensitive Linux sandbox behaves the same as a
Windows host.

`requirements_path`/`knowledge_base_path` take an optional
`folder_override` -- an exact top-level folder name, used verbatim with no
matching at all. It carries the user's own `--req`/`--kb` value, and also
serves the case where a project names one of these folders something the
convention match can't recognize (`Specs/` instead of any spelling of
`Requirements`, say) and the invoking agent has listed the project root
itself and used its judgment to identify the right one. Either way this
module isn't clever about it: an override that isn't a directory resolves
to `None` rather than falling back to a folder the caller didn't ask for.
There is nowhere to persist that choice (no settings file), so it's
re-supplied on whichever call needs it, same as everything else here being
resolved fresh rather than cached.

There is no handoff destination: deliverables are written straight into
this same folder's `output/`, which is already where the user works.

Nothing is cached -- every call reads the folder as it is right now, so a
subfolder created mid-session (e.g. adding `Knowledge Base/` before a
generator agent runs) is picked up by the very next call.
"""

import re
from pathlib import Path

REQUIREMENTS_DIRNAME = "Requirements"
KNOWLEDGE_BASE_DIRNAME = "Knowledge Base"
BRANDING_DIRNAME = "Branding"


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

    `folder_override`, when given (the command's own `--req "<folder>"`, or
    an agent's auto-detected name), is an exact top-level folder name used
    instead of matching `Requirements` by convention -- see the module
    docstring. `None` if that exact name isn't a directory of the project
    root, never a silent fallback to a different folder."""
    if folder_override:
        candidate = workspace_root() / folder_override
        return candidate if candidate.is_dir() else None
    return _find_child(REQUIREMENTS_DIRNAME, want_dir=True)


def knowledge_base_path(folder_override: str | None = None) -> Path | None:
    """The knowledge-base subfolder -- `None` when absent. Optional: no
    knowledge base simply means agents reason from the requirement text
    alone. See `requirements_path` for `folder_override`, which here
    carries the command's `--kb "<folder>"`."""
    if folder_override:
        candidate = workspace_root() / folder_override
        return candidate if candidate.is_dir() else None
    return _find_child(KNOWLEDGE_BASE_DIRNAME, want_dir=True)


def branding_path() -> Path | None:
    """The optional `Branding/` subfolder supplying `header-logo.png` /
    `project-logo.png` (see `paths.header_logo_path`/`project_logo_path`).
    The plugin ships no default logos of its own -- `None` here just means
    reports render without one."""
    return _find_child(BRANDING_DIRNAME, want_dir=True)


def document_name() -> str:
    """`<doc-name>` for every output path: the project root's own folder
    name (e.g. `LinkGrid`), not the requirement subfolder's, which would be
    identical for every project."""
    return workspace_root().resolve().name

