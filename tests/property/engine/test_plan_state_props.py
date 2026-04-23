"""Property-based tests for DB plan state persistence.

Test Spec: TS-105-P1 through TS-105-P5
Requirements: Properties 1-5 from design.md
"""

from __future__ import annotations

import string

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

# NOTE: These imports will fail with ImportError until task group 3 implements
# the new DB-based persistence functions and task group 2 adds the dataclasses.
from agent_fox.engine.state import (  # noqa: F401
    SessionOutcomeRecord,
    complete_run,
    create_run,
    load_execution_state,
    persist_node_status,
    record_session,
    update_run_totals,
)
from agent_fox.graph.persistence import compute_plan_hash, load_plan, save_plan
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph

# -- Schema DDL for plan + run + extended session tables ----------------------

_FULL_SCHEMA_DDL = """
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

CREATE TABLE IF NOT EXISTS runs (
    id                  VARCHAR PRIMARY KEY,
    plan_content_hash   VARCHAR NOT NULL,
    started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at        TIMESTAMP,
    status              VARCHAR NOT NULL DEFAULT 'running',
    total_input_tokens  BIGINT NOT NULL DEFAULT 0,
    total_output_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost          DOUBLE NOT NULL DEFAULT 0.0,
    total_sessions      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_outcomes (
    id                  VARCHAR PRIMARY KEY,
    spec_name           VARCHAR,
    task_group          VARCHAR,
    node_id             VARCHAR,
    touched_path        VARCHAR,
    status              VARCHAR,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    duration_ms         INTEGER,
    created_at          TIMESTAMP,
    run_id              VARCHAR,
    attempt             INTEGER DEFAULT 1,
    cost                DOUBLE DEFAULT 0.0,
    model               VARCHAR,
    archetype           VARCHAR,
    commit_sha          VARCHAR,
    error_message       TEXT,
    is_transport_error  BOOLEAN DEFAULT FALSE,
    retrieval_summary   TEXT,
    coverage_data       TEXT
);
"""

# -- Strategies ---------------------------------------------------------------

_SAFE_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + "_-",
    min_size=1,
    max_size=20,
)

_ARCHETYPES = st.sampled_from(["coder", "reviewer", "verifier", "planner"])
_MODES = st.one_of(st.none(), st.sampled_from(["fast", "hunt", "strict"]))
_V3_STATUSES = st.sampled_from(
    [
        "pending",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "skipped",
        "cost_blocked",
        "merge_blocked",
    ]
)


@st.composite
def valid_nodes(draw: st.DrawFn, node_id: str) -> Node:
    """Generate a valid Node with random field values."""
    spec_name, group_str = (node_id.rsplit(":", 1) + ["1"])[:2]
    return Node(
        id=node_id,
        spec_name=spec_name,
        group_number=int(group_str) if group_str.isdigit() else 1,
        title=draw(_SAFE_TEXT),
        optional=draw(st.booleans()),
        status=NodeStatus.PENDING,  # initial status; transitions tested separately
        subtask_count=draw(st.integers(min_value=0, max_value=20)),
        body=draw(st.text(max_size=200)),
        archetype=draw(_ARCHETYPES),
        mode=draw(_MODES),
        instances=draw(st.integers(min_value=1, max_value=4)),
    )


@st.composite
def valid_task_graphs(draw: st.DrawFn) -> TaskGraph:
    """Generate a valid acyclic TaskGraph with 0-8 nodes and well-formed edges."""
    n = draw(st.integers(min_value=0, max_value=8))

    node_ids = [f"spec_{i}:{i + 1}" for i in range(n)]
    nodes = {}
    for nid in node_ids:
        nodes[nid] = draw(valid_nodes(nid))

    # Build a DAG: only allow edges from lower-index to higher-index nodes
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if draw(st.booleans()) and j - i == 1:
                # Only add sequential edges to keep the graph simple
                edges.append(Edge(source=node_ids[i], target=node_ids[j], kind="intra_spec"))

    # Topological order is just the node_ids in definition order (already a DAG)
    order = node_ids[:]

    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=order,
        metadata=PlanMetadata(
            created_at="2026-01-01T00:00:00",
            fast_mode=draw(st.booleans()),
            filtered_spec=draw(st.one_of(st.none(), _SAFE_TEXT)),
            version=draw(_SAFE_TEXT),
        ),
    )


@st.composite
def session_outcome_records(draw: st.DrawFn, run_id: str = "run_1") -> SessionOutcomeRecord:
    """Generate a valid SessionOutcomeRecord with random fields."""
    return SessionOutcomeRecord(
        id=draw(_SAFE_TEXT),
        spec_name=draw(_SAFE_TEXT),
        task_group=draw(st.integers(min_value=1, max_value=10).map(str)),
        node_id=draw(_SAFE_TEXT),
        touched_path=draw(_SAFE_TEXT),
        status=draw(st.sampled_from(["completed", "failed"])),
        input_tokens=draw(st.integers(min_value=0, max_value=100_000)),
        output_tokens=draw(st.integers(min_value=0, max_value=100_000)),
        duration_ms=draw(st.integers(min_value=0, max_value=600_000)),
        created_at="2026-01-01T00:00:00",
        run_id=run_id,
        attempt=draw(st.integers(min_value=1, max_value=5)),
        cost=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False)),
        model=draw(st.sampled_from(["claude-sonnet-4-6", "claude-opus-4-6"])),
        archetype=draw(_ARCHETYPES),
        commit_sha=draw(_SAFE_TEXT),
        error_message=draw(st.one_of(st.none(), _SAFE_TEXT)),
        is_transport_error=draw(st.booleans()),
    )


