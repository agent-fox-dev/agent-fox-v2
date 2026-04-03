"""DuckDB connection management, schema initialization, VSS extension setup.

Requirements: 11-REQ-1.1, 11-REQ-1.2, 11-REQ-1.3, 11-REQ-1.E1, 11-REQ-1.E2,
              11-REQ-2.1, 11-REQ-2.2, 11-REQ-2.3, 11-REQ-7.1
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb  # noqa: F401

from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.errors import KnowledgeStoreError  # noqa: F401
from agent_fox.knowledge.migrations import apply_pending_migrations

logger = logging.getLogger("agent_fox.knowledge.db")


class KnowledgeDB:
    """Manages the DuckDB knowledge store lifecycle."""

    def __init__(self, config: KnowledgeConfig, *, read_only: bool = False) -> None:
        self._config = config
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the active connection, raising if closed."""
        if self._conn is None:
            raise KnowledgeStoreError("Knowledge store is not open")
        return self._conn

    def open(self) -> None:
        """Open the database, install/load VSS, run migrations.

        Creates the parent directory if it does not exist. On first
        open, installs the VSS extension and creates the full schema.
        On subsequent opens, loads VSS and applies pending migrations.

        Raises:
            KnowledgeStoreError: If the database cannot be opened or
                schema initialization fails.
        """
        try:
            self._ensure_parent_dir()
            self._conn = duckdb.connect(self._config.store_path, read_only=self._read_only)
            if not self._read_only:
                self._setup_vss()
                self._initialize_schema()
                apply_pending_migrations(self._conn)
        except KnowledgeStoreError:
            raise
        except Exception as exc:
            raise KnowledgeStoreError(
                f"Failed to open knowledge store: {exc}",
            ) from exc

    def close(self) -> None:
        """Close the database connection, releasing file locks."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _ensure_parent_dir(self) -> None:
        """Create the parent directory for the database file."""
        parent = Path(self._config.store_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _setup_vss(self) -> None:
        """Install (first time) or load the VSS extension."""
        assert self._conn is not None
        try:
            self._conn.execute("LOAD vss;")
        except Exception:
            # First time: install then load
            try:
                self._conn.execute("INSTALL vss; LOAD vss;")
            except Exception as exc:
                logger.warning("VSS extension unavailable: %s", exc)

    def _initialize_schema(self) -> None:
        """Create all tables if schema_version does not exist.

        Uses IF NOT EXISTS on all CREATE TABLE statements for
        idempotency. Records schema version 1 only if no version
        row exists yet.
        """
        assert self._conn is not None
        dim = self._config.embedding_dimensions

        ddl = f"""
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_facts (
            id            UUID PRIMARY KEY,
            content       TEXT NOT NULL,
            category      TEXT,
            spec_name     TEXT,
            session_id    TEXT,
            commit_sha    TEXT,
            confidence    DOUBLE DEFAULT 0.6,
            created_at    TIMESTAMP,
            superseded_by UUID
        );

        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id        UUID PRIMARY KEY REFERENCES memory_facts(id),
            embedding FLOAT[{dim}]
        );

        CREATE TABLE IF NOT EXISTS session_outcomes (
            id            UUID PRIMARY KEY,
            spec_name     TEXT,
            task_group    TEXT,
            node_id       TEXT,
            touched_path  TEXT,
            status        TEXT,
            input_tokens  INTEGER,
            output_tokens INTEGER,
            duration_ms   INTEGER,
            created_at    TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fact_causes (
            cause_id  UUID,
            effect_id UUID,
            PRIMARY KEY (cause_id, effect_id)
        );

        CREATE TABLE IF NOT EXISTS tool_calls (
            id         UUID PRIMARY KEY,
            session_id TEXT,
            node_id    TEXT,
            tool_name  TEXT,
            called_at  TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tool_errors (
            id        UUID PRIMARY KEY,
            session_id TEXT,
            node_id    TEXT,
            tool_name  TEXT,
            failed_at  TIMESTAMP
        );

        INSERT INTO schema_version (version, description)
            SELECT 1, 'initial schema'
            WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = 1);
        """
        self._conn.execute(ddl)

    def __enter__(self) -> KnowledgeDB:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_knowledge_store(config: KnowledgeConfig, *, read_only: bool = False) -> KnowledgeDB:
    """Open the knowledge store. Raises on failure.

    Args:
        config: Knowledge configuration with store path.
        read_only: If True, open in read-only mode (allows concurrent
            access while another process holds a write lock).

    Returns a KnowledgeDB instance on success.

    Raises:
        RuntimeError: If the knowledge store cannot be opened,
            with message containing "Knowledge store initialization failed"
            and the underlying error detail including the file path.

    Requirements: 38-REQ-1.1, 38-REQ-1.2, 38-REQ-1.E1
    """
    try:
        db = KnowledgeDB(config, read_only=read_only)
        db.open()
        return db
    except Exception as exc:
        raise RuntimeError(f"Knowledge store initialization failed ({config.store_path}): {exc}") from exc
