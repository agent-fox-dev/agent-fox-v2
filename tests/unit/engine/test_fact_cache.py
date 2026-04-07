"""Tests for pre-computed ranked fact cache.

Test Spec: TS-39-14, TS-39-15, TS-39-16
Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3

Updated for spec 38: Tests now use the shared knowledge_conn fixture
(38-REQ-5.3) instead of creating inline duckdb.connect() connections.

Updated for fix-issue-273: Tolerance-based invalidation replaces exact
count matching.  Tests that previously validated count-delta-of-1
invalidation now use deltas that exceed the 10% default tolerance.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.engine.fact_cache import RankedFactCache
from tests.unit.knowledge.conftest import make_fact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_facts(conn: duckdb.DuckDBPyConnection, spec_name: str, n: int = 5) -> None:
    """Insert n facts into memory_facts for a given spec."""
    for i in range(n):
        fact_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO memory_facts
               (id, content, spec_name, category, confidence, created_at)
               VALUES (?::UUID, ?, ?, 'pattern', 0.9, CURRENT_TIMESTAMP)""",
            [fact_id, f"Fact {i} for {spec_name}", spec_name],
        )


@pytest.fixture
def cache_db(knowledge_conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """knowledge_conn with seeded facts for cache tests."""
    _seed_facts(knowledge_conn, "spec_a", n=5)
    _seed_facts(knowledge_conn, "spec_b", n=3)
    return knowledge_conn


def _make_cache_entry(
    spec_name: str = "spec_a",
    fact_count_at_creation: int = 100,
    n_facts: int = 1,
) -> RankedFactCache:
    return RankedFactCache(
        spec_name=spec_name,
        ranked_facts=[make_fact(id=f"f{i}", spec_name=spec_name) for i in range(n_facts)],
        created_at="2026-01-01T00:00:00",
        fact_count_at_creation=fact_count_at_creation,
    )


# ---------------------------------------------------------------------------
# TS-39-14: Fact Rankings Pre-Computed at Plan Time
# ---------------------------------------------------------------------------


class TestFactCache:
    """TS-39-14, TS-39-15, TS-39-16: Fact cache operations.

    Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3
    """

    def test_precompute_rankings(self, cache_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-14: Pre-computed rankings exist for each spec.

        Requirement: 39-REQ-5.1
        """
        from agent_fox.engine.fact_cache import (
            RankedFactCache,
            precompute_fact_rankings,
        )

        cache = precompute_fact_rankings(cache_db, ["spec_a", "spec_b"])
        assert "spec_a" in cache
        assert "spec_b" in cache
        assert isinstance(cache["spec_a"], RankedFactCache)
        assert len(cache["spec_a"].ranked_facts) > 0

    def test_stale_cache_returns_none(self) -> None:
        """TS-39-15: Cache exceeding tolerance threshold returns None.

        Requirement: 39-REQ-5.2
        AC-4: Uses a count change that exceeds the 10% default tolerance.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        # 115 vs 100 → 15% drift, exceeds 10% default tolerance
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=115)
        assert result is None

    def test_cache_invalidation(self) -> None:
        """TS-39-16: Cache invalidated when fact count drift exceeds threshold.

        Requirement: 39-REQ-5.3
        AC-4: Uses a count change clearly beyond the tolerance threshold.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        # 120 vs 100 → 20% drift, exceeds 10% default tolerance
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=120)
        assert result is None

    def test_valid_cache_returns_facts(self) -> None:
        """Valid cache returns cached facts when count matches exactly."""
        from agent_fox.engine.fact_cache import get_cached_facts

        facts = [make_fact(id="f1", spec_name="spec_a")]
        from agent_fox.engine.fact_cache import RankedFactCache

        cache_entry = RankedFactCache(
            spec_name="spec_a",
            ranked_facts=facts,
            created_at="2026-01-01T00:00:00",
            fact_count_at_creation=5,
        )
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=5)
        assert result is not None
        assert len(result) == 1


# ---------------------------------------------------------------------------
# AC-1: Tolerance-based invalidation — small count increase
# ---------------------------------------------------------------------------


class TestToleranceBasedInvalidation:
    """AC-1, AC-2, AC-6: Tolerance-based cache invalidation."""

    def test_within_tolerance_small_increase_returns_facts(self) -> None:
        """AC-1: 5% increase (within 10% default tolerance) returns cached facts.

        cache built at 100 facts, queried with 105 — 5% drift, within tolerance.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=105)
        assert result is not None, "Expected cache hit for 5% count drift within 10% tolerance"

    def test_exceeds_tolerance_large_increase_returns_none(self) -> None:
        """AC-1: 15% increase (exceeds 10% default tolerance) returns None.

        cache built at 100 facts, queried with 115 — 15% drift, exceeds tolerance.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=115)
        assert result is None, "Expected cache miss for 15% count drift exceeding 10% tolerance"

    def test_within_tolerance_small_decrease_returns_facts(self) -> None:
        """AC-2: 5% decrease (within 10% default tolerance) returns cached facts.

        cache built at 100 facts, queried with 95 — 5% drift, within tolerance.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=95)
        assert result is not None, "Expected cache hit for 5% count decrease within 10% tolerance"

    def test_exceeds_tolerance_large_decrease_returns_none(self) -> None:
        """AC-2: 15% decrease (exceeds 10% default tolerance) returns None.

        cache built at 100 facts, queried with 85 — 15% drift, exceeds tolerance.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=85)
        assert result is None, "Expected cache miss for 15% count decrease exceeding 10% tolerance"


# ---------------------------------------------------------------------------
# AC-6: Configurable tolerance parameter
# ---------------------------------------------------------------------------


class TestConfigurableTolerance:
    """AC-6: get_cached_facts accepts a configurable tolerance parameter."""

    def test_tolerance_zero_exact_match_required(self) -> None:
        """AC-6: tolerance=0.0 restores exact-count matching.

        A count change of 1 (100 → 101) should return None with tolerance=0.0.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=101, tolerance=0.0
        )
        assert result is None, "tolerance=0.0 should enforce exact count match"

    def test_tolerance_zero_exact_match_hits(self) -> None:
        """AC-6: tolerance=0.0 returns cached facts when count is exactly equal."""
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=100, tolerance=0.0
        )
        assert result is not None, "tolerance=0.0 should return cached facts on exact match"

    def test_tolerance_10pct_within_range(self) -> None:
        """AC-6: tolerance=0.1 allows up to 10% drift.

        105 vs 100 → 5% → within tolerance=0.1, should return cached facts.
        """
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=105, tolerance=0.1
        )
        assert result is not None, "5% drift should be within 10% tolerance"

    def test_tolerance_custom_strict(self) -> None:
        """AC-6: Custom tight tolerance (2%) invalidates a 5% drift."""
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=105, tolerance=0.02
        )
        assert result is None, "5% drift should exceed 2% custom tolerance"

    def test_missing_spec_always_returns_none(self) -> None:
        """Cache miss for unknown spec name returns None regardless of tolerance."""
        from agent_fox.engine.fact_cache import get_cached_facts

        cache_entry = _make_cache_entry(fact_count_at_creation=100)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_b", current_fact_count=100, tolerance=0.1
        )
        assert result is None


