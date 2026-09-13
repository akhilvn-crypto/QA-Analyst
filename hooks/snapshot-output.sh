#!/usr/bin/env bash
# PreToolUse hook for Write|Edit: before an existing JSON deliverable under
# this workspace's output/ (a *-analysis.json, *-test-plan.json, or
# *-test-cases.json) is overwritten, copies the current version to a sibling
# history/ folder, named with the version it carries (e.g.
# history/LinkGrid-analysis-v1.0.json).
#
# This is what makes re-analysis/regeneration a *provable* controlled
# revision rather than a trusted one: with the previous version preserved on
# disk, the validator can mechanically verify append-only changelogs,
# version bumps, and that carried-forward requirements really were carried
# forward unchanged.
#
# Contract: reads the tool-call JSON from stdin (tool_input.file_path).
# Always exits 0 / never denies -- snapshotting must never block the write,
# and a snapshot failure only logs to stderr.

set -uo pipefail

cat | python -c '
import json, re, shutil, sys
from pathlib import Path

try:
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
except Exception:
    sys.exit(0)

norm = file_path.replace("\\", "/")
if not re.search(
    r"output/(requirement-analysis|test-plan|test-cases)/[^/]+"
    r"-(analysis|test-plan|test-cases)\.json$",
    norm,
):
    sys.exit(0)

path = Path(file_path)
if not path.is_file():
    sys.exit(0)  # first generation -- nothing to snapshot


def payload_version(payload):
    if not isinstance(payload, dict):
        return "legacy"
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return "unversioned"
    return str(meta.get("version", "")).strip() or "unversioned"


try:
    version = payload_version(json.loads(path.read_text(encoding="utf-8")))
except Exception:
    version = "unversioned"

# Write tool calls carry the full new content -- when the incoming version
# equals the on-disk version, this is an in-run rewrite of the same draft
# (e.g. the agent fixing a validation error), not a revision overwrite.
# Snapshotting it would archive a draft under a real version label and make
# later history comparisons diff against that draft. Only a genuine version
# transition gets snapshotted. (Edit calls have no full content; they fall
# through to snapshotting, where the never-clobber rule below still keeps
# the first capture of each version authoritative.)
new_content = data.get("tool_input", {}).get("content")
if isinstance(new_content, str) and new_content.strip():
    try:
        new_version = payload_version(json.loads(new_content))
    except Exception:
        new_version = None
    if new_version is not None and new_version == version:
        sys.exit(0)

history_dir = path.parent / "history"
history_dir.mkdir(parents=True, exist_ok=True)
snapshot = history_dir / f"{path.stem}-v{version}{path.suffix}"

# Never clobber an existing snapshot of the same version (e.g. repeated
# edits within one run) -- the first capture of a version is the record.
def _report(message):
    # "allow" (never "deny") -- this hook must never block the write, only
    # report what it did. permissionDecisionReason is what actually surfaces
    # this message; a plain stderr print is invisible to the calling agent.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": message,
        }
    }))


if not snapshot.exists():
    try:
        shutil.copy2(path, snapshot)
        _report(f"snapshot-output hook: preserved {snapshot.name}")
    except Exception as exc:
        _report(f"snapshot-output hook: snapshot failed ({exc})")
'

exit 0
