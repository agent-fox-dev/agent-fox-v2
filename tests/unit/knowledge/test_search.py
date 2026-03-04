"""Tests for vector similarity search.

Test Spec: TS-12-4 (sorted results), TS-12-5 (excludes unembedded),
           TS-12-6 (excludes superseded), TS-12-7 (empty store),
           TS-12-18 (has_embeddings)
Requirements: 12-REQ-3.1, 12-REQ-3.2, 12-REQ-3.3, 12-REQ-3.E1,
              12-REQ-5.E1, 12-REQ-7.2
"""

from __future__ import annotations

import duckdb

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.search import SearchResult, VectorSearch

from .conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    FACT_DDD,
    FACT_EEE,
    MOCK_EMBEDDING_1,
    MOCK_EMBEDDING_2,
    MOCK_EMBEDDING_3,
    MOCK_EMBEDDING_4,
    MOCK_EMBEDDING_5,
    MOCK_QUERY_EMBEDDING,
    insert_fact_with_embedding,
    insert_fact_without_embedding,
)


class TestVectorSearchSortedResults:
    """TS-12-4: Vector search returns results sorted by similarity.

    Requirements: 12-REQ-3.1, 12-REQ-3.2
    """

    def test_results_sorted_descending(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify results are sorted by descending cosine similarity."""
        # Insert 5 facts with different embeddings
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Fact about DuckDB",
            MOCK_EMBEDDING_1,
            spec_name="11_duckdb",
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_BBB,
            "Fact about embeddings",
            MOCK_EMBEDDING_2,
            spec_name="12_fox_ball",
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_CCC,
            "Fact about JSONL",
            MOCK_EMBEDDING_3,
            spec_name="05_memory",
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_DDD,
            "Fact about testing",
            MOCK_EMBEDDING_4,
            spec_name="10_testing",
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_EEE,
            "Fact about auth",
            MOCK_EMBEDDING_5,
            spec_name="07_auth",
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=3)

        assert len(results) == 3
        assert results[0].similarity >= results[1].similarity
        assert results[1].similarity >= results[2].similarity

    def test_results_have_required_fields(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify each result has fact_id, content, spec_name, and similarity."""
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Test fact content",
            MOCK_EMBEDDING_1,
            spec_name="test_spec",
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=5)

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        assert result.fact_id != ""
        assert result.content != ""
        assert result.spec_name != ""
        assert isinstance(result.similarity, float)

    def test_respects_top_k_limit(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify search respects the top_k parameter."""
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Fact 1",
            MOCK_EMBEDDING_1,
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_BBB,
            "Fact 2",
            MOCK_EMBEDDING_2,
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_CCC,
            "Fact 3",
            MOCK_EMBEDDING_3,
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=2)

        assert len(results) == 2


class TestVectorSearchExcludesUnembedded:
    """TS-12-5: Vector search excludes facts without embeddings.

    Requirement: 12-REQ-3.3
    """

    def test_unembedded_fact_excluded(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify facts without embeddings are not in search results."""
        # 2 facts with embeddings
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Embedded fact 1",
            MOCK_EMBEDDING_1,
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_BBB,
            "Embedded fact 2",
            MOCK_EMBEDDING_2,
        )
        # 1 fact without embedding
        insert_fact_without_embedding(
            schema_conn,
            FACT_CCC,
            "Unembedded fact",
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=10)

        assert len(results) == 2
        fact_ids = {r.fact_id for r in results}
        assert FACT_CCC not in fact_ids


class TestVectorSearchExcludesSuperseded:
    """TS-12-6: Vector search excludes superseded facts.

    Requirement: 12-REQ-7.2
    """

    def test_superseded_fact_excluded(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify facts with superseded_by set are excluded from default search."""
        # Old fact (superseded by CCC)
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Old: we use SQLite",
            MOCK_EMBEDDING_1,
            superseded_by=FACT_CCC,
        )
        # Non-superseded facts
        insert_fact_with_embedding(
            schema_conn,
            FACT_BBB,
            "Embeddings are 1024-dim",
            MOCK_EMBEDDING_2,
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_CCC,
            "New: we use DuckDB",
            MOCK_EMBEDDING_3,
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(
            MOCK_QUERY_EMBEDDING, top_k=10, exclude_superseded=True
        )

        fact_ids = {r.fact_id for r in results}
        assert FACT_AAA not in fact_ids  # superseded
        assert FACT_CCC in fact_ids  # superseding fact present

    def test_superseded_included_when_disabled(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify superseded facts are included when exclude_superseded=False."""
        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Old: we use SQLite",
            MOCK_EMBEDDING_1,
            superseded_by=FACT_CCC,
        )
        insert_fact_with_embedding(
            schema_conn,
            FACT_CCC,
            "New: we use DuckDB",
            MOCK_EMBEDDING_3,
        )

        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(
            MOCK_QUERY_EMBEDDING, top_k=10, exclude_superseded=False
        )

        fact_ids = {r.fact_id for r in results}
        assert FACT_AAA in fact_ids  # should be included


class TestVectorSearchEmptyStore:
    """TS-12-7: Vector search returns empty for no embedded facts.

    Requirement: 12-REQ-3.E1
    """

    def test_empty_store_returns_empty_list(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify search returns empty list with no embedded facts."""
        searcher = VectorSearch(schema_conn, knowledge_config)
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=20)
        assert results == []

    def test_no_exception_on_empty_store(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify no exception is raised for empty store."""
        searcher = VectorSearch(schema_conn, knowledge_config)
        # Should not raise
        results = searcher.search(MOCK_QUERY_EMBEDDING, top_k=20)
        assert isinstance(results, list)


class TestHasEmbeddings:
    """TS-12-18: has_embeddings returns correct state.

    Requirement: 12-REQ-5.E1
    """

    def test_returns_false_for_empty_store(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify has_embeddings returns False with no embedded facts."""
        searcher = VectorSearch(schema_conn, knowledge_config)
        assert searcher.has_embeddings() is False

    def test_returns_true_after_inserting_embedding(
        self, schema_conn: duckdb.DuckDBPyConnection, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify has_embeddings returns True after inserting a fact with embedding."""
        searcher = VectorSearch(schema_conn, knowledge_config)
        assert searcher.has_embeddings() is False

        insert_fact_with_embedding(
            schema_conn,
            FACT_AAA,
            "Test fact",
            MOCK_EMBEDDING_1,
        )
        assert searcher.has_embeddings() is True
