"""Tests for store_causal_links in causal.py.

Requirements: 13-REQ-3.1, 13-REQ-3.E1
"""

from __future__ import annotations

from collections.abc import Generator

import duckdb
import pytest

from agent_fox.knowledge.causal import store_causal_links

from .conftest import create_schema, seed_facts


@pytest.fixture
def db_with_facts() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    seed_facts(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


class TestStoreCausalLinks:
    """Verify causal link insertion."""

    def test_inserts_links(self, db_with_facts: duckdb.DuckDBPyConnection) -> None:
        from .conftest import FACT_AAA, FACT_DDD

        links = [(FACT_AAA, FACT_DDD)]
        inserted = store_causal_links(db_with_facts, links)
        assert inserted == 1

        rows = db_with_facts.execute(
            "SELECT * FROM fact_causes WHERE cause_id = ?",
            [FACT_AAA],
        ).fetchall()
        assert len(rows) >= 1

    def test_idempotent_insert(self, db_with_facts: duckdb.DuckDBPyConnection) -> None:
        from .conftest import FACT_AAA, FACT_DDD

        links = [(FACT_AAA, FACT_DDD)]
        store_causal_links(db_with_facts, links)
        # Second insert should not raise
        inserted = store_causal_links(db_with_facts, links)
        assert inserted == 1  # idempotent, counted but no duplicate

    def test_empty_links(self, db_with_facts: duckdb.DuckDBPyConnection) -> None:
        inserted = store_causal_links(db_with_facts, [])
        assert inserted == 0
