"""Tests for entity_query module.

Test Spec: TS-95-22 through TS-95-26, TS-95-E10, TS-95-E11
Requirements: 95-REQ-6.*
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import duckdb
import pytest
from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.entity_query import find_related_facts, get_facts_for_entities, traverse_neighbors
from agent_fox.knowledge.entity_store import create_fact_entity_links, upsert_edges, upsert_entities

from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema + all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _make_entity(
    name: str,
    path: str,
    entity_type: EntityType = EntityType.FILE,
) -> Entity:
    """Create a minimal Entity for testing."""
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_name=name,
        entity_path=path,
        created_at=datetime.now(tz=UTC).isoformat(),
        deleted_at=None,
    )


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    superseded_by: str | None = None,
) -> None:
    """Insert a minimal fact into memory_facts."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, superseded_by)
        VALUES (?, 'Test fact', 'decision', 'test_spec', 0.9, CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, superseded_by],
    )


def _upsert(conn: duckdb.DuckDBPyConnection, entity: Entity) -> str:
    """Upsert a single entity and return its stored ID."""
    return upsert_entities(conn, [entity])[0]


def _add_edge(
    conn: duckdb.DuckDBPyConnection,
    source_id: str,
    target_id: str,
    rel: EdgeType = EdgeType.CONTAINS,
) -> None:
    """Add a directed edge between two entities."""
    upsert_edges(conn, [EntityEdge(source_id=source_id, target_id=target_id, relationship=rel)])


# ---------------------------------------------------------------------------
# TS-95-22: Graph traversal within max_depth
# ---------------------------------------------------------------------------


