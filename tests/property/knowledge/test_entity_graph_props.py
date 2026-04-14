"""Property-based tests for entity graph correctness invariants.

Test Spec: TS-95-P1 through TS-95-P6
Requirements: Property 1-6 from design.md
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
    gc_stale_entities,
    upsert_edges,
    upsert_entities,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    entity_type: EntityType,
    name: str,
    path: str,
) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_name=name,
        entity_path=path,
        created_at=datetime.now(tz=UTC).isoformat(),
        deleted_at=None,
    )


def _insert_fact_bare(conn: duckdb.DuckDBPyConnection, fact_id: str) -> None:
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at)
        VALUES (?, 'Prop test fact', 'decision', 'test_spec', 0.9, CURRENT_TIMESTAMP)
        """,
        [fact_id],
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Path component: alphanumeric plus underscore and dot, no slashes
_path_component = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
)

_safe_path = st.lists(_path_component, min_size=1, max_size=4).map("/".join)

_entity_type_st = st.sampled_from(list(EntityType))

_entity_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=20,
)


@st.composite
def _entity_strategy(draw: st.DrawFn) -> Entity:
    return _make_entity(
        entity_type=draw(_entity_type_st),
        name=draw(_entity_name_st),
        path=draw(_safe_path),
    )


@st.composite
def _entities_list(draw: st.DrawFn, min_size: int = 1, max_size: int = 10) -> list[Entity]:
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    seen_keys: set[tuple[str, str, str]] = set()
    entities = []
    for _ in range(n):
        entity_type = draw(_entity_type_st)
        name = draw(_entity_name_st)
        path = draw(_safe_path)
        key = (str(entity_type), path, name)
        if key not in seen_keys:
            seen_keys.add(key)
            entities.append(_make_entity(entity_type, name, path))
    return entities


# ---------------------------------------------------------------------------
# TS-95-P1: Path normalization invariant
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    path=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789_./",
        min_size=1,
        max_size=50,
    )
)
def test_path_normalization_invariant(path: str) -> None:
    """For any path string, normalize_path output has no leading slash, no '..',
    and no trailing slash.

    Property 1 from design.md; Requirement: 95-REQ-1.3
    """
    result = normalize_path(path)

    # No leading slash
    assert not result.startswith("/"), f"Leading slash in: {result!r}"

    # No '..' components
    parts = result.split("/")
    assert ".." not in parts, f"'..' found in: {result!r}"

    # No trailing slash (unless empty string)
    if result:
        assert not result.endswith("/"), f"Trailing slash in: {result!r}"


# ---------------------------------------------------------------------------
# TS-95-P2: Upsert idempotency
# ---------------------------------------------------------------------------


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entities=_entities_list(min_size=1, max_size=5))
def test_upsert_idempotency(
    entity_conn: duckdb.DuckDBPyConnection,
    entities: list[Entity],
) -> None:
    """Upserting the same list of entities twice yields identical database state.

    Property 2 from design.md; Requirements: 95-REQ-1.E1, 95-REQ-2.4, 95-REQ-3.3
    """
    ids_first = set(upsert_entities(entity_conn, entities))
    count_first = entity_conn.execute("SELECT COUNT(*) FROM entity_graph").fetchone()[0]

    ids_second = set(upsert_entities(entity_conn, entities))
    count_second = entity_conn.execute("SELECT COUNT(*) FROM entity_graph").fetchone()[0]

    assert ids_first == ids_second, "Same entities should produce same IDs"
    assert count_first == count_second, "Entity count should not grow on re-upsert"


# ---------------------------------------------------------------------------
# TS-95-P3: Traversal bound
# ---------------------------------------------------------------------------


@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    max_depth=st.integers(min_value=1, max_value=4),
    max_entities=st.integers(min_value=1, max_value=15),
    num_entities=st.integers(min_value=2, max_value=10),
)
def test_traversal_bound(
    entity_conn: duckdb.DuckDBPyConnection,
    max_depth: int,
    max_entities: int,
    num_entities: int,
) -> None:
    """Traversal result never exceeds max_entities.

    Property 3 from design.md; Requirements: 95-REQ-6.1, 95-REQ-6.2
    """
    from agent_fox.knowledge.entity_query import traverse_neighbors

    # Build a linear chain of entities
    entity_ids = []
    for i in range(num_entities):
        e = _make_entity(EntityType.FILE, f"e{i}.py", f"src/e{i}.py")
        eid = upsert_entities(entity_conn, [e])[0]
        entity_ids.append(eid)
        if i > 0:
            upsert_edges(
                entity_conn,
                [EntityEdge(source_id=entity_ids[i - 1], target_id=eid, relationship=EdgeType.CONTAINS)],
            )

    result = traverse_neighbors(
        entity_conn,
        [entity_ids[0]],
        max_depth=max_depth,
        max_entities=max_entities,
    )

    assert len(result) <= max_entities, (
        f"Traversal returned {len(result)} entities, exceeding max_entities={max_entities}"
    )


# ---------------------------------------------------------------------------
# TS-95-P4: Soft-delete exclusion
# ---------------------------------------------------------------------------


