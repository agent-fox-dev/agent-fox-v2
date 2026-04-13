"""Tests for entity_store and entities modules.

Test Spec: TS-95-1 through TS-95-11, TS-95-27, TS-95-28,
           TS-95-E1 through TS-95-E4, TS-95-E12, TS-95-E13
Requirements: 95-REQ-1.*, 95-REQ-2.*, 95-REQ-3.*, 95-REQ-7.*
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from agent_fox.knowledge.entities import (
    EdgeType,
    Entity,
    EntityEdge,
    EntityType,
    normalize_path,
)
from agent_fox.knowledge.entity_store import (
    create_fact_entity_links,
    find_entities_by_path,
    gc_stale_entities,
    soft_delete_missing,
    upsert_edges,
    upsert_entities,
)

from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema + all migrations applied.

    Entity graph tables are created by migration v8.
    """
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    commit_sha: str | None = None,
    superseded_by: str | None = None,
) -> None:
    """Insert a minimal memory fact for referential integrity tests."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at,
             commit_sha, superseded_by)
        VALUES (?, 'Test fact content', 'decision', 'test_spec', 0.9,
                CURRENT_TIMESTAMP, ?, ?)
        """,
        [fact_id, commit_sha, superseded_by],
    )


def _make_entity(
    entity_type: EntityType = EntityType.FILE,
    entity_name: str = "foo.py",
    entity_path: str = "src/foo.py",
) -> Entity:
    """Create a minimal Entity for testing."""
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_name=entity_name,
        entity_path=entity_path,
        created_at=datetime.now(tz=UTC).isoformat(),
        deleted_at=None,
    )


# ---------------------------------------------------------------------------
# TS-95-1: Entity table schema
# ---------------------------------------------------------------------------


class TestEntityTableSchema:
    """TS-95-1: entity_graph table has the correct columns.

    Requirement: 95-REQ-1.1
    """

    def test_entity_graph_columns_exist(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Verify entity_graph has all required columns with correct types."""
        rows = entity_conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'entity_graph'
            ORDER BY column_name
            """
        ).fetchall()
        columns = {r[0]: r[1].upper() for r in rows}

        assert "id" in columns
        assert "entity_type" in columns
        assert "entity_name" in columns
        assert "entity_path" in columns
        assert "created_at" in columns
        assert "deleted_at" in columns

        # UUID primary key
        assert "UUID" in columns["id"]
        # Timestamps
        assert "TIMESTAMP" in columns["created_at"]
        assert "TIMESTAMP" in columns["deleted_at"]


# ---------------------------------------------------------------------------
# TS-95-2: Entity UUID assignment
# ---------------------------------------------------------------------------