class TestTraversalMaxDepth:
    """TS-95-22: Traversal returns neighbors within max_depth hops.

    Requirement: 95-REQ-6.1
    """

    def test_linear_graph_traversal_max_depth_2(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Linear A->B->C->D: traversal from A with depth=2 returns A,B,C not D."""
        a = _make_entity("a.py", "src/a.py")
        b = _make_entity("b.py", "src/b.py")
        c = _make_entity("c.py", "src/c.py")
        d = _make_entity("d.py", "src/d.py")

        a_id = _upsert(entity_conn, a)
        b_id = _upsert(entity_conn, b)
        c_id = _upsert(entity_conn, c)
        d_id = _upsert(entity_conn, d)

        _add_edge(entity_conn, a_id, b_id)
        _add_edge(entity_conn, b_id, c_id)
        _add_edge(entity_conn, c_id, d_id)

        result = traverse_neighbors(entity_conn, [a_id], max_depth=2)
        result_ids = {e.id for e in result}

        assert a_id in result_ids
        assert b_id in result_ids
        assert c_id in result_ids
        assert d_id not in result_ids


# ---------------------------------------------------------------------------
# TS-95-23: Traversal max_entities limit
# ---------------------------------------------------------------------------


class TestTraversalMaxEntities:
    """TS-95-23: Traversal respects max_entities limit.

    Requirement: 95-REQ-6.2
    """

    def test_star_graph_max_entities_5(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Star graph A->B1..B10: traversal with max_entities=5 returns 5 entities."""
        a = _make_entity("a.py", "src/a.py")
        a_id = _upsert(entity_conn, a)

        for i in range(10):
            b = _make_entity(f"b{i}.py", f"src/b{i}.py")
            b_id = _upsert(entity_conn, b)
            _add_edge(entity_conn, a_id, b_id)

        result = traverse_neighbors(entity_conn, [a_id], max_depth=1, max_entities=5)

        assert len(result) == 5


# ---------------------------------------------------------------------------
# TS-95-24: Traversal relationship type filtering
# ---------------------------------------------------------------------------


class TestTraversalRelationshipFilter:
    """TS-95-24: Traversal respects relationship_types filter.

    Requirement: 95-REQ-6.3
    """

    def test_filter_by_imports_excludes_contains(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Traversal filtered to IMPORTS excludes entities reached only via CONTAINS."""
        a = _make_entity("a.py", "src/a.py")
        b = _make_entity("b.py", "src/b.py")
        c = _make_entity("c.py", "src/c.py")

        a_id = _upsert(entity_conn, a)
        b_id = _upsert(entity_conn, b)
        c_id = _upsert(entity_conn, c)

        _add_edge(entity_conn, a_id, b_id, EdgeType.CONTAINS)
        _add_edge(entity_conn, a_id, c_id, EdgeType.IMPORTS)

        result = traverse_neighbors(entity_conn, [a_id], relationship_types=[EdgeType.IMPORTS])
        result_ids = {e.id for e in result}

        assert c_id in result_ids
        assert b_id not in result_ids


# ---------------------------------------------------------------------------
# TS-95-25: Fact retrieval for entities
# ---------------------------------------------------------------------------


class TestGetFactsForEntities:
    """TS-95-25: get_facts_for_entities returns non-superseded facts only.

    Requirement: 95-REQ-6.4
    """

    def test_returns_active_facts_excludes_superseded(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Active fact F1 returned; superseded fact F2 excluded."""
        entity = _make_entity("e.py", "src/e.py")
        entity_id = _upsert(entity_conn, entity)

        f1_id = str(uuid.uuid4())
        f2_id = str(uuid.uuid4())
        f3_id = str(uuid.uuid4())  # supersedes f2

        _insert_fact(entity_conn, f1_id)
        _insert_fact(entity_conn, f3_id)  # superseding fact must exist first
        _insert_fact(entity_conn, f2_id, superseded_by=f3_id)

        create_fact_entity_links(entity_conn, f1_id, [entity_id])
        create_fact_entity_links(entity_conn, f2_id, [entity_id])

        facts = get_facts_for_entities(entity_conn, [entity_id])
        fact_ids = {f.id for f in facts}

        assert f1_id in fact_ids
        assert f2_id not in fact_ids


# ---------------------------------------------------------------------------
# TS-95-26: Convenience function find_related_facts
# ---------------------------------------------------------------------------


class TestFindRelatedFacts:
    """TS-95-26: find_related_facts resolves path to entities and returns linked facts.

    Requirement: 95-REQ-6.5
    """

    def test_find_related_facts_returns_linked_facts(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Facts linked to file entity and its class entity are returned."""
        file_entity = _make_entity("foo.py", "src/foo.py")
        class_entity = _make_entity("Foo", "src/foo.py", EntityType.CLASS)

        file_id = _upsert(entity_conn, file_entity)
        class_id = _upsert(entity_conn, class_entity)
        _add_edge(entity_conn, file_id, class_id, EdgeType.CONTAINS)

        f1_id = str(uuid.uuid4())
        f2_id = str(uuid.uuid4())
        _insert_fact(entity_conn, f1_id)
        _insert_fact(entity_conn, f2_id)

        create_fact_entity_links(entity_conn, f1_id, [file_id])
        create_fact_entity_links(entity_conn, f2_id, [class_id])

        facts = find_related_facts(entity_conn, "src/foo.py", max_depth=1)
        fact_ids = {f.id for f in facts}

        assert f1_id in fact_ids
        assert f2_id in fact_ids

    def test_find_related_facts_deduplicates(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Facts linked to multiple entities appear only once in results."""
        file_entity = _make_entity("foo.py", "src/foo.py")
        class_entity = _make_entity("Foo", "src/foo.py", EntityType.CLASS)

        file_id = _upsert(entity_conn, file_entity)
        class_id = _upsert(entity_conn, class_entity)
        _add_edge(entity_conn, file_id, class_id, EdgeType.CONTAINS)

        f1_id = str(uuid.uuid4())
        _insert_fact(entity_conn, f1_id)

        # Link same fact to both entities
        create_fact_entity_links(entity_conn, f1_id, [file_id])
        create_fact_entity_links(entity_conn, f1_id, [class_id])

        facts = find_related_facts(entity_conn, "src/foo.py", max_depth=1)
        fact_ids = [f.id for f in facts]

        assert fact_ids.count(f1_id) == 1, "Duplicate facts should be deduplicated"


# ---------------------------------------------------------------------------
# TS-95-E10: Traversal with no matching entities
# ---------------------------------------------------------------------------


class TestTraversalNoMatchingEntities:
    """TS-95-E10: Empty result when no entities match the starting path.

    Requirement: 95-REQ-6.E1
    """

    def test_nonexistent_path_returns_empty_list(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """find_related_facts returns [] for a path with no matching entity."""
        facts = find_related_facts(entity_conn, "nonexistent.py")
        assert facts == []

    def test_empty_entity_ids_returns_empty_list(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """traverse_neighbors returns [] for an empty entity_ids list."""
        result = traverse_neighbors(entity_conn, [])
        assert result == []


# ---------------------------------------------------------------------------
# TS-95-E11: Traversal excludes soft-deleted entities
# ---------------------------------------------------------------------------


class TestTraversalExcludesSoftDeleted:
    """TS-95-E11: Soft-deleted entities excluded from default traversal.

    Requirement: 95-REQ-6.E2
    """

    def test_soft_deleted_neighbor_excluded(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Entity A (active) with edge to B (soft-deleted): traversal returns only A."""
        a = _make_entity("a.py", "src/a.py")
        b = _make_entity("b.py", "src/b.py")

        a_id = _upsert(entity_conn, a)
        b_id = _upsert(entity_conn, b)
        _add_edge(entity_conn, a_id, b_id)

        # Soft-delete B
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            [b_id],
        )

        result = traverse_neighbors(entity_conn, [a_id], max_depth=1)
        result_ids = {e.id for e in result}

        assert a_id in result_ids
        assert b_id not in result_ids

    def test_include_deleted_flag_includes_soft_deleted(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """With include_deleted=True, soft-deleted entities appear in traversal."""
        a = _make_entity("a.py", "src/a.py")
        b = _make_entity("b.py", "src/b.py")

        a_id = _upsert(entity_conn, a)
        b_id = _upsert(entity_conn, b)
        _add_edge(entity_conn, a_id, b_id)

        # Soft-delete B
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            [b_id],
        )

        result = traverse_neighbors(entity_conn, [a_id], max_depth=1, include_deleted=True)
        result_ids = {e.id for e in result}

        assert b_id in result_ids
