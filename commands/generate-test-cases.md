---
description: Generate traceable test cases from this project's analyzed requirements
argument-hint: "[--xlsx] [--csv]"
---

No doc-name to resolve — this project has exactly one requirement analysis.
Find it: there should be exactly one
`output/requirement-analysis/*-analysis.json`. If there isn't one, tell the
user to run `/analyse-requirement` first — test-case generation requires a
completed analysis and never reads the raw requirement source itself.

Parse `ARGUMENTS` for two independent, optional flags, anywhere in the
string: `--xlsx` and `--csv`. Strip each out and pass it along as a distinct
flag. Either, both, or neither may be given. Ignore stray text rather than
erroring.

Invoke the `test-case-generator` subagent with the resolved doc-name (the
analysis JSON's stem minus `-analysis.json`) and whether each flag was
given.

The JSON and Markdown under `output/test-cases/` are always produced — the
Markdown is the file to review before `/handoff-test-cases`. The
Zephyr-import CSV and the Excel review workbook only when their flag is
given.
