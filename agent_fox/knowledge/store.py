"""DuckDB-primary fact store with JSONL export support.

DuckDB is the primary read/write path for facts. JSONL is retained
as an export-only format for portability. The MemoryStore class
writes facts to DuckDB with optional embedding generation.

Requirements: 05-REQ-3.1, 05-REQ-3.2, 05-REQ-3.3, 05-REQ-3.E1,
              05-REQ-3.E2, 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.3,
              12-REQ-1.E1, 12-REQ-2.E1, 12-REQ-7.1,
              39-REQ-2.1, 39-REQ-2.2, 39-REQ-2.3, 39-REQ-2.4,
              39-REQ-2.5, 39-REQ-3.1, 39-REQ-3.2, 39-REQ-3.E1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from agent_fox.knowledge.facts import Fact, parse_confidence

if TYPE_CHECKING:
    from agent_fox.knowledge.embeddings import EmbeddingGenerator

logger = logging.getLogger("agent_fox.knowledge.store")

DEFAULT_MEMORY_PATH = Path(".agent-fox/memory.jsonl")


def append_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Append facts to the JSONL file.

    Retained as an internal helper for JSONL export. Not called during
    normal fact ingestion (39-REQ-3.4).

    Args:
        facts: List of Fact objects to append.
        path: Path to the JSONL file.
    """
    _write_jsonl(facts, path, mode="a")


