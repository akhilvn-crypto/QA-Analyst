---
description: Build (or preview) the Knowledge Catalog from the attached folder's Knowledge Base/ notes standalone — the generator agents build/refresh it automatically themselves, so this is a convenience, not a prerequisite
---

No arguments. Invoke the `knowledge-base-catalog` subagent.

Scans every `.md` file under `Knowledge Base/` and writes one catalog entry
per file (name, purpose, description — never the file's full content) to
`output/knowledge-base/catalog.json`. `requirement-analyzer`,
`test-case-generator`, and `test-plan-generator` each build/refresh this
file themselves, automatically, once per run, immediately before they
consult it — so it's always current when any of them reasons against it,
whether or not this command was ever run.

Run this yourself when you just want to build or inspect the catalog on its
own — e.g. to sanity-check what a note's `purpose`/`description` came out
as — without running a full analysis, plan, or test-case generation. Safe
to re-run any time; it always overwrites the catalog from what's on disk
right now.
