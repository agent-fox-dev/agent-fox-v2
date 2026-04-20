"""Unit tests for the BundleBuilder sleep task.

Test Spec: TS-112-16 through TS-112-20,
           TS-112-E4, TS-112-E5,
           TS-112-P9

Requirements: 112-REQ-4.*
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import duckdb
from agent_fox.knowledge.sleep_compute import (  # noqa: F401
    SleepContext,
    SleepTaskResult,
    upsert_artifact,
)
from agent_fox.knowledge.sleep_tasks.bundle_builder import BundleBuilder  # noqa: F401

# ---------------------------------------------------------------------------
# Imports from non-existent modules — will trigger ImportError at collection
# ---------------------------------------------------------------------------
from agent_fox.core.config import SleepConfig  # noqa: F401

# ---------------------------------------------------------------------------
# Existing imports (these exist)
# ---------------------------------------------------------------------------
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.retrieval import _keyword_signal

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
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    return conn


def _insert_active_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    fact_id: str,
    spec_name: str,
    content: str = "A relevant fact.",
    keywords: list[str] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, spec_name, confidence, created_at, keywords)
        VALUES (?, ?, ?, 0.9, CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, content, spec_name, keywords or ["test"]],
    )


def _insert_superseded_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str,
) -> None:
    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, spec_name, confidence, created_at, superseded_by)
        VALUES (?, ?, ?, 0.9, CURRENT_TIMESTAMP, ?)
        """,
        [old_id, "Old superseded fact.", spec_name, new_id],
    )


def _make_ctx(conn: duckdb.DuckDBPyConnection) -> SleepContext:
    return SleepContext(
        conn=conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=5.0,
        sink_dispatcher=None,
    )


# ---------------------------------------------------------------------------
# TS-112-16: BundleBuilder identifies active specs
# ---------------------------------------------------------------------------


async def test_identifies_active_specs() -> None:
    """TS-112-16: Bundles created for spec_a, spec_b; not spec_c (only superseded)."""
    conn = _make_conn()

    # spec_a: 1 active fact
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="spec_a")
    # spec_b: 1 active fact
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="spec_b")
    # spec_c: only superseded fact
    _insert_superseded_fact(conn, spec_name="spec_c")

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    result = await builder.run(ctx)

    assert result.created == 2

    rows = conn.execute(
        "SELECT scope_key FROM sleep_artifacts WHERE task_name='bundle_builder' AND superseded_at IS NULL"
    ).fetchall()
    scope_keys = {r[0] for r in rows}
    assert "spec:spec_a" in scope_keys
    assert "spec:spec_b" in scope_keys
    assert "spec:spec_c" not in scope_keys


# ---------------------------------------------------------------------------
# TS-112-17: BundleBuilder content hash staleness
# ---------------------------------------------------------------------------


async def test_content_hash_staleness() -> None:
    """TS-112-17: Second run with same facts reports unchanged == first.created."""
    conn = _make_conn()
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="my_spec")

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    result1 = await builder.run(ctx)
    result2 = await builder.run(ctx)

    assert result2.unchanged == result1.created
    assert result2.created == 0


# ---------------------------------------------------------------------------
# TS-112-18: BundleBuilder stores keyword and causal signals
# ---------------------------------------------------------------------------


