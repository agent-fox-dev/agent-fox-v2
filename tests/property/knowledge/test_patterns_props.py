"""Property tests for pattern detection.

Test Spec: TS-13-P4
Property: Property 6 (pattern minimum threshold)
Requirements: 13-REQ-5.1, 13-REQ-5.2
"""

from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.patterns import detect_patterns
from tests.unit.knowledge.conftest import (
    create_schema,
    seed_causal_links,
    seed_facts,
    seed_session_outcomes,
)


def _make_causal_db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DB with schema and seeded data."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    seed_causal_links(conn)
    seed_session_outcomes(conn)
    return conn


class TestPatternMinimumThreshold:
    """TS-13-P4: Pattern minimum threshold.

    Property 6: Every detected pattern meets the minimum occurrence threshold.
    Validates: 13-REQ-5.1, 13-REQ-5.2
    """

    @given(
        min_occ=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=10, deadline=None)
    def test_all_patterns_meet_threshold(self, min_occ: int) -> None:
        """All returned patterns have occurrences >= min_occurrences."""
        conn = _make_causal_db()
        try:
            patterns = detect_patterns(conn, min_occurrences=min_occ)
            for p in patterns:
                assert p.occurrences >= min_occ
        finally:
            conn.close()