# ---------------------------------------------------------------------------
# AC-5: Cache hit is logged when fact count is within tolerance
# ---------------------------------------------------------------------------


class TestCacheHitLogging:
    """AC-5: load_relevant_facts logs cache hit when count is within tolerance."""

    def test_logs_cache_hit_when_within_tolerance(
        self,
        cache_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """AC-5: 'Using cached fact rankings' is logged when drift is within tolerance.

        Simulates: cache built at count N, 3 new facts ingested (count N+3).
        load_relevant_facts should log a cache hit, not a cache miss.
        """
        from unittest.mock import MagicMock

        from agent_fox.engine.fact_cache import precompute_fact_rankings
        from agent_fox.engine.session_lifecycle import load_relevant_facts

        # Seed 100 facts
        for i in range(92):  # 8 already seeded by cache_db fixture → 100 total
            _seed_facts(cache_db, "spec_a", n=1)

        # Build cache at current count (100)
        cache = precompute_fact_rankings(cache_db, ["spec_a"])
        assert "spec_a" in cache

        # Add 3 more facts (3% drift, within 10% default tolerance)
        _seed_facts(cache_db, "spec_a", n=3)

        # Wrap the bare connection in a minimal KnowledgeDB-like object
        knowledge_db = MagicMock()
        knowledge_db.connection = cache_db

        with patch("agent_fox.engine.session_lifecycle.logger") as mock_logger:
            load_relevant_facts(
                knowledge_db=knowledge_db,
                spec_name="spec_a",
                confidence_threshold=0.5,
                fact_cache=cache,
            )

        # Check that the cache-hit message was logged, not the miss message
        debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
        hit_logged = any("Using cached fact rankings" in c for c in debug_calls)
        miss_logged = any("Cache miss" in c for c in debug_calls)
        assert hit_logged, f"Expected cache hit log; got calls: {debug_calls}"
        assert not miss_logged, f"Unexpected cache miss log; got calls: {debug_calls}"


# ---------------------------------------------------------------------------
# AC-3: Barrier sync rebuilds fact cache
# ---------------------------------------------------------------------------


class TestBarrierCacheRebuild:
    """AC-3: _barrier_sync rebuilds fact_cache after knowledge ingestion."""

    def test_barrier_sync_updates_fact_cache_in_place(
        self,
        cache_db: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """AC-3: After _barrier_sync, fact_cache entries reflect new fact count.

        Builds an initial fact cache, adds new facts to the DB, then calls
        _barrier_sync via a minimal infra dict and verifies that the cache dict
        is updated in-place with a new fact_count_at_creation.
        """
        from unittest.mock import MagicMock, patch

        from agent_fox.engine.fact_cache import precompute_fact_rankings
        from agent_fox.engine.run import _barrier_sync

        # Build initial cache at 8 facts (5 spec_a + 3 spec_b from fixture)
        initial_cache = precompute_fact_rankings(cache_db, ["spec_a"])
        original_count = initial_cache["spec_a"].fact_count_at_creation

        # Simulate infra dict (minimal)
        knowledge_db_mock = MagicMock()
        knowledge_db_mock.connection = cache_db

        infra = {
            "knowledge_db": knowledge_db_mock,
            "fact_cache": initial_cache,
        }

        # Insert 5 more facts so the count changes noticeably
        _seed_facts(cache_db, "spec_a", n=5)

        config_mock = MagicMock()
        config_mock.knowledge.confidence_threshold = 0.5

        # Patch run_background_ingestion (no real git workspace) and export.
        # _barrier_sync uses local imports so we patch at the source modules.
        with (
            patch("agent_fox.knowledge.ingest.run_background_ingestion"),
            patch("agent_fox.knowledge.store.export_facts_to_jsonl"),
        ):
            _barrier_sync(infra, config_mock)

        # The cache dict is updated in-place
        updated_count = infra["fact_cache"]["spec_a"].fact_count_at_creation
        assert updated_count > original_count, (
            f"Expected fact_count_at_creation to increase after barrier sync; "
            f"was {original_count}, got {updated_count}"
        )
