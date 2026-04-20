"""Unit tests for the ContextRewriter sleep task.

Test Spec: TS-112-11 through TS-112-15,
           TS-112-E1, TS-112-E2, TS-112-E3,
           TS-112-P8

Requirements: 112-REQ-3.*
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pytest
from agent_fox.knowledge.sleep_compute import (  # noqa: F401
    SleepContext,
    SleepTaskResult,
    upsert_artifact,
)
from agent_fox.knowledge.sleep_tasks.context_rewriter import ContextRewriter  # noqa: F401
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Imports from non-existent modules — will trigger ImportError at collection
# ---------------------------------------------------------------------------
from agent_fox.core.config import SleepConfig  # noqa: F401

# ---------------------------------------------------------------------------
# Existing imports
# ---------------------------------------------------------------------------
from agent_fox.knowledge.migrations import run_migrations

# ---------------------------------------------------------------------------
# Sleep artifacts DDL
# ---------------------------------------------------------------------------

_SLEEP_ARTIFACTS_DDL = """
CREATE TABLE IF NOT EXISTS sleep_artifacts (
    id            UUID PRIMARY KEY,
    task_name     VARCHAR,
    scope_key     VARCHAR,
    content       TEXT,
    metadata_json TEXT,
    content_hash  VARCHAR,
    created_at    TIMESTAMP,
    superseded_at TIMESTAMP
)
"""

# ---------------------------------------------------------------------------
# Helper: create a fully migrated in-memory DB with sleep_artifacts
# ---------------------------------------------------------------------------


def _make_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    return conn


# ---------------------------------------------------------------------------
# Helper: insert a fact and link it to an entity_graph entry
# ---------------------------------------------------------------------------


def _insert_fact_with_entity(
    conn: duckdb.DuckDBPyConnection,
    *,
    fact_id: str,
    content: str,
    spec_name: str = "test_spec",
    entity_path: str,
) -> None:
    """Insert a fact into memory_facts and link it via entity_graph + fact_entities."""
    entity_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO memory_facts (id, content, spec_name, confidence, created_at)
        VALUES (?, ?, ?, 0.9, CURRENT_TIMESTAMP)
        """,
        [fact_id, content, spec_name],
    )
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)
        """,
        [entity_id, entity_path, entity_path],
    )
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [fact_id, entity_id],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def migrated_conn() -> duckdb.DuckDBPyConnection:
    return _make_conn()


def _make_sleep_ctx(
    conn: duckdb.DuckDBPyConnection,
    *,
    llm_response: str = "A short narrative.",
) -> SleepContext:
    """Build a SleepContext with a mock LLM embedded in it."""
    return SleepContext(
        conn=conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=5.0,
        sink_dispatcher=None,
    )


# ---------------------------------------------------------------------------
# TS-112-11: ContextRewriter clusters by directory
# ---------------------------------------------------------------------------


async def test_clusters_by_directory() -> None:
    """TS-112-11: 3 facts in agent_fox/knowledge/ → 1 block; 1 in engine/ → skipped."""
    conn = _make_conn()
    # 3 facts in agent_fox/knowledge/
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Knowledge fact {i}",
            entity_path=f"agent_fox/knowledge/module_{i}.py",
        )
    # 1 fact in agent_fox/engine/ — not enough for a cluster
    _insert_fact_with_entity(
        conn,
        fact_id=str(uuid.uuid4()),
        content="Engine fact",
        entity_path="agent_fox/engine/barrier.py",
    )

    mock_llm_response = "This module handles knowledge storage and retrieval."
    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value=mock_llm_response),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        result = await rewriter.run(ctx)

    assert result.created == 1
    rows = conn.execute(
        "SELECT scope_key FROM sleep_artifacts WHERE task_name = 'context_rewriter' AND superseded_at IS NULL"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "dir:agent_fox/knowledge"


# ---------------------------------------------------------------------------
# TS-112-12: ContextRewriter content hash staleness
# ---------------------------------------------------------------------------


async def test_content_hash_staleness() -> None:
    """TS-112-12: Second run with same facts reports unchanged=1, created=0."""
    conn = _make_conn()
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Stable fact {i}",
            entity_path=f"agent_fox/knowledge/store_{i}.py",
        )

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value="Module summary."),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        result1 = await rewriter.run(ctx)
        assert result1.created == 1

        result2 = await rewriter.run(ctx)

    assert result2.unchanged == 1
    assert result2.created == 0
    assert result2.refreshed == 0


# ---------------------------------------------------------------------------
# TS-112-13: ContextRewriter LLM call and storage
# ---------------------------------------------------------------------------


async def test_llm_call_and_storage() -> None:
    """TS-112-13: LLM called once; artifact stored in sleep_artifacts."""
    conn = _make_conn()
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Fact {i} about retrieval system",
            entity_path=f"agent_fox/knowledge/retrieval_{i}.py",
        )

    llm_call_count = 0
    llm_response = "x" * 500  # 500-char narrative

    async def mock_llm(*args: object, **kwargs: object) -> str:
        nonlocal llm_call_count
        llm_call_count += 1
        return llm_response

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=mock_llm,
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        await rewriter.run(ctx)

    assert llm_call_count == 1
    row = conn.execute(
        "SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter' AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    assert len(row[0]) > 0


# ---------------------------------------------------------------------------
# TS-112-14: Context block size cap
# ---------------------------------------------------------------------------


async def test_context_block_size_cap() -> None:
    """TS-112-14: LLM returns 3000 chars → stored content ≤ 2000 chars, ends with '.'."""
    conn = _make_conn()
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Fact {i} in module",
            entity_path=f"agent_fox/knowledge/big_{i}.py",
        )

    # Build a 3000-char string with multiple sentences so truncation can find "."
    llm_response = ("This is sentence one. This is sentence two. " * 70)[:3000]

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value=llm_response),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        await rewriter.run(ctx)

    row = conn.execute(
        "SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter' AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    stored = row[0]
    assert len(stored) <= 2000
    assert stored.rstrip().endswith(".")


# ---------------------------------------------------------------------------
# TS-112-15: ContextRewriter metadata
# ---------------------------------------------------------------------------


async def test_metadata_json() -> None:
    """TS-112-15: metadata_json has directory, fact_count, fact_ids."""
    conn = _make_conn()
    fact_ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, fid in enumerate(fact_ids):
        _insert_fact_with_entity(
            conn,
            fact_id=fid,
            content=f"Meta fact {i}",
            entity_path=f"agent_fox/knowledge/meta_{i}.py",
        )

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value="Summary of meta facts."),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        await rewriter.run(ctx)

    row = conn.execute(
        "SELECT metadata_json FROM sleep_artifacts WHERE task_name='context_rewriter' AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    meta = json.loads(row[0])
    assert "directory" in meta
    assert meta["fact_count"] == 3
    assert "fact_ids" in meta
    assert len(meta["fact_ids"]) == 3


# ---------------------------------------------------------------------------
# TS-112-E1: Fact in multiple directories
# ---------------------------------------------------------------------------


async def test_fact_in_multiple_dirs() -> None:
    """TS-112-E1: Shared fact appears in both qualifying clusters' metadata."""
    conn = _make_conn()

    shared_fact_id = str(uuid.uuid4())
    # Insert shared fact (no entity link yet)
    conn.execute(
        "INSERT INTO memory_facts"
        " (id, content, spec_name, confidence, created_at)"
        " VALUES (?, ?, ?, 0.9, CURRENT_TIMESTAMP)",
        [shared_fact_id, "Shared fact content", "test_spec"],
    )

    # Link shared fact to dir_a/ entity
    entity_a = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entity_graph"
        " (id, entity_type, entity_name, entity_path, created_at)"
        " VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)",
        [entity_a, "dir_a/shared.py", "dir_a/shared.py"],
    )
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [shared_fact_id, entity_a],
    )

    # Link shared fact to dir_b/ entity
    entity_b = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entity_graph"
        " (id, entity_type, entity_name, entity_path, created_at)"
        " VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)",
        [entity_b, "dir_b/shared.py", "dir_b/shared.py"],
    )
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [shared_fact_id, entity_b],
    )

    # Add 2 more unique facts in dir_a/
    for i in range(2):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"dir_a unique fact {i}",
            entity_path=f"dir_a/module_{i}.py",
        )

    # Add 2 more unique facts in dir_b/
    for i in range(2):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"dir_b unique fact {i}",
            entity_path=f"dir_b/module_{i}.py",
        )

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value="Summary."),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        result = await rewriter.run(ctx)

    assert result.created == 2

    row_a = conn.execute(
        "SELECT metadata_json FROM sleep_artifacts"
        " WHERE task_name='context_rewriter' AND scope_key='dir:dir_a'"
        " AND superseded_at IS NULL"
    ).fetchone()
    row_b = conn.execute(
        "SELECT metadata_json FROM sleep_artifacts"
        " WHERE task_name='context_rewriter' AND scope_key='dir:dir_b'"
        " AND superseded_at IS NULL"
    ).fetchone()

    assert row_a is not None
    assert row_b is not None
    meta_a = json.loads(row_a[0])
    meta_b = json.loads(row_b[0])
    assert shared_fact_id in meta_a["fact_ids"]
    assert shared_fact_id in meta_b["fact_ids"]


