"""Graph traversal and fact retrieval for the entity graph subsystem.

Provides BFS traversal of the entity graph and fact retrieval for
related entities.

Requirements: 95-REQ-6.*
"""

from __future__ import annotations

import logging

import duckdb

from agent_fox.knowledge.entities import EdgeType, Entity, EntityType
from agent_fox.knowledge.entity_store import find_entities_by_path
from agent_fox.knowledge.facts import Fact

logger = logging.getLogger(__name__)


def _row_to_entity(row: tuple) -> Entity:
    """Convert a DB row to an Entity dataclass."""
    entity_id, entity_type, entity_name, entity_path, created_at, deleted_at = row
    return Entity(
        id=str(entity_id),
        entity_type=EntityType(entity_type),
        entity_name=entity_name,
        entity_path=entity_path,
        created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        deleted_at=(
            deleted_at.isoformat() if deleted_at is not None and hasattr(deleted_at, "isoformat") else deleted_at
        ),
    )


def _row_to_fact(row: tuple) -> Fact:
    """Convert a memory_facts DB row to a Fact dataclass.

    Row columns: id, content, category, spec_name, confidence,
                 created_at, session_id, commit_sha
    """
    fact_id, content, category, spec_name, confidence, created_at, session_id, commit_sha = row
    return Fact(
        id=str(fact_id),
        content=content,
        category=category or "decision",
        spec_name=spec_name or "",
        keywords=[],
        confidence=float(confidence) if confidence is not None else 0.6,
        created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        supersedes=None,
        session_id=session_id,
        commit_sha=commit_sha,
    )


def traverse_neighbors(
    conn: duckdb.DuckDBPyConnection,
    entity_ids: list[str],
    max_depth: int = 2,
    max_entities: int = 50,
    relationship_types: list[EdgeType] | None = None,
    include_deleted: bool = False,
) -> list[Entity]:
    """BFS traversal from entity_ids within max_depth hops.

    Follows edges in both directions (bidirectional). Respects the
    max_entities limit — entities are added in BFS order (depth ascending),
    then alphabetically by entity_name within each depth level.

    Optionally filters by relationship_types (only follows matching edges).
    Excludes soft-deleted entities by default (include_deleted=False).

    Uses a Python-level BFS with a visited set to avoid cycles and duplicate
    results. This avoids the duplicate-depth issue that arises with recursive
    SQL CTEs on bidirectional graphs.

    Requirements: 95-REQ-6.1, 95-REQ-6.2, 95-REQ-6.3, 95-REQ-6.E2
    """
    if not entity_ids:
        return []

    deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"

    # BFS state
    visited: set[str] = set()
    results: list[Entity] = []
    frontier: list[str] = list(entity_ids)

    for depth in range(max_depth + 1):
        if not frontier or len(results) >= max_entities:
            break

        # Only process IDs not yet visited
        new_ids = [eid for eid in frontier if eid not in visited]
        visited.update(new_ids)

        if not new_ids:
            break

        # Fetch entities for this frontier, applying soft-delete filter
        id_placeholders = ", ".join("?" for _ in new_ids)
        rows = conn.execute(
            f"""
            SELECT id, entity_type, entity_name, entity_path, created_at, deleted_at
            FROM entity_graph
            WHERE id IN ({id_placeholders})
              {deleted_clause}
            ORDER BY entity_name ASC
            """,
            new_ids,
        ).fetchall()

        # Track which frontier entities actually passed the deleted filter
        # (only expand from active entities)
        active_in_frontier: list[str] = []
        for row in rows:
            if len(results) >= max_entities:
                break
            entity = _row_to_entity(row)
            results.append(entity)
            active_in_frontier.append(entity.id)

        # Expand to next frontier only if we haven't reached max_depth
        if depth < max_depth and active_in_frontier:
            # Build optional relationship filter
            rel_clause = ""
            rel_params: list[str] = []
            if relationship_types:
                rel_placeholders = ", ".join("?" for _ in relationship_types)
                rel_clause = f"AND relationship IN ({rel_placeholders})"
                rel_params = [str(r) for r in relationship_types]

            active_placeholders = ", ".join("?" for _ in active_in_frontier)

            # Bidirectional neighbor lookup:
            # For each active entity, return the "other end" of each edge.
            # CASE: if active entity is the source, return target; else return source.
            edge_rows = conn.execute(
                f"""
                SELECT DISTINCT
                    CASE
                        WHEN source_id IN ({active_placeholders}) THEN CAST(target_id AS VARCHAR)
                        ELSE CAST(source_id AS VARCHAR)
                    END AS neighbor_id
                FROM entity_edges
                WHERE (source_id IN ({active_placeholders})
                       OR target_id IN ({active_placeholders}))
                  {rel_clause}
                """,
                active_in_frontier + active_in_frontier + active_in_frontier + rel_params,
            ).fetchall()

            frontier = [str(row[0]) for row in edge_rows if str(row[0]) not in visited]
        else:
            frontier = []

    return results


def get_facts_for_entities(
    conn: duckdb.DuckDBPyConnection,
    entity_ids: list[str],
    exclude_superseded: bool = True,
) -> list[Fact]:
    """Return facts linked to the given entity IDs via fact_entities.

    By default, excludes superseded facts (superseded_by IS NOT NULL in
    memory_facts). Returns a deduplicated list (each fact appears once
    even if linked to multiple entities).

    Requirements: 95-REQ-6.4
    """
    if not entity_ids:
        return []

    superseded_clause = "AND mf.superseded_by IS NULL" if exclude_superseded else ""
    placeholders = ", ".join("?" for _ in entity_ids)

    rows = conn.execute(
        f"""
        SELECT DISTINCT
            mf.id, mf.content, mf.category, mf.spec_name,
            mf.confidence, mf.created_at, mf.session_id, mf.commit_sha
        FROM fact_entities fe
        JOIN memory_facts mf ON mf.id = fe.fact_id
        WHERE fe.entity_id IN ({placeholders})
          {superseded_clause}
        """,
        entity_ids,
    ).fetchall()

    seen_ids: set[str] = set()
    facts: list[Fact] = []
    for row in rows:
        fact_id = str(row[0])
        if fact_id not in seen_ids:
            seen_ids.add(fact_id)
            facts.append(_row_to_fact(row))

    return facts


def find_related_facts(
    conn: duckdb.DuckDBPyConnection,
    file_path: str,
    max_depth: int = 2,
    max_entities: int = 50,
) -> list[Fact]:
    """Convenience function: resolve file_path to entities, traverse, return facts.

    1. Looks up active entities matching file_path.
    2. Traverses neighbors within max_depth (excluding soft-deleted by default).
    3. Returns all non-superseded facts linked to the traversed entities
       (deduplicated).

    Returns an empty list if no entities match the starting path.

    Requirements: 95-REQ-6.5, 95-REQ-6.E1
    """
    # Resolve file_path to starting entities (active only)
    entities = find_entities_by_path(conn, file_path)
    if not entities:
        # 95-REQ-6.E1: no entities match — return empty list
        return []

    entity_ids = [e.id for e in entities]

    # Traverse the graph from the starting entities
    all_entities = traverse_neighbors(
        conn,
        entity_ids,
        max_depth=max_depth,
        max_entities=max_entities,
    )
    all_entity_ids = [e.id for e in all_entities]

    # Retrieve non-superseded facts linked to all traversed entities
    return get_facts_for_entities(conn, all_entity_ids)
