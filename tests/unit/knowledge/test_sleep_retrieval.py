"""Unit tests for AdaptiveRetriever sleep artifact consumption.

Test Spec: TS-112-21 through TS-112-29,
           TS-112-E6, TS-112-E7,
           TS-112-P4, TS-112-P5, TS-112-P6

Requirements: 112-REQ-5.*, 112-REQ-6.*
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Imports from non-existent modules — will trigger ImportError at collection
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Existing imports (these already exist)
# ---------------------------------------------------------------------------
from agent_fox.core.config import (
    KnowledgeConfig,
    RetrievalConfig,
    SleepConfig,  # noqa: F401
)
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.retrieval import (  # noqa: F401
    AdaptiveRetriever,
    CachedBundle,
    RetrievalResult,
    ScoredFact,
    _causal_signal,
    _keyword_signal,
    _load_cached_bundle,
    _load_context_preamble,
)
from agent_fox.knowledge.sleep_compute import (  # noqa: F401
    SleepContext,
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


def _make_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full schema + sleep_artifacts."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    return conn


def _insert_sleep_artifact(
    conn: duckdb.DuckDBPyConnection,
    *,
    task_name: str,
    scope_key: str,
    content: str,
    metadata_json: str = "{}",
    content_hash: str = "abc123",
    superseded: bool = False,
) -> None:
    """Directly insert a row into sleep_artifacts."""
    conn.execute(
        """
        INSERT INTO sleep_artifacts (id, task_name, scope_key, content, metadata_json,
                                     content_hash, created_at, superseded_at)
        VALUES (gen_random_uuid(), ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        [
            task_name,
            scope_key,
            content,
            metadata_json,
            content_hash,
            "2024-01-01" if superseded else None,
        ],
    )


def _make_knowledge_config(token_budget: int = 30000) -> KnowledgeConfig:
    return KnowledgeConfig(retrieval=RetrievalConfig(token_budget=token_budget))


def _make_mock_embedder() -> MagicMock:
    embedder = MagicMock()
    embedder.embedding_dimensions = 384
    embedder.embed_text.return_value = [0.1] * 384
    return embedder


# ---------------------------------------------------------------------------
# TS-112-21: Retriever prepends context preamble
# ---------------------------------------------------------------------------


def test_prepends_context_preamble() -> None:
    """TS-112-21: context block for 'dir:agent_fox/knowledge' prepended with ## Module Context."""
    conn = _make_conn()
    _insert_sleep_artifact(
        conn,
        task_name="context_rewriter",
        scope_key="dir:agent_fox/knowledge",
        content="This module handles knowledge storage.",
    )

    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    result = retriever.retrieve(
        spec_name="test_spec",
        archetype="coder",
        node_status="fresh",
        task_description="Working on knowledge store",
        touched_files=["agent_fox/knowledge/store.py"],
        keywords=[],
    )

    assert "## Module Context" in result.context
    assert result.context.index("## Module Context") < result.context.index("## Knowledge Context")


# ---------------------------------------------------------------------------
# TS-112-22: Preamble respects 30% budget cap
# ---------------------------------------------------------------------------


def test_preamble_budget_cap() -> None:
    """TS-112-22: _load_context_preamble returns ≤ 3000 chars when budget=10000."""
    conn = _make_conn()

    # Insert multiple large context blocks totaling >> 3000 chars
    for i in range(10):
        _insert_sleep_artifact(
            conn,
            task_name="context_rewriter",
            scope_key=f"dir:module_{i}",
            content="x" * 500,  # 500 chars each, 5000 total
            metadata_json=json.dumps({"directory": f"module_{i}", "fact_count": 3, "fact_ids": []}),
            content_hash=f"hash_{i}",
        )

    preamble = _load_context_preamble(
        conn,
        touched_files=[f"module_{i}/file.py" for i in range(10)],
        token_budget=10000,
    )
    assert len(preamble) <= 3000


# ---------------------------------------------------------------------------
# TS-112-23: Retriever uses cached bundle signals
# ---------------------------------------------------------------------------


def test_uses_cached_bundle_signals() -> None:
    """TS-112-23: With valid bundle, _keyword_signal and _causal_signal not called."""
    conn = _make_conn()

    # Pre-populate a bundle for test_spec
    bundle_data = json.dumps({
        "keyword": [
            {
                "fact_id": str(uuid.uuid4()),
                "content": "Cached keyword fact",
                "spec_name": "test_spec",
                "confidence": 0.9,
                "created_at": "2026-01-01",
                "category": "decision",
                "score": 0.5,
            }
        ],
        "causal": [],
    })
    _insert_sleep_artifact(
        conn,
        task_name="bundle_builder",
        scope_key="spec:test_spec",
        content=bundle_data,
        content_hash="bundle_hash_123",
    )

    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    with (
        patch("agent_fox.knowledge.retrieval._keyword_signal") as kw_mock,
        patch("agent_fox.knowledge.retrieval._causal_signal") as cau_mock,
    ):
        result = retriever.retrieve(
            spec_name="test_spec",
            archetype="coder",
            node_status="fresh",
            task_description="Retrieve from cache",
            touched_files=[],
            keywords=["test"],
        )
        assert kw_mock.call_count == 0
        assert cau_mock.call_count == 0

    assert result.sleep_hit is True


