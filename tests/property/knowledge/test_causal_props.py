"""Property tests for causal graph operations.

Test Spec: TS-13-P1, TS-13-P2, TS-13-P6
Properties: Property 1 (referential integrity), Property 2 (idempotency),
            Property 3 (traversal depth bound)
Requirements: 13-REQ-3.1, 13-REQ-3.4, 13-REQ-3.E1, 13-REQ-2.E2
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.causal import (
    add_causal_link,
    traverse_causal_chain,
)
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    FACT_DDD,
    FACT_EEE,
    create_schema,
    seed_causal_links,
    seed_facts,
)

# Strategy: choose from seeded fact IDs
FACT_IDS = [FACT_AAA, FACT_BBB, FACT_CCC, FACT_DDD, FACT_EEE]
fact_id_strategy = st.sampled_from(FACT_IDS)


def _make_causal_db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DB with schema and seeded data."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    seed_causal_links(conn)
    return conn


class TestCausalLinkIdempotency:
    """TS-13-P1: Causal link idempotency.

    Property 2: Inserting the same causal link twice results in exactly one row.
    Validates: 13-REQ-3.E1
    """

    @given(
        cause_id=fact_id_strategy,
        effect_id=fact_id_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_double_insert_yields_one_row(
        self, cause_id: str, effect_id: str
    ) -> None:
        """Inserting a link twice results in at most one row."""
        conn = _make_causal_db()
        try:
            add_causal_link(conn, cause_id, effect_id)
            add_causal_link(conn, cause_id, effect_id)
            count = conn.execute(
                "SELECT COUNT(*) FROM fact_causes WHERE cause_id=? AND effect_id=?",
                [cause_id, effect_id],
            ).fetchone()
            assert count is not None
            assert count[0] == 1
        finally:
            conn.close()


class TestTraversalDepthBound:
    """TS-13-P2: Traversal depth bound.

    Property 3: No fact in a traversal result exceeds the configured max depth.
    Validates: 13-REQ-3.4
    """

    @given(
        fact_id=fact_id_strategy,
        max_depth=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30, deadline=None)
    def test_no_fact_exceeds_max_depth(
        self, fact_id: str, max_depth: int
    ) -> None:
        """All returned facts have abs(depth) <= max_depth."""
        conn = _make_causal_db()
        try:
            chain = traverse_causal_chain(conn, fact_id, max_depth=max_depth)
            for fact in chain:
                assert abs(fact.depth) <= max_depth
        finally:
            conn.close()


class TestReferentialIntegrityOnInsert:
    """TS-13-P6: Referential integrity on insert.

    Property 1: Causal links are only inserted when both fact IDs exist.
    Validates: 13-REQ-3.1, 13-REQ-2.E2
    """

    @given(data=st.data())
    @settings(max_examples=20, deadline=None)
    def test_nonexistent_id_rejected(self, data: st.DataObject) -> None:
        """A link with a non-existent ID is always rejected."""
        conn = _make_causal_db()
        try:
            nonexistent_id = str(uuid.uuid4())
            # Test with non-existent cause
            existing_id = data.draw(fact_id_strategy)
            result = add_causal_link(conn, nonexistent_id, existing_id)
            assert result is False

            # Test with non-existent effect
            result = add_causal_link(conn, existing_id, nonexistent_id)
            assert result is False
        finally:
            conn.close()
