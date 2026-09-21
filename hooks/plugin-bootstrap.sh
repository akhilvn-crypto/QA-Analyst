#!/usr/bin/env bash
# Registered twice in hooks.json: as a SessionStart hook (fires once, the
# moment a session opens) and as a PreToolUse hook for Bash|PowerShell (a
# redundant safety net for the rare case a session resumes/continues
# without ever re-firing SessionStart). SessionStart is the mechanism this
# relies on for correctness -- it doesn't key off any tool name, so it
# fires identically whether the session's shell tool is Bash, PowerShell,
# or not exposed to the agent yet at all.
#
# Why this exists: `python -m orchestrator.<module>` needs this plugin's own
# bundled orchestrator/ directory on PYTHONPATH, but an agent's own
# Bash-tool-issued commands don't reliably see $CLAUDE_PLUGIN_ROOT (only hook
# subprocesses are confirmed to have it). This hook -- which does have it --
# writes a tiny shim that self-locates scripts/run.sh via its own baked-in
# plugin install root, so every agent/hook invocation just runs
# `bash "$HOME/.qa-analyst/run.sh" <folder.module> [args...]`.
#
# **Nothing is ever written into the user's working directory.** The shim
# and the dependency marker both live in one per-user directory,
# $HOME/.qa-analyst/ -- one copy per machine, not a pair of dotfiles in
# every folder the user ever opens. That's also why the shim is referenced
# through $HOME (expanded by the Bash tool's own shell) rather than as a
# cwd-relative `./.qa-orchestrator`: the path has to be identical from
# every project, since the plugin is used from whichever project root is
# open in VS Code. Nothing is scaffolded in the project either:
# `Requirements/`, `Knowledge Base/` and `Branding/` are the user's own
# content (named explicitly via `--req`/`--kb`, or discovered by convention
# in `orchestrator/utils/workspace.py`), and `output/` self-creates via
# every writer's own mkdir.
#
# Python resolution: Cowork runs sessions in a Linux sandbox where only
# `python3` may exist, while Windows hosts usually only have `python`. The
# first working interpreter is baked into the shim as PYTHON_EXE (read by
# scripts/run.sh). Dependency installs retry with `--user` and then
# `--break-system-packages` for PEP 668 "externally managed" environments.
#
# Contract: always "allow" (silent exit 0) -- this is a pure side effect and
# must never block whatever triggered it, or fail loudly on its own account.
# Reads no stdin (unlike this project's other hooks) -- everything it needs
# comes from $CLAUDE_PLUGIN_ROOT and $HOME, which is why the exact same
# script is safe to register under both SessionStart and PreToolUse.

set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$PLUGIN_ROOT" ]; then
  exit 0
fi

# Git Bash on Windows sets HOME; fall back to USERPROFILE if some host
# doesn't. With neither there is no stable per-user location to write to,
# and guessing one would be worse than doing nothing.
HOME_DIR="${HOME:-}"
if [ -z "$HOME_DIR" ]; then
  HOME_DIR="${USERPROFILE:-}"
fi
if [ -z "$HOME_DIR" ]; then
  exit 0
fi

QA_DIR="$HOME_DIR/.qa-analyst"
SHIM="$QA_DIR/run.sh"
DEPS_MARKER="$QA_DIR/deps-ok"

mkdir -p "$QA_DIR" 2>/dev/null || exit 0

PY=""
for candidate in python3 python; do
  if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  exit 0
fi

# --- 1. (Re)write the shim if missing or pointing at a different plugin
#        install root / interpreter. ---
expected_shim="#!/usr/bin/env bash
export PYTHON_EXE=\"\${PYTHON_EXE:-$PY}\"
exec bash \"$PLUGIN_ROOT/scripts/run.sh\" \"\$@\"
"

current_shim=""
if [ -f "$SHIM" ]; then
  current_shim="$(cat "$SHIM" 2>/dev/null || true)"
fi

if [ "$current_shim" != "$expected_shim" ]; then
  tmp_shim="$QA_DIR/.run.sh.tmp.$$"
  printf '%s' "$expected_shim" > "$tmp_shim" 2>/dev/null && \
    chmod +x "$tmp_shim" 2>/dev/null; \
    mv -f "$tmp_shim" "$SHIM" 2>/dev/null || rm -f "$tmp_shim" 2>/dev/null
  chmod +x "$SHIM" 2>/dev/null || true
fi

# --- 2. Ensure orchestrator's dependencies are importable (one-time,
#        re-checked only if the plugin install root changes). ---
recorded_root=""
if [ -f "$DEPS_MARKER" ]; then
  recorded_root="$(cat "$DEPS_MARKER" 2>/dev/null || true)"
fi

if [ "$recorded_root" != "$PLUGIN_ROOT" ]; then
  REQS="$PLUGIN_ROOT/orchestrator/requirements.txt"
  if "$PY" -c "import docx, openpyxl" >/dev/null 2>&1 \
    || "$PY" -m pip install -q -r "$REQS" >/dev/null 2>&1 \
    || "$PY" -m pip install -q --user -r "$REQS" >/dev/null 2>&1 \
    || "$PY" -m pip install -q --user --break-system-packages -r "$REQS" >/dev/null 2>&1; then
    printf '%s' "$PLUGIN_ROOT" > "$DEPS_MARKER" 2>/dev/null || true
  fi
  # A failed install just means the next real orchestrator invocation fails
  # with an ImportError the user can act on -- this hook never blocks the
  # command that triggered it over a dependency problem.
fi

exit 0
