---
description: Load (or reload) the Knowledge Base and its Catalog into the running Knowledge Base Service's memory
---

No arguments — there's exactly one folder this service manages (the
attached folder's `Knowledge Base/` subfolder). Invoke the `knowledge-base-service` subagent
with `verb: load`.

Requires the service to already be `RUNNING` (`/start-kb-service` first); if
it isn't, the subagent relays that plainly rather than starting it for you.
Safe to re-run any time the vault's notes change — a reload builds the new
Knowledge Base and Catalog separately and only replaces the active ones
once both are validated, so a failed reload never exposes partial data and
never discards a previously good Knowledge Base.
