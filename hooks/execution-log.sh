#!/usr/bin/env bash
# PostToolUse hook for Write|Edit: after an output JSON deliverable under
# this workspace's output/ (a *-analysis.json, *-test-plan.json, or
# *-test-cases.json) is written -- and after snapshot-output.sh's own
# PreToolUse snapshot for the same call has already landed in history/ --
# records who made this revision and when (IST) to a sibling
# execution-log/ folder, via `orchestrator.utils.execution_log`.
#
# This is the audit-trail counterpart to snapshot-output.sh: that hook
# preserves the outgoing *file*; this one records the *event* -- actor,
# timestamp, and version transition -- reusing history/'s own contents to
# recover the "from" version rather than needing any state handed over from
# the PreToolUse hook. The four `.md` reports get the identical treatment
# from `orchestrator.utils.md_history.snapshot_previous_md` instead, called
# directly from Python by their own writers.
#
# Contract: reads the tool-call JSON from stdin (tool_input.file_path).
# Always exits 0 -- this must never block the write or surface an error to
# the agent; a failed log entry only costs visibility, never the actual
# deliverable. The inner `python -m orchestrator.utils.execution_log`
# subprocess gets PYTHONPATH=$CLAUDE_PLUGIN_ROOT explicitly, same as
# validate-output.sh, since this hook can fire before any Bash call has run
# in this workspace.

set -uo pipefail

PY="$(command -v python3 >/dev/null 2>&1 && python3 -c "" >/dev/null 2>&1 && echo python3 || echo python)"

cat | "$PY" -c '
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
    subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "orchestrator.utils.execution_log", file_path],
        capture_output=True,
        timeout=60,
        env=env,
    )
except Exception:
    sys.exit(0)
'

exit 0