# -- Property Test TS-105-P1: Plan round-trip equivalence ---------------------


@given(graph=valid_task_graphs())
@settings(max_examples=30)
def test_plan_round_trip_equivalence(graph: TaskGraph) -> None:
    """TS-105-P1: Any valid TaskGraph survives save/load without data loss.

    Property 1 from design.md: For any valid TaskGraph, save_plan followed
    by load_plan produces a structurally equivalent TaskGraph.

    Requirements: 105-REQ-1.1, 105-REQ-1.2
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)

    save_plan(graph, conn)
    loaded = load_plan(conn)

    assert loaded is not None
    assert set(loaded.nodes.keys()) == set(graph.nodes.keys())

    for nid, orig in graph.nodes.items():
        loaded_node = loaded.nodes[nid]
        assert loaded_node.id == orig.id
        assert loaded_node.spec_name == orig.spec_name
        assert loaded_node.group_number == orig.group_number
        assert loaded_node.title == orig.title
        assert loaded_node.optional == orig.optional
        assert loaded_node.subtask_count == orig.subtask_count
        assert loaded_node.body == orig.body
        assert loaded_node.archetype == orig.archetype
        assert loaded_node.mode == orig.mode
        assert loaded_node.instances == orig.instances

    # Edges are order-independent for equivalence
    orig_edges = {(e.source, e.target, e.kind) for e in graph.edges}
    loaded_edges = {(e.source, e.target, e.kind) for e in loaded.edges}
    assert loaded_edges == orig_edges

    assert loaded.order == graph.order

    conn.close()


# -- Property Test TS-105-P2: Status transition atomicity --------------------


@given(
    statuses=st.lists(_V3_STATUSES, min_size=1, max_size=10),
)
@settings(max_examples=30)
def test_status_transition_atomicity(statuses: list[str]) -> None:
    """TS-105-P2: After each status transition, load_execution_state reflects it.

    Property 2 from design.md: Every status transition is immediately visible
    on reload.

    Requirements: 105-REQ-2.1, 105-REQ-2.4
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)

    # Seed a single node
    conn.execute(
        "INSERT INTO plan_nodes (id, spec_name, group_number, title, sort_position) "
        "VALUES ('spec_a:1', 'spec_a', 1, 'Task 1', 0)"
    )

    node_id = "spec_a:1"
    for status in statuses:
        persist_node_status(conn, node_id, status)
        loaded = load_execution_state(conn)
        assert loaded[node_id] == status

    conn.close()


# -- Property Test TS-105-P3: Content hash stability -------------------------


@given(graph=valid_task_graphs())
@settings(max_examples=30)
def test_content_hash_stability(graph: TaskGraph) -> None:
    """TS-105-P3: Content hash is stable across save/load round-trips.

    Property 3 from design.md: For any TaskGraph, the hash before saving
    equals the hash computed from the loaded copy.

    Requirements: 105-REQ-1.4
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)

    hash_before = compute_plan_hash(graph)
    save_plan(graph, conn)
    loaded = load_plan(conn)

    assert loaded is not None
    hash_after = compute_plan_hash(loaded)

    assert hash_before == hash_after

    conn.close()


# -- Property Test TS-105-P4: Session record completeness --------------------


@given(record=session_outcome_records())
@settings(max_examples=30)
def test_session_record_completeness(record: SessionOutcomeRecord) -> None:
    """TS-105-P4: All session record fields survive a DB round-trip.

    Property 4 from design.md: For any SessionOutcomeRecord, record_session
    inserts a row whose columns match all fields of the record.

    Requirements: 105-REQ-3.1, 105-REQ-3.2
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)

    record_session(conn, record)

    row = conn.sql(
        "SELECT id, run_id, attempt, cost, model, archetype, commit_sha, "
        "error_message, is_transport_error, status, input_tokens, output_tokens "
        f"FROM session_outcomes WHERE id = '{record.id}'"
    ).fetchone()

    assert row is not None
    assert row[0] == record.id
    assert row[1] == record.run_id
    assert row[2] == record.attempt
    assert abs(row[3] - record.cost) < 1e-6
    assert row[4] == record.model
    assert row[5] == record.archetype
    assert row[6] == record.commit_sha
    assert row[7] == record.error_message  # NULL if None
    assert row[8] == record.is_transport_error
    assert row[9] == record.status
    assert row[10] == record.input_tokens
    assert row[11] == record.output_tokens

    conn.close()


# -- Property Test TS-105-P5: Run aggregate accuracy -------------------------


@given(
    deltas=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=10_000),
            st.integers(min_value=0, max_value=10_000),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=30)
def test_run_aggregate_accuracy(deltas: list[tuple[int, int, float]]) -> None:
    """TS-105-P5: Final run totals equal the exact sum of all update_run_totals calls.

    Property 5 from design.md: For any sequence of token/cost deltas, the
    final run row totals equal the sum of all deltas.

    Requirements: 105-REQ-4.3
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)

    run_id = "run_prop_test"
    create_run(conn, run_id, "hash_prop")

    expected_input = 0
    expected_output = 0
    expected_cost = 0.0

    for inp, out, cost in deltas:
        update_run_totals(conn, run_id, input_tokens=inp, output_tokens=out, cost=cost)
        expected_input += inp
        expected_output += out
        expected_cost += cost

    from agent_fox.engine.state import load_run

    run = load_run(conn, run_id)
    assert run is not None
    assert run.total_input_tokens == expected_input
    assert run.total_output_tokens == expected_output
    assert abs(run.total_cost - expected_cost) < 1e-4

    conn.close()
