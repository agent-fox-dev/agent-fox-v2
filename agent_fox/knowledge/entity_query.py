"""Graph traversal and fact retrieval for the entity graph subsystem.

Provides BFS traversal of the entity graph and fact retrieval for
related entities.

Requirements: 95-REQ-6.*

NOTE: This module is a stub pending task group 4 implementation.
"""

from __future__ import annotations

import duckdb

from agent_fox.knowledge.entities import EdgeType, Entity
from agent_fox.knowledge.facts import Fact


def traverse_neighbors(
    conn: duckdb.DuckDBPyConnection,
    entity_ids: list[str],
    max_depth: int = 2,
    max_entities: int = 50,
    relationship_types: list[EdgeType] | None = None,
    include_deleted: bool = False,
) -> list[Entity]:
    """BFS traversal from entity_ids within max_depth hops.

    Follows edges in both directions. Respects max_entities limit (closest
    entities first, ordered by depth then entity_name). Optionally filters
    by relationship_types. Excludes soft-deleted entities by default.

    Requirements: 95-REQ-6.1, 95-REQ-6.2, 95-REQ-6.3, 95-REQ-6.E2
    """
    raise NotImplementedError("entity_query.traverse_neighbors: pending task group 4")


def get_facts_for_entities(
    conn: duckdb.DuckDBPyConnection,
    entity_ids: list[str],
    exclude_superseded: bool = True,
) -> list[Fact]:
    """Return facts linked to the given entity IDs via fact_entities.

    By default, excludes superseded facts (superseded_by IS NOT NULL).
    Returns a deduplicated list.

    Requirements: 95-REQ-6.4
    """
    raise NotImplementedError("entity_query.get_facts_for_entities: pending task group 4")


def find_related_facts(
    conn: duckdb.DuckDBPyConnection,
    file_path: str,
    max_depth: int = 2,
    max_entities: int = 50,
) -> list[Fact]:
    """Convenience function: resolve file_path to entities, traverse, return facts.

    1. Looks up entities by file_path.
    2. Traverses neighbors within max_depth.
    3. Returns all facts linked to the traversed entities (deduplicated).

    Returns an empty list if no entities match the starting path.

    Requirements: 95-REQ-6.5, 95-REQ-6.E1
    """
    raise NotImplementedError("entity_query.find_related_facts: pending task group 4")
