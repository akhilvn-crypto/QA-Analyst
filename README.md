# qa-analyst

Autonomous QA copilot for **Cowork / Claude Code**: requirement analysis,
test planning, and test-case generation, working directly inside the vault
folder you attach. Test automation (Playwright scaffolding, script
generation/healing, suite execution/reporting) is out of scope here — a
separate agent setup consumes this plugin's generated test cases.

This repo is a **plugin marketplace of one plugin** (`qa-analyst`), meant
to be installed once per person and then used against any number of
client vault folders.

## Install (team)

In a Cowork / Claude Code session, run:

```
/plugin marketplace add akhilvn-crypto/QA-Analyst
/plugin install qa-analyst@qa-analyst-local
```

When prompted for scope, choose **user** — this makes the plugin available
in every folder you attach afterward, not just one.

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

There is nothing to configure. Attach the client's vault folder in Cowork
and lay it out like this — the plugin finds everything by folder name:

```
<client vault>/
  Requirements/      requirement .md notes              (required)
  Knowledge Base/    domain-background .md notes        (optional)
  Branding/          header-logo.png, project-logo.png  (optional — overrides the bundled Emvigo logos)
  Project Info.md    who's running QA                   (optional)
  output/            generated deliverables             (created automatically)
```

Folder names are matched ignoring case, spaces, `-` and `_`
(`knowledge-base` works too). Deliverables are named after the attached
folder (e.g. `LinkGrid-analysis.md`).

`Project Info.md` supplies the identity recorded on every revision in
`execution-log/`; any field left out shows as `TBD`:

```markdown
---
name: Your Name
designation: QA Lead
projectName: LinkGrid
projectId: LG-001
---
```

Then:

1. `/analyse-requirement` — analyzes everything in `Requirements/`. If you
   also added a `Knowledge Base/` folder, this (and every other generator
   command below) catalogs it automatically each run — no separate step
   needed, and edits to those notes are always picked up fresh.
2. `/generate-test-plan` and `/generate-test-cases` as needed.
3. Optional: `/build-kb-catalog` to build or preview the Knowledge Catalog
   on its own, without running a full analysis/plan/test-case generation.

Review the `.md` reports directly under `output/` — they already live in
your vault.

See this repo's own `CLAUDE.md` for the full workspace and deliverable
model.

## Local development

To iterate on the plugin itself without reinstalling from GitHub each time:

```
claude --plugin-dir "/path/to/this/repo"
```

loads it for that session only, from your local checkout.
