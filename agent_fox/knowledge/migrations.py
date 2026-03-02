"""Schema version table, forward-only migration runner, migration registry.

Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3, 11-REQ-3.E1
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import duckdb  # noqa: F401

from agent_fox.core.errors import KnowledgeStoreError  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.migrations")

MigrationFn = Callable[[duckdb.DuckDBPyConnection], None]


@dataclass(frozen=True)
class Migration:
    """A forward-only schema migration."""

    version: int
    description: str
    apply: MigrationFn


# Registry of all migrations, ordered by version.
MIGRATIONS: list[Migration] = [
    # Migration(version=2, description="add foo column", apply=migrate_v2),
]


def get_current_version(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the current schema version, or 0 if no version table."""
    raise NotImplementedError


def apply_pending_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all migrations newer than the current schema version.

    Each migration runs in its own transaction. On failure, raises
    KnowledgeStoreError with the failing version and cause.
    """
    raise NotImplementedError


def record_version(
    conn: duckdb.DuckDBPyConnection,
    version: int,
    description: str,
) -> None:
    """Insert a row into schema_version."""
    raise NotImplementedError
