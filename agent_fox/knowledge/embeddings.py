"""Local embedding generation using sentence-transformers.

Generates vector embeddings locally (no API call required), enabling
semantic similarity search over the knowledge store. The model is
lazy-loaded on first use and runs efficiently on Apple Silicon.

Requirements: 12-REQ-2.1, 12-REQ-2.2, 12-REQ-2.E1
"""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from agent_fox.core.config import KnowledgeConfig

logger = logging.getLogger("agent_fox.knowledge.embeddings")


class EmbeddingGenerator:
    """Generates vector embeddings using a local sentence-transformers model.

    The model is lazy-loaded on first use. Failures are handled
    gracefully: returns None for individual texts that fail to embed,
    allowing the caller to proceed without an embedding.
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        self._config = config
        self._model: SentenceTransformer | None = None

    @property
    def embedding_dimensions(self) -> int:
        """Return the configured embedding dimensions."""
        return self._config.embedding_dimensions

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            import transformers.utils.logging as tf_logging

            # Suppress the "Loading weights" tqdm bar and
            # "LOAD REPORT" warning emitted by transformers during model load.
            tf_logging.disable_progress_bar()
            prev_level = tf_logging.get_verbosity()
            tf_logging.set_verbosity_error()
            # Suppress "unauthenticated requests" warning from huggingface_hub.
            hf_logger = logging.getLogger("huggingface_hub.utils._headers")
            prev_hf_level = hf_logger.level
            hf_logger.setLevel(logging.ERROR)
            try:
                self._model = SentenceTransformer(self._config.embedding_model)
            finally:
                tf_logging.set_verbosity(prev_level)
                tf_logging.enable_progress_bar()
                hf_logger.setLevel(prev_hf_level)
        return self._model

    def embed_text(self, text: str) -> list[float] | None:
        """Generate an embedding for a single text string.

        Returns a list of floats on success, or None if encoding
        fails. Failures are logged as warnings, never raised.
        """
        try:
            embedding = self.model.encode([text])
            return embedding[0].tolist()
        except Exception:
            logger.warning("Embedding failed for text (length=%d)", len(text))
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in one call.

        Returns a list parallel to the input: each element is either
        a list of floats or None if that text failed to embed.
        Failures are logged as warnings.
        """
        if not texts:
            return []
        try:
            embeddings = self.model.encode(texts)
            return [row.tolist() for row in embeddings]
        except Exception:
            logger.warning(
                "Batch embedding failed for %d texts",
                len(texts),
            )
            return [None] * len(texts)
