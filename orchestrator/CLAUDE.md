## Orchestrator conventions

`parsing/` input→markdown · `generation/` writes deliverables (docx/xlsx/csv)
· `knowledge_base/` direct markdown search over `Requirements/` only
(`search.py`) — the domain-background vault has no module at all: agents
read every note under it themselves, in full (see root `CLAUDE.md`'s
"Knowledge Base ingestion") ·
`validation/` deterministic JSON checks ·
`models/` data structures only · `utils/` generic helpers only · `templates/`
static assets copied verbatim, never generated · `tests/` pytest, run via
`python -m pytest orchestrator/tests -q`. New logic goes in the matching
folder, never loose under `orchestrator/`.

(Migrated from the project root `CLAUDE.md` — this only loads when working
under `orchestrator/`.)
