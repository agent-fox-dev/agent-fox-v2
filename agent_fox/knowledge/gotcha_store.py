"""DuckDB CRUD for the gotchas table.

Provides query-by-spec with TTL and limit, store with content-hash
deduplication, and content hash computation.

Requirements: 115-REQ-2.4, 115-REQ-2.E1, 115-REQ-3.1, 115-REQ-3.2,
              115-REQ-3.3, 115-REQ-3.4, 115-REQ-7.1, 115-REQ-7.2
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import duckdb

from agent_fox.knowledge.gotcha_extraction import GotchaCandidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GotchaRecord:
    """A gotcha record as stored in the database."""

    id: str
    spec_name: str
    text: str
    content_hash: str
    session_id: str
    created_at: datetime


def compute_content_hash(text: str) -> str:
    """SHA-256 of normalized (lowered, whitespace-collapsed) text.

    Normalization: lowercase the text, then collapse all whitespace
    (including newlines, tabs, multiple spaces) into single spaces,
    and strip leading/trailing whitespace.

    Requirements: 115-REQ-2.4 (Property 8: determinism and case/whitespace insensitivity)
    """
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def store_gotchas(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    session_id: str,
    candidates: list[GotchaCandidate],
) -> int:
    """Store gotcha candidates with content-hash deduplication.

    For each candidate, checks whether a gotcha with the same content_hash
    already exists for the same spec_name. If so, the candidate is silently
    skipped (115-REQ-2.E1).

    Args:
        conn: DuckDB connection with the gotchas table.
        spec_name: Spec name to associate gotchas with.
        session_id: Session that produced the gotchas.
        candidates: List of GotchaCandidate objects to store.

    Returns:
        Count of actually stored (non-duplicate) gotchas.
    """
    stored = 0
    for candidate in candidates:
        # Check for existing gotcha with same content hash for this spec
        existing = conn.execute(
            "SELECT 1 FROM gotchas WHERE spec_name = ? AND content_hash = ?",
            [spec_name, candidate.content_hash],
        ).fetchone()
        if existing is not None:
            continue

        gotcha_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO gotchas (id, spec_name, category, text, content_hash, "
            "session_id, created_at) VALUES (?, ?, 'gotcha', ?, ?, ?, ?)",
            [
                gotcha_id,
                spec_name,
                candidate.text,
                candidate.content_hash,
                session_id,
                datetime.now(UTC),
            ],
        )
        stored += 1

    if stored:
        logger.info(
            "Stored %d gotchas for %s (session %s)",
            stored,
            spec_name,
            session_id,
        )

    return stored


def query_gotchas(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    ttl_days: int,
    limit: int = 5,
) -> list[str]:
    """Query non-expired gotchas for spec, ordered by recency.

    Excludes gotchas whose created_at is older than ttl_days from now.
    Returns at most ``limit`` gotchas (default 5), most recent first.

    Each returned string is prefixed with ``[GOTCHA] ``.

    Expired gotchas are NOT deleted from the database; they are simply
    excluded from the query result (115-REQ-7.2).

    Args:
        conn: DuckDB connection with the gotchas table.
        spec_name: Spec name to filter by.
        ttl_days: Maximum age in days. Gotchas older than this are excluded.
            A value of 0 means immediate expiry (all gotchas excluded).
        limit: Maximum number of gotchas to return (default 5).

    Returns:
        List of formatted strings prefixed with ``[GOTCHA] ``.
    """
    cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
    rows = conn.execute(
        "SELECT text FROM gotchas "
        "WHERE spec_name = ? AND created_at > ? "
        "ORDER BY created_at DESC "
        "LIMIT ?",
        [spec_name, cutoff, limit],
    ).fetchall()
    return [f"[GOTCHA] {row[0]}" for row in rows]
