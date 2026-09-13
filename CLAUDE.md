# qa-analyst (Cowork/Claude Code plugin)

Autonomous QA copilot: requirement analysis, test planning, and test-case
generation. Test automation (Playwright scaffolding, script
generation/healing/refinement, and suite execution/reporting) is out of
scope here — it's handled by a separate, dedicated agent setup that
consumes this project's generated test cases.

This is the **plugin-packaged** form of the project — installed once (via
Cowork/Claude Code's Plugins UI or `/plugin`) and then used against any
number of client vault folders the user attaches in Cowork.
`.claude-plugin/plugin.json` is the manifest; everything below it is
auto-discovered from the standard plugin directory names. A sibling,
non-packaged copy of this same project (used for local development of new
features) lives outside this folder.

## Layout

```
.claude-plugin/
  plugin.json  plugin manifest (name/version/description/author)
agents/       5 subagent definitions (*.md)
commands/     9 slash commands (*.md) — one per agent, except
              knowledge-base-service, which backs four /start-kb-service,
              /load-kb, /kb-status, /stop-kb-service commands distinguished
              by a verb
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
assets/
  branding/             Emvigo bundled default branding (2 logos) — an
                        attached folder can override either with its own
                        Branding/ copy (see paths.py)
```

Agents invoke Python as `bash ./.qa-orchestrator <folder.module> [args]`
from the workspace root — a cwd-relative shim `plugin-bootstrap.sh` writes
at session start, pointing back at this plugin's own bundled
`orchestrator/` and baking in whichever interpreter works (`python3` in
Cowork's Linux sandbox, `python` on Windows).

## Workspace model — no settings file

The folder the user attaches in Cowork (the session cwd,
`paths.WORKSPACE_ROOT`) **is** the project: the client's vault, and the home
of every deliverable. There is no `config/settings.json`; every input is
found by convention in `orchestrator/utils/workspace.py`:

| Path in the attached folder | Role | Missing means |
|---|---|---|
| `Requirements/` | **The requirement input source** — and a reasoning-time fallback (see below) | Nothing to analyze; `/analyse-requirement` says so and stops |
| `Knowledge Base/` | General domain-background notes, served by the Knowledge Base Service | Opt-in — agents reason from requirement text alone |
| `Branding/` | `header-logo.png` / `project-logo.png` overrides | Bundled `assets/branding/` logos are used |
| `Project Info.md` | YAML frontmatter `name`, `designation`, `projectName`, `projectId` — the identity every execution-log entry attributes a revision to | Fields render as `"TBD – Client/Project Input Required"` |
| `output/` | All generated deliverables, plus the staged `<doc-name>-source.md` | Self-creates on first write |

Subfolder/file names match ignoring case, spaces, `-` and `_`
(`knowledge-base/` works). Nothing is cached — every lookup reads the
folder as it is now, including inside the long-lived KB service.
`<doc-name>` is the **attached folder's own name**, used for every output
path.

There is **no handoff step**: deliverables are written straight into the
attached folder's `output/`, which is where the user already works.

Both note folders are read **directly** — `knowledge_base.search` opens the
`.md` files themselves. There is no index, no ingestion step, and nothing on
disk that can fall behind the notes it describes. (There used to be a Chroma
vector store synced by a `/sync-knowledge-base` command. It's gone — a
nearest-neighbour hit was only ever *approximately* about what was asked,
which produced confidently cited snippets that weren't the passage that
answered the question.)

**`Requirements/` does double duty**, which is the one non-obvious thing
here: it is both this project's sole requirement input (every `.md` under it
is combined by `parsing.reading_vault_fetch` into the document
`/analyse-requirement` analyzes) *and* a per-requirement reasoning fallback
the agents query only when a requirement's own text isn't enough to reason
about.

## Knowledge base service

`Knowledge Base/` (only — `Requirements/` is untouched, see above) is
served by a persistent **Knowledge Base Service**, this project's one
long-lived background process (`orchestrator/knowledge_base/service.py`),
rather than being read fresh off disk on every call the way `Requirements/`
still is. Explicit lifecycle: `/start-kb-service` → `/load-kb` (builds an
in-memory Knowledge Base + a separate Catalog of file name/purpose/topics,
atomically — a failed reload never exposes partial data or discards a
previously good Knowledge Base) → agents investigate against it →
`/stop-kb-service` releases the memory. `/kb-status` reports the current
state at any time; all four are pure, deterministic wrappers
(`knowledge-base-service` agent) around
`bash ./.qa-orchestrator knowledge_base.service <start|load|status|stop>`.

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

`Requirements/` is untouched by any of this. All three agents still reach
it, when a doubt or a requirement's own text isn't enough, through
`knowledge_base.search`'s direct-disk-read `reading` source — ranked
sections, **every match returned, no cap**: a silent cutoff is the wrong
failure mode for a search an agent only reaches for when it's genuinely
unsure — better to hand back everything that matched (the agent already
judges each result for relevance itself) than to guess how many are
"enough" and hide the rest.

## Requirement input model

One attached folder → **exactly one requirement document per project**.
There is no `.docx`/`.xlsx` requirement input; a client's requirement text
lives as `.md` notes in `Requirements/`.

`parsing.reading_vault_fetch` is the mandatory first step of every
`/analyse-requirement` run: it combines every `.md` under `Requirements/`
(recursively, skipping dot-folders like `.obsidian/` and `.history/`) into
`output/requirement-analysis/<doc-name>-source.md`, one
`## Source: <relative path>` section per file. It rewrites that staged file
only when the combined content actually changed, preserving its mtime
otherwise — every downstream mtime-based staleness check depends on that.

Because there's one document, **no command in this project takes a
`<file>`/`<doc>` argument** — each resolves it from
`output/requirement-analysis/*-analysis.json` or a sibling deliverable
already on disk.

## Deliverable shape

Every JSON deliverable:
`{"meta", <content>, "document_control", "release_history"}`. Unknowns are
`"TBD – Client/Project Input Required"` or `"TBD – To be added by QA"` —
never fabricated.

Every regeneration is a controlled revision: `snapshot-output.sh` archives
the prior version to `history/` before overwrite; `validate-output.sh` runs
`orchestrator.validation.validate` after, blocking on errors; `execution-log.sh`
then records who made the revision (from `Project Info.md`) and when (IST)
to a sibling `execution-log/` folder, via `orchestrator.utils.execution_log`
— one JSON array (source of truth, append-only) plus a generated `.md`
table, per deliverable folder. All three hooks match on `Write|Edit` only —
which is why agents must write JSON with those tools, never via a
Bash-invoked script.

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

And a plain re-run of `/analyse-requirement` when nothing in `Requirements/`
changed since the last run is refused outright
(`validation.analysis_currency`, wired into requirement-analyzer.md's Mode
selection) rather than silently re-reasoning and re-versioning an analysis
with nothing new to say — the existing `--docx`-when-current shortcut
(Docx-only mode) already took the other branch of that same check.

| Command | Always | Opt-in |
|---|---|---|
| `/analyse-requirement` | JSON + `.md` | `--docx` |
| `/generate-clarification-sheet` | `.md` | `--docx` |
| `/generate-test-plan` | JSON + `.md` | `--docx` |
| `/generate-test-cases` | JSON + `.md` | `--csv` (Zephyr import), `--xlsx` (3-sheet workbook) |

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
