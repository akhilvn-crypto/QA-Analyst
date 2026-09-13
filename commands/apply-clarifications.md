---
description: Apply client answers from a filled-in Client Clarification Sheet back into the requirement analysis
argument-hint: "[--docx] [optional extra instructions]"
---

No document to resolve by name — this project has exactly one requirement
analysis.

1. Find the `<doc-name>`: there should be exactly one
   `output/requirement-analysis/*-analysis.json`. If there isn't one, tell
   the user to run `/analyse-requirement` first and stop.
2. Confirm a filled-in sheet exists: check
   `output/client-clarifications/<doc-name>-clarifications.md` first (the
   primary source). If missing, fall back to checking the `.docx` (the
   client/QA may have been given the Word copy). If neither exists, tell the
   user to run `/generate-clarification-sheet` first and stop.
3. Strip a `--docx` token from `ARGUMENTS` if present and pass it as a
   distinct flag.
4. Treat anything left over as extra instructions — pass it along.

Invoke the `requirement-analyzer` subagent in **clarification-update mode**
with the resolved `<doc-name>`, whether `--docx` was given, and any extra
instructions.

The Markdown report and a fresh clarification sheet `.md` (holding only
still-open questions) are always regenerated. The Word copies of both are
regenerated only if `--docx` was given here, or one already exists for this
document — never left stale.

Where a resolved gap can be traced back to a specific passage in the
requirement-reading vault, that vault note is also rewritten in place to
state the confirmed behaviour directly — its prior version is snapshotted to
`.history/` inside the vault first, and the edit is skipped (never guessed)
if the passage can't be safely relocated.
