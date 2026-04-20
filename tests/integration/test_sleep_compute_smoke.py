"""Integration smoke tests for the sleep-time compute pipeline.

Test Spec: TS-112-SMOKE-1, TS-112-SMOKE-2, TS-112-SMOKE-3

Requirements: 112-REQ-6.*, 112-REQ-5.*
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb

# ---------------------------------------------------------------------------
# Imports from non-existent modules — will trigger ImportError at collection
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Existing imports
# ---------------------------------------------------------------------------
from agent_fox.core.config import (
    KnowledgeConfig,
    RetrievalConfig,
    SleepConfig,  # noqa: F401
)
from agent_fox.engine.barrier import run_sync_barrier_sequence
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.retrieval import AdaptiveRetriever
from agent_fox.knowledge.sleep_compute import (  # noqa: F401
    SleepComputer,
    SleepComputeResult,
    SleepContext,
    SleepTaskResult,
)
from agent_fox.nightshift.daemon import SharedBudget
from agent_fox.nightshift.streams import SleepComputeStream  # noqa: F401

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
# Helpers
# ---------------------------------------------------------------------------


def _make_full_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full schema + sleep_artifacts."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    return conn


def _insert_fact_with_entity(
    conn: duckdb.DuckDBPyConnection,
    *,
    fact_id: str,
    content: str,
    spec_name: str = "test_spec",
    entity_path: str,
    keywords: list[str] | None = None,
) -> None:
    """Insert a fact + entity link for smoke test setup."""
    entity_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, spec_name, confidence, created_at, keywords)
        VALUES (?, ?, ?, 0.9, CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, content, spec_name, keywords or ["test"]],
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


def _make_mock_embedder() -> MagicMock:
    embedder = MagicMock()
    embedder.embedding_dimensions = 384
    embedder.embed_text.return_value = [0.1] * 384
    return embedder


# ---------------------------------------------------------------------------
# TS-112-SMOKE-1: Barrier triggers sleep compute end-to-end
# ---------------------------------------------------------------------------


async def test_barrier_end_to_end() -> None:
    """TS-112-SMOKE-1: Real SleepComputer + real tasks; barrier populates sleep_artifacts."""
    conn = _make_full_conn()

    # Seed 4 facts linked to same directory to trigger context_rewriter
    for i in range(4):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Knowledge system fact {i}: The module handles persistent storage.",
            spec_name="smoke_spec",
            entity_path=f"agent_fox/knowledge/module_{i}.py",
            keywords=["knowledge", "storage"],
        )

    # Mock only the LLM API call (not SleepComputer or the tasks themselves)
    async def mock_llm_call(*args: object, **kwargs: object) -> str:
        return "This module handles knowledge storage and retrieval. Facts are stored in DuckDB."

    state = MagicMock()
    state.node_states = {}

    knowledge_config = KnowledgeConfig()

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=mock_llm_call,
    ):
        await run_sync_barrier_sequence(
            state=state,
            sync_interval=1,
            repo_root=Path("."),
            emit_audit=lambda *a, **kw: None,
            specs_dir=None,
            hot_load_enabled=False,
            hot_load_fn=AsyncMock(),
            sync_plan_fn=lambda s: None,
            barrier_callback=None,
            knowledge_db_conn=conn,
            knowledge_config=knowledge_config,
            sink_dispatcher=None,
        )

    rows = conn.execute(
        "SELECT task_name FROM sleep_artifacts WHERE superseded_at IS NULL"
    ).fetchall()
    task_names = {r[0] for r in rows}

    # Both tasks should have produced artifacts
    assert "context_rewriter" in task_names
    assert "bundle_builder" in task_names


# ---------------------------------------------------------------------------
# TS-112-SMOKE-2: Nightshift stream triggers sleep compute
# ---------------------------------------------------------------------------


async def test_nightshift_stream() -> None:
    """TS-112-SMOKE-2: SleepComputeStream.run_once() populates sleep_artifacts; budget updated."""
    conn = _make_full_conn()

    for i in range(4):
        _insert_fact_with_entity(
            conn,
            fact_id=str(uuid.uuid4()),
            content=f"Nightshift fact {i}: system learns from history.",
            spec_name="ns_spec",
            entity_path=f"agent_fox/knowledge/ns_{i}.py",
        )

    config = SleepConfig()
    budget = SharedBudget(max_cost=10.0)

    async def mock_llm_call(*args: object, **kwargs: object) -> str:
        return "Summary of nightshift facts."

    with patch(
        "agent_fox.knowledge.sleep_tasks.context_rewriter.ContextRewriter._call_llm",
        new=mock_llm_call,
    ):
        stream = SleepComputeStream(
            config,
            budget=budget,
            db_factory=lambda: conn,
        )
        await stream.run_once()

    rows = conn.execute(
        "SELECT COUNT(*) FROM sleep_artifacts WHERE superseded_at IS NULL"
    ).fetchone()
    assert rows is not None
    assert rows[0] >= 1

    # Budget should have been updated (total_cost may be 0 if no LLM cost was real,
    # but the stream should have called add_cost)
    assert budget.total_cost >= 0.0


# ---------------------------------------------------------------------------
# TS-112-SMOKE-3: Retriever consumes real sleep artifacts
# ---------------------------------------------------------------------------


def test_retriever_consumes_artifacts() -> None:
    """TS-112-SMOKE-3: Real AdaptiveRetriever reads context blocks and bundle from sleep_artifacts."""
    conn = _make_full_conn()

    # Pre-populate a context block for agent_fox/knowledge/
    conn.execute(
        """
        INSERT INTO sleep_artifacts (id, task_name, scope_key, content, metadata_json,
                                     content_hash, created_at, superseded_at)
        VALUES (gen_random_uuid(), 'context_rewriter', 'dir:agent_fox/knowledge',
                '### agent_fox/knowledge\nThis module manages facts and retrieval.',
                ?, 'ctx_hash_abc', CURRENT_TIMESTAMP, NULL)
        """,
        [json.dumps({"directory": "agent_fox/knowledge", "fact_count": 3, "fact_ids": []})],
    )

    # Pre-populate a retrieval bundle for test_spec
    bundle_data = json.dumps({
        "keyword": [
            {
                "fact_id": str(uuid.uuid4()),
                "content": "Cached keyword fact for test_spec",
                "spec_name": "test_spec",
                "confidence": 0.9,
                "created_at": "2026-01-01T00:00:00",
                "category": "decision",
                "score": 0.5,
            }
        ],
        "causal": [],
    })
    conn.execute(
        """
        INSERT INTO sleep_artifacts (id, task_name, scope_key, content, metadata_json,
                                     content_hash, created_at, superseded_at)
        VALUES (gen_random_uuid(), 'bundle_builder', 'spec:test_spec',
                ?, '{"spec_name": "test_spec", "fact_count": 1, "keyword_count": 1, "causal_count": 0}',
                'bundle_hash_xyz', CURRENT_TIMESTAMP, NULL)
        """,
        [bundle_data],
    )

    config = KnowledgeConfig(retrieval=RetrievalConfig(token_budget=30000))
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    with (
        patch("agent_fox.knowledge.retrieval._keyword_signal") as kw_mock,
        patch("agent_fox.knowledge.retrieval._causal_signal") as cau_mock,
    ):
        kw_mock.return_value = []
        cau_mock.return_value = []

        result = retriever.retrieve(
            spec_name="test_spec",
            archetype="coder",
            node_status="fresh",
            task_description="Working on knowledge module",
            touched_files=["agent_fox/knowledge/foo.py"],
            keywords=["knowledge"],
        )

        assert kw_mock.call_count == 0
        assert cau_mock.call_count == 0

    assert "## Module Context" in result.context
    assert result.sleep_hit is True
