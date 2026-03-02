"""Fixtures for DuckDB knowledge store tests.

Provides KnowledgeConfig with tmp_path, in-memory DuckDB connections,
and a create_schema helper that mirrors the real schema DDL.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from agent_fox.core.config import KnowledgeConfig

# -- Schema DDL (mirrors KnowledgeDB._initialize_schema) --------------------

SCHEMA_DDL = """
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
    confidence    TEXT DEFAULT 'high',
    created_at    TIMESTAMP,
    superseded_by UUID
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id        UUID PRIMARY KEY REFERENCES memory_facts(id),
    embedding FLOAT[1024]
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


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the full knowledge store schema in an existing connection.

    This helper executes the same DDL that KnowledgeDB._initialize_schema
    uses, allowing tests to set up schema without going through the full
    KnowledgeDB.open() path.
    """
    conn.execute(SCHEMA_DDL)


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def knowledge_config(tmp_path: Path) -> KnowledgeConfig:
    """KnowledgeConfig with store_path pointing to a temp directory."""
    db_path = tmp_path / "knowledge.duckdb"
    return KnowledgeConfig(store_path=str(db_path))


@pytest.fixture
def in_memory_conn() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection for isolated unit tests."""
    conn = duckdb.connect(":memory:")
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def schema_conn(in_memory_conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with the full schema created."""
    create_schema(in_memory_conn)
    return in_memory_conn
