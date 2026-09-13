---
description: Hand off an approved Client Clarification Sheet to this project's configured Obsidian destination
argument-hint: "[--force]"
---

No document to resolve by name — this project has exactly one requirement
analysis.

1. Find the `<doc-name>`: there should be exactly one
   `output/requirement-analysis/*-analysis.json`. If there isn't one, tell
   the user to run `/analyse-requirement` first and stop.
2. Confirm the sheet exists at
   `output/client-clarifications/<doc-name>-clarifications.md`; if not, tell
   the user to run `/generate-clarification-sheet` first and stop.
3. Strip a `--force` token from `ARGUMENTS` if present and pass it as a
   distinct flag. **Never pass `--force` unless the user explicitly included
   it** — it overwrites a destination copy that may hold edits made directly
   in Obsidian.

Invoke the `requirement-handoff` subagent with the resolved `<doc-name>`,
`target: clarifications`, and whether `--force` was given.

It copies (never moves) the sheet to
`requirementHandoff.obsidianDestinationPath`; the original stays in
`output/client-clarifications/` as this project's record. If the destination
config key is blank, or a differing copy already exists there, the subagent
reports that plainly rather than guessing or silently overwriting.

**Caveat if the client answered directly in Obsidian:** this destination is
a write-only drop point — `requirementHandoff.obsidianDestinationPath` is
never read back from, by this command or by `/apply-clarifications`. If the
client (or QA on their behalf) typed answers into the handed-off Obsidian
copy rather than the workspace copy, copy those edits back into
`output/client-clarifications/<doc-name>-clarifications.md` yourself before
running `/apply-clarifications` — otherwise they're invisible to it.
