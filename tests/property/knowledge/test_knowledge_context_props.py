"""Property tests for knowledge context improvements (spec 42).

Test Spec: TS-42-P1 through TS-42-P4
Requirements: 42-REQ-1.3, 42-REQ-2.1, 42-REQ-3.3, 42-REQ-4.1
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.engine.fact_cache import (
    RankedFactCache,
    get_cached_facts,
)
from agent_fox.knowledge.causal import CausalFact, traverse_with_reviews
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.filtering import select_relevant_facts
from tests.unit.knowledge.conftest import create_schema


def _new_id() -> str:
    return str(uuid.uuid4())


def _make_fact(confidence: float, spec_name: str = "test_spec") -> Fact:
    return Fact(
        id=_new_id(),
        content=f"Fact with confidence {confidence}",
        category="pattern",
        spec_name=spec_name,
        keywords=["test", "knowledge"],
        confidence=confidence,
        created_at="2026-01-01T00:00:00+00:00",
    )


class TestConfidenceMonotonicity:
    """TS-42-P1: Increasing threshold can only reduce selected facts.

    Requirements: 42-REQ-2.1, 42-REQ-2.E1
    """

    @given(
        confidences=st.lists(
            st.floats(min_value=0.0, max_value=1.0),
            min_size=1,
            max_size=20,
        ),
        t1=st.floats(min_value=0.0, max_value=1.0),
        t2=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=100)
    def test_monotonicity(
        self,
        confidences: list[float],
        t1: float,
        t2: float,
    ) -> None:
        assume(t1 <= t2)

        facts = [_make_fact(c) for c in confidences]

        result_t1 = select_relevant_facts(
            facts,
            "test_spec",
            ["test"],
            confidence_threshold=t1,
        )
        result_t2 = select_relevant_facts(
            facts,
            "test_spec",
            ["test"],
            confidence_threshold=t2,
        )

        assert len(result_t2) <= len(result_t1)


class TestDeduplicationInvariant:
    """TS-42-P2: No id appears more than once in traversal results.

    Requirements: 42-REQ-1.3
    """

    @given(
        num_facts=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20)
    def test_no_duplicate_ids(self, num_facts: int) -> None:
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        fact_ids = [_new_id() for _ in range(num_facts)]

        for fid in fact_ids:
            conn.execute(
                "INSERT INTO memory_facts (id, content, category, spec_name, "
                "confidence, created_at) "
                "VALUES (?::UUID, 'test content', 'pattern', 'test_spec', "
                "0.9, CURRENT_TIMESTAMP)",
                [fid],
            )

        # Create a chain: fact_0 -> fact_1 -> ... -> fact_n
        for i in range(len(fact_ids) - 1):
            conn.execute(
                "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?::UUID, ?::UUID)",
                [fact_ids[i], fact_ids[i + 1]],
            )

        # Add a review finding for the spec
        review_id = _new_id()
        conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, spec_name, "
            "task_group, session_id, created_at) "
            "VALUES (?::UUID, 'major', 'Test finding', NULL, 'test_spec', "
            "'1', 'test-session', CURRENT_TIMESTAMP)",
            [review_id],
        )

        # Traverse from each fact and check deduplication
        for fid in fact_ids:
            result = traverse_with_reviews(conn, fid)
            ids = []
            for item in result:
                if isinstance(item, CausalFact):
                    ids.append(item.fact_id)
                elif hasattr(item, "id"):
                    ids.append(item.id)

            assert len(ids) == len(set(ids)), f"Duplicate IDs found in traversal from {fid}"

        conn.close()


class TestGroupBoundaryInvariant:
    """TS-42-P3: Prior group findings never include findings from group K or later.

    Requirements: 42-REQ-4.1
    """

    @given(
        n_groups=st.integers(min_value=2, max_value=8),
        target_group=st.integers(min_value=2, max_value=8),
    )
    @settings(max_examples=50)
    def test_boundary(self, n_groups: int, target_group: int) -> None:
        assume(target_group <= n_groups)

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        # Insert a review finding for each group
        for g in range(1, n_groups + 1):
            conn.execute(
                "INSERT INTO review_findings "
                "(id, severity, description, requirement_ref, spec_name, "
                "task_group, session_id, created_at) "
                "VALUES (?::UUID, 'major', ?, NULL, 'test_spec', "
                "?, 'test-session', CURRENT_TIMESTAMP)",
                [_new_id(), f"Finding from group {g}", str(g)],
            )

        from agent_fox.session.prompt import get_prior_group_findings

        result = get_prior_group_findings(
            conn,
            "test_spec",
            task_group=target_group,
        )

        for r in result:
            group_val = r.group if hasattr(r, "group") else r.task_group  # type: ignore[attr-defined]
            assert int(group_val) < target_group, f"Finding from group {group_val} included for target {target_group}"

        conn.close()


class TestCacheStalenessDetection:
    """TS-42-P4: Cache respects tolerance-based staleness detection.

    Requirements: 42-REQ-3.3

    Updated for fix-issue-273: invalidation uses a 10% tolerance window
    instead of exact count matching.
    """

    _DEFAULT_TOLERANCE = 0.1

    @given(
        cache_count=st.integers(min_value=0, max_value=100),
        query_count=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=100)
    def test_staleness(self, cache_count: int, query_count: int) -> None:
        cache = {
            "test_spec": RankedFactCache(
                spec_name="test_spec",
                ranked_facts=[],
                created_at="2026-01-01T00:00:00+00:00",
                fact_count_at_creation=cache_count,
            ),
        }

        result = get_cached_facts(cache, "test_spec", current_fact_count=query_count)

        # Determine expected outcome based on tolerance logic that mirrors the
        # implementation: drift = |query - cache| / cache; stale if drift > tol.
        if cache_count == 0:
            expected_hit = query_count == 0
        else:
            drift = abs(query_count - cache_count) / cache_count
            expected_hit = drift <= self._DEFAULT_TOLERANCE

        if expected_hit:
            assert result is not None
        else:
            assert result is None