# ---------------------------------------------------------------------------
# TS-112-E2: No qualifying clusters (fewer than 3 facts per directory)
# ---------------------------------------------------------------------------


async def test_no_qualifying_clusters() -> None:
    """TS-112-E2: Only 2 facts in same dir → created=0."""
    conn = _make_conn()
    for i in range(2):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Small cluster fact {i}",
            entity_path=f"agent_fox/knowledge/small_{i}.py",
        )

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value="Should not be called."),
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        result = await rewriter.run(ctx)

    assert result.created == 0
    assert result.refreshed == 0
    assert result.unchanged == 0


# ---------------------------------------------------------------------------
# TS-112-E3: LLM failure for one cluster, success for the other
# ---------------------------------------------------------------------------


async def test_llm_failure_skips_cluster() -> None:
    """TS-112-E3: LLM fails for cluster A, succeeds for cluster B → created=1."""
    conn = _make_conn()

    # Cluster A: 3 facts in alpha/
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Alpha fact {i}",
            entity_path=f"alpha/module_{i}.py",
        )

    # Cluster B: 3 facts in beta/
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Beta fact {i}",
            entity_path=f"beta/module_{i}.py",
        )

    call_count = 0

    async def llm_side_effect(*args: object, **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM failed for first cluster")
        return "Beta cluster summary."

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=llm_side_effect,
    ):
        rewriter = ContextRewriter()
        ctx = _make_sleep_ctx(conn)
        result = await rewriter.run(ctx)

    assert result.created == 1


# ---------------------------------------------------------------------------
# TS-112-P8: Context block size bound (property)
# ---------------------------------------------------------------------------


@given(length=st.integers(min_value=0, max_value=10000))
@settings(max_examples=50)
async def test_property_block_size_bound(length: int) -> None:
    """TS-112-P8: Stored content ≤ 2000 chars for any LLM output length."""
    conn = _make_conn()
    # Re-seed 3 facts each time (each hypothesis example gets fresh conn)
    for i in range(3):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Prop fact {i}",
            entity_path=f"agent_fox/knowledge/prop_{i}.py",
        )

    llm_output = ("Sentence here. " * (length // 15 + 1))[:length]

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=AsyncMock(return_value=llm_output),
    ):
        rewriter = ContextRewriter()
        ctx = SleepContext(
            conn=conn,
            repo_root=Path("."),
            model="standard",
            embedder=None,
            budget_remaining=5.0,
            sink_dispatcher=None,
        )
        await rewriter.run(ctx)

    rows = conn.execute(
        "SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter' AND superseded_at IS NULL"
    ).fetchall()
    for row in rows:
        assert len(row[0]) <= 2000
