# qa-analyst (Cowork/Claude Code plugin)

Autonomous QA copilot: requirement analysis, test planning, and test-case
generation. Test automation (Playwright scaffolding, script
generation/healing/refinement, and suite execution/reporting) is out of
scope here — it's handled by a separate, dedicated agent setup that
consumes this project's generated test cases.

This is the **plugin-packaged** form of the project — installed once (via
Cowork/Claude Code's Plugins UI or `/plugin`) and then used against any
number of separate workspace folders. `.claude-plugin/plugin.json` is the
manifest; everything below it is auto-discovered from the standard plugin
directory names. A sibling, non-packaged copy of this same project (used
for local development of new features) lives outside this folder.

## Layout

```
.claude-plugin/
  plugin.json  plugin manifest (name/version/description/author)
agents/       6 subagent definitions (*.md)
commands/     13 slash commands (*.md) — one per agent, except
              requirement-handoff, which backs four /handoff-* commands
              distinguished by a --target flag, and knowledge-base-service,
              which backs four /start-kb-service, /load-kb, /kb-status,
              /stop-kb-service commands distinguished by a verb
skills/       framework + output-structure skills (*/SKILL.md); each
              *-output-structure skill also has a reference/ folder that
              is NOT auto-loaded
hooks/
  hooks.json  hook registration (plugin form of a project's settings.json)
  *.sh        PreToolUse/PostToolUse/SessionStart scripts, resolved via
              $CLAUDE_PLUGIN_ROOT rather than $CLAUDE_PROJECT_DIR
orchestrator/          Python backend — parsing, generation, validation,
                       knowledge_base, models, utils, templates, tests.
                       Bundled with the plugin (REPO_ROOT in
                       orchestrator/utils/paths.py); never copied into a
                       user's workspace
scripts/run.sh         wrapper: `python -m orchestrator.<module>`
config/
  branding/             Emvigo bundled fallback branding (2 logos) —
                        replace in place to change the plugin's own
                        default; a workspace can still override with its
                        own config/branding/ copy (see paths.py)
```

Each **workspace** the plugin is used against (a separate folder the user
opens in Cowork/Claude Code, not this plugin's own install directory) gets
its own self-creating `config/settings.json` (user settings — obsidian
paths, operator identity) and `output/` (generated deliverables) — see
Configuration and Workspace model below. Agents invoke Python as
`bash ./.qa-orchestrator <folder.module> [args]` from that workspace root —
a cwd-relative shim `plugin-bootstrap.sh` writes at session start, pointing
back at this plugin's own bundled `orchestrator/`.

## Configuration (`config/settings.json`)

Read by `orchestrator/utils/config.py`. Three independent paths:

| Key | Role | Blank means |
|---|---|---|
| `requirementReading.obsidianPath` | **The requirement input source** — and a reasoning-time fallback (see below) | No requirement source configured; `/analyse-requirement` has nothing to analyze |
| `knowledgeBase.obsidianPath` | General domain-background vault | Opt-in, not configured yet — not an error |
| `requirementHandoff.obsidianDestinationPath` | Where the four `/handoff-*` commands copy an approved `.md`. A destination, never a source | Opt-in, not configured yet — not an error |

Both vault settings are read **directly, on every query** —
`knowledge_base.search` opens the `.md` files themselves. There is no index,
no ingestion step, and nothing on disk that can fall behind the notes it
describes. (There used to be: notes were chunked, embedded, and stored in a
Chroma vector store under `knowledge-base/`, synced by a
`/sync-knowledge-base` command. Both are gone — a nearest-neighbour hit was
only ever *approximately* about what was asked, which produced confidently
cited snippets that weren't the passage that answered the question. A
config still carrying the retired `chunkingLimit` key loads fine; nothing
reads it.)

**`requirementReading.obsidianPath` does double duty**, which is the one
non-obvious thing here: it is both this project's sole requirement input
(every `.md` under it is combined by `parsing.reading_vault_fetch` into the
document `/analyse-requirement` analyzes) *and* a per-requirement reasoning
fallback the requirement-analyzer queries only when a requirement's own text
isn't enough to reason about.

A fourth block, `operator` (`name`, `designation`, `projectName`,
`projectId`), isn't a path — it's the human identity every execution-log
entry (see Deliverable shape below) attributes a controlled revision to.
This is a single-operator CLI with no multi-user auth, so there's no session
identity to read this from automatically; a user fills it in once. Blank
fields render as `"TBD – Client/Project Input Required"`, same as any other
unset client/project fact.

## Knowledge base service

`knowledgeBase.obsidianPath` (only — `requirementReading.obsidianPath` is
untouched, see above) is served by a persistent **Knowledge Base
Service**, this project's one long-lived background process
(`orchestrator/knowledge_base/service.py`), rather than being read fresh
off disk on every call the way `requirementReading.obsidianPath` still is.
Explicit lifecycle: `/start-kb-service` → `/load-kb` (builds an in-memory
Knowledge Base + a separate Catalog of file name/purpose/topics, atomically
— a failed reload never exposes partial data or discards a previously good
Knowledge Base) → agents investigate against it → `/stop-kb-service`
releases the memory. `/kb-status` reports the current state at any time;
all four are pure, deterministic wrappers (`knowledge-base-service` agent)
around `bash ./.qa-orchestrator knowledge_base.service <start|load|status|stop>`.

All three generator agents query this service, each **deliberately, never
automatically**: `requirement-analyzer` runs one upfront domain
investigation (investigation questions generated once from the requirement,
no fixed count; every file the catalog's `purpose`/`topics` judge genuinely
relevant to a question is retrieved, no per-question cap) so relevant
knowledge is never left out for the sake of a round number;
`test-case-generator`/`test-plan-generator` query it ad hoc, one genuine
doubt at a time, while drafting (every genuinely relevant file retrieved per
doubt, never speculatively). All three follow the same shape: fetch the Catalog
once per run, judge relevant files by `purpose`/`topics`, retrieve each
**complete** file from memory — no vector search, embeddings, or chunking
anywhere in this path — reusing a file already fetched this run rather than
re-fetching it. All three also self-heal a stopped/unloaded service
transparently as part of that step; the four commands above never do, and
always report the service's exact state.

`requirementReading.obsidianPath` is untouched by any of this. All three
agents still reach it, when a doubt or a requirement's own text isn't
enough, through `knowledge_base.search`'s direct-disk-read `reading`
source — ranked sections, **every match returned, no cap**: there used to
be a `knowledgeBase.topK` config knob capping this, removed because a
silent cutoff is the wrong failure mode for a search an agent only reaches
for when it's genuinely unsure — better to hand back everything that
matched (the agent already judges each result for relevance itself) than
to guess how many are "enough" and hide the rest. A config still carrying
the retired `topK` key loads fine, same as `chunkingLimit` above; nothing
reads it.

## Requirement input model

One configured vault → **exactly one requirement document per project**.
There is no `requirements/` folder and no `.docx`/`.xlsx` requirement input;
a client's requirement text lives as `.md` notes in the vault.

`parsing.reading_vault_fetch` is the mandatory first step of every
`/analyse-requirement` run: it combines every `.md` under the vault
(recursively, skipping `.obsidian/`) into
`output/requirement-analysis/<doc-name>-source.md`, one
`## Source: <relative path>` section per file. The vault folder's own name
becomes `<doc-name>`, used for every output path from then on. It rewrites
that staged file only when the combined content actually changed, preserving
its mtime otherwise — every downstream mtime-based staleness check depends
on that.

Because there's one document, **no command in this project takes a
`<file>`/`<doc>` argument** — each resolves it from
`output/requirement-analysis/*-analysis.json` or a sibling deliverable
already on disk.

## Workspace model

No setup command scaffolds anything. Each folder is checked in, created by
hand, or self-creates on first write:

| Folder | Created by | Purpose |
|---|---|---|
| `output/` | self-creates (each writer's own `mkdir(parents=True, exist_ok=True)`) | All generated deliverables, plus the staged `<doc-name>-source.md` |
| `config/branding/` | checked in | Branding (header/project logo) — replace the two files in place |
| `config/settings.json` | self-creates with defaults on first read (`orchestrator/utils/config.py`) | User settings — see Configuration above |

## Deliverable shape

Every JSON deliverable:
`{"meta", <content>, "document_control", "release_history"}`. Unknowns are
`"TBD – Client/Project Input Required"` or `"TBD – To be added by QA"` —
never fabricated.

Every regeneration is a controlled revision: `snapshot-output.sh` archives
the prior version to `history/` before overwrite; `validate-output.sh` runs
`orchestrator.validation.validate` after, blocking on errors; `execution-log.sh`
then records who made the revision and when (IST) to a sibling
`execution-log/` folder, via `orchestrator.utils.execution_log` — one JSON
array (source of truth, append-only) plus a generated `.md` table, per
deliverable folder. All three hooks match on `Write|Edit` only — which is
why agents must write JSON with those tools, never via a Bash-invoked
script.

**The JSON is always the source of truth; the Markdown report is always
generated alongside it; every other format is opt-in.** Agents author the
JSON only — deterministic Python writers render everything else.

Every always-generated `.md` report — requirement analysis, Test Plan, Test
Cases, and the Client Clarification Sheet — gets the same
controlled-revision treatment its JSON sibling gets from
`snapshot-output.sh`, just not from a hook: since each is written by a
Bash-invoked script rather than `Write`/`Edit`, that PreToolUse hook never
sees it. `orchestrator.utils.md_history` is the shared archiving helper
each writer (`generation.md_report_writer`,
`generation.test_plan_md_writer`, `generation.test_case_md_writer`,
`generation.clarification_sheet_writer`) calls before overwriting its own
`.md`, copying it into a sibling `history/` folder named with that copy's
version — recovered from the *outgoing* file's own rendered text (a labeled
bullet, or the last Document Release History row for the Test Plan, whose
Version Control section has no standalone version bullet; the
Clarification Sheet carries no version at all, so its snapshots are always
"unversioned") — and the timestamp it was written at. A failed archive only
loses that history copy, never the run's actual deliverable. The same call
also records the matching `execution-log/` entry for the `.md` (see above),
using that same recovered old version as `from` and the outgoing file's own
new version as `to`.

And a plain re-run of `/analyse-requirement` when nothing in the
requirement vault changed since the last run is refused outright
(`validation.analysis_currency`, wired into requirement-analyzer.md's Mode
selection) rather than silently re-reasoning and re-versioning an analysis
with nothing new to say — the existing `--docx`-when-current shortcut
(Docx-only mode) already took the other branch of that same check.

| Command | Always | Opt-in | Handoff |
|---|---|---|---|
| `/analyse-requirement` | JSON + `.md` | `--docx` | `/handoff-requirement` |
| `/generate-clarification-sheet` | `.md` | `--docx` | `/handoff-clarification-sheet` |
| `/generate-test-plan` | JSON + `.md` | `--docx` | `/handoff-test-plan` |
| `/generate-test-cases` | JSON + `.md` | `--csv` (Zephyr import), `--xlsx` (3-sheet workbook) | `/handoff-test-cases` |

Passing an opt-in flag on an already-current deliverable **skips
re-reasoning entirely** and exports straight from the existing JSON.

The Clarification Sheet's `.md` is the round-trip source
`/apply-clarifications` reads client answers back from; the `.docx` is only
a fallback for when the Word copy got filled in instead.

The Test Cases `.md` report also carries three per-test-case tracking
fields — Execution Status, Actual Result, Linked Issue — that stay QA-typed
in this project: there is no automation flow here to run a suite and write
results back into them. A separate automation project consuming these test
cases may populate them the same way (editing the same `.md` bullets);
`test_case_md_writer.write_report`'s `overrides` parameter exists for
exactly that kind of external write-back, but nothing in this project calls
it.

## Also see

`commands/*.md` frontmatter — each command's own `argument-hint` and
the subagent it invokes; that per-command mapping is the source of truth.
`orchestrator/CLAUDE.md` — orchestrator subfolder conventions.
`skills/CLAUDE.md` — what each skill is for.
`hooks/CLAUDE.md` — hook-specific notes.