async def test_stores_keyword_and_causal() -> None:
    """TS-112-18: Bundle content is JSON with 'keyword' and 'causal' arrays."""
    conn = _make_conn()
    _insert_active_fact(
        conn,
        fact_id=str(uuid.uuid4()),
        spec_name="spec_a",
        content="The system uses DuckDB for storage.",
        keywords=["duckdb", "storage"],
    )

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    await builder.run(ctx)

    row = conn.execute(
        "SELECT content FROM sleep_artifacts"
        " WHERE task_name='bundle_builder' AND scope_key='spec:spec_a'"
        " AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    bundle = json.loads(row[0])
    assert "keyword" in bundle
    assert "causal" in bundle
    # keyword array should have ScoredFact-shaped objects
    if bundle["keyword"]:
        first = bundle["keyword"][0]
        assert "fact_id" in first


# ---------------------------------------------------------------------------
# TS-112-19: BundleBuilder metadata
# ---------------------------------------------------------------------------


async def test_bundle_metadata() -> None:
    """TS-112-19: metadata_json has spec_name, fact_count, keyword_count, causal_count."""
    conn = _make_conn()
    _insert_active_fact(
        conn,
        fact_id=str(uuid.uuid4()),
        spec_name="spec_a",
        content="A fact about caching.",
        keywords=["cache"],
    )

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    await builder.run(ctx)

    row = conn.execute(
        "SELECT metadata_json FROM sleep_artifacts"
        " WHERE task_name='bundle_builder' AND scope_key='spec:spec_a'"
        " AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    meta = json.loads(row[0])
    assert meta["spec_name"] == "spec_a"
    assert "fact_count" in meta
    assert "keyword_count" in meta
    assert "causal_count" in meta


# ---------------------------------------------------------------------------
# TS-112-20: BundleBuilder zero LLM cost
# ---------------------------------------------------------------------------


async def test_zero_llm_cost() -> None:
    """TS-112-20: BundleBuilder.run() returns llm_cost == 0.0."""
    conn = _make_conn()
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="spec_x")

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    result = await builder.run(ctx)

    assert result.llm_cost == 0.0


# ---------------------------------------------------------------------------
# TS-112-E4: Spec with zero active facts
# ---------------------------------------------------------------------------


async def test_spec_zero_active_facts() -> None:
    """TS-112-E4: spec 'empty_spec' has only superseded facts → no bundle."""
    conn = _make_conn()
    _insert_superseded_fact(conn, spec_name="empty_spec")

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    await builder.run(ctx)

    rows = conn.execute(
        "SELECT * FROM sleep_artifacts WHERE task_name='bundle_builder' AND scope_key='spec:empty_spec'"
    ).fetchall()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# TS-112-E5: Signal computation failure skips spec
# ---------------------------------------------------------------------------


async def test_signal_computation_failure() -> None:
    """TS-112-E5: _keyword_signal raises for 'bad_spec'; good_spec still gets bundle."""
    conn = _make_conn()
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="good_spec")
    _insert_active_fact(conn, fact_id=str(uuid.uuid4()), spec_name="bad_spec")

    original_keyword_signal = _keyword_signal

    def failing_keyword_signal(spec_name: str, *args: object, **kwargs: object) -> list:
        if spec_name == "bad_spec":
            raise RuntimeError("Simulated signal failure")
        return original_keyword_signal(spec_name, *args, **kwargs)

    with patch(
        "agent_fox.knowledge.sleep_tasks.bundle_builder._keyword_signal",
        side_effect=failing_keyword_signal,
    ):
        builder = BundleBuilder()
        ctx = _make_ctx(conn)
        result = await builder.run(ctx)

    # Only good_spec should have a bundle
    assert result.created == 1
    rows = conn.execute(
        "SELECT scope_key FROM sleep_artifacts WHERE task_name='bundle_builder' AND superseded_at IS NULL"
    ).fetchall()
    scope_keys = {r[0] for r in rows}
    assert "spec:good_spec" in scope_keys
    assert "spec:bad_spec" not in scope_keys


# ---------------------------------------------------------------------------
# TS-112-P9: Bundle signal fidelity (simplified unit test)
# ---------------------------------------------------------------------------


async def test_property_bundle_fidelity() -> None:
    """TS-112-P9: Deserialized bundle keyword/causal lists match live computation.

    Uses empty keywords (query-independent) for comparison, as live
    _keyword_signal needs a keyword list. This is a known limitation
    acknowledged in the spec Skeptic notes.
    """
    conn = _make_conn()
    fact_id = str(uuid.uuid4())
    _insert_active_fact(
        conn,
        fact_id=fact_id,
        spec_name="fidelity_spec",
        content="Fidelity test fact about retrieval.",
        keywords=["retrieval"],
    )

    builder = BundleBuilder()
    ctx = _make_ctx(conn)
    await builder.run(ctx)

    # Load cached bundle content
    row = conn.execute(
        "SELECT content FROM sleep_artifacts"
        " WHERE task_name='bundle_builder' AND scope_key='spec:fidelity_spec'"
        " AND superseded_at IS NULL"
    ).fetchone()
    assert row is not None
    bundle = json.loads(row[0])

    # Live keyword signal with empty keywords
    live_kw = _keyword_signal(
        spec_name="fidelity_spec",
        keywords=[],
        conn=conn,
        confidence_threshold=0.0,
    )
    live_kw_ids = {f.fact_id for f in live_kw}

    # Cached keyword fact IDs
    cached_kw_ids = {f["fact_id"] for f in bundle.get("keyword", [])}

    # The cached bundle should contain the same fact IDs as live computation
    assert cached_kw_ids == live_kw_ids
