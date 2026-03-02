"""Property tests for timeline ordering.

Test Spec: TS-13-P3
Property: Property 5 (timeline ordering)
Requirements: 13-REQ-6.1, 13-REQ-6.2
"""

from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.temporal import build_timeline
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

FACT_IDS = [FACT_AAA, FACT_BBB, FACT_CCC, FACT_DDD, FACT_EEE]


def _make_causal_db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DB with schema and seeded data."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    seed_causal_links(conn)
    return conn


class TestTimelineOrdering:
    """TS-13-P3: Timeline ordering.

    Property 5: Timeline nodes are always ordered by timestamp.
    Validates: 13-REQ-6.1, 13-REQ-6.2
    """

    @given(
        seed_ids=st.lists(
            st.sampled_from(FACT_IDS),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=20, deadline=None)
    def test_timestamps_in_ascending_order(
        self, seed_ids: list[str]
    ) -> None:
        """Timeline nodes have non-decreasing timestamps."""
        conn = _make_causal_db()
        try:
            timeline = build_timeline(conn, seed_ids)
            timestamps = [n.timestamp for n in timeline.nodes if n.timestamp]
            assert timestamps == sorted(timestamps)
        finally:
            conn.close()
