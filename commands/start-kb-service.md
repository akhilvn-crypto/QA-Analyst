---
description: Start the Knowledge Base Service (the persistent in-memory holder of this project's domain-background vault)
---

No arguments. Invoke the `knowledge-base-service` subagent with `verb: start`.

Starts the service if it isn't already running (idempotent — running it
again just reports the current state) and initializes it to `RUNNING` /
`NOT_LOADED`. Starting the service never loads the Knowledge Base itself —
run `/load-kb` next.
