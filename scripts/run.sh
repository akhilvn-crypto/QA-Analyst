#!/usr/bin/env bash
# Self-locating wrapper so `orchestrator/` (this project's own repo root) is
# importable via `python -m orchestrator.<module>` regardless of the
# caller's cwd (which is always the workspace root this project operates
# on -- the same directory `orchestrator/` and `scripts/` both live in).
#
# Usage: run.sh <folder.module> [args...]
#   e.g. run.sh generation.docx_report_writer Requirements
#   ->   python -m orchestrator.generation.docx_report_writer Requirements
#
# Usage: run.sh --print-project-root
#   Prints this project's own repo root and exits -- the same value
#   PYTHONPATH is set to below. An agent step that needs the repo root for a
#   plain file copy, not a Python invocation, can use this to ask for it
#   through the same reliable self-location mechanism, without needing
#   $CLAUDE_PROJECT_DIR (not reliably available to agent-issued Bash) or a
#   second discovery path.
#
# Deliberately self-locating via $0/BASH_SOURCE rather than reading
# $CLAUDE_PROJECT_DIR directly -- that variable is confirmed available to
# hook subprocesses but not to an agent's own Bash-tool-issued commands, so
# nothing here may depend on it being set. This script only needs to know
# its own path, which is always true.
#
# Single-path PYTHONPATH assignment deliberately -- sidesteps the `:` vs `;`
# separator difference between POSIX and native Windows Python, since
# there's nothing to join.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ "$#" -lt 1 ]; then
  echo "Usage: run.sh <folder.module> [args...]  |  run.sh --print-project-root" >&2
  exit 2
fi

if [ "$1" = "--print-project-root" ]; then
  printf '%s\n' "$PROJECT_ROOT"
  exit 0
fi

module="$1"
shift

PYTHON_BIN="${PYTHON_EXE:-}"
if [ -z "$PYTHON_BIN" ]; then
  # python3 first for Cowork's Linux sandbox; `python` for Windows hosts,
  # where `python3` is often a Microsoft Store stub that doesn't run.
  if python3 -c "" >/dev/null 2>&1; then PYTHON_BIN=python3; else PYTHON_BIN=python; fi
fi
exec env PYTHONPATH="$PROJECT_ROOT" "$PYTHON_BIN" -m "orchestrator.$module" "$@"
