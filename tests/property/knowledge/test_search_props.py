"""Property tests for search result ordering.

Test Spec: TS-12-P3 (search result ordering)
Property: Property 3 from design.md
Requirement: 12-REQ-3.1
"""

from __future__ import annotations

import math
import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.search import VectorSearch

# -- Helpers -----------------------------------------------------------------


def _fresh_schema_conn() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with schema."""
    from tests.unit.knowledge.conftest import create_schema

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return conn


def _make_embedding(seed: int, dim: int = 1024) -> list[float]:
    """Create a deterministic normalized embedding vector."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw] if norm > 0 else [1.0 / math.sqrt(dim)] * dim


def _insert_fact_with_embedding(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    content: str,
    embedding: list[float],
) -> None:
    """Insert a fact and embedding into the test database."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name,
                                  confidence, created_at)
        VALUES (?, ?, 'decision', 'test', 'high', CURRENT_TIMESTAMP)
        """,
        [fact_id, content],
    )
    conn.execute(
        "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[1024])",
        [fact_id, embedding],
    )


# -- Property Tests ----------------------------------------------------------


class TestSearchResultOrdering:
    """TS-12-P3: Search result ordering.

    Property 3: For any vector search with k results, the returned list
    is sorted in descending order of similarity score.

    Requirement: 12-REQ-3.1
    """

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=10, deadline=None)
    def test_results_sorted_descending(self, n: int) -> None:
        """For N embedded facts, search results are sorted by descending similarity."""
        conn = _fresh_schema_conn()
        config = KnowledgeConfig()

        # Insert N facts with different embeddings
        for i in range(n):
            fact_id = str(uuid.uuid4())
            embedding = _make_embedding(i + 1)
            _insert_fact_with_embedding(conn, fact_id, f"Fact number {i}", embedding)

        # Search with a query vector
        query_vec = _make_embedding(42)
        searcher = VectorSearch(conn, config)
        results = searcher.search(query_vec, top_k=n)

        # Assert ordering
        for i in range(len(results) - 1):
            assert results[i].similarity >= results[i + 1].similarity, (
                f"Result {i} (sim={results[i].similarity}) < "
                f"Result {i + 1} (sim={results[i + 1].similarity})"
            )

        conn.close()
