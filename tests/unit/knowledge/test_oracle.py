"""Tests for the Oracle RAG pipeline.

Test Spec: TS-12-11 (grounded answer), TS-12-12 (single API call),
           TS-12-13 (contradiction detection), TS-12-E3 (embed failure),
           TS-12-E5 (confidence levels)
Requirements: 12-REQ-5.1, 12-REQ-5.2, 12-REQ-5.3, 12-REQ-6.1,
              12-REQ-8.1, 12-REQ-2.E2
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.query import Oracle, OracleAnswer
from agent_fox.knowledge.search import SearchResult, VectorSearch

from .conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    MOCK_QUERY_EMBEDDING,
)


def _make_search_results(
    *, count: int = 3, similarity: float = 0.8
) -> list[SearchResult]:
    """Create mock search results."""
    fact_ids = [FACT_AAA, FACT_BBB, FACT_CCC]
    contents = [
        "DuckDB was chosen for columnar analytics",
        "Embeddings use voyage-3 at 1024 dimensions",
        "JSONL is the source of truth for facts",
    ]
    results = []
    for i in range(min(count, 3)):
        results.append(
            SearchResult(
                fact_id=fact_ids[i],
                content=contents[i],
                category="decision",
                spec_name=f"spec_{i}",
                session_id=f"session/{i}",
                commit_sha=f"sha{i}",
                similarity=similarity - (i * 0.05),
            )
        )
    return results


def _make_mock_synthesis_response(text: str) -> MagicMock:
    """Create a mock Anthropic messages.create response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


class TestOracleGroundedAnswer:
    """TS-12-11: Oracle returns grounded answer with sources.

    Requirements: 12-REQ-5.1, 12-REQ-5.2
    """

    def test_returns_oracle_answer(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify the oracle pipeline returns an OracleAnswer."""
        mock_search = MagicMock(spec=VectorSearch)
        search_results = _make_search_results()
        mock_search.search.return_value = search_results

        mock_embedder.embed_text.return_value = MOCK_QUERY_EMBEDDING

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        mock_response = _make_mock_synthesis_response(
            "DuckDB was chosen because of its columnar storage capabilities."
        )
        with patch.object(
            type(oracle), "client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            answer = oracle.ask("why did we choose DuckDB?")

        assert isinstance(answer, OracleAnswer)
        assert answer.answer != ""
        assert len(answer.sources) == 3
        assert answer.confidence in ["high", "medium", "low"]

    def test_sources_have_provenance(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify sources include provenance metadata."""
        mock_search = MagicMock(spec=VectorSearch)
        search_results = _make_search_results()
        mock_search.search.return_value = search_results

        mock_embedder.embed_text.return_value = MOCK_QUERY_EMBEDDING

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        mock_response = _make_mock_synthesis_response("DuckDB was chosen...")
        with patch.object(
            type(oracle), "client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            answer = oracle.ask("why did we choose DuckDB?")

        for source in answer.sources:
            assert source.spec_name is not None
            assert source.fact_id != ""


class TestOracleSingleAPICall:
    """TS-12-12: Oracle uses single API call (not streaming).

    Requirement: 12-REQ-5.3
    """

    def test_uses_messages_create(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify client.messages.create is called exactly once."""
        mock_search = MagicMock(spec=VectorSearch)
        mock_search.search.return_value = _make_search_results()
        mock_embedder.embed_text.return_value = MOCK_QUERY_EMBEDDING

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        mock_response = _make_mock_synthesis_response("Answer text")
        with patch.object(
            type(oracle), "client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            oracle.ask("any question")

            assert mock_client.messages.create.call_count == 1

    def test_does_not_use_stream(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify client.messages.stream is never called."""
        mock_search = MagicMock(spec=VectorSearch)
        mock_search.search.return_value = _make_search_results()
        mock_embedder.embed_text.return_value = MOCK_QUERY_EMBEDDING

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        mock_response = _make_mock_synthesis_response("Answer text")
        with patch.object(
            type(oracle), "client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            oracle.ask("any question")

            mock_client.messages.stream.assert_not_called()


class TestOracleContradictionDetection:
    """TS-12-13: Oracle flags contradictions.

    Requirement: 12-REQ-6.1
    """

    def test_detects_contradictions(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify contradictions are flagged when synthesis detects them."""
        # Create search results with conflicting info
        contradicting_results = [
            SearchResult(
                fact_id=FACT_AAA,
                content="We use SQLite for storage",
                category="decision",
                spec_name="old_spec",
                session_id="1/1",
                commit_sha="old_sha",
                similarity=0.85,
            ),
            SearchResult(
                fact_id=FACT_BBB,
                content="We use DuckDB for storage",
                category="decision",
                spec_name="new_spec",
                session_id="2/1",
                commit_sha="new_sha",
                similarity=0.82,
            ),
        ]

        mock_search = MagicMock(spec=VectorSearch)
        mock_search.search.return_value = contradicting_results
        mock_embedder.embed_text.return_value = MOCK_QUERY_EMBEDDING

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        # Synthesis response includes contradiction flag
        contradiction_response = (
            "The project has conflicting information about the database. "
            "CONTRADICTION: Fact A says SQLite while Fact B says DuckDB."
        )
        mock_response = _make_mock_synthesis_response(contradiction_response)
        with patch.object(
            type(oracle), "client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            answer = oracle.ask("what database do we use?")

        assert answer.contradictions is not None
        assert len(answer.contradictions) > 0


class TestOracleEmbedFailure:
    """TS-12-E3: Embedding API failure on ask query.

    Requirement: 12-REQ-2.E2
    """

    def test_raises_knowledge_store_error(
        self,
        knowledge_config: KnowledgeConfig,
    ) -> None:
        """Verify KnowledgeStoreError raised when query embedding fails."""
        mock_embedder = MagicMock(spec=EmbeddingGenerator)
        mock_embedder.embed_text.return_value = None  # embedding failure

        mock_search = MagicMock(spec=VectorSearch)

        oracle = Oracle(mock_embedder, mock_search, knowledge_config)
        with pytest.raises(KnowledgeStoreError) as exc_info:
            oracle.ask("any question")

        error_msg = str(exc_info.value).lower()
        assert "retry" in error_msg or "embedding" in error_msg


class TestOracleConfidenceLevels:
    """TS-12-E5: Confidence levels based on result quality.

    Requirement: 12-REQ-8.1
    """

    def test_high_confidence(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify high confidence for 3+ results with similarity > 0.7."""
        mock_search = MagicMock(spec=VectorSearch)
        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        results_high = _make_search_results(count=3, similarity=0.85)
        assert oracle._determine_confidence(results_high) == "high"

    def test_medium_confidence(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify medium confidence for 1-2 results with similarity > 0.5."""
        mock_search = MagicMock(spec=VectorSearch)
        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        results_med = [
            SearchResult(
                fact_id=FACT_AAA,
                content="Some fact",
                category="decision",
                spec_name="spec",
                session_id="1/1",
                commit_sha="sha",
                similarity=0.6,
            )
        ]
        assert oracle._determine_confidence(results_med) == "medium"

    def test_low_confidence(
        self,
        knowledge_config: KnowledgeConfig,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify low confidence for no results."""
        mock_search = MagicMock(spec=VectorSearch)
        oracle = Oracle(mock_embedder, mock_search, knowledge_config)

        assert oracle._determine_confidence([]) == "low"
