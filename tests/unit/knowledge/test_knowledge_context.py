"""Unit tests for knowledge context improvements (spec 42).

Tests causal traversal with review findings, confidence-aware filtering,
and pre-computed fact ranking cache.

Test Spec: TS-42-1 through TS-42-13, TS-42-E1, TS-42-E2, TS-42-E3
Requirements: 42-REQ-1.*, 42-REQ-2.*, 42-REQ-3.*
"""

from __future__ import annotations

import uuid

import duckdb

from agent_fox.core.config import KnowledgeConfig
from agent_fox.engine.fact_cache import (
    RankedFactCache,
    get_cached_facts,
    precompute_fact_rankings,
)
from agent_fox.knowledge.causal import CausalFact, traverse_with_reviews
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(uuid.uuid4())


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    content: str,
    spec_name: str = "test_spec",
    *,
    confidence: float | str = 0.9,
) -> None:
    """Insert a memory fact into the test database."""
    conn.execute(
        "INSERT INTO memory_facts (id, content, category, spec_name, "
        "confidence, created_at) "
        "VALUES (?::UUID, ?, 'pattern', ?, ?, CURRENT_TIMESTAMP)",
        [fact_id, content, spec_name, confidence],
    )


def _insert_causal_link(
    conn: duckdb.DuckDBPyConnection,
    cause_id: str,
    effect_id: str,
) -> None:
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?::UUID, ?::UUID)",
        [cause_id, effect_id],
    )


def _insert_review_finding(
    conn: duckdb.DuckDBPyConnection,
    finding_id: str,
    spec_name: str,
    *,
    severity: str = "major",
    description: str = "A review finding",
    task_group: str = "1",
    session_id: str = "test-session",
) -> None:
    conn.execute(
        "INSERT INTO review_findings "
        "(id, severity, description, requirement_ref, spec_name, "
        "task_group, session_id, created_at) "
        "VALUES (?::UUID, ?, ?, NULL, ?, ?, ?, CURRENT_TIMESTAMP)",
        [finding_id, severity, description, spec_name, task_group, session_id],
    )


def _insert_drift_finding(
    conn: duckdb.DuckDBPyConnection,
    finding_id: str,
    spec_name: str,
    *,
    severity: str = "minor",
    description: str = "A drift finding",
    task_group: str = "1",
    session_id: str = "test-session",
) -> None:
    conn.execute(
        "INSERT INTO drift_findings "
        "(id, severity, description, spec_ref, artifact_ref, spec_name, "
        "task_group, session_id, created_at) "
        "VALUES (?::UUID, ?, ?, NULL, NULL, ?, ?, ?, CURRENT_TIMESTAMP)",
        [finding_id, severity, description, spec_name, task_group, session_id],
    )


def _insert_verification_result(
    conn: duckdb.DuckDBPyConnection,
    result_id: str,
    spec_name: str,
    *,
    requirement_id: str = "REQ-1",
    verdict: str = "FAIL",
    evidence: str = "Test failed",
    task_group: str = "1",
    session_id: str = "test-session",
) -> None:
    conn.execute(
        "INSERT INTO verification_results "
        "(id, requirement_id, verdict, evidence, spec_name, "
        "task_group, session_id, created_at) "
        "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        [
            result_id,
            requirement_id,
            verdict,
            evidence,
            spec_name,
            task_group,
            session_id,
        ],
    )


# ---------------------------------------------------------------------------
# TestTraverseWithReviews
# ---------------------------------------------------------------------------


