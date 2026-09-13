"""Reads this project's own `config/settings.json` -- the single place a
user points this project at the folders of markdown it should read.

Self-creates the file with defaults on first read -- the same
"don't force an explicit setup step, make the first real use work" pattern
every docx/xlsx writer already follows for its own folders -- except the
three path settings below, which only a human can supply, so they're left
blank rather than guessed.

Nothing here points at a database anymore. The knowledge base used to be a
Chroma vector store under a workspace-local `knowledge-base/` folder, fed by
a separate `/sync-knowledge-base` ingestion pass; `knowledge_base.search`
now reads the configured markdown folders directly on every query, so a
configured path is the whole story -- there is no second location holding a
stale copy of it.

Three independent path settings live here, each answering a different
question:
- `knowledgeBase.obsidianPath` -- the general domain-background vault.
  Served by the persistent Knowledge Base Service (`knowledge_base.service`)
  rather than read here: `requirement-analyzer`, `test-case-generator`, and
  `test-plan-generator` each investigate it deliberately (bounded, self-
  healing) via that service's Catalog + complete-file retrieval, never via
  `knowledge_base.search`. `knowledge_base.search`'s own `vault` source
  (no `--source`, or `--source vault`) still reads this same path directly
  off disk and still works -- it's just no longer what any agent's own
  instructions call for this source.
- `requirementReading.obsidianPath` -- a *separate* vault/folder, used two
  distinct ways: (1) searched per-requirement (`knowledge_base.search ...
  --source reading`) only when the requirement-analyzer judges a
  requirement's own text isn't enough to reason about confidently; and (2)
  read whole by `parsing.reading_vault_fetch` as this project's **sole
  requirement input source** -- every `.md` file found under it is combined
  into one requirement set and staged at
  `output/requirement-analysis/<doc-name>-source.md` (`<doc-name>` being
  the vault folder's own name) on every `/analyse-requirement` run. There
  is no `requirements/` folder -- a client drops/edits their requirement
  `.md` notes directly in this vault, not in a workspace-local folder.
  Deliberately distinct from `knowledgeBase.obsidianPath` -- a client's
  general domain-background notes and the requirement text itself are not
  necessarily the same folder.
- `requirementHandoff.obsidianDestinationPath` -- where `/handoff-requirement`
  copies an approved `<doc-name>-analysis.md` once a human has reviewed it.
  A destination, not a source -- never read from, only written into.

A fourth block, `operator`, isn't a path -- it's the human-supplied identity
this project attributes every controlled revision to in its per-deliverable
execution-log/ audit trail (`orchestrator.utils.execution_log`). This is a
single-operator CLI with no multi-user auth, so there's no session identity
to derive it from automatically; a user fills in `name`/`designation`/
`projectName`/`projectId` once and every writer's execution-log entry reads
it from here. Left blank, each field renders as this project's standard
"TBD -- Client/Project Input Required" placeholder, same as any other unset
client/project fact -- never fabricated, never silently defaulted to an OS
or git username.
"""

import json
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = "config"
CONFIG_FILENAME = "settings.json"

DEFAULTS = {
    "knowledgeBase": {
        "obsidianPath": "",
    },
    "requirementReading": {
        "obsidianPath": "",
    },
    "requirementHandoff": {
        "obsidianDestinationPath": "",
    },
    "operator": {
        "name": "",
        "designation": "",
        "projectName": "",
        "projectId": "",
    },
}


def config_path() -> Path:
    from orchestrator.utils.paths import WORKSPACE_ROOT

    return WORKSPACE_ROOT / CONFIG_DIR / CONFIG_FILENAME


def _write_defaults(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8")
    return json.loads(json.dumps(DEFAULTS))


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Read `config/settings.json`, creating it with defaults if missing or
    unreadable. Cached for the life of the process -- call
    `load_config.cache_clear()` if a test or a later step rewrites the file
    mid-run.

    Keys the defaults don't know about are carried through untouched, so a
    config still carrying the retired `chunkingLimit` from the vector-store
    era loads fine; nothing reads it anymore."""
    path = config_path()
    if not path.exists():
        return _write_defaults(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _write_defaults(path)
    if not isinstance(data, dict):
        return _write_defaults(path)
    kb = {**DEFAULTS["knowledgeBase"], **(data.get("knowledgeBase") or {})}
    reading = {**DEFAULTS["requirementReading"], **(data.get("requirementReading") or {})}
    handoff = {**DEFAULTS["requirementHandoff"], **(data.get("requirementHandoff") or {})}
    operator = {**DEFAULTS["operator"], **(data.get("operator") or {})}
    return {
        **DEFAULTS,
        **data,
        "knowledgeBase": kb,
        "requirementReading": reading,
        "requirementHandoff": handoff,
        "operator": operator,
    }


def _kb_setting(key: str):
    return (load_config().get("knowledgeBase") or {}).get(key, DEFAULTS["knowledgeBase"][key])


def _reading_setting(key: str):
    return (load_config().get("requirementReading") or {}).get(
        key, DEFAULTS["requirementReading"][key]
    )


def _handoff_setting(key: str):
    return (load_config().get("requirementHandoff") or {}).get(
        key, DEFAULTS["requirementHandoff"][key]
    )


def operator_info() -> dict:
    """The human identity execution-log entries attribute a controlled
    revision to -- `name`, `designation`, `projectName`, `projectId`, each
    the empty string until a user fills in `operator` in
    `config/settings.json`. Callers render a blank field as this project's
    standard TBD placeholder themselves; this just returns what's configured,
    same as every other setting here."""
    return {**DEFAULTS["operator"], **(load_config().get("operator") or {})}


def obsidian_vault_path() -> Path | None:
    """This project's configured Obsidian vault (or plain markdown folder)
    of domain-background notes -- `None` when `knowledgeBase.obsidianPath`
    is left blank, meaning there is no knowledge base to search. Read
    directly, on every query; nothing is copied or indexed elsewhere."""
    configured = _kb_setting("obsidianPath")
    return Path(configured).expanduser() if configured else None


def requirement_reading_vault_path() -> Path | None:
    """This project's *separate* reasoning-time source -- `None` when
    `requirementReading.obsidianPath` is left blank, meaning there is
    nothing for `knowledge_base.search --source reading` to fall back to,
    and nothing for `parsing.reading_vault_fetch` to read as the
    requirement source either.

    Distinct from `obsidian_vault_path` above: that one is the general
    domain-background source (one bounded search per analysis run); this
    one is searched per-requirement, only when the requirement-analyzer
    judges the requirement's own text isn't enough to reason about
    confidently -- and, separately, is this project's sole requirement
    input source: every `.md` file found under it is what
    `parsing.reading_vault_fetch` combines into the document
    `/analyse-requirement` actually analyzes. A blank config here genuinely
    means "fall back to the requirement text alone" for the first use and
    "no requirement source configured yet at all" for the second, not an
    error either way."""
    configured = _reading_setting("obsidianPath")
    return Path(configured).expanduser() if configured else None


def requirement_handoff_destination_path() -> Path | None:
    """Where `/handoff-requirement` copies an approved
    `<doc-name>-analysis.md` -- `None` when
    `requirementHandoff.obsidianDestinationPath` is left blank, meaning
    handoff has nowhere configured to copy to yet. A destination, unlike
    every other path this module resolves -- never read from, only written
    into."""
    configured = _handoff_setting("obsidianDestinationPath")
    return Path(configured).expanduser() if configured else None
