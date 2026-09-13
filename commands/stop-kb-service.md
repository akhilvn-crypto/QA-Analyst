---
description: Stop the Knowledge Base Service and release its in-memory Knowledge Base and Catalog
---

No arguments. Invoke the `knowledge-base-service` subagent with `verb: stop`.

Attempts a graceful shutdown, force-terminating the background process only
if that doesn't finish quickly; either way the in-memory Knowledge Base and
Catalog are released and its state files are cleaned up. Idempotent —
stopping an already-stopped service just reports `STOPPED`. Requirement
Analysis must not be run expecting Knowledge Base content while the service
is stopped; `/start-kb-service` and `/load-kb` bring it back.
