#!/usr/bin/env bash
# PostToolUse hook for Write|Edit: whenever an agent writes or edits a JSON
# deliverable under this workspace's output/ (a *-analysis.json, *-test-plan.json,
# or *-test-cases.json), runs `python -m orchestrator.validation.validate` on
# it and feeds the result back:
#   - validation errors  -> {"decision": "block", "reason": ...} so the
#     writing agent immediately sees exactly what to fix, instead of the
#     problem surfacing later (or never) in the docx step.
#   - warnings only      -> additionalContext, informational.
#   - clean              -> silent no-op.
#
# This is the mechanical enforcement of the frameworks' "final consistency
# review" checklists -- the agent still does that review itself, but a slip
# no longer reaches the docx or downstream agents undetected.
#
# Contract: reads the tool-call JSON from stdin (tool_input.file_path).
# No-ops (exit 0) for any other file, and never blocks on its own failure.
# The inner `python -m orchestrator.validation.validate` subprocess gets
# PYTHONPATH=$CLAUDE_PLUGIN_ROOT explicitly (inherited from this hook's own
# environment, which reliably has it -- orchestrator/ is bundled with the
# plugin, not the workspace) rather than depending on cwd or the
# ./.qa-orchestrator shim -- this hook can fire before any Bash call has run
# in this workspace, so the shim isn't guaranteed to exist yet.

set -uo pipefail

cat | python -c '
import json, os, re, subprocess, sys

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

try:
    env = {**os.environ, "PYTHONPATH": os.environ.get("CLAUDE_PLUGIN_ROOT", "")}
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "orchestrator.validation.validate", file_path],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
except Exception:
    sys.exit(0)

output = ((proc.stdout or "") + (proc.stderr or "")).strip()

if proc.returncode != 0:
    print(json.dumps({
        "decision": "block",
        "reason": (
            "validate-output hook: the JSON deliverable just written failed "
            "validation. Fix the JSON before generating the docx or "
            "finishing.\n\n" + output
        ),
    }))
elif "WARNING:" in output:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "validate-output hook (non-blocking):\n" + output,
        }
    }))
'

exit 0
