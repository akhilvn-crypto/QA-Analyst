---
description: Hand off an approved Test Plan Markdown report to this project's configured Obsidian destination
argument-hint: "[--force]"
---

No document to resolve by name — this project has exactly one Test Plan.

1. Find the `<doc-name>`: there should be exactly one
   `output/test-plan/*-test-plan.md`. If there isn't one, tell the user to
   run `/generate-test-plan` first and stop.
2. Strip a `--force` token from `ARGUMENTS` if present and pass it as a
   distinct flag. **Never pass `--force` unless the user explicitly included
   it** — it overwrites a destination copy that may hold edits made directly
   in Obsidian.

Invoke the `requirement-handoff` subagent with the resolved `<doc-name>`,
`target: test-plan`, and whether `--force` was given.

It copies (never moves) the reviewed `.md` to
`requirementHandoff.obsidianDestinationPath`; the original stays in
`output/test-plan/` as this project's record. A pure file copy — no
re-derivation, and it assumes a human has already reviewed and approved. If
the destination config key is blank, or a differing copy already exists
there, the subagent reports that plainly rather than guessing or silently
overwriting.