def load_all_facts(conn: duckdb.DuckDBPyConnection) -> list[Fact]:
    """Load all non-superseded facts from DuckDB memory_facts table.

    Previously read from JSONL. Now queries DuckDB directly.

    Args:
        conn: DuckDB connection.

    Returns:
        A list of all non-superseded Fact objects. Returns an empty list
        if the table is empty.

    Requirements: 39-REQ-2.1, 39-REQ-2.3, 39-REQ-2.5, 39-REQ-2.E1
    """
    rows = conn.execute(
        "SELECT CAST(id AS VARCHAR), content, category, spec_name, "
        "confidence, created_at, session_id, commit_sha, "
        "CAST(superseded_by AS VARCHAR) "
        "FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchall()

    return [_row_to_fact(row) for row in rows]


def load_facts_by_spec(
    spec_name: str,
    conn: duckdb.DuckDBPyConnection,
) -> list[Fact]:
    """Load non-superseded facts for a spec from DuckDB.

    Previously filtered JSONL in Python. Now uses SQL WHERE clause.

    Args:
        spec_name: The specification name to filter by.
        conn: DuckDB connection.

    Returns:
        A list of Fact objects matching the spec name.

    Requirements: 39-REQ-2.2, 39-REQ-2.4
    """
    rows = conn.execute(
        "SELECT CAST(id AS VARCHAR), content, category, spec_name, "
        "confidence, created_at, session_id, commit_sha, "
        "CAST(superseded_by AS VARCHAR) "
        "FROM memory_facts WHERE superseded_by IS NULL AND spec_name = ?",
        [spec_name],
    ).fetchall()

    return [_row_to_fact(row) for row in rows]


def write_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Overwrite the JSONL file with the given facts.

    Used by compaction and session-end export.

    Args:
        facts: The complete list of facts to write.
        path: Path to the JSONL file.
    """
    _write_jsonl(facts, path, mode="w")


def export_facts_to_jsonl(
    conn: duckdb.DuckDBPyConnection,
    path: Path = DEFAULT_MEMORY_PATH,
) -> int:
    """Export all non-superseded facts from DuckDB to JSONL.

    Full overwrite of the JSONL file. Logs a warning on write failure
    but does not roll back DuckDB state.

    Args:
        conn: DuckDB connection.
        path: Path to the JSONL file.

    Returns:
        Count of exported facts.

    Requirements: 39-REQ-3.2, 39-REQ-3.E1
    """
    facts = load_all_facts(conn)
    try:
        write_facts(facts, path)
    except OSError:
        logger.warning(
            "JSONL export failed for %s; DuckDB state preserved",
            path,
            exc_info=True,
        )
    return len(facts)


def _write_jsonl(facts: list[Fact], path: Path, *, mode: str) -> None:
    """Write facts to a JSONL file using the given open mode ('a' or 'w')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as f:
        for fact in facts:
            line = json.dumps(_fact_to_dict(fact), ensure_ascii=False)
            f.write(line + "\n")


def _fact_to_dict(fact: Fact) -> dict:
    """Serialize a Fact to a JSON-compatible dictionary."""
    d: dict = {
        "id": fact.id,
        "content": fact.content,
        "category": fact.category,
        "spec_name": fact.spec_name,
        "keywords": fact.keywords,
        "confidence": fact.confidence,
        "created_at": fact.created_at,
        "supersedes": fact.supersedes,
    }
    if fact.session_id is not None:
        d["session_id"] = fact.session_id
    if fact.commit_sha is not None:
        d["commit_sha"] = fact.commit_sha
    return d


def _dict_to_fact(data: dict) -> Fact:
    """Deserialize a dictionary to a Fact object."""
    return Fact(
        id=data["id"],
        content=data["content"],
        category=data["category"],
        spec_name=data["spec_name"],
        keywords=data.get("keywords", []),
        confidence=parse_confidence(data.get("confidence")),
        created_at=data["created_at"],
        supersedes=data.get("supersedes"),
        session_id=data.get("session_id"),
        commit_sha=data.get("commit_sha"),
    )


def _row_to_fact(row: tuple) -> Fact:
    """Convert a DuckDB row tuple to a Fact object."""
    (
        fact_id,
        content,
        category,
        spec_name,
        confidence,
        created_at,
        session_id,
        commit_sha,
        _superseded_by,
    ) = row

    return Fact(
        id=str(fact_id),
        content=content or "",
        category=category or "pattern",
        spec_name=spec_name or "",
        keywords=[],
        confidence=parse_confidence(confidence),
        created_at=_ensure_iso(created_at),
        session_id=session_id,
        commit_sha=commit_sha,
    )


def _ensure_iso(ts: object) -> str:
    """Convert a timestamp to ISO 8601 string."""
    from datetime import UTC, datetime

    if ts is None:
        return datetime.now(tz=UTC).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.isoformat()
    return str(ts)


class MemoryStore:
    """DuckDB-primary fact store with optional embedding generation.

    Writes facts to DuckDB only. JSONL is not written during normal
    fact ingestion (39-REQ-3.1). If ``embedder`` is ``None``, facts
    are written without embeddings.

    Requirements: 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.3, 12-REQ-1.E1,
                  12-REQ-2.E1, 12-REQ-7.1, 38-REQ-2.2, 38-REQ-2.4,
                  38-REQ-3.2, 39-REQ-3.1
    """

    def __init__(
        self,
        jsonl_path: Path,
        db_conn: duckdb.DuckDBPyConnection,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        """Initialize with JSONL path and required DuckDB connection.

        Args:
            jsonl_path: Path to the JSONL file (used for export only).
            db_conn: DuckDB connection (required, primary store).
            embedder: Optional embedding generator.  If ``None``, facts
                are written without embeddings.
        """
        self._jsonl_path = jsonl_path
        self._db_conn = db_conn
        self._embedder = embedder

    # -- Public API ----------------------------------------------------------

    def write_fact(self, fact: Fact) -> None:
        """Write a fact to DuckDB only.

        1. Insert the fact into DuckDB ``memory_facts`` (raises on failure).
        2. Generate an embedding and insert into ``memory_embeddings``
           (best-effort, non-fatal on failure).

        JSONL write removed per 39-REQ-3.1. If step 1 fails, the
        exception propagates (38-REQ-3.2). If step 2 fails, log a
        warning and continue.
        """
        # Step 1: DuckDB write -- must succeed (38-REQ-3.2)
        self._write_to_duckdb(fact)

        # Step 2: Embedding -- best-effort
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
        self._db_conn.execute(
            "UPDATE memory_facts SET superseded_by = ?::UUID "
            "WHERE CAST(id AS VARCHAR) = ?",
            [new_fact_id, old_fact_id],
        )

    # -- Private helpers -----------------------------------------------------

    def _write_to_duckdb(self, fact: Fact) -> None:
        """Insert a fact into the DuckDB ``memory_facts`` table.

        DuckDB errors propagate to the caller (38-REQ-3.2).
        """
        self._db_conn.execute(
            """
            INSERT OR IGNORE INTO memory_facts
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
        dim = (
            self._embedder.embedding_dimensions
            if self._embedder is not None
            else len(embedding)
        )
        self._db_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) "
            f"VALUES (?::UUID, ?::FLOAT[{dim}])",
            [fact_id, embedding],
        )