class TestTraverseWithReviews:
    """Tests for traverse_with_reviews() — causal traversal including findings.

    Requirements: 42-REQ-1.1, 42-REQ-1.3, 42-REQ-1.E1, 42-REQ-1.E2
    """

    def test_returns_causal_facts_and_review_findings(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-1: traverse_with_reviews returns CausalFact and review findings."""
        fact_a = _new_id()
        fact_b = _new_id()
        review_id = _new_id()

        _insert_fact(schema_conn, fact_a, "Cause fact", "test_spec")
        _insert_fact(schema_conn, fact_b, "Effect fact", "test_spec")
        _insert_causal_link(schema_conn, fact_a, fact_b)
        _insert_review_finding(schema_conn, review_id, "test_spec")

        result = traverse_with_reviews(schema_conn, fact_a)

        # Should contain CausalFact objects for both facts
        causal_facts = [r for r in result if isinstance(r, CausalFact)]
        assert len(causal_facts) == 2

        # Should contain the ReviewFinding
        review_findings = [r for r in result if isinstance(r, ReviewFinding)]
        assert len(review_findings) == 1
        assert review_findings[0].id == review_id

        # All items are deduplicated by ID
        ids = [r.fact_id if isinstance(r, CausalFact) else getattr(r, "id", None) for r in result]
        assert len(ids) == len(set(ids))

    def test_includes_drift_findings(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-2: traverse_with_reviews includes drift findings."""
        fact_id = _new_id()
        drift_id = _new_id()

        _insert_fact(schema_conn, fact_id, "A fact", "test_spec")
        _insert_drift_finding(schema_conn, drift_id, "test_spec")

        result = traverse_with_reviews(schema_conn, fact_id)

        causal_facts = [r for r in result if isinstance(r, CausalFact)]
        drift_findings = [r for r in result if isinstance(r, DriftFinding)]
        assert len(causal_facts) == 1
        assert len(drift_findings) == 1
        assert drift_findings[0].id == drift_id

    def test_includes_verification_results(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-3: traverse_with_reviews includes verification results."""
        fact_id = _new_id()
        ver_id = _new_id()

        _insert_fact(schema_conn, fact_id, "A fact", "test_spec")
        _insert_verification_result(schema_conn, ver_id, "test_spec")

        result = traverse_with_reviews(schema_conn, fact_id)

        causal_facts = [r for r in result if isinstance(r, CausalFact)]
        verification_results = [r for r in result if isinstance(r, VerificationResult)]
        assert len(causal_facts) == 1
        assert len(verification_results) == 1
        assert verification_results[0].id == ver_id

    def test_deduplicates_across_seeds(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-4: traverse_with_reviews deduplicates across seeds."""
        fact_a = _new_id()
        fact_b = _new_id()
        review_id = _new_id()

        _insert_fact(schema_conn, fact_a, "Fact A", "test_spec")
        _insert_fact(schema_conn, fact_b, "Fact B", "test_spec")
        _insert_causal_link(schema_conn, fact_a, fact_b)
        _insert_review_finding(schema_conn, review_id, "test_spec")

        # Traverse from A — should include the review finding
        result_a = traverse_with_reviews(schema_conn, fact_a)
        review_ids_a = [r.id for r in result_a if isinstance(r, ReviewFinding)]
        assert review_ids_a.count(review_id) == 1

        # Traverse from B — should also include the review finding exactly once
        result_b = traverse_with_reviews(schema_conn, fact_b)
        review_ids_b = [r.id for r in result_b if isinstance(r, ReviewFinding)]
        assert review_ids_b.count(review_id) == 1

    def test_no_findings_returns_only_causal_facts(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-E1: traverse_with_reviews with no findings returns only CausalFacts."""
        fact_a = _new_id()
        fact_b = _new_id()

        _insert_fact(schema_conn, fact_a, "Cause fact", "test_spec")
        _insert_fact(schema_conn, fact_b, "Effect fact", "test_spec")
        _insert_causal_link(schema_conn, fact_a, fact_b)

        result = traverse_with_reviews(schema_conn, fact_a)

        assert all(isinstance(r, CausalFact) for r in result)
        assert len(result) == 2

    def test_handles_missing_tables_gracefully(self) -> None:
        """TS-42-E2: traverse_with_reviews handles missing tables gracefully."""
        # Create a DB with only memory_facts and fact_causes (no review tables)
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE memory_facts (
                id UUID PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT,
                spec_name TEXT,
                session_id TEXT,
                commit_sha TEXT,
                confidence TEXT DEFAULT 'high',
                created_at TIMESTAMP,
                superseded_by UUID
            )
        """)
        conn.execute("""
            CREATE TABLE fact_causes (
                cause_id UUID,
                effect_id UUID,
                PRIMARY KEY (cause_id, effect_id)
            )
        """)

        fact_id = _new_id()
        conn.execute(
            "INSERT INTO memory_facts (id, content, spec_name, created_at) "
            "VALUES (?::UUID, 'Test fact', 'test_spec', CURRENT_TIMESTAMP)",
            [fact_id],
        )

        # Should return CausalFact objects without error
        result = traverse_with_reviews(conn, fact_id)
        assert len(result) >= 1
        assert all(isinstance(r, CausalFact) for r in result)

        conn.close()


# ---------------------------------------------------------------------------
# TestConfidenceFiltering
# ---------------------------------------------------------------------------


class TestConfidenceFiltering:
    """Tests for confidence-aware fact filtering.

    Requirements: 42-REQ-2.1, 42-REQ-2.3, 42-REQ-2.E1, 42-REQ-2.E2
    """

    @staticmethod
    def _make_fact(
        confidence: float,
        spec_name: str = "test_spec",
        keywords: list[str] | None = None,
    ) -> Fact:
        return Fact(
            id=_new_id(),
            content=f"Fact with confidence {confidence}",
            category="pattern",
            spec_name=spec_name,
            keywords=keywords or ["test"],
            confidence=confidence,
            created_at="2026-01-01T00:00:00+00:00",
        )

    def test_filters_below_threshold(self) -> None:
        """TS-42-6: select_relevant_facts filters below threshold."""
        facts = [
            self._make_fact(0.3),
            self._make_fact(0.5),
            self._make_fact(0.7),
            self._make_fact(0.9),
        ]

        result = select_relevant_facts(
            facts,
            "test_spec",
            ["test"],
            confidence_threshold=0.5,
        )

        # Only facts with confidence >= 0.5 should appear
        confidences = {f.confidence for f in result}
        assert 0.3 not in confidences
        assert len(result) == 3

    def test_threshold_zero_includes_all(self) -> None:
        """TS-42-7: confidence threshold 0.0 includes all facts."""
        facts = [
            self._make_fact(0.0),
            self._make_fact(0.1),
            self._make_fact(0.5),
            self._make_fact(1.0),
        ]

        result = select_relevant_facts(
            facts,
            "test_spec",
            ["test"],
            confidence_threshold=0.0,
        )

        # All four facts should be eligible
        assert len(result) == 4

    def test_threshold_one_includes_only_perfect(self) -> None:
        """TS-42-8: confidence threshold 1.0 includes only perfect confidence."""
        facts = [
            self._make_fact(0.9),
            self._make_fact(0.99),
            self._make_fact(1.0),
        ]

        result = select_relevant_facts(
            facts,
            "test_spec",
            ["test"],
            confidence_threshold=1.0,
        )

        assert len(result) == 1
        assert result[0].confidence == 1.0

    def test_config_confidence_threshold_clamped(self) -> None:
        """TS-42-9: config confidence threshold is clamped to [0.0, 1.0]."""
        # Below range
        config_low = KnowledgeConfig(confidence_threshold=-0.5)
        assert config_low.confidence_threshold == 0.0

        # Above range
        config_high = KnowledgeConfig(confidence_threshold=1.5)
        assert config_high.confidence_threshold == 1.0


# ---------------------------------------------------------------------------
# TestFactCache
# ---------------------------------------------------------------------------


class TestFactCache:
    """Tests for pre-computed fact ranking cache.

    Requirements: 42-REQ-3.1, 42-REQ-3.2, 42-REQ-3.3, 42-REQ-3.E1, 42-REQ-3.E2
    """

    def test_precompute_produces_cache_entries(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-10: precompute_fact_rankings produces cache entries."""
        # Insert 5 facts across 2 specs
        for i in range(3):
            _insert_fact(
                schema_conn,
                _new_id(),
                f"Fact {i} for alpha",
                "alpha",
            )
        for i in range(2):
            _insert_fact(
                schema_conn,
                _new_id(),
                f"Fact {i} for beta",
                "beta",
            )

        cache = precompute_fact_rankings(schema_conn, ["alpha", "beta"])

        assert len(cache) == 2
        assert "alpha" in cache
        assert "beta" in cache

        # Each entry has fact_count_at_creation matching total active count (5)
        assert cache["alpha"].fact_count_at_creation == 5
        assert cache["beta"].fact_count_at_creation == 5

    def test_get_cached_facts_returns_valid(self) -> None:
        """TS-42-11: get_cached_facts returns cached facts when valid."""
        facts = [
            Fact(
                id=_new_id(),
                content="test",
                category="pattern",
                spec_name="alpha",
                keywords=["test"],
                confidence=0.9,
                created_at="2026-01-01T00:00:00+00:00",
            ),
        ]
        cache = {
            "alpha": RankedFactCache(
                spec_name="alpha",
                ranked_facts=facts,
                created_at="2026-01-01T00:00:00+00:00",
                fact_count_at_creation=10,
            ),
        }

        result = get_cached_facts(cache, "alpha", current_fact_count=10)
        assert result is not None
        assert result == facts

    def test_get_cached_facts_returns_none_on_stale(self) -> None:
        """TS-42-12: get_cached_facts returns None on stale cache."""
        cache = {
            "alpha": RankedFactCache(
                spec_name="alpha",
                ranked_facts=[],
                created_at="2026-01-01T00:00:00+00:00",
                fact_count_at_creation=5,
            ),
        }

        result = get_cached_facts(cache, "alpha", current_fact_count=6)
        assert result is None

    def test_get_cached_facts_returns_none_for_missing_spec(self) -> None:
        """TS-42-13: get_cached_facts returns None for missing spec."""
        cache = {
            "alpha": RankedFactCache(
                spec_name="alpha",
                ranked_facts=[],
                created_at="2026-01-01T00:00:00+00:00",
                fact_count_at_creation=5,
            ),
        }

        result = get_cached_facts(cache, "beta", current_fact_count=5)
        assert result is None

    def test_precompute_with_zero_facts(
        self,
        schema_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-42-E3: precompute with zero facts produces empty cache entries."""
        cache = precompute_fact_rankings(schema_conn, ["alpha", "beta"])

        assert len(cache) == 2
        assert cache["alpha"].ranked_facts == []
        assert cache["beta"].ranked_facts == []
        assert cache["alpha"].fact_count_at_creation == 0
        assert cache["beta"].fact_count_at_creation == 0
