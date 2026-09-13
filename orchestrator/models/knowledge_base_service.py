"""Shared data structures for the Knowledge Base Service. No logic lives
here -- see `orchestrator/knowledge_base/service.py` for the
`KnowledgeBaseService` class these describe.

The four error-message constants are kept here, not inline in `service.py`,
so the HTTP layer and its tests import the exact same wording rather than
risking two copies drifting apart -- these are also the literal strings a
human sees from `/kb-status`/`/start-kb-service`/`/load-kb`/
`/stop-kb-service`, which never paraphrase them.
"""

from dataclasses import dataclass, field

# Service process state -- whether the detached HTTP server is reachable at
# all. Distinct from KBState below: a RUNNING service can still have
# NOT_LOADED knowledge.
SERVICE_STOPPED = "STOPPED"
SERVICE_RUNNING = "RUNNING"

# Knowledge Base state, independent of the service process itself.
KB_NOT_LOADED = "NOT_LOADED"
KB_LOADING = "LOADING"
KB_LOADED = "LOADED"
KB_ERROR = "ERROR"

ERROR_SERVICE_STOPPED = (
    "Knowledge Base Service is not running. Execute start-kb-service before requesting knowledge."
)
ERROR_KB_NOT_LOADED = (
    "Knowledge Base Service is running, but the Knowledge Base has not been loaded. "
    "Execute load-kb before starting Knowledge Base investigation."
)
ERROR_KB_LOADING = (
    "Knowledge Base is currently loading. Use the currently active valid Knowledge Base "
    "if one exists, or wait and retry."
)
ERROR_FILE_NOT_FOUND = (
    "Requested Knowledge Base file was not found. Please select a valid file from the "
    "Knowledge Catalog."
)


@dataclass
class CatalogEntry:
    """One Knowledge Catalog row -- name, purpose, and topics only, never
    the file's complete content (that's `get_file`'s job, and it's what
    keeps the catalog small enough for an agent to scan before deciding
    what to retrieve)."""

    name: str
    purpose: str
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "purpose": self.purpose, "topics": list(self.topics)}

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogEntry":
        return cls(
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            topics=list(data.get("topics") or []),
        )


@dataclass
class ServiceStatus:
    """The shape `GET /status` returns and `kb-status` prints -- everything
    a caller needs to decide what to do next, without a second round trip."""

    service_state: str = SERVICE_STOPPED
    kb_state: str = KB_NOT_LOADED
    files_loaded: int = 0
    catalog_ready: bool = False
    loaded_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "service_state": self.service_state,
            "kb_state": self.kb_state,
            "files_loaded": self.files_loaded,
            "catalog_ready": self.catalog_ready,
            "loaded_at": self.loaded_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServiceStatus":
        return cls(
            service_state=data.get("service_state", SERVICE_STOPPED),
            kb_state=data.get("kb_state", KB_NOT_LOADED),
            files_loaded=int(data.get("files_loaded", 0) or 0),
            catalog_ready=bool(data.get("catalog_ready", False)),
            loaded_at=data.get("loaded_at", ""),
            error=data.get("error", ""),
        )
