# qa-analyst (Cowork/Claude Code plugin)

Autonomous QA copilot: requirement analysis, test planning, and test-case
generation. Test automation (Playwright scaffolding, script
generation/healing/refinement, and suite execution/reporting) is out of
scope here — it's handled by a separate, dedicated agent setup that
consumes this project's generated test cases.

This is the **plugin-packaged** form of the project — installed once (via
the Plugins UI or `/plugin`) and then used against any number of client
projects. The primary way it's used is **from VS Code**: open the client's
project folder, and every command runs against that folder as the project
root (it works the same against a folder attached in Cowork — same cwd,
same behaviour).
`.claude-plugin/plugin.json` is the manifest; everything below it is
auto-discovered from the standard plugin directory names. A sibling,
non-packaged copy of this same project (used for local development of new
features) lives outside this folder.

## Layout

```
.claude-plugin/
  plugin.json  plugin manifest (name/version/description/author)
agents/       5 subagent definitions (*.md)
commands/     6 slash commands (*.md) — one per agent
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
```

Agents invoke Python as `bash "$HOME/.qa-analyst/run.sh" <folder.module>
[args]` — a **per-user** shim `plugin-bootstrap.sh` writes at session
start, pointing back at this plugin's own bundled `orchestrator/` and
baking in whichever interpreter works (`python3` in Cowork's Linux sandbox,
`python` on Windows). It lives in `$HOME/.qa-analyst/` alongside the
one-time dependency marker `deps-ok`: one copy per machine, at a path
identical from every project, so **the plugin never writes anything into
the user's own folders**. (It used to write a cwd-relative
`./.qa-orchestrator` + `.qa-orchestrator-deps-ok` pair into whichever
directory a session happened to open, QA project or not, and append them
to that directory's `.gitignore` — pure noise in every non-QA folder.)

## Workspace model — no settings file

The project root open in VS Code (the session cwd, `paths.WORKSPACE_ROOT`)
**is** the project: the client's notes, and the home of every deliverable.
There is no `config/settings.json`. The two input folders are named by the
user on the command itself — `--req "<folder>"` for the requirement notes,
`--kb "<folder>"` for the domain-background notes, both top-level folders
of that project root — and fall back to being found by convention in
`orchestrator/utils/workspace.py` when a flag is omitted:

| Path in the project root | Role | Missing means |
|---|---|---|
| `Requirements/` (or `--req "<folder>"`) | **The requirement input source** — and a reasoning-time fallback (see below) | Nothing to analyze; `/analyse-requirement` says so and stops |
| `Knowledge Base/` (or `--kb "<folder>"`) | General domain-background notes the agents read to understand the project, auto-cataloged each run by the generator agents themselves (`/build-kb-catalog` also available standalone) | Opt-in — agents reason from requirement text alone |
| `Branding/` | `header-logo.png` / `project-logo.png` | No bundled default — reports render without a logo |
| `output/` | All generated deliverables, plus the staged `<doc-name>-source.md` | Self-creates on first write |

A `--req`/`--kb` value is used verbatim — an exact top-level folder name,
no matching, no guessing. Without one, subfolder/file names match ignoring
case, spaces, `-` and `_` (`knowledge-base/` works). Nothing is cached —
every lookup reads the folder as it is now, and no folder name is
remembered between calls, so `--folder` is re-passed on each script call
within a run. When a project names one of these folders something the
convention match can't recognize at all and no flag was given, see "Folder
auto-detection" below. `<doc-name>` is the **project root's own folder
name**, used for every output path.

There is **no handoff step**: deliverables are written straight into the
project root's `output/`, which is where the user already works.

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

## Knowledge base catalog

`Knowledge Base/` (only — `Requirements/` is untouched, see below) is
served by a single deterministic build, `bash "$HOME/.qa-analyst/run.sh"
knowledge_base.catalog` — a pure, no-lifecycle replacement for what used to
be a persistent background service (start/load/status/stop, an in-memory
hot-swap, its own HTTP client). That was a lot of machinery for what agents
actually need: a small map of what's there. The build scans every `.md`
file under `Knowledge Base/` and writes one JSON file,
`output/knowledge-base/catalog.json`: that folder's own resolved path, plus
one `{name, purpose, description}` entry per note — never a file's content,
which is what keeps the catalog small enough to scan whole. No vector
search, embeddings, or chunking anywhere in this path.

All three generator agents open every run with a **Knowledge Base
orientation**, before they touch the requirement at all: each
builds/refreshes the catalog itself, reads it whole (it is `{name, purpose,
description}` per note, never file content — that is what keeps it small
enough to hold entirely), and then reads *in full* the entries whose
`purpose`/`description` mark them as **foundational** — an overview, a
glossary, a domain primer, an architecture/conventions note, a
business-rules summary: the notes that describe the project or domain as a
whole rather than answering one narrow question. No fixed count, and none
is a valid answer for a Knowledge Base whose notes are all narrow.
Narrow/specific notes stay unread until something actually points at one.
The point is that the agent holds the project's domain background *before*
it starts reasoning, so a doubt later on is "I already know which note
covers this — read it" rather than "stop, build a catalog, work out what's
in it, then read".

