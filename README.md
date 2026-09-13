# qa-analyst

Autonomous QA copilot for **Cowork / Claude Code**: requirement analysis,
test planning, and test-case generation against a configured Obsidian
vault. Test automation (Playwright scaffolding, script generation/healing,
suite execution/reporting) is out of scope here — a separate agent setup
consumes this plugin's generated test cases.

This repo is a **plugin marketplace of one plugin** (`qa-analyst`), meant
to be installed once per person and then used against any number of
separate client workspace folders.

## Install (team)

In a Cowork / Claude Code session, run:

```
/plugin marketplace add akhilvn-crypto/QA-Analyst
/plugin install qa-analyst@qa-analyst-local
```

When prompted for scope, choose **user** — this makes the plugin available
in every workspace folder you open afterward, not just one repo.

Confirm it worked:

```
/help
```

You should see commands like `/analyse-requirement`, `/generate-test-plan`,
`/generate-test-cases`, etc.

## Updating

When the team pushes changes to this repo:

```
/plugin marketplace update
```

then reinstall/reload if prompted.

## Using it

The plugin is installed once; each **workspace folder** you point it at
(a separate project folder you open in Cowork — not this plugin repo) gets
its own self-created `config/settings.json` and `output/`:

1. Open your client's workspace folder in Cowork.
2. Fill in `config/settings.json` in that workspace (it self-creates with
   blank defaults on first read):
   - `requirementReading.obsidianPath` — **required**: the Obsidian vault
     folder holding that client's requirement `.md` notes. This is the
     project's sole requirement input.
   - `knowledgeBase.obsidianPath` — optional general domain-background
     vault, served by the Knowledge Base Service (`/start-kb-service` →
     `/load-kb`).
   - `requirementHandoff.obsidianDestinationPath` — optional, where
     `/handoff-*` commands copy an approved deliverable.
   - `operator` — your name/designation/project info, attributed on every
     revision.
3. Run `/analyse-requirement`, then `/generate-test-plan` and
   `/generate-test-cases` as needed. Use `/handoff-*` once a deliverable is
   approved.

See this repo's own `CLAUDE.md` for the full configuration, workspace, and
deliverable model.

## Local development

To iterate on the plugin itself without reinstalling from GitHub each time:

```
claude --plugin-dir "/path/to/this/repo"
```

loads it for that session only, from your local checkout.
