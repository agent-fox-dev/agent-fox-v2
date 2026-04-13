"""Data models for the entity graph subsystem.

Requirements: 95-REQ-1.2, 95-REQ-1.3, 95-REQ-1.4, 95-REQ-2.2
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EntityType(StrEnum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"


class EdgeType(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    EXTENDS = "extends"


@dataclass(frozen=True)
class Entity:
    id: str  # UUID v4
    entity_type: EntityType
    entity_name: str
    entity_path: str  # repo-relative path
    created_at: str  # ISO 8601
    deleted_at: str | None  # ISO 8601 or None


@dataclass(frozen=True)
class EntityEdge:
    source_id: str
    target_id: str
    relationship: EdgeType


@dataclass(frozen=True)
class AnalysisResult:
    entities_upserted: int
    edges_upserted: int
    entities_soft_deleted: int


@dataclass(frozen=True)
class LinkResult:
    facts_processed: int
    links_created: int
    facts_skipped: int


def normalize_path(path: str, repo_root: Path | None = None) -> str:
    """Normalize a path to repo-relative format.

    - Strips repo_root prefix if present.
    - Resolves '.' and '..' components via posixpath.normpath.
    - Strips leading '/' and trailing '/'.
    - Returns the normalized repo-relative path.
    """
    p = path
    if repo_root is not None:
        repo_str = str(repo_root).rstrip("/") + "/"
        if p.startswith(repo_str):
            p = p[len(repo_str) :]
        elif p == str(repo_root).rstrip("/"):
            p = ""
    # Normalize . and .. components
    p = posixpath.normpath(p) if p else "."
    # Strip leading slash
    p = p.lstrip("/")
    # posixpath.normpath of empty string gives ".", clean that up
    if p == ".":
        p = ""
    # Strip trailing slash
    p = p.rstrip("/")
    return p