Past the orientation, each agent goes further into the narrow notes its own
way: `requirement-analyzer` runs one bounded domain investigation
(investigation questions generated once from the requirement and the
inferred domain, no fixed count; every entry the catalog judges genuinely
relevant to a question is read, no per-question cap) so relevant knowledge
is never left out for the sake of a round number;
`test-case-generator`/`test-plan-generator` consult the map ad hoc, one
genuine doubt at a time, while drafting (every genuinely relevant file read
per doubt, never speculatively). In all three, the catalog is built and
read exactly once per run — at the orientation — and every later step
reuses that same in-hand `files` list rather than rebuilding or re-reading
it, `Read`ing a relevant entry's **complete** file at `<catalog's
"folder">/<entry's "name">` and reusing one already read this run (the
foundational ones included) rather than re-reading it.

Because every run's orientation rebuilds the catalog from whatever notes
exist on disk *right now*, there is no notion of a stale or missing-but-
buildable catalog to fall back from — only a `Knowledge Base/` folder
that's genuinely absent (by naming convention and by the same
folder-auto-detection judgment call described below) is an ordinary
fallback to requirement text alone, exactly like an unconfigured knowledge
base always has been. This reverses an earlier, deliberate design of this
project (each generator only ever reading whatever catalog happened to
already exist, never building one itself) in favor of the Cowork workflow
this plugin is meant for: a QA person attaches a vault folder and invokes
an agent directly, without a separate "build the catalog first" step to
remember or forget.

**`/build-kb-catalog`** (the `knowledge-base-catalog` agent, a deterministic
wrapper around the same build) still exists, but only as a convenience for
a user who wants to build or preview the catalog standalone — e.g. to
sanity-check a note's `purpose`/`description` — without running a full
analysis, plan, or test-case generation. It is no longer a prerequisite
before running any of the three generator agents.

`Requirements/` is untouched by any of this. All three agents still reach
it, when a doubt or a requirement's own text isn't enough, through
`knowledge_base.search` — ranked sections read straight off disk,
**every match returned, no cap**: a silent cutoff is the wrong failure mode
for a search an agent only reaches for when it's genuinely unsure — better
to hand back everything that matched (the agent already judges each result
for relevance itself) than to guess how many are "enough" and hide the
rest. (`knowledge_base.search` only ever reads `Requirements/` now — the
general domain-background source above it used to also serve is the
catalog's job instead.)

## Folder auto-detection

Every script that resolves `Requirements/` or `Knowledge Base/`
(`orchestrator.utils.workspace.requirements_path`/`knowledge_base_path`)
accepts a `--folder "<exact name>"` override, which is what a command's
`--req`/`--kb` is passed through as: given one, that's the whole of the
resolution — no convention match, no auto-detection, and a folder of that
name not existing is reported as such rather than worked around.

Without it, the convention match described above runs first — exact name,
then ignoring case/spaces/`-`/`_`. When that finds nothing at all, the
*invoking agent* — not any Python code — is the fallback: list the project
root's top-level entries itself (`Read`/`Bash ls`) and use judgment to
spot a folder that plausibly serves that role under a different name
(`Specs`, `Reqs`, `User Stories`, `BRD` for requirements; `Domain
Knowledge`, `Reference`, `Notes`, `Wiki`, `Background` for the knowledge
base). Exactly one plausible candidate → pass it straight through as
`--folder "<exact name>"` to whichever script needed it
(`parsing.reading_vault_fetch`, `parsing.vault_writeback`,
`knowledge_base.search`, `knowledge_base.catalog` all accept it). More than
one plausible candidate, or none → ask the user rather than guessing.

There is no settings file to remember that choice in, so it isn't
persisted anywhere — a later command that needs the same folder repeats the
same judgment call against the same static listing, which is what "nothing
is cached" already means everywhere else in this project, extended to
folder identity too. An agent that has to auto-detect a folder should say
so plainly, so the user knows to either pass `--req`/`--kb` next time, or
simply rename the folder to the conventional name so every future command
finds it without help. Passing the flag is the cheaper habit: it skips the
judgment call entirely, every run.

## Requirement input model

One project root → **exactly one requirement document per project**.
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
`orchestrator.validation.validate` after, blocking on errors. Both hooks
match on `Write|Edit` only — which is why agents must write JSON with those
tools, never via a Bash-invoked script.

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
loses that history copy, never the run's actual deliverable.

And a plain re-run of `/analyse-requirement` when nothing in `Requirements/`
changed since the last run is refused outright
(`validation.analysis_currency`, wired into requirement-analyzer.md's Mode
selection) rather than silently re-reasoning and re-versioning an analysis
with nothing new to say — the existing `--docx`-when-current shortcut
(Docx-only mode) already took the other branch of that same check.

| Command | Always | Opt-in | Folder flags |
|---|---|---|---|
| `/analyse-requirement` | JSON + `.md` | `--docx` | `--req`, `--kb` |
| `/generate-clarification-sheet` | `.md` | `--docx` | — (pure render from the analysis JSON) |
| `/generate-test-plan` | JSON + `.md` | `--docx` | `--req`, `--kb` |
| `/generate-test-cases` | JSON + `.md` | `--csv` (Zephyr import), `--xlsx` (3-sheet workbook) | `--req`, `--kb` |
| `/apply-clarifications` | `.md` + refreshed sheet | `--docx` | `--req` |
| `/build-kb-catalog` | `catalog.json` | — | `--kb` |

Every `--req "<folder>"`/`--kb "<folder>"` is an exact top-level folder
name in the project root, used verbatim (see "Workspace model" above).

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
