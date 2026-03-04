"""Property tests for causal graph traversal.

Test Spec: TS-13-P2
Property: Property 3 (traversal depth bound)
Requirements: 13-REQ-3.4
"""

from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.causal import traverse_causal_chain
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
    def test_no_fact_exceeds_max_depth(self, fact_id: str, max_depth: int) -> None:
        """All returned facts have abs(depth) <= max_depth."""
        conn = _make_causal_db()
        try:
            chain = traverse_causal_chain(conn, fact_id, max_depth=max_depth)
            for fact in chain:
                assert abs(fact.depth) <= max_depth
        finally:
            conn.close()
