"""Tests for embedding generation.

Test Spec: TS-12-1 (single embed), TS-12-2 (batch embed),
           TS-12-3 (embed failure)
Requirements: 12-REQ-2.1, 12-REQ-2.2, 12-REQ-2.E1
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.embeddings import EmbeddingGenerator

from .conftest import MOCK_EMBEDDING_1, MOCK_EMBEDDING_2, MOCK_EMBEDDING_3


def _make_mock_embedding_response(embeddings: list[list[float]]) -> MagicMock:
    """Create a mock Anthropic embeddings API response."""
    mock_response = MagicMock()
    mock_data = []
    for emb in embeddings:
        item = MagicMock()
        item.embedding = emb
        mock_data.append(item)
    mock_response.data = mock_data
    return mock_response


def _make_generator_with_mock_client(
    config: KnowledgeConfig,
) -> tuple[EmbeddingGenerator, MagicMock]:
    """Create an EmbeddingGenerator with a pre-set mock client."""
    generator = EmbeddingGenerator(config)
    mock_client = MagicMock()
    generator._client = mock_client
    return generator, mock_client


class TestEmbedSingleText:
    """TS-12-1: Embed single text returns 1024-dim vector.

    Requirement: 12-REQ-2.1
    """

    def test_returns_1024_dim_vector(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_text returns a 1024-dimensional float vector."""
        mock_response = _make_mock_embedding_response([MOCK_EMBEDDING_1])

        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.return_value = mock_response

        result = generator.embed_text(
            "DuckDB was chosen for its columnar analytics capabilities"
        )

        assert result is not None
        assert len(result) == 1024
        assert all(isinstance(v, float) for v in result)

    def test_calls_anthropic_with_correct_model(
        self, knowledge_config: KnowledgeConfig
    ) -> None:
        """Verify the correct embedding model is passed to the API."""
        mock_response = _make_mock_embedding_response([MOCK_EMBEDDING_1])

        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.return_value = mock_response

        generator.embed_text("some text")

        mock_client.embeddings.create.assert_called_once()
        call_kwargs = mock_client.embeddings.create.call_args
        assert knowledge_config.embedding_model in str(call_kwargs)


class TestEmbedBatch:
    """TS-12-2: Embed batch returns parallel list of vectors.

    Requirement: 12-REQ-2.2
    """

    def test_returns_parallel_list(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_batch returns one embedding per input text."""
        mock_response = _make_mock_embedding_response(
            [MOCK_EMBEDDING_1, MOCK_EMBEDDING_2, MOCK_EMBEDDING_3]
        )

        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.return_value = mock_response

        results = generator.embed_batch(["fact one", "fact two", "fact three"])

        assert len(results) == 3
        for result in results:
            assert result is not None
            assert len(result) == 1024

    def test_single_api_call_for_batch(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify batch uses a single API call, not one per text."""
        mock_response = _make_mock_embedding_response(
            [MOCK_EMBEDDING_1, MOCK_EMBEDDING_2]
        )

        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.return_value = mock_response

        generator.embed_batch(["text a", "text b"])

        assert mock_client.embeddings.create.call_count == 1


class TestEmbedFailure:
    """TS-12-3: Embed failure returns None.

    Requirement: 12-REQ-2.E1
    """

    def test_returns_none_on_api_error(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_text returns None when the API raises an error."""
        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.side_effect = Exception("rate limited")

        result = generator.embed_text("some text")

        assert result is None

    def test_logs_warning_on_failure(
        self, knowledge_config: KnowledgeConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify a warning is logged when embedding fails."""
        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.side_effect = Exception("rate limited")

        with caplog.at_level(logging.WARNING):
            generator.embed_text("some text")

        assert "embedding" in caplog.text.lower() or "failed" in caplog.text.lower()

    def test_does_not_raise(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify no exception propagates to the caller."""
        generator, mock_client = _make_generator_with_mock_client(knowledge_config)
        mock_client.embeddings.create.side_effect = Exception("network error")

        # Should not raise
        result = generator.embed_text("some text")
        assert result is None
