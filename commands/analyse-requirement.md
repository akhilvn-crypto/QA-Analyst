---
description: Run QA requirement analysis on this project's requirement notes
argument-hint: "[--req \"<folder>\"] [--kb \"<folder>\"] [--docx] [optional extra instructions]"
---

No filename to resolve — this project analyzes exactly one requirement
source: every `.md` under the requirement folder in the project root,
combined by the subagent's own fetch step.

Parse `ARGUMENTS` for four independent, optional pieces, in any order:
1. `--req "<folder name>"` — the top-level folder in the project root
   holding the client's requirement `.md` notes. Take the value that
   follows the flag (quoted if it contains spaces) and pass it along as a
   distinct piece, not as free-text instructions. When it's given, the
   subagent uses that folder verbatim and never guesses; without it, the
   subagent falls back to finding `Requirements/` by naming convention.
2. `--kb "<folder name>"` — likewise, the top-level folder holding the
   project's domain-background notes for the subagent to read and
   understand the project from. Without it, the subagent falls back to
   `Knowledge Base/` by naming convention; with no such folder either, it
   reasons from requirement text alone.
3. A `--docx` token anywhere in the string (order-independent) — strip it
   out and pass it as a distinct flag, not as free-text instructions.
4. Anything left over is extra instructions from the user (which note to
   focus on, context about a sprint) — pass it along, don't discard it.
   Never fold a `--req`/`--kb` value into this leftover text.

Invoke the `requirement-analyzer` subagent with the `--req`/`--kb` folder
names (when given), whether `--docx` was given, and any extra
instructions.

The Markdown report under `output/requirement-analysis/` is always produced
— it's the file to review. The Word report only when `--docx` is given.

If the subagent reports that the requirement folder doesn't exist or has no
`.md` files, relay that plainly — there is nothing to analyze until the
requirement notes are placed in a folder of the project root and named with
`--req "<folder>"` (or placed in a `Requirements/` subfolder).
