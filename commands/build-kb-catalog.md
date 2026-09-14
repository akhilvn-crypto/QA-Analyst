---
description: Build (or rebuild) the Knowledge Catalog from the attached folder's Knowledge Base/ notes, for the generator agents to reason against
---

No arguments. Invoke the `knowledge-base-catalog` subagent.

Scans every `.md` file under `Knowledge Base/` and writes one catalog entry
per file (name, purpose, description — never the file's full content) to
`output/knowledge-base/catalog.json`. `requirement-analyzer`,
`test-case-generator`, and `test-plan-generator` each read this file
directly when a domain question or genuine doubt comes up, then read a
relevant file's complete content themselves.

Run this once after attaching a vault with a `Knowledge Base/` folder, and
again any time its notes are added, edited, or removed — nothing reloads
automatically. Safe to re-run any time; it always overwrites the catalog
from what's on disk right now.
