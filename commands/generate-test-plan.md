---
description: Generate a client-ready Test Plan document from this project's analyzed requirements
argument-hint: "[--docx] [optional extra instructions]"
---

No filename to resolve — this project has exactly one requirement source.

1. Find the `<doc-name>`: there should be exactly one
   `output/requirement-analysis/*-analysis.json`. If there isn't one, still
   proceed **if** there is exactly one
   `output/requirement-analysis/*-source.md` (the subagent can work from the
   combined source alone). If neither exists, tell the user to run
   `/analyse-requirement` first and stop.
2. Parse `ARGUMENTS` for two independent pieces:
   - A `--docx` token anywhere in the string — strip it out and pass it as a
     distinct flag, not as free-text instructions.
   - Anything left over is extra instructions (resource names, environment
     details, target dates, sprint length) — pass it verbatim. A Test Plan
     needs project facts no requirement document can supply, and the
     subagent marks anything not supplied as `TBD – Client/Project Input
     Required` rather than inventing it.

Invoke the `test-plan-generator` subagent with the resolved `<doc-name>`,
whether `--docx` was given, and the extra instructions.

The JSON and Markdown under `output/test-plan/` are always produced — the
Markdown is the file to review. The Word report
only when `--docx` is given.