@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_active=st.integers(min_value=1, max_value=5),
    num_deleted=st.integers(min_value=1, max_value=5),
)
def test_soft_delete_exclusion(
    entity_conn: duckdb.DuckDBPyConnection,
    num_active: int,
    num_deleted: int,
) -> None:
    """Soft-deleted entities never appear in default traversal results.

    Property 4 from design.md; Requirements: 95-REQ-6.E2, 95-REQ-7.1
    """
    from agent_fox.knowledge.entity_query import traverse_neighbors

    active_ids = []
    for i in range(num_active):
        e = _make_entity(EntityType.FILE, f"active_{i}.py", f"src/active_{i}.py")
        eid = upsert_entities(entity_conn, [e])[0]
        active_ids.append(eid)

    deleted_ids = []
    for i in range(num_deleted):
        e = _make_entity(EntityType.FILE, f"deleted_{i}.py", f"src/deleted_{i}.py")
        eid = upsert_entities(entity_conn, [e])[0]
        deleted_ids.append(eid)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            [eid],
        )

    # Connect active[0] to all deleted entities
    for did in deleted_ids:
        upsert_edges(
            entity_conn,
            [EntityEdge(source_id=active_ids[0], target_id=did, relationship=EdgeType.CONTAINS)],
        )

    result = traverse_neighbors(entity_conn, active_ids[:1], include_deleted=False)
    result_ids = {e.id for e in result}

    for did in deleted_ids:
        assert did not in result_ids, f"Soft-deleted entity {did} appeared in default traversal"
    for e in result:
        assert e.deleted_at is None, f"Entity with deleted_at={e.deleted_at} appeared in default traversal"


# ---------------------------------------------------------------------------
# TS-95-P5: Referential integrity
# ---------------------------------------------------------------------------


@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(num_entities=st.integers(min_value=2, max_value=6))
def test_referential_integrity(
    entity_conn: duckdb.DuckDBPyConnection,
    num_entities: int,
) -> None:
    """Every edge source/target and every fact link entity_id/fact_id references
    existing rows.

    Property 5 from design.md; Requirements: 95-REQ-2.3, 95-REQ-3.2
    """
    entity_ids = []
    for i in range(num_entities):
        e = _make_entity(EntityType.FILE, f"ref_{i}.py", f"src/ref_{i}.py")
        eid = upsert_entities(entity_conn, [e])[0]
        entity_ids.append(eid)

    # Add edges between consecutive entities
    for i in range(len(entity_ids) - 1):
        upsert_edges(
            entity_conn,
            [
                EntityEdge(
                    source_id=entity_ids[i],
                    target_id=entity_ids[i + 1],
                    relationship=EdgeType.CONTAINS,
                )
            ],
        )

    # Add fact-entity links
    fact_id = str(uuid.uuid4())
    _insert_fact_bare(entity_conn, fact_id)
    if entity_ids:
        create_fact_entity_links(entity_conn, fact_id, [entity_ids[0]])

    # Verify all edges reference existing entities
    edges = entity_conn.execute("SELECT source_id, target_id FROM entity_edges").fetchall()
    existing_entity_ids = {str(r[0]) for r in entity_conn.execute("SELECT id FROM entity_graph").fetchall()}
    for src_id, tgt_id in edges:
        assert str(src_id) in existing_entity_ids, f"Edge source {src_id} not in entity_graph"
        assert str(tgt_id) in existing_entity_ids, f"Edge target {tgt_id} not in entity_graph"

    # Verify all fact-entity links reference existing entities and facts
    links = entity_conn.execute("SELECT fact_id, entity_id FROM fact_entities").fetchall()
    existing_fact_ids = {str(r[0]) for r in entity_conn.execute("SELECT id FROM memory_facts").fetchall()}
    for fid, eid in links:
        assert str(fid) in existing_fact_ids, f"Link fact_id {fid} not in memory_facts"
        assert str(eid) in existing_entity_ids, f"Link entity_id {eid} not in entity_graph"


# ---------------------------------------------------------------------------
# TS-95-P6: GC cascade completeness
# ---------------------------------------------------------------------------


@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(num_stale=st.integers(min_value=1, max_value=4))
def test_gc_cascade_completeness(
    entity_conn: duckdb.DuckDBPyConnection,
    num_stale: int,
) -> None:
    """After GC, no edges or links reference hard-deleted entities.

    Property 6 from design.md; Requirement: 95-REQ-7.2
    """
    stale_ids = []
    active = _make_entity(EntityType.FILE, "active.py", "src/active.py")
    active_id = upsert_entities(entity_conn, [active])[0]

    for i in range(num_stale):
        e = _make_entity(EntityType.FILE, f"stale_{i}.py", f"src/stale_{i}.py")
        eid = upsert_entities(entity_conn, [e])[0]
        stale_ids.append(eid)

        # Link stale entity to active via edge
        upsert_edges(
            entity_conn,
            [EntityEdge(source_id=active_id, target_id=eid, relationship=EdgeType.CONTAINS)],
        )

        # Add fact-entity link
        fact_id = str(uuid.uuid4())
        _insert_fact_bare(entity_conn, fact_id)
        create_fact_entity_links(entity_conn, fact_id, [eid])

        # Set deleted_at to 30 days ago
        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?",
            [old_ts, eid],
        )

    gc_stale_entities(entity_conn, retention_days=7)

    # Verify no edges reference deleted entities
    for stale_id in stale_ids:
        edge_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ? OR target_id = ?",
            [stale_id, stale_id],
        ).fetchone()[0]
        assert edge_count == 0, f"Edge still references hard-deleted entity {stale_id}"

        link_count = entity_conn.execute(
            "SELECT COUNT(*) FROM fact_entities WHERE entity_id = ?",
            [stale_id],
        ).fetchone()[0]
        assert link_count == 0, f"Fact link still references hard-deleted entity {stale_id}"

        entity_row = entity_conn.execute("SELECT id FROM entity_graph WHERE id = ?", [stale_id]).fetchone()
        assert entity_row is None, f"Stale entity {stale_id} still in entity_graph after GC"
