"""Embedding generation using the Anthropic voyage-3 API.

Generates vector embeddings for fact content, enabling semantic
similarity search over the knowledge store.

Requirements: 12-REQ-2.1, 12-REQ-2.2, 12-REQ-2.E1
"""

from __future__ import annotations

import logging

import anthropic  # noqa: F401

from agent_fox.core.config import KnowledgeConfig

logger = logging.getLogger("agent_fox.knowledge.embeddings")


class EmbeddingGenerator:
    """Generates vector embeddings using the Anthropic voyage-3 API.

    Handles API failures gracefully: returns None for individual texts
    that fail to embed, allowing the caller to proceed without an
    embedding.
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        self._config = config
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        """Lazy-initialize the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def embed_text(self, text: str) -> list[float] | None:
        """Generate an embedding for a single text string.

        Returns a list of floats (1024 dimensions for voyage-3) on
        success, or None if the API call fails. Failures are logged
        as warnings, never raised.
        """
        try:
            response = self.client.embeddings.create(  # type: ignore[attr-defined]
                model=self._config.embedding_model,
                input=[text],
            )
            return [float(v) for v in response.data[0].embedding]
        except Exception:
            logger.warning("Embedding failed for text (length=%d)", len(text))
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in a single API call.

        Returns a list parallel to the input: each element is either
        a list of floats or None if that text failed to embed.
        API failures are logged as warnings.
        """
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(  # type: ignore[attr-defined]
                model=self._config.embedding_model,
                input=texts,
            )
            return [
                [float(v) for v in item.embedding]
                for item in response.data
            ]
        except Exception:
            logger.warning(
                "Batch embedding failed for %d texts", len(texts),
            )
            return [None] * len(texts)
