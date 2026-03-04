"""Causal graph operations: store links, traverse causal chains.

Requirements: 13-REQ-3.1, 13-REQ-3.4
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

import duckdb  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.causal")


@dataclass(frozen=True)
class CausalLink:
    """A directed edge in the causal graph."""

    cause_id: str  # UUID as string
    effect_id: str  # UUID as string


@dataclass(frozen=True)
class CausalFact:
    """A fact with its position in a causal chain."""

    fact_id: str
    content: str
    spec_name: str | None
    session_id: str | None
    commit_sha: str | None
    created_at: str | None
    depth: int  # 0 = starting fact, positive = effects, negative = causes
    relationship: str  # "root" | "cause" | "effect"


def store_causal_links(
    conn: duckdb.DuckDBPyConnection,
    links: list[tuple[str, str]],
) -> int:
    """Insert causal links into the fact_causes table (idempotent).

    Each link is a (cause_id, effect_id) pair. Duplicate links are
    silently ignored via INSERT OR IGNORE.

    Returns the number of links successfully inserted.

    Requirements: 13-REQ-3.1, 13-REQ-3.E1
    """
    inserted = 0
    for cause_id, effect_id in links:
        try:
            # Check referential integrity: both fact IDs must exist.
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT id::VARCHAR FROM memory_facts "
                    "WHERE id IN (?::UUID, ?::UUID)",
                    [cause_id, effect_id],
                ).fetchall()
            }
            if cause_id not in existing or effect_id not in existing:
                missing = []
                if cause_id not in existing:
                    missing.append(f"cause={cause_id}")
                if effect_id not in existing:
                    missing.append(f"effect={effect_id}")
                logger.warning(
                    "Skipping causal link %s -> %s: missing fact(s) %s",
                    cause_id,
                    effect_id,
                    ", ".join(missing),
                )
                continue
            conn.execute(
                "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) "
                "VALUES (?::UUID, ?::UUID)",
                [cause_id, effect_id],
            )
            inserted += 1
        except Exception:
            logger.debug(
                "Failed to insert causal link %s -> %s",
                cause_id,
                effect_id,
                exc_info=True,
            )
    return inserted


def _fetch_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
) -> dict[str, str | None] | None:
    """Fetch a single fact's content and provenance from memory_facts."""
    row = conn.execute(
        "SELECT id, content, spec_name, session_id, commit_sha, created_at "
        "FROM memory_facts WHERE id = ?",
        [fact_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "content": row[1],
        "spec_name": row[2],
        "session_id": row[3],
        "commit_sha": row[4],
        "created_at": str(row[5]) if row[5] is not None else None,
    }


def _get_direct_effect_ids(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
) -> list[str]:
    """Return IDs of direct effects (for traversal)."""
    rows = conn.execute(
        "SELECT CAST(effect_id AS VARCHAR) FROM fact_causes WHERE cause_id = ?",
        [fact_id],
    ).fetchall()
    return [row[0] for row in rows]


def _get_direct_cause_ids(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
) -> list[str]:
    """Return IDs of direct causes (for traversal)."""
    rows = conn.execute(
        "SELECT CAST(cause_id AS VARCHAR) FROM fact_causes WHERE effect_id = ?",
        [fact_id],
    ).fetchall()
    return [row[0] for row in rows]


def traverse_causal_chain(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    *,
    max_depth: int = 10,
    direction: str = "both",  # "causes" | "effects" | "both"
) -> list[CausalFact]:
    """Traverse the causal graph from a starting fact.

    Performs breadth-first traversal following causal links up to
    max_depth. Returns all reachable facts with their depth relative
    to the starting fact. Causes have negative depth, effects have
    positive depth, the starting fact has depth 0.

    Direction controls traversal:
    - "causes": follow links backward (cause direction only)
    - "effects": follow links forward (effect direction only)
    - "both": follow links in both directions
    """
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(fact_id, 0)])
    result: list[CausalFact] = []

    while queue:
        current_id, depth = queue.popleft()
        if current_id in visited or abs(depth) > max_depth:
            continue
        visited.add(current_id)

        fact = _fetch_fact(conn, current_id)
        if fact is None:
            continue

        relationship = "root" if depth == 0 else ("cause" if depth < 0 else "effect")
        result.append(
            CausalFact(
                fact_id=current_id,
                content=fact["content"] or "",
                spec_name=fact["spec_name"],
                session_id=fact["session_id"],
                commit_sha=fact["commit_sha"],
                created_at=fact["created_at"],
                depth=depth,
                relationship=relationship,
            )
        )

        if direction in ("effects", "both"):
            for effect_id in _get_direct_effect_ids(conn, current_id):
                queue.append((effect_id, depth + 1))

        if direction in ("causes", "both"):
            for cause_id in _get_direct_cause_ids(conn, current_id):
                queue.append((cause_id, depth - 1))

    return sorted(result, key=lambda f: (f.created_at or "", f.depth))