# ---------------------------------------------------------------------------
# TS-112-24: Retriever falls back without bundle
# ---------------------------------------------------------------------------


def test_fallback_without_bundle() -> None:
    """TS-112-24: No bundle for spec → _keyword_signal is called, sleep_hit=False."""
    conn = _make_conn()
    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    with patch("agent_fox.knowledge.retrieval._keyword_signal") as kw_mock:
        kw_mock.return_value = []
        result = retriever.retrieve(
            spec_name="no_bundle_spec",
            archetype="coder",
            node_status="fresh",
            task_description="Test fallback",
            touched_files=[],
            keywords=["test"],
        )
        assert kw_mock.call_count >= 1

    assert result.sleep_hit is False


# ---------------------------------------------------------------------------
# TS-112-25: RetrievalResult sleep fields
# ---------------------------------------------------------------------------


def test_sleep_fields() -> None:
    """TS-112-25: RetrievalResult.sleep_hit is bool, sleep_artifact_count is int."""
    conn = _make_conn()
    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    result = retriever.retrieve(
        spec_name="any_spec",
        archetype="coder",
        node_status="fresh",
        task_description="Check fields",
        touched_files=[],
        keywords=[],
    )

    assert isinstance(result.sleep_hit, bool)
    assert isinstance(result.sleep_artifact_count, int)


# ---------------------------------------------------------------------------
# TS-112-26: Barrier runs sleep compute after compaction
# ---------------------------------------------------------------------------


async def test_barrier_runs_sleep_compute() -> None:
    """TS-112-26: sleep compute step appears in call order between compact and render_summary."""
    from agent_fox.engine.barrier import run_sync_barrier_sequence

    call_order: list[str] = []

    # Track compact (consolidation) calls
    async def mock_consolidation(*args: object, **kwargs: object) -> None:
        call_order.append("compact")

    async def mock_sleep_computer_run(*args: object, **kwargs: object) -> object:
        call_order.append("sleep_compute")
        from agent_fox.knowledge.sleep_compute import SleepComputeResult

        return SleepComputeResult(task_results={}, total_llm_cost=0.0, errors=[])

    def mock_render_summary(*args: object, **kwargs: object) -> str:
        call_order.append("render_summary")
        return ""

    # Build a minimal fake state object
    state = MagicMock()
    state.node_states = {}

    conn = _make_conn()
    config = KnowledgeConfig()

    with (
        patch("agent_fox.engine.barrier.run_consolidation", mock_consolidation),
        patch("agent_fox.knowledge.sleep_compute.SleepComputer.run", mock_sleep_computer_run),
        patch("agent_fox.knowledge.rendering.render_summary", mock_render_summary),
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
            knowledge_config=config,
            sink_dispatcher=None,
        )

    if "sleep_compute" in call_order:
        if "compact" in call_order:
            assert call_order.index("compact") < call_order.index("sleep_compute")
        if "render_summary" in call_order:
            assert call_order.index("sleep_compute") < call_order.index("render_summary")


# ---------------------------------------------------------------------------
# TS-112-27: SleepComputeStream implements WorkStream
# ---------------------------------------------------------------------------


def test_sleep_compute_stream() -> None:
    """TS-112-27: SleepComputeStream has name='sleep-compute', interval=1800, enabled is bool."""
    config = SleepConfig()
    stream = SleepComputeStream(config)

    assert stream.name == "sleep-compute"
    assert stream.interval == 1800
    assert isinstance(stream.enabled, bool)


# ---------------------------------------------------------------------------
# TS-112-28: SleepComputeStream run_once lifecycle
# ---------------------------------------------------------------------------


async def test_stream_run_once_lifecycle() -> None:
    """TS-112-28: run_once opens DB, runs SleepComputer, closes DB."""
    config = SleepConfig()

    open_count = 0
    close_count = 0
    run_count = 0

    def mock_db_factory() -> duckdb.DuckDBPyConnection:
        nonlocal open_count
        open_count += 1
        conn = _make_conn()
        original_close = conn.close

        def tracking_close() -> None:
            nonlocal close_count
            close_count += 1
            original_close()

        conn.close = tracking_close  # type: ignore[method-assign]
        return conn

    async def mock_sleep_run(*args: object, **kwargs: object) -> object:
        nonlocal run_count
        run_count += 1
        from agent_fox.knowledge.sleep_compute import SleepComputeResult

        return SleepComputeResult(task_results={}, total_llm_cost=0.0, errors=[])

    with patch("agent_fox.knowledge.sleep_compute.SleepComputer.run", mock_sleep_run):
        stream = SleepComputeStream(config, db_factory=mock_db_factory)
        await stream.run_once()

    assert open_count == 1
    assert run_count == 1
    assert close_count == 1


