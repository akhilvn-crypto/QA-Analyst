"""Shared data structure for the Knowledge Catalog `/build-kb-catalog`
writes -- see `orchestrator/knowledge_base/catalog.py` for how one is
built. No logic lives here, only the shape.
"""

from dataclasses import dataclass


@dataclass
class CatalogEntry:
    """One Knowledge Catalog row -- name, purpose, and description only,
    never the file's complete content. That's what keeps the catalog small
    enough for an agent to scan in full before deciding which files, if
    any, are worth reading completely."""

    name: str
    purpose: str
    description: str

    def to_dict(self) -> dict:
        return {"name": self.name, "purpose": self.purpose, "description": self.description}

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogEntry":
        return cls(
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            description=data.get("description", ""),
        )
