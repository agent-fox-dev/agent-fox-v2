"""Property tests for context budget compliance.

Test Spec: TS-13-P5
Property: Property 7 (context budget compliance)
Requirements: 13-REQ-7.2
"""

from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.session.prompt import select_context_with_causal
from tests.unit.knowledge.conftest import (
    create_schema,
    seed_causal_links,
    seed_facts,
)


def _make_causal_db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DB with schema and seeded data."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    seed_causal_links(conn)
    return conn


class TestContextBudgetCompliance:
    """TS-13-P5: Context budget compliance.

    Property 7: Context selection never exceeds the max_facts budget.
    Validates: 13-REQ-7.2
    """

    @given(
        max_facts=st.integers(min_value=1, max_value=100),
        n_keywords=st.integers(min_value=0, max_value=200),
    )
    @settings(max_examples=20, deadline=None)
    def test_never_exceeds_budget(self, max_facts: int, n_keywords: int) -> None:
        """Result length never exceeds max_facts."""
        conn = _make_causal_db()
        try:
            keyword_facts = [
                {
                    "id": f"kw_{i:08d}-0000-0000-0000-000000000000",
                    "content": f"keyword fact {i}",
                }
                for i in range(n_keywords)
            ]
            result = select_context_with_causal(
                conn,
                "test_spec",
                [],
                keyword_facts=keyword_facts,
                max_facts=max_facts,
            )
            assert len(result) <= max_facts
        finally:
            conn.close()
