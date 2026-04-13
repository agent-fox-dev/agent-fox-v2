"""DuckDB CRUD operations for the entity graph subsystem.

Requirements: 95-REQ-1.*, 95-REQ-2.*, 95-REQ-3.*, 95-REQ-7.*
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import duckdb

from agent_fox.knowledge.entities import (
    Entity,
    EntityEdge,
    EntityType,
)


def _row_to_entity(row: tuple) -> Entity:
    """Convert a DB row (id, entity_type, entity_name, entity_path, created_at, deleted_at) to Entity."""
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


def upsert_entities(conn: duckdb.DuckDBPyConnection, entities: list[Entity]) -> list[str]:
    """Upsert entities by natural key (entity_type, entity_path, entity_name).

    - If an active entity with the same natural key exists, return its ID.
    - If a soft-deleted entity with the same natural key exists, restore it
      (clear deleted_at) and return its original ID.
    - Otherwise, insert the entity with a new UUID v4 and return its ID.

    Returns a list of IDs in the same order as the input list.

    Requirements: 95-REQ-1.2, 95-REQ-1.E1, 95-REQ-1.E2
    """
    result_ids: list[str] = []

    for entity in entities:
        # Check for existing entity (active or soft-deleted) by natural key
        row = conn.execute(
            """
            SELECT id, deleted_at
            FROM entity_graph
            WHERE entity_type = ?
              AND entity_path  = ?
              AND entity_name  = ?
            LIMIT 1
            """,
            [str(entity.entity_type), entity.entity_path, entity.entity_name],
        ).fetchone()

        if row is not None:
            existing_id, deleted_at = row
            existing_id_str = str(existing_id)
            if deleted_at is not None:
                # Restore soft-deleted entity
                conn.execute(
                    "UPDATE entity_graph SET deleted_at = NULL WHERE id = ?",
                    [existing_id_str],
                )
            result_ids.append(existing_id_str)
        else:
            # Insert new entity with UUID v4
            new_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO entity_graph
                    (id, entity_type, entity_name, entity_path, created_at, deleted_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
                """,
                [new_id, str(entity.entity_type), entity.entity_name, entity.entity_path],
            )
            result_ids.append(new_id)

    return result_ids


def _entity_exists(conn: duckdb.DuckDBPyConnection, entity_id: str) -> bool:
    """Return True if entity_id exists in entity_graph (active or soft-deleted)."""
    row = conn.execute("SELECT 1 FROM entity_graph WHERE id = ? LIMIT 1", [entity_id]).fetchone()
    return row is not None


def _fact_exists(conn: duckdb.DuckDBPyConnection, fact_id: str) -> bool:
    """Return True if fact_id exists in memory_facts."""
    row = conn.execute("SELECT 1 FROM memory_facts WHERE id = ? LIMIT 1", [fact_id]).fetchone()
    return row is not None


def upsert_edges(conn: duckdb.DuckDBPyConnection, edges: list[EntityEdge]) -> int:
    """Upsert edges into entity_edges, ignoring duplicates.

    - Raises ValueError if source_id == target_id (self-loop).
    - Raises ValueError if source_id or target_id does not exist in entity_graph.
    - Duplicate edges (same source_id, target_id, relationship) are silently ignored.

    Note: Referential integrity is enforced in application code because DuckDB 1.5.x
    has a bug that causes FK constraints on referenced tables to block UPDATE statements
    even when the referenced column is not modified. See docs/errata/95_entity_graph.md.

    Returns the number of upsert attempts.

    Requirements: 95-REQ-2.3, 95-REQ-2.4, 95-REQ-2.E1
    """
    inserted = 0
    for edge in edges:
        if edge.source_id == edge.target_id:
            raise ValueError(f"Self-referencing edge rejected: source_id == target_id == {edge.source_id!r}")
        # Manual referential integrity check (workaround for DuckDB 1.5.x FK bug)
        if not _entity_exists(conn, edge.source_id):
            raise ValueError(f"source_id {edge.source_id!r} does not exist in entity_graph")
        if not _entity_exists(conn, edge.target_id):
            raise ValueError(f"target_id {edge.target_id!r} does not exist in entity_graph")
        conn.execute(
            """
            INSERT INTO entity_edges (source_id, target_id, relationship)
            VALUES (?, ?, ?)
            ON CONFLICT (source_id, target_id, relationship) DO NOTHING
            """,
            [edge.source_id, edge.target_id, str(edge.relationship)],
        )
        inserted += 1

    return inserted


def create_fact_entity_links(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    entity_ids: list[str],
) -> int:
    """Create links between a fact and entities in fact_entities.

    - Raises ValueError if fact_id is not in memory_facts.
    - Raises ValueError if any entity_id is not in entity_graph
      (soft-deleted entities are allowed).
    - Duplicate links are silently ignored.

    Note: Referential integrity is enforced in application code because DuckDB 1.5.x
    has a bug that causes FK constraints on referenced tables to block UPDATE statements
    even when the referenced column is not modified. See docs/errata/95_entity_graph.md.

    Returns the number of upsert attempts.

    Requirements: 95-REQ-3.2, 95-REQ-3.3, 95-REQ-3.E1
    """
    # Validate fact_id first (manual referential integrity)
    if not _fact_exists(conn, fact_id):
        raise ValueError(f"fact_id {fact_id!r} does not exist in memory_facts")

    inserted = 0
    for entity_id in entity_ids:
        # Validate entity_id (soft-deleted entities are allowed)
        if not _entity_exists(conn, entity_id):
            raise ValueError(f"entity_id {entity_id!r} does not exist in entity_graph")
        conn.execute(
            """
            INSERT INTO fact_entities (fact_id, entity_id)
            VALUES (?, ?)
            ON CONFLICT (fact_id, entity_id) DO NOTHING
            """,
            [fact_id, entity_id],
        )
        inserted += 1

    return inserted


