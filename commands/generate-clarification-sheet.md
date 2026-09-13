---
description: Generate the Client Clarification Sheet from the current requirement analysis
argument-hint: "[--docx] [--force]"
---

No document to resolve by name — this project has exactly one requirement
analysis.

1. Find the `<doc-name>`: there should be exactly one
   `output/requirement-analysis/*-analysis.json`. If there isn't one, tell
   the user to run `/analyse-requirement` first and stop.
2. Strip a `--docx` token from `ARGUMENTS` if present and pass it as a
   distinct flag. Without it, only the `.md` sheet is produced.
3. Strip a `--force` token likewise. **Never pass `--force` unless the user
   explicitly included it** — it discards client responses already typed
   into an existing sheet that haven't been applied yet.

Invoke the `clarification-sheet-generator` subagent with the resolved
`<doc-name>` and whether each flag was given.

It (re)writes
`output/client-clarifications/<doc-name>-clarifications.md` — one row per
open client question with a blank Client Response column — plus the Word
copy only if `--docx` was given. Answers typed into either are read back by
`/apply-clarifications`.
