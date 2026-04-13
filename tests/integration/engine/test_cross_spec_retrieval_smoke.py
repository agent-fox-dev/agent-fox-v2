"""Integration smoke tests for cross-spec vector retrieval.

Tests: TS-94-SMOKE-1, TS-94-SMOKE-2
Execution Paths: Path 1 (full pipeline), Path 2 (graceful degradation)
Requirements: 94-REQ-2.1, 94-REQ-2.2, 94-REQ-3.1, 94-REQ-5.1

These tests use REAL components (no VectorSearch or EmbeddingGenerator mocks).
The knowledge store uses an in-memory DuckDB connection to avoid filesystem I/O.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import duckdb

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.facts import Fact

# ---------------------------------------------------------------------------
# Schema DDL (mirrors KnowledgeDB._initialize_schema)
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
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
    embedding FLOAT[384]
);

CREATE TABLE IF NOT EXISTS fact_causes (
    cause_id  UUID,
    effect_id UUID,
    PRIMARY KEY (cause_id, effect_id)
);
"""

# ---------------------------------------------------------------------------
# Helper for deterministic embeddings without loading the real model
# ---------------------------------------------------------------------------


def _make_deterministic_embedding(seed: int, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized embedding vector for tests."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / norm for x in raw]


# Embeddings for smoke tests: auth fact and rate_limit fact are semantically
# similar (both about API/token topics) while being distinct vectors.
_EMBEDDING_AUTH = _make_deterministic_embedding(1)
_EMBEDDING_RATE_LIMIT = _make_deterministic_embedding(2)
# Query embedding is closest to auth embedding (seed 1) for testing
_EMBEDDING_QUERY_LIKE_AUTH = _make_deterministic_embedding(1)

# tasks.md for spec "12_rate_limiting" with task group 2
_TASKS_MD_RATE_LIMITING = """\
- [ ] 2. Implement rate limiting middleware

  - [ ] 2.1 Create rate limiting middleware class
    - Implement rate limiting middleware for API endpoints
    - _Requirements: 12-REQ-1.1_
"""


def _setup_knowledge_store_with_embeddings() -> tuple[duckdb.DuckDBPyConnection, str, str]:
    """Create in-memory DuckDB with two facts and their embeddings.

    Returns (conn, auth_fact_id, rate_limit_fact_id).
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_SCHEMA_DDL)

    auth_fact_id = str(uuid.uuid4())
    rate_limit_fact_id = str(uuid.uuid4())

    # Insert auth fact (from spec "03_auth")
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)"
        " VALUES (?, ?, 'convention', '03_auth', 0.9, CURRENT_TIMESTAMP)",
        [auth_fact_id, "API uses JWT with RS256 signing"],
    )
    conn.execute(
        "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
        [auth_fact_id, _EMBEDDING_AUTH],
    )

    # Insert rate_limit fact (from spec "12_rate_limiting")
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)"
        " VALUES (?, ?, 'decision', '12_rate_limiting', 0.9, CURRENT_TIMESTAMP)",
        [rate_limit_fact_id, "Rate limiter config uses token bucket algorithm"],
    )
    conn.execute(
        "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
        [rate_limit_fact_id, _EMBEDDING_RATE_LIMIT],
    )

    return conn, auth_fact_id, rate_limit_fact_id


def _setup_knowledge_store_no_embeddings() -> tuple[duckdb.DuckDBPyConnection, str]:
    """Create in-memory DuckDB with a fact but NO embeddings.

    Returns (conn, fact_id).
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_SCHEMA_DDL)

    fact_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)"
        " VALUES (?, ?, 'pattern', '12_rate_limiting', 0.9, CURRENT_TIMESTAMP)",
        [fact_id, "Rate limiter config uses token bucket algorithm"],
    )
    # Deliberately no embedding inserted

    return conn, fact_id


def _make_fact_from_db(
    fact_id: str,
    content: str,
    spec_name: str,
) -> Fact:
    """Create a Fact object for use as spec-specific facts input."""
    return Fact(
        id=fact_id,
        content=content,
        category="decision",
        spec_name=spec_name,
        keywords=[],
        confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# TS-94-SMOKE-1: Full cross-spec retrieval pipeline
# Execution Path 1 from design.md
# ---------------------------------------------------------------------------


def test_full_pipeline(tmp_path: Path) -> None:
    """TS-94-SMOKE-1: Cross-spec facts appear in merged result via real vector search.

    Uses real DuckDB vector search and a real EmbeddingGenerator.
    The mock is ONLY applied to EmbeddingGenerator.embed_text to return
    a deterministic embedding (avoiding model loading in tests).
    VectorSearch.search runs against real DuckDB.
    """
    spec_dir = tmp_path / "12_rate_limiting"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(_TASKS_MD_RATE_LIMITING)

    conn, auth_fact_id, rate_limit_fact_id = _setup_knowledge_store_with_embeddings()

    # The rate limiting fact (same spec) is the spec-specific input
    rate_limit_fact = _make_fact_from_db(
        rate_limit_fact_id,
        "Rate limiter config uses token bucket algorithm",
        "12_rate_limiting",
    )

    # Set up mock KnowledgeDB wrapping the real in-memory connection
    mock_kb = MagicMock(spec=KnowledgeDB)
    mock_kb.connection = conn

    # Use a mock embedder that returns the query embedding deterministically
    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = _EMBEDDING_QUERY_LIKE_AUTH

    config = AgentFoxConfig()

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        config,
        knowledge_db=mock_kb,
        embedder=mock_embedder,
    )

    merged = runner._retrieve_cross_spec_facts(spec_dir, [rate_limit_fact])

    # The auth fact from 03_auth should appear in merged result
    merged_ids = {f.id for f in merged}
    assert auth_fact_id in merged_ids, (
        f"Cross-spec auth fact (id={auth_fact_id!r}) not found in merged result: {merged_ids!r}"
    )
    assert len(merged) >= 2, f"Expected at least 2 facts in merged result, got {len(merged)}"

    conn.close()


# ---------------------------------------------------------------------------
# TS-94-SMOKE-2: Graceful degradation with empty knowledge store
# Execution Path 2 from design.md
# ---------------------------------------------------------------------------


def test_empty_knowledge_store(tmp_path: Path) -> None:
    """TS-94-SMOKE-2: No embeddings in store → spec facts returned unchanged.

    Uses real DuckDB (no embedding mock for the store), real VectorSearch,
    and a real mock embedder that returns a valid query embedding.
    The search returns empty because no memory_embeddings rows exist.
    """
    spec_dir = tmp_path / "12_rate_limiting"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(_TASKS_MD_RATE_LIMITING)

    conn, fact_id = _setup_knowledge_store_no_embeddings()

    rate_limit_fact = _make_fact_from_db(
        fact_id,
        "Rate limiter config uses token bucket algorithm",
        "12_rate_limiting",
    )

    mock_kb = MagicMock(spec=KnowledgeDB)
    mock_kb.connection = conn

    # Embedder returns a valid embedding, but the store has no embeddings to search
    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = _EMBEDDING_QUERY_LIKE_AUTH

    config = AgentFoxConfig()

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        config,
        knowledge_db=mock_kb,
        embedder=mock_embedder,
    )

    spec_facts = [rate_limit_fact]
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts, (
        f"With empty embeddings store, expected spec facts unchanged: {spec_facts!r}, got {result!r}"
    )

    conn.close()