def find_entities_by_path(
    conn: duckdb.DuckDBPyConnection,
    path: str,
    include_deleted: bool = False,
) -> list[Entity]:
    """Find entities by exact entity_path match.

    By default, excludes soft-deleted entities (deleted_at IS NOT NULL).
    Pass include_deleted=True to include them.

    Requirements: 95-REQ-4.1
    """
    if include_deleted:
        rows = conn.execute(
            """
            SELECT id, entity_type, entity_name, entity_path, created_at, deleted_at
            FROM entity_graph
            WHERE entity_path = ?
            """,
            [path],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, entity_type, entity_name, entity_path, created_at, deleted_at
            FROM entity_graph
            WHERE entity_path = ?
              AND deleted_at IS NULL
            """,
            [path],
        ).fetchall()

    return [_row_to_entity(row) for row in rows]


def find_entities_by_paths(
    conn: duckdb.DuckDBPyConnection,
    paths: list[str],
) -> list[Entity]:
    """Find active entities whose entity_path is in the given list.

    Excludes soft-deleted entities.

    Requirements: 95-REQ-4.2
    """
    if not paths:
        return []

    placeholders = ", ".join("?" for _ in paths)
    rows = conn.execute(
        f"""
        SELECT id, entity_type, entity_name, entity_path, created_at, deleted_at
        FROM entity_graph
        WHERE entity_path IN ({placeholders})
          AND deleted_at IS NULL
        """,
        paths,
    ).fetchall()

    return [_row_to_entity(row) for row in rows]


def soft_delete_missing(
    conn: duckdb.DuckDBPyConnection,
    found_keys: set[tuple[str, str, str]],
) -> int:
    """Soft-delete all active entities whose natural key is not in found_keys.

    Sets deleted_at = CURRENT_TIMESTAMP for every entity where:
    - deleted_at IS NULL (active)
    - (entity_type, entity_path, entity_name) is NOT in found_keys

    Returns the count of entities newly soft-deleted.

    Requirements: 95-REQ-7.1
    """
    # Fetch all active entities and determine which to soft-delete in Python
    rows = conn.execute(
        """
        SELECT id, entity_type, entity_path, entity_name
        FROM entity_graph
        WHERE deleted_at IS NULL
        """
    ).fetchall()

    if found_keys:
        ids_to_delete = [str(row[0]) for row in rows if (str(row[1]), str(row[2]), str(row[3])) not in found_keys]
    else:
        ids_to_delete = [str(row[0]) for row in rows]

    if not ids_to_delete:
        return 0

    placeholders = ", ".join("?" for _ in ids_to_delete)
    conn.execute(
        f"UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
        ids_to_delete,
    )
    return len(ids_to_delete)


def gc_stale_entities(conn: duckdb.DuckDBPyConnection, retention_days: int) -> int:
    """Hard-delete entities soft-deleted beyond the retention period.

    - Raises ValueError if retention_days <= 0.
    - Cascade-deletes associated edges (entity_edges) and links (fact_entities).
    - Returns the count of entities hard-deleted.

    Cascade deletes are performed manually before deleting from entity_graph
    because the entity_edges and fact_entities tables do not define ON DELETE CASCADE
    (FK constraints are omitted due to a DuckDB 1.5.x bug; see docs/errata/95_entity_graph.md).

    Requirements: 95-REQ-7.2, 95-REQ-7.E1, 95-REQ-7.E2
    """
    if retention_days <= 0:
        raise ValueError(f"retention_days must be positive, got {retention_days!r}")

    cutoff = datetime.now(tz=UTC) - timedelta(days=retention_days)

    # Find stale entity IDs
    stale_rows = conn.execute(
        """
        SELECT id
        FROM entity_graph
        WHERE deleted_at IS NOT NULL
          AND deleted_at < ?
        """,
        [cutoff],
    ).fetchall()

    if not stale_rows:
        return 0

    stale_ids = [str(row[0]) for row in stale_rows]
    placeholders = ", ".join("?" for _ in stale_ids)

    # Cascade: delete edges referencing stale entities (source or target)
    conn.execute(
        f"""
        DELETE FROM entity_edges
        WHERE source_id IN ({placeholders})
           OR target_id IN ({placeholders})
        """,
        stale_ids + stale_ids,
    )

    # Cascade: delete fact_entities links referencing stale entities
    conn.execute(
        f"DELETE FROM fact_entities WHERE entity_id IN ({placeholders})",
        stale_ids,
    )

    # Hard-delete stale entities
    conn.execute(
        f"DELETE FROM entity_graph WHERE id IN ({placeholders})",
        stale_ids,
    )

    return len(stale_ids)
