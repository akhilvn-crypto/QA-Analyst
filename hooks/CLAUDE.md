## Hooks

Registered in `hooks/hooks.json` (plugin form — not a project
`.claude/settings.json`). Every hook is invoked as
`bash "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh"`.

| Hook | Event | Does |
|---|---|---|
| `plugin-bootstrap` | SessionStart **and** PreToolUse `Bash\|PowerShell` | Writes the `./.qa-orchestrator` shim, installs Python deps once, gitignores those artifacts plus the Knowledge Base Service's `.qa-kb-service/` state dir (pre-emptively — it doesn't create that dir itself). Pure side effect, always silent exit 0 |
| `snapshot-output` | PreToolUse `Write\|Edit` | Archives an existing output JSON to `history/<name>-v<version>.json` before overwrite. Never denies |
| `validate-output` | PostToolUse `Write\|Edit` | Runs `validation.validate` on a written output JSON. **Blocks** on errors, informs on warnings, silent when clean |
| `execution-log` | PostToolUse `Write\|Edit` | Records who/when an output JSON revision happened to a sibling `execution-log/` folder, via `orchestrator.utils.execution_log`. Never denies |
| `format-report` | PostToolUse `Bash\|PowerShell` | After a docx writer runs, renders to PDF/JPEG via Word COM to confirm pagination, then discards. Smoke test only — never changes formatting |

## Environment

`$CLAUDE_PLUGIN_ROOT` is reliably set for hook subprocesses but **not** for
agent-issued Bash — which is why `plugin-bootstrap` writes the cwd-relative
`./.qa-orchestrator` shim with the plugin's own install root baked in, and
why `validate-output` passes `PYTHONPATH` explicitly to its inner Python
rather than relying on cwd or the shim (it can fire before any Bash call
has run). `orchestrator/` ships bundled inside this plugin (see
`orchestrator/utils/paths.py`'s `REPO_ROOT`) — it is never copied into the
user's own workspace.

## Contract

Every hook here exits 0 and allows by default. Only `validate-output` ever
denies/blocks, and only on its own matched command. A hook must never fail
loudly on its own account.

## Cost characteristics

Hook **scripts** never enter the context window — only their stdout does
(`additionalContext` / `permissionDecisionReason`). On an ordinary Bash call
the PreToolUse hook emits **0 bytes** unless matched. Keep it that way: any
unconditional `print` here becomes a per-tool-call context cost.

Each hook spawns its own Python/Bash process, and `plugin-bootstrap`
re-runs as a redundant safety net over its SessionStart registration.
Consolidating them into one dispatcher would fix the resulting wall-clock
cost; it hasn't been done.

This is the plugin-packaged form of this project (see root `CLAUDE.md`) —
hooks resolve their own scripts via `$CLAUDE_PLUGIN_ROOT` rather than a
project-level `$CLAUDE_PROJECT_DIR/.claude/`.

(Migrated from the project root `CLAUDE.md` — this only loads when working
under `hooks/`.)