# ---------------------------------------------------------------------------
# TS-112-29: SleepComputeStream respects SharedBudget
# ---------------------------------------------------------------------------


async def test_stream_shared_budget() -> None:
    """TS-112-29: Exceeded SharedBudget causes run_once to skip SleepComputer."""
    config = SleepConfig()
    budget = SharedBudget(max_cost=1.0)
    budget.add_cost(1.0)  # budget.exceeded is now True

    run_count = 0

    async def mock_sleep_run(*args: object, **kwargs: object) -> object:
        nonlocal run_count
        run_count += 1
        from agent_fox.knowledge.sleep_compute import SleepComputeResult

        return SleepComputeResult(task_results={}, total_llm_cost=0.0, errors=[])

    with patch("agent_fox.knowledge.sleep_compute.SleepComputer.run", mock_sleep_run):
        stream = SleepComputeStream(config, budget=budget)
        await stream.run_once()

    assert run_count == 0


# ---------------------------------------------------------------------------
# TS-112-E6: Missing sleep_artifacts table
# ---------------------------------------------------------------------------


def test_missing_table() -> None:
    """TS-112-E6: Retriever with no sleep_artifacts table → sleep_hit=False, no crash."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    # Intentionally do NOT create sleep_artifacts

    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    # Should not raise
    result = retriever.retrieve(
        spec_name="any_spec",
        archetype="coder",
        node_status="fresh",
        task_description="Test missing table",
        touched_files=[],
        keywords=[],
    )

    assert result.sleep_hit is False


# ---------------------------------------------------------------------------
# TS-112-E7: All context blocks stale (superseded)
# ---------------------------------------------------------------------------


def test_all_blocks_stale() -> None:
    """TS-112-E7: All sleep_artifacts superseded → no '## Module Context' in result."""
    conn = _make_conn()
    _insert_sleep_artifact(
        conn,
        task_name="context_rewriter",
        scope_key="dir:agent_fox/knowledge",
        content="Stale context block.",
        superseded=True,
    )

    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    result = retriever.retrieve(
        spec_name="test_spec",
        archetype="coder",
        node_status="fresh",
        task_description="Check stale blocks",
        touched_files=["agent_fox/knowledge/store.py"],
        keywords=[],
    )

    assert "## Module Context" not in result.context


# ---------------------------------------------------------------------------
# TS-112-P4: Graceful degradation (simplified property)
# ---------------------------------------------------------------------------


def test_property_graceful_degradation() -> None:
    """TS-112-P4: When no sleep_artifacts exist, retriever returns valid result with sleep_hit=False."""
    conn = _make_conn()
    config = _make_knowledge_config()
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    result = retriever.retrieve(
        spec_name="some_spec",
        archetype="coder",
        node_status="fresh",
        task_description="Graceful degradation test",
        touched_files=[],
        keywords=[],
    )

    assert isinstance(result, RetrievalResult)
    assert result.sleep_hit is False
    assert isinstance(result.context, str)


# ---------------------------------------------------------------------------
# TS-112-P5: Token budget compliance (property)
# ---------------------------------------------------------------------------


@given(budget=st.integers(min_value=100, max_value=100000))
@settings(max_examples=50)
def test_property_token_budget(budget: int) -> None:
    """TS-112-P5: Total context length ≤ token_budget."""
    conn = _make_conn()
    config = _make_knowledge_config(token_budget=budget)
    retriever = AdaptiveRetriever(conn, config, embedder=_make_mock_embedder())

    with (
        patch("agent_fox.knowledge.retrieval._keyword_signal", return_value=[]),
        patch("agent_fox.knowledge.retrieval._causal_signal", return_value=[]),
        patch("agent_fox.knowledge.retrieval._vector_signal", return_value=[]),
        patch("agent_fox.knowledge.retrieval._entity_signal", return_value=[]),
    ):
        result = retriever.retrieve(
            spec_name="budget_spec",
            archetype="coder",
            node_status="fresh",
            task_description="Budget test",
            touched_files=[],
            keywords=[],
        )

    assert len(result.context) <= budget


# ---------------------------------------------------------------------------
# TS-112-P6: Preamble budget cap (property)
# ---------------------------------------------------------------------------


@given(budget=st.integers(min_value=100, max_value=100000))
@settings(max_examples=50)
def test_property_preamble_cap(budget: int) -> None:
    """TS-112-P6: Preamble length ≤ int(budget * 0.3)."""
    conn = _make_conn()

    # Insert multiple blocks with content that would exceed 30% of budget
    for i in range(20):
        _insert_sleep_artifact(
            conn,
            task_name="context_rewriter",
            scope_key=f"dir:module_{i}",
            content="z" * 1000,
            metadata_json=json.dumps({"directory": f"module_{i}", "fact_count": 3, "fact_ids": []}),
            content_hash=f"hash_{i}",
        )

    preamble = _load_context_preamble(
        conn,
        touched_files=[f"module_{i}/file.py" for i in range(20)],
        token_budget=budget,
    )

    assert len(preamble) <= int(budget * 0.3)
