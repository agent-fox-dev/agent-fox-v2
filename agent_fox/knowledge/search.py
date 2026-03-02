"""Vector similarity search over the memory_embeddings table.

Uses DuckDB's cosine distance for semantic search, returning
facts ranked by similarity with provenance metadata.

Requirements: 12-REQ-3.1, 12-REQ-3.2, 12-REQ-3.3, 12-REQ-3.E1,
              12-REQ-7.2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb

from agent_fox.core.config import KnowledgeConfig

logger = logging.getLogger("agent_fox.knowledge.search")


@dataclass(frozen=True)
class SearchResult:
    """A single result from vector similarity search."""

    fact_id: str
    content: str
    category: str
    spec_name: str
    session_id: str | None
    commit_sha: str | None
    similarity: float


class VectorSearch:
    """Vector similarity search over the memory_embeddings table.

    Uses DuckDB's cosine distance for semantic search, returning
    facts ranked by similarity with provenance metadata. The INNER
    JOIN with memory_embeddings automatically excludes facts that
    have no embedding (12-REQ-3.3).
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        config: KnowledgeConfig,
    ) -> None:
        self._conn = conn
        self._config = config

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int | None = None,
        exclude_superseded: bool = True,
    ) -> list[SearchResult]:
        """Find the top-k facts most similar to the query embedding.

        Args:
            query_embedding: The embedding vector of the query text.
            top_k: Number of results to return. Defaults to
                config.ask_top_k (20).
            exclude_superseded: If True, exclude facts that have been
                superseded by newer facts.

        Returns:
            A list of SearchResult, sorted by descending similarity.
        """
        k = top_k if top_k is not None else self._config.ask_top_k

        where_clause = "WHERE f.superseded_by IS NULL" if exclude_superseded else ""

        query = f"""
            SELECT
                CAST(f.id AS VARCHAR) AS fact_id,
                f.content,
                COALESCE(f.category, '') AS category,
                COALESCE(f.spec_name, '') AS spec_name,
                CAST(f.session_id AS VARCHAR) AS session_id,
                CAST(f.commit_sha AS VARCHAR) AS commit_sha,
                1 - array_cosine_distance(
                    e.embedding, ?::FLOAT[1024]
                ) AS similarity
            FROM memory_embeddings e
            JOIN memory_facts f ON e.id = f.id
            {where_clause}
            ORDER BY similarity DESC
            LIMIT ?
        """

        try:
            rows = self._conn.execute(query, [query_embedding, k]).fetchall()
        except duckdb.Error:
            logger.warning("Vector search query failed", exc_info=True)
            return []

        return [
            SearchResult(
                fact_id=row[0],
                content=row[1],
                category=row[2],
                spec_name=row[3],
                session_id=row[4],
                commit_sha=row[5],
                similarity=float(row[6]),
            )
            for row in rows
        ]

    def has_embeddings(self) -> bool:
        """Check whether the knowledge store contains any embedded facts."""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_embeddings"
            ).fetchone()
            return row is not None and row[0] > 0
        except duckdb.Error:
            logger.warning("Failed to check for embeddings", exc_info=True)
            return False
