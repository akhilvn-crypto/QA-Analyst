## Skills

`requirement-analysis-framework`, `test-plan-framework`,
`test-case-generation-framework` — analysis/derivation rules.
`output-structure`, `test-plan-output-structure`, `test-case-output-structure`
— output shape per deliverable (`disable-model-invocation: true`, owning
agent only).

### `reference/` subfolders

Each of the three `*-output-structure` skills has a `reference/rendering.md`
holding the maintainer-facing detail its `SKILL.md` used to carry inline:
how the deterministic Python writers lay out the docx/xlsx/md (fonts,
margins, page breaks, column widths, table shapes), plus the historical
rationale for those choices and the legacy-tolerance rules.

That content was moved out because **no agent authors those files by hand**
— the writers render them from the JSON — so it was pure runtime cost in
every agent invocation. `reference/` files are *not* auto-loaded with the
skill; they're read on demand, and only when debugging a writer. When you
change a writer's layout, update its `reference/rendering.md`, not the
`SKILL.md`.

(Migrated from the project root `CLAUDE.md` — this only loads when working
under `skills/`.)
