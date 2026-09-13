---
description: Report the Knowledge Base Service's current state — running/stopped, and loaded/not loaded/loading/error
---

No arguments. Invoke the `knowledge-base-service` subagent with `verb:
status`.

Always answerable — reporting `STOPPED` or `NOT_LOADED` is an ordinary
result here, never an error. Use this to check whether `/load-kb` has ever
been run, or whether a background reload is still in progress, before
relying on Knowledge Base content elsewhere.
