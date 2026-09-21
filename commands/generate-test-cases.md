---
description: Generate traceable test cases from this project's analyzed requirements
argument-hint: "[--req \"<folder>\"] [--kb \"<folder>\"] [--xlsx] [--csv]"
---

No doc-name to resolve — this project has exactly one requirement analysis.
Find it: there should be exactly one
`output/requirement-analysis/*-analysis.json`. If there isn't one, tell the
user to run `/analyse-requirement` first — test-case generation requires a
completed analysis and never reads the raw requirement source itself.

Parse `ARGUMENTS` for these independent, optional pieces, anywhere in the
string:

- `--req "<folder name>"` / `--kb "<folder name>"` — the top-level folders
  in the project root holding the requirement notes and the
  domain-background notes. Take the value following each flag (quoted if it
  contains spaces) and pass it along as a distinct piece. Given, the
  subagent uses that folder verbatim; omitted, it falls back to
  `Requirements/` / `Knowledge Base/` by naming convention.
- `--xlsx` and `--csv` — strip each out and pass it along as a distinct
  flag. Either, both, or neither may be given.

Ignore stray text rather than erroring.

Invoke the `test-case-generator` subagent with the resolved doc-name (the
analysis JSON's stem minus `-analysis.json`), the `--req`/`--kb` folder
names (when given), and whether each flag was given.

The JSON and Markdown under `output/test-cases/` are always produced — the
Markdown is the file to review. The
Zephyr-import CSV and the Excel review workbook only when their flag is
given.