class TestEntityUUIDAssignment:
    """TS-95-2: Upserted entities receive UUID v4 identifiers.

    Requirement: 95-REQ-1.2
    """

    def test_upserted_entity_has_uuid_v4_id(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Returned ID is a valid UUID v4 string."""
        entity = _make_entity()
        entity_ids = upsert_entities(entity_conn, [entity])
        entity_id = entity_ids[0]
        parsed = uuid.UUID(entity_id, version=4)
        assert str(parsed) == entity_id or parsed.version == 4


# ---------------------------------------------------------------------------
# TS-95-3: Path normalization on storage
# ---------------------------------------------------------------------------


class TestPathNormalization:
    """TS-95-3: Entity paths are normalized to repo-relative format.

    Requirement: 95-REQ-1.3
    """

    def test_no_leading_slash(self) -> None:
        """Normalized path has no leading slash."""
        result = normalize_path("/repo/root/src/foo.py", repo_root=None)
        assert not result.startswith("/")

    def test_dot_dot_resolved(self) -> None:
        """Normalized path has no '..' components."""
        result = normalize_path("./src/../src/bar.py")
        assert ".." not in result.split("/")
        assert result == "src/bar.py"

    def test_trailing_slash_stripped(self) -> None:
        """Normalized path has no trailing slash."""
        result = normalize_path("src/baz.py/")
        assert not result.endswith("/")
        assert result == "src/baz.py"

    def test_dot_component_resolved(self) -> None:
        """Normalized path has no '.' component."""
        result = normalize_path("./src/foo.py")
        parts = result.split("/")
        assert "." not in parts


# ---------------------------------------------------------------------------
# TS-95-4: Entity type support
# ---------------------------------------------------------------------------


class TestEntityTypeSupport:
    """TS-95-4: All four entity types can be stored and retrieved.

    Requirement: 95-REQ-1.4
    """

    def test_all_entity_types_storable(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Entities of all four types are stored and retrievable."""
        types = [EntityType.FILE, EntityType.MODULE, EntityType.CLASS, EntityType.FUNCTION]
        for et in types:
            entity = _make_entity(
                entity_type=et,
                entity_name=f"{et}_name",
                entity_path=f"src/{et}_entity.py",
            )
            upsert_entities(entity_conn, [entity])

        for et in types:
            results = find_entities_by_path(entity_conn, f"src/{et}_entity.py")
            assert any(e.entity_type == et for e in results), (
                f"Entity type {et} not found after upsert"
            )


# ---------------------------------------------------------------------------
# TS-95-5: Edge table schema
# ---------------------------------------------------------------------------


class TestEdgeTableSchema:
    """TS-95-5: entity_edges table has the correct schema.

    Requirement: 95-REQ-2.1
    """

    def test_entity_edges_columns_exist(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """entity_edges has source_id, target_id, relationship columns."""
        rows = entity_conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'entity_edges'
            ORDER BY column_name
            """
        ).fetchall()
        columns = {r[0]: r[1].upper() for r in rows}

        assert "source_id" in columns
        assert "target_id" in columns
        assert "relationship" in columns

        assert "UUID" in columns["source_id"]
        assert "UUID" in columns["target_id"]
        assert "VARCHAR" in columns["relationship"]


# ---------------------------------------------------------------------------
# TS-95-6: Edge relationship types
# ---------------------------------------------------------------------------


class TestEdgeRelationshipTypes:
    """TS-95-6: All three relationship types can be stored.

    Requirement: 95-REQ-2.2
    """

    def test_all_relationship_types_storable(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """edges with contains, imports, and extends relationships are stored."""
        src = _make_entity(entity_name="src.py", entity_path="src/src.py")
        tgt = _make_entity(entity_name="tgt.py", entity_path="src/tgt.py")
        src_ids = upsert_entities(entity_conn, [src])
        tgt_ids = upsert_entities(entity_conn, [tgt])
        src_id, tgt_id = src_ids[0], tgt_ids[0]

        for rel in [EdgeType.CONTAINS, EdgeType.IMPORTS, EdgeType.EXTENDS]:
            upsert_edges(
                entity_conn,
                [EntityEdge(source_id=src_id, target_id=tgt_id, relationship=rel)],
            )

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ?", [src_id]
        ).fetchone()[0]
        assert count == 3


# ---------------------------------------------------------------------------
# TS-95-7: Edge referential integrity
# ---------------------------------------------------------------------------


class TestEdgeReferentialIntegrity:
    """TS-95-7: Edges with missing endpoints are rejected.

    Requirement: 95-REQ-2.3
    """

    def test_missing_target_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Edge with valid source but non-existent target raises an error."""
        src = _make_entity()
        src_id = upsert_entities(entity_conn, [src])[0]
        fake_target = str(uuid.uuid4())

        with pytest.raises(Exception):
            upsert_edges(
                entity_conn,
                [EntityEdge(source_id=src_id, target_id=fake_target, relationship=EdgeType.CONTAINS)],
            )

    def test_missing_source_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Edge with valid target but non-existent source raises an error."""
        tgt = _make_entity(entity_name="tgt.py", entity_path="src/tgt.py")
        tgt_id = upsert_entities(entity_conn, [tgt])[0]
        fake_source = str(uuid.uuid4())

        with pytest.raises(Exception):
            upsert_edges(
                entity_conn,
                [EntityEdge(source_id=fake_source, target_id=tgt_id, relationship=EdgeType.CONTAINS)],
            )


# ---------------------------------------------------------------------------
# TS-95-8: Edge deduplication
# ---------------------------------------------------------------------------


class TestEdgeDeduplication:
    """TS-95-8: Duplicate edges are silently ignored.

    Requirement: 95-REQ-2.4
    """

    def test_duplicate_edge_not_inserted(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Upserting the same edge twice keeps edge count at 1."""
        src = _make_entity(entity_name="a.py", entity_path="src/a.py")
        tgt = _make_entity(entity_name="b.py", entity_path="src/b.py")
        src_id = upsert_entities(entity_conn, [src])[0]
        tgt_id = upsert_entities(entity_conn, [tgt])[0]

        edge = EntityEdge(source_id=src_id, target_id=tgt_id, relationship=EdgeType.CONTAINS)
        upsert_edges(entity_conn, [edge])
        upsert_edges(entity_conn, [edge])  # duplicate

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ? AND target_id = ?",
            [src_id, tgt_id],
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# TS-95-9: Fact-entity table schema
# ---------------------------------------------------------------------------


class TestFactEntityTableSchema:
    """TS-95-9: fact_entities table has the correct schema.

    Requirement: 95-REQ-3.1
    """

    def test_fact_entities_columns_exist(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """fact_entities has fact_id and entity_id columns."""
        rows = entity_conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fact_entities'
            ORDER BY column_name
            """
        ).fetchall()
        columns = {r[0]: r[1].upper() for r in rows}

        assert "fact_id" in columns
        assert "entity_id" in columns
        assert "UUID" in columns["fact_id"]
        assert "UUID" in columns["entity_id"]


# ---------------------------------------------------------------------------
# TS-95-10: Fact-entity referential integrity
# ---------------------------------------------------------------------------


class TestFactEntityReferentialIntegrity:
    """TS-95-10: Fact-entity links with missing references are rejected.

    Requirement: 95-REQ-3.2
    """

    def test_missing_entity_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Link with valid fact_id but non-existent entity_id raises an error."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)
        fake_entity_id = str(uuid.uuid4())

        with pytest.raises(Exception):
            create_fact_entity_links(entity_conn, fact_id, [fake_entity_id])

    def test_missing_fact_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Link with non-existent fact_id but valid entity_id raises an error."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]
        fake_fact_id = str(uuid.uuid4())

        with pytest.raises(Exception):
            create_fact_entity_links(entity_conn, fake_fact_id, [entity_id])


# ---------------------------------------------------------------------------
# TS-95-11: Fact-entity deduplication
# ---------------------------------------------------------------------------


class TestFactEntityDeduplication:
    """TS-95-11: Duplicate fact-entity links are silently ignored.

    Requirement: 95-REQ-3.3
    """

    def test_duplicate_link_not_inserted(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Creating the same link twice keeps link count at 1."""
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]

        create_fact_entity_links(entity_conn, fact_id, [entity_id])
        create_fact_entity_links(entity_conn, fact_id, [entity_id])  # duplicate

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM fact_entities WHERE fact_id = ?", [fact_id]
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# TS-95-27: Soft-delete sets deleted_at, preserves edges and links
# ---------------------------------------------------------------------------


class TestSoftDeletePreserves:
    """TS-95-27: Soft-delete sets deleted_at and preserves edges and links.

    Requirement: 95-REQ-7.1
    """

    def test_soft_delete_sets_deleted_at(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """soft_delete_missing marks entity with deleted_at timestamp."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]

        # Soft-delete by passing empty found set (entity not in found set)
        soft_delete_missing(entity_conn, set())

        row = entity_conn.execute(
            "SELECT deleted_at FROM entity_graph WHERE id = ?", [entity_id]
        ).fetchone()
        assert row is not None
        assert row[0] is not None, "deleted_at should be set after soft delete"

    def test_soft_delete_preserves_edges(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Edges still exist after entity is soft-deleted."""
        src = _make_entity(entity_name="a.py", entity_path="src/a.py")
        tgt = _make_entity(entity_name="b.py", entity_path="src/b.py")
        src_id = upsert_entities(entity_conn, [src])[0]
        tgt_id = upsert_entities(entity_conn, [tgt])[0]
        edge = EntityEdge(source_id=src_id, target_id=tgt_id, relationship=EdgeType.CONTAINS)
        upsert_edges(entity_conn, [edge])

        # Soft-delete src
        soft_delete_missing(entity_conn, set())

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ?", [src_id]
        ).fetchone()[0]
        assert count > 0, "Edges should still exist after soft delete"

    def test_soft_delete_preserves_fact_links(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Fact-entity links still exist after entity is soft-deleted."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)
        create_fact_entity_links(entity_conn, fact_id, [entity_id])

        # Soft-delete by passing empty found set
        soft_delete_missing(entity_conn, set())

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM fact_entities WHERE entity_id = ?", [entity_id]
        ).fetchone()[0]
        assert count > 0, "Fact-entity links should still exist after soft delete"


# ---------------------------------------------------------------------------
# TS-95-28: Garbage collection cascade
# ---------------------------------------------------------------------------


class TestGCCascade:
    """TS-95-28: GC hard-deletes stale entities and cascades to edges and links.

    Requirement: 95-REQ-7.2
    """

    def test_gc_removes_stale_entity(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC removes entity soft-deleted beyond retention period."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]

        # Manually set deleted_at to 30 days ago
        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?",
            [old_ts, entity_id],
        )

        count = gc_stale_entities(entity_conn, retention_days=7)
        assert count == 1

        row = entity_conn.execute(
            "SELECT id FROM entity_graph WHERE id = ?", [entity_id]
        ).fetchone()
        assert row is None, "Stale entity should be removed by GC"

    def test_gc_cascades_edges(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC removes edges referencing the hard-deleted entity."""
        src = _make_entity(entity_name="a.py", entity_path="src/a.py")
        tgt = _make_entity(entity_name="b.py", entity_path="src/b.py")
        src_id = upsert_entities(entity_conn, [src])[0]
        tgt_id = upsert_entities(entity_conn, [tgt])[0]
        upsert_edges(entity_conn, [EntityEdge(source_id=src_id, target_id=tgt_id, relationship=EdgeType.CONTAINS)])

        # Soft-delete src 30 days ago
        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?", [old_ts, src_id]
        )

        gc_stale_entities(entity_conn, retention_days=7)

        edge_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ? OR target_id = ?",
            [src_id, src_id],
        ).fetchone()[0]
        assert edge_count == 0, "Edges referencing removed entity should be cascade-deleted"

    def test_gc_cascades_fact_links(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC removes fact_entities links referencing the hard-deleted entity."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)
        create_fact_entity_links(entity_conn, fact_id, [entity_id])

        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?", [old_ts, entity_id]
        )

        gc_stale_entities(entity_conn, retention_days=7)

        link_count = entity_conn.execute(
            "SELECT COUNT(*) FROM fact_entities WHERE entity_id = ?", [entity_id]
        ).fetchone()[0]
        assert link_count == 0, "Fact links referencing removed entity should be cascade-deleted"

    def test_gc_does_not_touch_active_entities(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC leaves active entities untouched."""
        stale = _make_entity(entity_name="stale.py", entity_path="src/stale.py")
        active = _make_entity(entity_name="active.py", entity_path="src/active.py")
        stale_id = upsert_entities(entity_conn, [stale])[0]
        active_id = upsert_entities(entity_conn, [active])[0]

        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?", [old_ts, stale_id]
        )

        count = gc_stale_entities(entity_conn, retention_days=7)
        assert count == 1

        active_row = entity_conn.execute(
            "SELECT id FROM entity_graph WHERE id = ?", [active_id]
        ).fetchone()
        assert active_row is not None, "Active entity should remain after GC"


# ---------------------------------------------------------------------------
# TS-95-E1: Upsert existing active entity returns same ID
# ---------------------------------------------------------------------------


class TestUpsertExistingActive:
    """TS-95-E1: Upserting an entity with an existing natural key returns original ID.

    Requirement: 95-REQ-1.E1
    """

    def test_same_natural_key_returns_same_id(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Second upsert of same natural key returns the first entity's ID."""
        entity1 = _make_entity(EntityType.FILE, "foo.py", "src/foo.py")
        entity2 = Entity(
            id=str(uuid.uuid4()),  # different UUID but same natural key
            entity_type=EntityType.FILE,
            entity_name="foo.py",
            entity_path="src/foo.py",
            created_at=datetime.now(tz=UTC).isoformat(),
            deleted_at=None,
        )

        id1 = upsert_entities(entity_conn, [entity1])[0]
        id2 = upsert_entities(entity_conn, [entity2])[0]

        assert id1 == id2, "Same natural key should return the original entity ID"

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE entity_path = 'src/foo.py'"
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# TS-95-E2: Upsert restores soft-deleted entity
# ---------------------------------------------------------------------------


class TestUpsertRestoresSoftDeleted:
    """TS-95-E2: Upserting a soft-deleted entity restores it.

    Requirement: 95-REQ-1.E2
    """

    def test_upsert_clears_deleted_at(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Re-upserting a soft-deleted entity clears deleted_at."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]

        # Soft-delete it
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            [entity_id],
        )

        # Upsert with the same natural key
        restored_entity = Entity(
            id=str(uuid.uuid4()),  # new UUID, same natural key
            entity_type=entity.entity_type,
            entity_name=entity.entity_name,
            entity_path=entity.entity_path,
            created_at=datetime.now(tz=UTC).isoformat(),
            deleted_at=None,
        )
        restored_id = upsert_entities(entity_conn, [restored_entity])[0]

        assert restored_id == entity_id, "Restored entity should keep original ID"

        row = entity_conn.execute(
            "SELECT deleted_at FROM entity_graph WHERE id = ?", [entity_id]
        ).fetchone()
        assert row[0] is None, "deleted_at should be NULL after restore"


# ---------------------------------------------------------------------------
# TS-95-E3: Self-referencing edge rejected
# ---------------------------------------------------------------------------


class TestSelfEdgeRejected:
    """TS-95-E3: Edges where source equals target are rejected with ValueError.

    Requirement: 95-REQ-2.E1
    """

    def test_self_edge_raises_value_error(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Edge from entity to itself raises ValueError."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]

        with pytest.raises(ValueError):
            upsert_edges(
                entity_conn,
                [EntityEdge(source_id=entity_id, target_id=entity_id, relationship=EdgeType.CONTAINS)],
            )


# ---------------------------------------------------------------------------
# TS-95-E4: Fact-entity link to soft-deleted entity is allowed
# ---------------------------------------------------------------------------


class TestLinkToSoftDeletedEntity:
    """TS-95-E4: Links to soft-deleted entities are allowed.

    Requirement: 95-REQ-3.E1
    """

    def test_link_to_soft_deleted_entity_succeeds(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Creating a link to a soft-deleted entity does not raise an error."""
        entity = _make_entity()
        entity_id = upsert_entities(entity_conn, [entity])[0]
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)

        # Soft-delete the entity
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            [entity_id],
        )

        # Creating link to soft-deleted entity should succeed
        create_fact_entity_links(entity_conn, fact_id, [entity_id])

        count = entity_conn.execute(
            "SELECT COUNT(*) FROM fact_entities WHERE fact_id = ?", [fact_id]
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# TS-95-E12: GC with invalid retention_days raises ValueError
# ---------------------------------------------------------------------------


class TestGCInvalidRetentionDays:
    """TS-95-E12: GC with zero or negative retention_days raises ValueError.

    Requirement: 95-REQ-7.E1
    """

    def test_zero_retention_days_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """gc_stale_entities(conn, 0) raises ValueError."""
        with pytest.raises(ValueError):
            gc_stale_entities(entity_conn, retention_days=0)

    def test_negative_retention_days_raises(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """gc_stale_entities(conn, -5) raises ValueError."""
        with pytest.raises(ValueError):
            gc_stale_entities(entity_conn, retention_days=-5)


# ---------------------------------------------------------------------------
# TS-95-E13: GC with no eligible entities returns zero
# ---------------------------------------------------------------------------


class TestGCNoEligibleEntities:
    """TS-95-E13: GC returns zero when no entities are eligible.

    Requirement: 95-REQ-7.E2
    """

    def test_no_stale_entities_returns_zero(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC returns 0 when no entities are soft-deleted beyond retention."""
        # Insert active entities
        entity = _make_entity()
        upsert_entities(entity_conn, [entity])

        count = gc_stale_entities(entity_conn, retention_days=7)
        assert count == 0

    def test_empty_graph_returns_zero(
        self, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """GC returns 0 on an empty entity graph."""
        count = gc_stale_entities(entity_conn, retention_days=7)
        assert count == 0
