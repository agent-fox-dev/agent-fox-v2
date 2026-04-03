"""Tests for embedding generation.

Test Spec: TS-12-1 (single embed), TS-12-2 (batch embed),
           TS-12-3 (embed failure)
Requirements: 12-REQ-2.1, 12-REQ-2.2, 12-REQ-2.E1
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import numpy as np
import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.embeddings import EmbeddingGenerator

from .conftest import MOCK_EMBEDDING_1, MOCK_EMBEDDING_2, MOCK_EMBEDDING_3


def _make_generator_with_mock_model(
    config: KnowledgeConfig,
) -> tuple[EmbeddingGenerator, MagicMock]:
    """Create an EmbeddingGenerator with a pre-set mock model."""
    generator = EmbeddingGenerator(config)
    mock_model = MagicMock()
    generator._model = mock_model
    return generator, mock_model


class TestEmbedSingleText:
    """TS-12-1: Embed single text returns 384-dim vector.

    Requirement: 12-REQ-2.1
    """

    def test_returns_384_dim_vector(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_text returns a 384-dimensional float vector."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.return_value = np.array([MOCK_EMBEDDING_1])

        result = generator.embed_text("DuckDB was chosen for its columnar analytics capabilities")

        assert result is not None
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_calls_model_encode(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify the model's encode method is called."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.return_value = np.array([MOCK_EMBEDDING_1])

        generator.embed_text("some text")

        mock_model.encode.assert_called_once_with(["some text"])


class TestEmbedBatch:
    """TS-12-2: Embed batch returns parallel list of vectors.

    Requirement: 12-REQ-2.2
    """

    def test_returns_parallel_list(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_batch returns one embedding per input text."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.return_value = np.array([MOCK_EMBEDDING_1, MOCK_EMBEDDING_2, MOCK_EMBEDDING_3])

        results = generator.embed_batch(["fact one", "fact two", "fact three"])

        assert len(results) == 3
        for result in results:
            assert result is not None
            assert len(result) == 384

    def test_single_encode_call_for_batch(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify batch uses a single encode call, not one per text."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.return_value = np.array([MOCK_EMBEDDING_1, MOCK_EMBEDDING_2])

        generator.embed_batch(["text a", "text b"])

        assert mock_model.encode.call_count == 1


class TestEmbedFailure:
    """TS-12-3: Embed failure returns None.

    Requirement: 12-REQ-2.E1
    """

    def test_returns_none_on_error(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embed_text returns None when encoding raises an error."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.side_effect = Exception("model load failed")

        result = generator.embed_text("some text")

        assert result is None

    def test_logs_warning_on_failure(self, knowledge_config: KnowledgeConfig, caplog: pytest.LogCaptureFixture) -> None:
        """Verify a warning is logged when embedding fails."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.side_effect = Exception("model load failed")

        with caplog.at_level(logging.WARNING):
            generator.embed_text("some text")

        assert "embedding" in caplog.text.lower() or "failed" in caplog.text.lower()

    def test_does_not_raise(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify no exception propagates to the caller."""
        generator, mock_model = _make_generator_with_mock_model(knowledge_config)
        mock_model.encode.side_effect = Exception("runtime error")

        # Should not raise
        result = generator.embed_text("some text")
        assert result is None


class TestEmbeddingDimensions:
    """Verify embedding_dimensions property."""

    def test_returns_config_dimensions(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify embedding_dimensions matches config."""
        generator = EmbeddingGenerator(knowledge_config)
        assert generator.embedding_dimensions == 384
