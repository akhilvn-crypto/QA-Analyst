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
agents/       4 subagent definitions (*.md)
commands/     5 slash commands (*.md) — one per agent
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
| `Knowledge Base/` (or `--kb "<folder>"`) | General domain-background notes the generator agents read **in full, every note, every run** to understand the project | Opt-in — agents reason from requirement text alone |
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

## Knowledge Base ingestion

`Knowledge Base/` (only — `Requirements/` is untouched, see below) is read
by the agents themselves, directly and in full. There is **no catalog, no
index, no search, no embeddings and no Python module** in this path: the
three generator agents each open their run by reading **every** `.md` file
under that folder, complete, before they touch the requirement at all.

1. **Resolve the knowledge-base folder** — `--kb` verbatim, else the
   naming-convention match, else the one auto-detection judgment call.
2. **List every `.md` under it**, recursively, skipping dot-folders
   (`.obsidian/`, `.history/`).
3. **Read them all, in full** — domain knowledge, architecture, API
   documentation, compliance rules, data dictionaries, conventions and the
   narrowest single-question note alike. No triage, no skimming, no
   excerpting, no deciding up front that a note looks irrelevant. Notes
   whose *file name* marks them as the project's domain background as a
   whole (`domain-knowledge.md`, `domain.md`, `project-overview.md`,
   `overview.md`, `about.md`, matched ignoring case/spaces/`-`/`_`) are
   read first so the broad picture is in place as the specifics land
   against it; the rest follow in listing order. Reads are issued in
   batches, not one at a time.
4. **That's the knowledge base for the run.** Every later step reasons
   from what's already in context — never a re-read, never a lookup,
   never a search against that folder.

The point is that the agent holds the project's *entire* domain background
before it starts reasoning, so a doubt later on is answered by knowledge
it already has, rather than by stopping to work out which note might cover
it and going to fetch that one. Past the ingestion, `requirement-analyzer`
reasons the whole requirement against everything it read (no fixed rounds —
an answer that raises a further question is followed up on the spot, since
the material is all in context);
`test-case-generator`/`test-plan-generator` resolve genuine doubts the same
way, by recall, falling back to a generic placeholder or `TBD` only when
nothing they read bears on the doubt.

This replaced a catalog-plus-questions design (a deterministic
`knowledge_base.catalog` build writing `output/knowledge-base/catalog.json`
— one `{name, purpose, description}` line per note — which agents scanned
to pick which notes to read, plus a `/build-kb-catalog` command and a
`knowledge-base-catalog` agent wrapping it). All of it is gone. Deciding
whether a note is relevant from a one-line description is a judgment you
can only make properly *after* reading the note, and the machinery to
avoid reading was more complexity than the reading it saved.

**No cross-run cache.** Each of the three generator commands is its own
agent invocation with its own fresh context, so each reads the whole
Knowledge Base itself, every run. Nothing carries over from
`/analyse-requirement` to `/generate-test-cases`. That is also what keeps
every run current with whatever is on disk *right now*: there is no
artifact that can fall behind the notes it describes.

A `Knowledge Base/` folder that's genuinely absent (by naming convention
and by the same folder-auto-detection judgment call described below), or
one holding no `.md` files, is an ordinary fallback to requirement text
alone, exactly like an unconfigured knowledge base always has been.

`Requirements/` is untouched by any of this. All three agents still reach
it, when a doubt or a requirement's own text isn't enough, through
`knowledge_base.search` — ranked sections read straight off disk,
**every match returned, no cap**: a silent cutoff is the wrong failure mode
for a search an agent only reaches for when it's genuinely unsure — better
to hand back everything that matched (the agent already judges each result
for relevance itself) than to guess how many are "enough" and hide the
rest. (`knowledge_base.search` only ever reads `Requirements/` — the
general domain-background source it used to also serve is read whole by
the agents instead.)

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
`knowledge_base.search` all accept it; the knowledge-base folder itself
is read by the agent directly, with no script in between). More than
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
