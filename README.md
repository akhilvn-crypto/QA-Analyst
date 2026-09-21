# qa-analyst

Autonomous QA copilot for **VS Code / Claude Code** (and Cowork):
requirement analysis, test planning, and test-case generation, working
directly inside the project folder you have open. Test automation (Playwright scaffolding, script
generation/healing, suite execution/reporting) is out of scope here — a
separate agent setup consumes this plugin's generated test cases.

This repo is a **plugin marketplace of one plugin** (`qa-analyst`), meant
to be installed once per person and then used against any number of
client projects. It writes nothing into your folders except the
deliverables it generates under `output/`.

## Install (team)

In a Claude Code session (VS Code terminal, or Cowork), run:

```
/plugin marketplace add akhilvn-crypto/QA-Analyst
/plugin install qa-analyst@qa-analyst-local
```

When prompted for scope, choose **user** — this makes the plugin available
in every project you open afterward, not just one.

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

There is nothing to configure. Open the client's project folder in VS
Code, put the two input folders in its root, and name them on the command:

```
<client project>/
  <requirement notes>/   requirement .md notes              -> --req "<folder>"
  <domain notes>/        domain-background .md notes        -> --kb "<folder>"  (optional)
  Branding/              header-logo.png, project-logo.png  (optional — no bundled default; reports render without a logo if absent)
  output/                generated deliverables             (created automatically)
```

Then:

1. `/analyse-requirement --req "Requirements" --kb "Knowledge Base"` —
   understands the `--kb` notes *first* (it catalogs that folder itself and
   reads the foundational notes in full), then analyzes every `.md` under
   `--req` with that background already in hand. Every generator command
   below opens the same way — no separate step — so edits to those notes
   are always picked up fresh.
2. `/generate-test-plan` and `/generate-test-cases`, passing the same
   `--req`/`--kb` names. Nothing is remembered between commands (there is
   no settings file), so pass them each time.
3. Optional: `/build-kb-catalog --kb "<folder>"` to build or preview the
   Knowledge Catalog on its own, without running a full
   analysis/plan/test-case generation.

The flags are optional: with neither, the plugin looks for folders named
`Requirements/` and `Knowledge Base/` (matched ignoring case, spaces, `-`
and `_`, so `knowledge-base` works too), and asks you only if it can't
find them. Deliverables are named after the project folder (e.g.
`LinkGrid-analysis.md`).

Review the `.md` reports directly under `output/` — they already live in
your project.

See this repo's own `CLAUDE.md` for the full workspace and deliverable
model.

## Local development

To iterate on the plugin itself without reinstalling from GitHub each time:

```
claude --plugin-dir "/path/to/this/repo"
```

loads it for that session only, from your local checkout.
