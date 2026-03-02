"""Fixtures for DuckDB knowledge store tests.

Provides KnowledgeConfig with tmp_path, in-memory DuckDB connections,
a create_schema helper that mirrors the real schema DDL, and seeded
causal graph data for Time Vision (spec 13) tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import duckdb
import pytest

from agent_fox.core.config import KnowledgeConfig

# -- Well-known fact UUIDs for Time Vision tests --------------------------------
# These are full UUIDs used consistently across causal/temporal/pattern tests.

FACT_AAA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FACT_BBB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FACT_CCC = "cccccccc-cccc-cccc-cccc-cccccccccccc"
FACT_DDD = "dddddddd-dddd-dddd-dddd-dddddddddddd"
FACT_EEE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

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


# -- Seed data helpers for Time Vision (spec 13) --------------------------------


def seed_facts(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert well-known facts into memory_facts for causal graph tests."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, spec_name, session_id,
                                  commit_sha, category, confidence, created_at)
        VALUES
            (?, 'User.email changed to nullable', '07_oauth', '07/3',
             'a1b2c3d', 'decision', 'high', '2025-11-03 14:22:00'),
            (?, 'test_user_model.py assertions failed', '09_user_tests', '09/1',
             'e4f5g6h', 'gotcha', 'high', '2025-11-17 09:15:00'),
            (?, 'Added migration for nullable email', '12_auth_fix', '12/2',
             'i7j8k9l', 'pattern', 'high', '2025-11-18 11:30:00'),
            (?, 'Isolated root fact with no links', '05_setup', '05/1',
             NULL, 'convention', 'medium', '2025-10-01 08:00:00'),
            (?, 'Auth module refactored', '17_auth_v2', '17/1',
             'm0n1o2p', 'decision', 'high', '2025-12-01 10:00:00')
        """,
        [FACT_AAA, FACT_BBB, FACT_CCC, FACT_DDD, FACT_EEE],
    )


def seed_causal_links(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert causal links: aaa -> bbb -> ccc, aaa -> eee."""
    conn.execute(
        """
        INSERT INTO fact_causes (cause_id, effect_id) VALUES
            (?, ?),
            (?, ?),
            (?, ?)
        """,
        [FACT_AAA, FACT_BBB, FACT_BBB, FACT_CCC, FACT_AAA, FACT_EEE],
    )


def seed_session_outcomes(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert session outcomes for pattern detection tests."""
    conn.execute(
        """
        INSERT INTO session_outcomes (id, spec_name, task_group, node_id,
                                      touched_path, status, created_at)
        VALUES
            ('11111111-1111-1111-1111-111111111111', '07_oauth', '3', '07/3',
             'src/auth/user.py', 'completed', '2025-11-03 14:00:00'),
            ('22222222-2222-2222-2222-222222222222', '09_user_tests', '1', '09/1',
             'tests/test_user_model.py', 'failed', '2025-11-03 15:00:00'),
            ('33333333-3333-3333-3333-333333333333', '14_billing', '2', '14/2',
             'src/auth/session.py', 'completed', '2025-12-10 10:00:00'),
            ('44444444-4444-4444-4444-444444444444', '15_payments', '1', '15/1',
             'tests/test_payments.py', 'failed', '2025-12-10 11:00:00'),
            ('55555555-5555-5555-5555-555555555555', '20_auth_v3', '1', '20/1',
             'src/auth/user.py', 'completed', '2026-01-05 09:00:00'),
            ('66666666-6666-6666-6666-666666666666', '21_user_tests_v2', '1', '21/1',
             'tests/test_user_model.py', 'failed', '2026-01-05 10:00:00')
        """,
    )


def create_empty_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with schema but no seeded data."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return conn


@pytest.fixture
def causal_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with schema and seeded causal data.

    Includes: memory_facts (5 facts), fact_causes (3 links),
    and session_outcomes (6 entries) as defined in test_spec.md.
    """
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    seed_causal_links(conn)
    seed_session_outcomes(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass
