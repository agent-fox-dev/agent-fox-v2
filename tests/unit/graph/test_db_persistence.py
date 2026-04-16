"""Unit tests for DB-based plan persistence.

Test Spec: TS-105-1, TS-105-2, TS-105-3, TS-105-E1, TS-105-E2, TS-105-11
Requirements: 105-REQ-1.1, 105-REQ-1.2, 105-REQ-1.3, 105-REQ-1.4,
              105-REQ-1.E1, 105-REQ-1.E2, 105-REQ-5.2, 105-REQ-5.E1
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

# NOTE: compute_plan_hash does not yet exist at module level in persistence.py.
# This import will fail with ImportError until task group 3 implements it.
from agent_fox.graph.persistence import (  # noqa: F401
    compute_plan_hash,
    load_plan,
    save_plan,
)
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

# -- Schema DDL for plan tables (matches v9 migration) --------------------------

_PLAN_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS plan_nodes (
    id              VARCHAR PRIMARY KEY,
    spec_name       VARCHAR NOT NULL,
    group_number    INTEGER NOT NULL,
    title           VARCHAR NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    archetype       VARCHAR NOT NULL DEFAULT 'coder',
    mode            VARCHAR,
    model_tier      VARCHAR,
    status          VARCHAR NOT NULL DEFAULT 'pending',
    subtask_count   INTEGER NOT NULL DEFAULT 0,
    optional        BOOLEAN NOT NULL DEFAULT FALSE,
    instances       INTEGER NOT NULL DEFAULT 1,
    sort_position   INTEGER NOT NULL DEFAULT 0,
    blocked_reason  VARCHAR,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_edges (
    from_node   VARCHAR NOT NULL,
    to_node     VARCHAR NOT NULL,
    edge_type   VARCHAR NOT NULL DEFAULT 'intra_spec',
    PRIMARY KEY (from_node, to_node)
);

CREATE TABLE IF NOT EXISTS plan_meta (
    id              INTEGER PRIMARY KEY,
    content_hash    VARCHAR NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fast_mode       BOOLEAN NOT NULL DEFAULT FALSE,
    filtered_spec   VARCHAR,
    version         VARCHAR NOT NULL DEFAULT ''
);
"""

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def plan_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with plan tables (matching v9 migration schema)."""
    conn = duckdb.connect(":memory:")
    conn.execute(_PLAN_SCHEMA_DDL)
    yield conn
    conn.close()


@pytest.fixture
def three_node_graph() -> TaskGraph:
    """A simple TaskGraph with 3 nodes and 2 edges for round-trip tests."""
    nodes = {
        "spec_a:1": Node(
            id="spec_a:1",
            spec_name="spec_a",
            group_number=1,
            title="Task 1",
            optional=False,
            subtask_count=3,
            body="Do task 1",
            archetype="coder",
            mode=None,
            instances=1,
        ),
        "spec_a:2": Node(
            id="spec_a:2",
            spec_name="spec_a",
            group_number=2,
            title="Task 2",
            optional=False,
            subtask_count=2,
            body="Do task 2",
            archetype="reviewer",
            mode="fast",
            instances=1,
        ),
        "spec_a:3": Node(
            id="spec_a:3",
            spec_name="spec_a",
            group_number=3,
            title="Task 3",
            optional=True,
            subtask_count=0,
            body="",
            archetype="coder",
            mode=None,
            instances=2,
        ),
    }
    edges = [
        Edge(source="spec_a:1", target="spec_a:2", kind="intra_spec"),
        Edge(source="spec_a:2", target="spec_a:3", kind="intra_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["spec_a:1", "spec_a:2", "spec_a:3"],
        metadata=PlanMetadata(
            created_at="2026-01-01T00:00:00",
            fast_mode=False,
            filtered_spec=None,
            version="3.0.0",
        ),
    )


# -- Tests: TS-105-1 Plan nodes round-trip ------------------------------------


def test_plan_round_trip(
    plan_conn: duckdb.DuckDBPyConnection,
    three_node_graph: TaskGraph,
) -> None:
    """TS-105-1: save_plan then load_plan returns structurally identical graph.

    Requirements: 105-REQ-1.1, 105-REQ-1.2, 105-REQ-1.3
    """
    # save_plan currently takes a Path; calling with conn will fail at runtime.
    save_plan(three_node_graph, plan_conn)
    loaded = load_plan(plan_conn)

    assert loaded is not None
    assert set(loaded.nodes.keys()) == set(three_node_graph.nodes.keys())

    for nid, orig_node in three_node_graph.nodes.items():
        loaded_node = loaded.nodes[nid]
        assert loaded_node.id == orig_node.id
        assert loaded_node.spec_name == orig_node.spec_name
        assert loaded_node.group_number == orig_node.group_number
        assert loaded_node.title == orig_node.title
        assert loaded_node.optional == orig_node.optional
        assert loaded_node.subtask_count == orig_node.subtask_count
        assert loaded_node.body == orig_node.body
        assert loaded_node.archetype == orig_node.archetype
        assert loaded_node.mode == orig_node.mode
        assert loaded_node.instances == orig_node.instances
        assert str(loaded_node.status) == str(orig_node.status)

    loaded_edge_tuples = {(e.source, e.target, e.kind) for e in loaded.edges}
    orig_edge_tuples = {(e.source, e.target, e.kind) for e in three_node_graph.edges}
    assert loaded_edge_tuples == orig_edge_tuples
    assert loaded.order == three_node_graph.order


# -- Tests: TS-105-2 Atomic save ----------------------------------------------


def test_plan_saved_atomic(
    plan_conn: duckdb.DuckDBPyConnection,
    three_node_graph: TaskGraph,
) -> None:
    """TS-105-2: save_plan writes all three tables in a single call.

    Requirements: 105-REQ-1.1
    """
    save_plan(three_node_graph, plan_conn)

    _row = plan_conn.sql("SELECT count(*) FROM plan_nodes").fetchone()
    assert _row is not None
    node_count = _row[0]
    _row = plan_conn.sql("SELECT count(*) FROM plan_edges").fetchone()
    assert _row is not None
    edge_count = _row[0]
    _row = plan_conn.sql("SELECT count(*) FROM plan_meta").fetchone()
    assert _row is not None
    meta_count = _row[0]

    assert node_count == 3
    assert edge_count == 2
    assert meta_count == 1


# -- Tests: TS-105-3 Content hash stored --------------------------------------


def test_content_hash_stored(
    plan_conn: duckdb.DuckDBPyConnection,
    three_node_graph: TaskGraph,
) -> None:
    """TS-105-3: plan_meta stores the correct content hash.

    compute_plan_hash(graph) is a new function (not yet exported at module level).

    Requirements: 105-REQ-1.4
    """
    expected_hash = compute_plan_hash(three_node_graph)
    save_plan(three_node_graph, plan_conn)

    _row = plan_conn.sql("SELECT content_hash FROM plan_meta").fetchone()
    assert _row is not None
    stored_hash = _row[0]
    assert stored_hash == expected_hash


def test_content_hash_excludes_status(
    plan_conn: duckdb.DuckDBPyConnection,
    three_node_graph: TaskGraph,
) -> None:
    """TS-105-3 (variant): Content hash is identical before and after a status change.

    Requirements: 105-REQ-1.4
    """
    from agent_fox.graph.types import NodeStatus

    hash_before = compute_plan_hash(three_node_graph)

    # Mutate a node's status
    three_node_graph.nodes["spec_a:1"].status = NodeStatus.COMPLETED

    hash_after = compute_plan_hash(three_node_graph)

    assert hash_before == hash_after


# -- Tests: TS-105-E1 No plan returns None ------------------------------------


def test_no_plan_returns_none(plan_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E1: load_plan returns None when no plan exists in DB.

    Requirements: 105-REQ-1.E1
    """
    result = load_plan(plan_conn)
    assert result is None


# -- Tests: TS-105-E2 Empty plan ----------------------------------------------


def test_empty_plan(plan_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E2: Empty plan (zero nodes) round-trips correctly.

    Requirements: 105-REQ-1.E2
    """
    empty_graph = TaskGraph(
        nodes={},
        edges=[],
        order=[],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )
    save_plan(empty_graph, plan_conn)
    loaded = load_plan(plan_conn)

    assert loaded is not None
    assert loaded.nodes == {}
    assert loaded.edges == []
    assert loaded.order == []


# -- Tests: TS-105-11 Legacy files ignored ------------------------------------


def test_legacy_files_ignored(
    plan_conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
) -> None:
    """TS-105-11: load_plan ignores plan.json files on disk.

    If plan.json exists on disk but the DB has no plan, load_plan returns
    None (reads from DB only, not from the file).

    Requirements: 105-REQ-5.E1
    """
    # Write a plan.json with content to disk
    plan_json = tmp_path / ".agent-fox" / "plan.json"
    plan_json.parent.mkdir(parents=True, exist_ok=True)
    plan_json.write_text(
        '{"nodes": {"a:1": {"id": "a:1", "spec_name": "a", "group_number": 1}}}',
        encoding="utf-8",
    )

    # DB is empty — load_plan(conn) must return None, ignoring the file
    result = load_plan(plan_conn)
    assert result is None


def test_overwrite_plan_replaces_old(
    plan_conn: duckdb.DuckDBPyConnection,
    three_node_graph: TaskGraph,
) -> None:
    """save_plan called twice overwrites the previous plan atomically.

    This verifies the DELETE-then-INSERT approach required by REQ-1.1:
    each call to save_plan results in exactly one plan in the DB.
    """
    # Save the original plan
    save_plan(three_node_graph, plan_conn)

    # Build a smaller replacement plan
    small_graph = TaskGraph(
        nodes={
            "spec_b:1": Node(
                id="spec_b:1",
                spec_name="spec_b",
                group_number=1,
                title="New Task",
                optional=False,
            )
        },
        edges=[],
        order=["spec_b:1"],
        metadata=PlanMetadata(created_at="2026-06-01T00:00:00"),
    )
    save_plan(small_graph, plan_conn)

    loaded = load_plan(plan_conn)
    assert loaded is not None
    assert len(loaded.nodes) == 1
    assert "spec_b:1" in loaded.nodes
    # Old nodes must be gone
    assert "spec_a:1" not in loaded.nodes
