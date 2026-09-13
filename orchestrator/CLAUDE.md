## Orchestrator conventions

`parsing/` input→markdown · `generation/` writes deliverables (docx/xlsx/csv)
· `knowledge_base/` direct markdown search (`search.py`, still used by
test-case/test-plan agents and the reading vault) plus a persistent
in-memory service for the domain-background vault (`service.py`, its own
background HTTP process — see root `CLAUDE.md`'s "Knowledge base service")
· `validation/` deterministic JSON checks ·
`models/` data structures only · `utils/` generic helpers only · `templates/`
static assets copied verbatim, never generated · `tests/` pytest, run via
`python -m pytest orchestrator/tests -q`. New logic goes in the matching
folder, never loose under `orchestrator/`.

(Migrated from the project root `CLAUDE.md` — this only loads when working
under `orchestrator/`.)
