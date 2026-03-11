"""Tests for pre-computed ranked fact cache.

Test Spec: TS-39-14, TS-39-15, TS-39-16
Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema
from tests.unit.memory.conftest import make_fact

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
               VALUES (?::UUID, ?, ?, 'pattern', 'high', CURRENT_TIMESTAMP)""",
            [fact_id, f"Fact {i} for {spec_name}", spec_name],
        )


@pytest.fixture
def cache_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with schema and seeded facts for cache tests."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    _seed_facts(conn, "spec_a", n=5)
    _seed_facts(conn, "spec_b", n=3)
    return conn


# ---------------------------------------------------------------------------
# TS-39-14: Fact Rankings Pre-Computed at Plan Time
# ---------------------------------------------------------------------------


class TestFactCache:
    """TS-39-14, TS-39-15, TS-39-16: Fact cache operations.

    Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3
    """

    def test_precompute_rankings(
        self, cache_db: duckdb.DuckDBPyConnection
    ) -> None:
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
        """TS-39-15: Stale cache returns None.

        Requirement: 39-REQ-5.2
        """
        from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts

        cache_entry = RankedFactCache(
            spec_name="spec_a",
            ranked_facts=[
                make_fact(id="f1", spec_name="spec_a"),
            ],
            created_at="2026-01-01T00:00:00",
            fact_count_at_creation=5,
        )
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=7
        )
        assert result is None

    def test_cache_invalidation(self) -> None:
        """TS-39-16: Cache invalidated when facts added.

        Requirement: 39-REQ-5.3
        """
        from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts

        cache_entry = RankedFactCache(
            spec_name="spec_a",
            ranked_facts=[
                make_fact(id="f1", spec_name="spec_a"),
            ],
            created_at="2026-01-01T00:00:00",
            fact_count_at_creation=5,
        )
        # One new fact added (count went from 5 to 6)
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=6
        )
        assert result is None

    def test_valid_cache_returns_facts(self) -> None:
        """Valid cache returns cached facts when count matches."""
        from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts

        facts = [make_fact(id="f1", spec_name="spec_a")]
        cache_entry = RankedFactCache(
            spec_name="spec_a",
            ranked_facts=facts,
            created_at="2026-01-01T00:00:00",
            fact_count_at_creation=5,
        )
        result = get_cached_facts(
            {"spec_a": cache_entry}, "spec_a", current_fact_count=5
        )
        assert result is not None
        assert len(result) == 1
