#!/usr/bin/env bash
# Registered twice in hooks.json: as a SessionStart hook (fires once, the
# moment a session opens, regardless of what the user does first -- there
# is no Claude Code "template"/project-scaffold mechanism to lean on
# instead, confirmed by direct research, not assumed) and as a PreToolUse
# hook for Bash|PowerShell (fires on every shell-tool call, as a redundant
# safety net for the rare case a session resumes/continues without ever
# re-firing SessionStart). SessionStart is the mechanism this actually
# relies on for correctness -- it doesn't key off any tool name at all, so
# it fires identically whether the session's shell tool is Bash, PowerShell,
# or (confirmed by direct testing) not exposed to the agent yet at all. The
# PreToolUse registration is genuinely just a bonus, not a dependency.
# Lazily makes this workspace ready for orchestrator invocations, before the
# underlying command runs.
#
# Why this exists: `python -m orchestrator.<module>` needs this plugin's own
# bundled orchestrator/ directory on PYTHONPATH, but an agent's own
# Bash-tool-issued commands don't reliably see $CLAUDE_PLUGIN_ROOT (only hook
# subprocesses are confirmed to have it). This hook -- which does have it --
# writes a tiny, cwd-relative shim (./.qa-orchestrator) into the user's
# workspace that self-locates scripts/run.sh via its own baked-in plugin
# install root. Every later agent/hook invocation just runs
# `bash ./.qa-orchestrator <folder.module> [args...]` from the workspace root
# (the same cwd this hook and every agent Bash call both run in), with no
# need to know the plugin's install path itself.
#
# Also ensures orchestrator's own Python dependencies are installed --
# nothing else in the plugin-install flow does this.
#
# Deliberately does NOT scaffold `output/` -- there is no dedicated setup
# command for this project's workspace folders anymore. There is also no
# `requirements/` folder to scaffold: requirement input comes straight from
# the client's own `.md` notes in the Obsidian vault configured at
# `requirementReading.obsidianPath` (`orchestrator/utils/config.py`), read
# fresh by `parsing.reading_vault_fetch` on every `/analyse-requirement`
# run. `output/` self-creates via every writer's own
# `path.parent.mkdir(parents=True, exist_ok=True)`. The knowledge base needs
# no folder here at all: `knowledge_base.search` reads the vault configured
# in `config/settings.json` directly, and there is no local index to
# create or keep in sync.
# `config/branding/` is checked into this project directly (no seeding
# step needed) -- replace its two logo files in place with the client's
# own branding.
#
# Contract: always "allow" (silent exit 0) -- this is a pure side effect and
# must never block whatever triggered it, or fail loudly on its own account.
# Reads no stdin (unlike this project's other hooks) -- everything it needs
# comes from $CLAUDE_PLUGIN_ROOT and the cwd, which is why the exact same
# script is safe to register under both SessionStart and PreToolUse without
# any changes.

set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$PLUGIN_ROOT" ]; then
  exit 0
fi

SHIM=".qa-orchestrator"
DEPS_MARKER=".qa-orchestrator-deps-ok"

# --- 1. (Re)write the cwd-relative shim if missing or pointing at a
#        different plugin install root (e.g. if the plugin is ever
#        reinstalled/moved). ---
expected_shim="#!/usr/bin/env bash
exec bash \"$PLUGIN_ROOT/scripts/run.sh\" \"\$@\"
"

current_shim=""
if [ -f "$SHIM" ]; then
  current_shim="$(cat "$SHIM" 2>/dev/null || true)"
fi

if [ "$current_shim" != "$expected_shim" ]; then
  tmp_shim="./.qa-orchestrator.tmp.$$"
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
  if python -c "import docx, openpyxl" >/dev/null 2>&1; then
    printf '%s' "$PLUGIN_ROOT" > "$DEPS_MARKER" 2>/dev/null || true
  elif python -m pip install -q -r "$PLUGIN_ROOT/orchestrator/requirements.txt" >/dev/null 2>&1; then
    printf '%s' "$PLUGIN_ROOT" > "$DEPS_MARKER" 2>/dev/null || true
  fi
  # A failed install just means the next real orchestrator invocation fails
  # with an ImportError the user can act on -- this hook never blocks the
  # command that triggered it over a dependency problem.
fi

# --- 3. Keep the bootstrap artifacts out of the user's own git history,
#        without presuming to create a .gitignore that doesn't exist yet. ---
# `.qa-kb-service/` is the Knowledge Base Service's own transient state dir
# (port/pid/log files for its detached background process -- see
# orchestrator/knowledge_base/service.py) -- gitignored here for the same
# reason as the shim/deps-marker, independent of whether the service ever
# actually gets started in this workspace.
KB_SERVICE_DIR=".qa-kb-service"
if [ -f ".gitignore" ]; then
  grep -qxF "$SHIM" .gitignore 2>/dev/null || printf '\n%s\n' "$SHIM" >> .gitignore
  grep -qxF "$DEPS_MARKER" .gitignore 2>/dev/null || printf '%s\n' "$DEPS_MARKER" >> .gitignore
  grep -qxF "$KB_SERVICE_DIR" .gitignore 2>/dev/null || printf '%s\n' "$KB_SERVICE_DIR" >> .gitignore
fi

exit 0
