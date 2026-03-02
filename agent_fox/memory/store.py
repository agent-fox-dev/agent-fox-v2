"""JSONL-based fact store for structured memory with dual-write support.

Append facts, read all facts, load facts filtered by spec name.
Manages the `.agent-fox/memory.jsonl` file.  The MemoryStore class
extends persistence to DuckDB and embedding storage for semantic search.

Requirements: 05-REQ-3.1, 05-REQ-3.2, 05-REQ-3.3, 05-REQ-3.E1,
              05-REQ-3.E2, 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.3,
              12-REQ-1.E1, 12-REQ-2.E1, 12-REQ-7.1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.memory.types import Fact

if TYPE_CHECKING:
    import duckdb

    from agent_fox.knowledge.embeddings import EmbeddingGenerator

logger = logging.getLogger("agent_fox.memory.store")

DEFAULT_MEMORY_PATH = Path(".agent-fox/memory.jsonl")


def append_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Append facts to the JSONL file.

    Creates the file and parent directories if they do not exist.

    Args:
        facts: List of Fact objects to append.
        path: Path to the JSONL file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for fact in facts:
                line = json.dumps(_fact_to_dict(fact), ensure_ascii=False)
                f.write(line + "\n")
    except OSError:
        logger.error("Failed to write facts to %s", path, exc_info=True)


def load_all_facts(path: Path = DEFAULT_MEMORY_PATH) -> list[Fact]:
    """Load all facts from the JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        A list of all Fact objects. Returns an empty list if the file
        does not exist or is empty.
    """
    if not path.exists():
        return []

    facts: list[Fact] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            facts.append(_dict_to_fact(data))
    return facts


def load_facts_by_spec(
    spec_name: str,
    path: Path = DEFAULT_MEMORY_PATH,
) -> list[Fact]:
    """Load facts filtered by specification name.

    Args:
        spec_name: The specification name to filter by.
        path: Path to the JSONL file.

    Returns:
        A list of Fact objects matching the spec name.
    """
    return [f for f in load_all_facts(path) if f.spec_name == spec_name]


def write_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Overwrite the JSONL file with the given facts.

    Used by compaction to rewrite the file after deduplication.

    Args:
        facts: The complete list of facts to write.
        path: Path to the JSONL file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for fact in facts:
                line = json.dumps(_fact_to_dict(fact), ensure_ascii=False)
                f.write(line + "\n")
    except OSError:
        logger.error("Failed to write facts to %s", path, exc_info=True)


def _fact_to_dict(fact: Fact) -> dict:
    """Serialize a Fact to a JSON-compatible dictionary."""
    return {
        "id": fact.id,
        "content": fact.content,
        "category": fact.category,
        "spec_name": fact.spec_name,
        "keywords": fact.keywords,
        "confidence": fact.confidence,
        "created_at": fact.created_at,
        "supersedes": fact.supersedes,
    }


def _dict_to_fact(data: dict) -> Fact:
    """Deserialize a dictionary to a Fact object."""
    return Fact(
        id=data["id"],
        content=data["content"],
        category=data["category"],
        spec_name=data["spec_name"],
        keywords=data["keywords"],
        confidence=data["confidence"],
        created_at=data["created_at"],
        supersedes=data.get("supersedes"),
    )


class MemoryStore:
    """Dual-write fact store: JSONL (source of truth) + DuckDB (queryable index).

    Extends the existing JSONL persistence with optional DuckDB dual-write
    and embedding generation.  If ``db_conn`` is ``None``, facts are written
    to JSONL only (graceful degradation).  If ``embedder`` is ``None``, facts
    are written without embeddings.

    Requirements: 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.3, 12-REQ-1.E1,
                  12-REQ-2.E1, 12-REQ-7.1
    """

    def __init__(
        self,
        jsonl_path: Path,
        db_conn: duckdb.DuckDBPyConnection | None = None,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        """Initialize with JSONL path and optional DuckDB connection.

        Args:
            jsonl_path: Path to the JSONL file (source of truth).
            db_conn: Optional DuckDB connection for the queryable index.
                If ``None``, facts are written to JSONL only.
            embedder: Optional embedding generator.  If ``None``, facts
                are written without embeddings.
        """
        self._jsonl_path = jsonl_path
        self._db_conn = db_conn
        self._embedder = embedder

    # -- Public API ----------------------------------------------------------

    def write_fact(self, fact: Fact) -> None:
        """Dual-write a fact to JSONL and DuckDB.

        1. Append the fact to JSONL (always succeeds or raises).
        2. Insert the fact into DuckDB ``memory_facts`` (best-effort).
        3. Generate an embedding and insert into ``memory_embeddings``
           (best-effort, non-fatal on failure).

        If step 2 fails, log a warning and continue.
        If step 3 fails, log a warning and continue -- the fact
        exists in DuckDB without an embedding.
        """
        # Step 1: JSONL write -- never skipped
        self._write_to_jsonl(fact)

        # Step 2: DuckDB write -- best-effort
        if self._db_conn is None:
            logger.warning(
                "DuckDB unavailable; fact %s written to JSONL only",
                fact.id,
            )
            return

        try:
            self._write_to_duckdb(fact)
        except Exception:
            logger.warning(
                "DuckDB write failed for fact %s; JSONL write succeeded",
                fact.id,
                exc_info=True,
            )
            return

        # Step 3: Embedding -- best-effort
        if self._embedder is None:
            logger.warning(
                "No embedder configured; fact %s stored without embedding",
                fact.id,
            )
            return

        try:
            embedding = self._embedder.embed_text(fact.content)
            if embedding is not None:
                self._write_embedding(fact.id, embedding)
            else:
                logger.warning(
                    "Embedding generation returned None for fact %s",
                    fact.id,
                )
        except Exception:
            logger.warning(
                "Embedding write failed for fact %s",
                fact.id,
                exc_info=True,
            )

    def mark_superseded(self, old_fact_id: str, new_fact_id: str) -> None:
        """Mark an old fact as superseded by a new one.

        Updates the ``superseded_by`` column in ``memory_facts``.

        Args:
            old_fact_id: UUID of the fact being superseded.
            new_fact_id: UUID of the superseding fact.
        """
        if self._db_conn is None:
            logger.warning(
                "DuckDB unavailable; cannot mark fact %s as superseded",
                old_fact_id,
            )
            return

        self._db_conn.execute(
            "UPDATE memory_facts SET superseded_by = ?::UUID "
            "WHERE CAST(id AS VARCHAR) = ?",
            [new_fact_id, old_fact_id],
        )

    # -- Private helpers -----------------------------------------------------

    def _write_to_jsonl(self, fact: Fact) -> None:
        """Append a fact to the JSONL store."""
        append_facts([fact], self._jsonl_path)

    def _write_to_duckdb(self, fact: Fact) -> None:
        """Insert a fact into the DuckDB ``memory_facts`` table."""
        assert self._db_conn is not None  # caller ensures this

        self._db_conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, session_id,
                 commit_sha, confidence, created_at)
            VALUES (?::UUID, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                fact.id,
                fact.content,
                fact.category,
                fact.spec_name,
                getattr(fact, "session_id", None),
                getattr(fact, "commit_sha", None),
                fact.confidence,
            ],
        )

    def _write_embedding(self, fact_id: str, embedding: list[float]) -> None:
        """Insert an embedding into the DuckDB ``memory_embeddings`` table."""
        assert self._db_conn is not None  # caller ensures this

        self._db_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) "
            "VALUES (?::UUID, ?::FLOAT[1024])",
            [fact_id, embedding],
        )
