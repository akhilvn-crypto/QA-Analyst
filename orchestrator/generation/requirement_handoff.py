"""Hands off an approved requirement-analysis report, an approved Client
Clarification Sheet, an approved Test Plan, or an approved Test Case suite
to this project's configured Obsidian destination.

Usage:
    python -m orchestrator.generation.requirement_handoff <doc-name> [--target analysis|clarifications|test-plan|test-cases] [--force]

`--target analysis` (the default) copies
output/requirement-analysis/<doc-name>-analysis.md; `--target
clarifications` copies
output/client-clarifications/<doc-name>-clarifications.md; `--target
test-plan` copies output/test-plan/<doc-name>-test-plan.md; `--target
test-cases` copies output/test-cases/<doc-name>-test-cases.md — to
`config/settings.json`'s `requirementHandoff.obsidianDestinationPath`
(unchanged filename) -- a copy, not a move: the source `.md` stays in
`output/` as this project's own durable record, and the Obsidian folder
gets an identical copy for the client-facing vault. Invoked via
`/handoff-requirement [--force]`, `/handoff-clarification-sheet [--force]`,
`/handoff-test-plan [--force]`, or `/handoff-test-cases [--force]`, after a
human has reviewed the relevant `.md` and is satisfied with it -- this
script does no reviewing or reasoning of its own, it only relocates a file
a human already approved.

Refuses to silently clobber a destination copy that already exists with
different content (e.g. someone annotated the note in Obsidian since the
last handoff) -- `--force` overrides on explicit request, mirroring
`clarification_sheet_writer`'s overwrite guard for the same reason: never
silently discard content a person may have added.
"""

import argparse
import shutil
import sys
from pathlib import Path

from orchestrator.utils.config import requirement_handoff_destination_path
from orchestrator.utils.paths import (
    analysis_md_path,
    clarification_sheet_md_path,
    test_cases_md_path,
    test_plan_md_path,
)

# The four targets `handoff()` knows how to copy -- used for CLI --target
# choices and error messages. Deliberately *not* a dict of the path
# functions themselves: building that dict at import time would freeze in
# the function objects `analysis_md_path`/`clarification_sheet_md_path`/
# `test_plan_md_path`/`test_cases_md_path` were bound to at that moment,
# which breaks test monkeypatching of this module's own attributes (tests
# replace `requirement_handoff.analysis_md_path`, not
# `orchestrator.utils.paths.analysis_md_path`) -- see `handoff()` below,
# which instead looks each one up by name at call time so a patched
# attribute is always honored.
_TARGET_CHOICES = (
    "analysis",
    "clarifications",
    "test-plan",
    "test-cases",
)


def handoff(doc_name: str, *, target: str = "analysis", force: bool = False) -> Path:
    if target == "analysis":
        source = analysis_md_path(doc_name)
        hint_command = "/analyse-requirement"
    elif target == "clarifications":
        source = clarification_sheet_md_path(doc_name)
        hint_command = "/generate-clarification-sheet"
    elif target == "test-plan":
        source = test_plan_md_path(doc_name)
        hint_command = "/generate-test-plan"
    elif target == "test-cases":
        source = test_cases_md_path(doc_name)
        hint_command = "/generate-test-cases"
    else:
        raise ValueError(f"Unknown target {target!r} -- expected one of {_TARGET_CHOICES}")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found -- run {hint_command} {doc_name} first to produce it."
        )

    destination_dir = requirement_handoff_destination_path()
    if destination_dir is None:
        raise RuntimeError(
            "requirementHandoff.obsidianDestinationPath is blank in config/settings.json -- "
            "set it to the Obsidian folder approved analyses should be handed off into."
        )

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name

    if destination.exists() and not force:
        existing = destination.read_text(encoding="utf-8", errors="replace")
        incoming = source.read_text(encoding="utf-8")
        if existing != incoming:
            raise FileExistsError(
                f"{destination} already exists with different content -- pass --force to overwrite, "
                "or move/rename the existing note first if it holds edits you don't want to lose."
            )

    shutil.copy2(source, destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.generation.requirement_handoff",
        description="Copy an approved analysis or clarification-sheet .md to the configured Obsidian destination.",
    )
    parser.add_argument("doc_name")
    parser.add_argument(
        "--target",
        choices=_TARGET_CHOICES,
        default="analysis",
        help="Which deliverable's .md to hand off (default: analysis).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing destination copy even if its content differs.",
    )
    args = parser.parse_args()

    try:
        destination = handoff(args.doc_name, target=args.target, force=args.force)
    except (FileNotFoundError, RuntimeError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(str(destination))


if __name__ == "__main__":
    main()
