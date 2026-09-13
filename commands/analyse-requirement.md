---
description: Run QA requirement analysis on this project's configured requirement-reading vault
argument-hint: "[--docx] [optional extra instructions]"
---

No filename to resolve — this project analyzes exactly one requirement
source: every `.md` under `config/settings.json`'s
`requirementReading.obsidianPath`, combined by the subagent's own fetch step.

Parse `ARGUMENTS` for two independent, optional pieces:
1. A `--docx` token anywhere in the string (order-independent) — strip it
   out and pass it as a distinct flag, not as free-text instructions.
2. Anything left over is extra instructions from the user (which vault note
   to focus on, context about a sprint) — pass it along, don't discard it.

Invoke the `requirement-analyzer` subagent with whether `--docx` was given
and any extra instructions.

The Markdown report under `output/requirement-analysis/` is always produced
— it's the file to review before `/handoff-requirement`. The Word report
only when `--docx` is given.

If the subagent reports that `requirementReading.obsidianPath` isn't
configured, doesn't exist, or has no `.md` files, relay that plainly — there
is nothing to analyze until that's fixed.
