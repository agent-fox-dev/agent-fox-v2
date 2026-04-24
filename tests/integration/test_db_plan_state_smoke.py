"""Integration smoke tests for DB-based plan state.

Test Spec: TS-105-SMOKE-1, TS-105-SMOKE-2
Requirements: 105-REQ-5.4, 105-REQ-6.1, 105-REQ-6.2, 105-REQ-6.3
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# NOTE: These imports will fail with ImportError until task groups 2-4 implement
# the new DB-based persistence layer and orchestrator wiring.
from agent_fox.engine.state import (  # noqa: F401
    SessionOutcomeRecord,
    complete_run,
    create_run,
    load_execution_state,
    persist_node_status,
    record_session,
    update_run_totals,
)
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

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
    is_transport_error  BOOLEAN DEFAULT FALSE
);
"""

# -- Helpers ------------------------------------------------------------------


def _make_two_node_graph() -> TaskGraph:
    """Build a simple two-node sequential TaskGraph for smoke tests."""
    return TaskGraph(
        nodes={
            "smoke_spec:1": Node(
                id="smoke_spec:1",
                spec_name="smoke_spec",
                group_number=1,
                title="Write failing tests",
                optional=False,
                subtask_count=4,
                body="Create all spec test files",
                archetype="coder",
            ),
            "smoke_spec:2": Node(
                id="smoke_spec:2",
                spec_name="smoke_spec",
                group_number=2,
                title="Implement persistence",
                optional=False,
                subtask_count=5,
                body="Implement DB-based save/load",
                archetype="coder",
            ),
        },
        edges=[
            Edge(source="smoke_spec:1", target="smoke_spec:2", kind="intra_spec"),
        ],
        order=["smoke_spec:1", "smoke_spec:2"],
        metadata=PlanMetadata(
            created_at="2026-01-01T00:00:00",
            fast_mode=False,
            version="3.0.0",
        ),
    )


def _simulate_session(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    node_id: str,
    attempt: int = 1,
) -> None:
    """Simulate a session: in_progress → completed with a recorded outcome."""
    persist_node_status(conn, node_id, "in_progress")

    record = SessionOutcomeRecord(
        id=f"session_{node_id}_{attempt}",
        spec_name=node_id.split(":")[0],
        task_group=node_id.split(":")[1],
        node_id=node_id,
        touched_path="agent_fox/engine/state.py",
        status="completed",
        input_tokens=1500,
        output_tokens=800,
        duration_ms=45_000,
        created_at="2026-01-01T00:00:00",
        run_id=run_id,
        attempt=attempt,
        cost=0.07,
        model="claude-sonnet-4-6",
        archetype="coder",
        commit_sha="deadbeef",
        error_message=None,
        is_transport_error=False,
    )
    record_session(conn, record)
    update_run_totals(conn, run_id, input_tokens=1500, output_tokens=800, cost=0.07)
    persist_node_status(conn, node_id, "completed")


# -- TS-105-SMOKE-1: Full orchestration cycle with DB state -------------------


def test_full_orchestration_cycle(tmp_path: Path) -> None:
    """TS-105-SMOKE-1: Full plan + execution cycle uses DB only — no files.

    Verifies:
    - plan_nodes has 2 rows with status 'completed'
    - session_outcomes has 2 rows with run_id and model populated
    - runs has 1 row with status 'completed'
    - No plan.json or state.jsonl created on disk

    Requirements: 105-REQ-5.4, 105-REQ-6.2
    """
    # Use a file-based DB in tmp_path (not in-memory) to verify no side files
    agent_fox_dir = tmp_path / ".agent-fox"
    agent_fox_dir.mkdir(parents=True)
    db_path = str(agent_fox_dir / "knowledge.duckdb")

    conn = duckdb.connect(db_path)
    conn.execute(_FULL_SCHEMA_DDL)

    # Step 1: Plan — save plan to DB (no plan.json)
    graph = _make_two_node_graph()
    save_plan(graph, conn)

    # Step 2: Load plan and initialize run
    loaded_graph = load_plan(conn)
    assert loaded_graph is not None
    assert len(loaded_graph.nodes) == 2

    run_id = "smoke_run_1"
    create_run(conn, run_id, "smoke_hash")

    # Step 3: Execute each node with mock sessions
    for node_id in loaded_graph.order:
        _simulate_session(conn, run_id, node_id)

    # Step 4: Complete the run
    complete_run(conn, run_id, "completed")

    conn.close()

    # -- Assertions -----------------------------------------------------------

    # Reopen to verify final state
    verify_conn = duckdb.connect(db_path)

    _row = verify_conn.sql("SELECT count(*) FROM plan_nodes WHERE status = 'completed'").fetchone()
    assert _row is not None
    completed_nodes = _row[0]
    assert completed_nodes == 2, f"Expected 2 completed nodes, got {completed_nodes}"

    _row = verify_conn.sql("SELECT count(*) FROM session_outcomes").fetchone()
    assert _row is not None
    session_count = _row[0]
    assert session_count == 2, f"Expected 2 session rows, got {session_count}"

    # All sessions must have run_id and model populated
    _row = verify_conn.sql(
        "SELECT count(*) FROM session_outcomes WHERE run_id IS NULL OR model IS NULL"
    ).fetchone()
    assert _row is not None
    incomplete_sessions = _row[0]
    assert incomplete_sessions == 0

    _row = verify_conn.execute("SELECT status FROM runs WHERE id = ?", [run_id]).fetchone()
    assert _row is not None
    run_status = _row[0]
    assert run_status == "completed"

    verify_conn.close()

    # No file-based state files should exist
    plan_json = agent_fox_dir / "plan.json"
    state_jsonl = agent_fox_dir / "state.jsonl"
    assert not plan_json.exists(), "plan.json must not be created"
    assert not state_jsonl.exists(), "state.jsonl must not be created"


# -- TS-105-SMOKE-2: Concurrent status read during execution ------------------


def test_concurrent_status_read(tmp_path: Path) -> None:
    """TS-105-SMOKE-2: Read-only connection sees consistent state after write commits.

    DuckDB 1.5.1 does not allow a read_only=True and a write connection to the
    same file in the same OS process simultaneously.  In production ``af status``
    runs in a separate process from the orchestrator, so cross-process concurrent
    access is fully supported via DuckDB's WAL mechanism.

    This test validates the relevant invariant: a read-only connection opened
    after the write connection releases the file sees a consistent, non-partial
    view of the data.

    Requirements: 105-REQ-6.1, 105-REQ-6.3
    """
    db_path = str(tmp_path / "concurrent_test.duckdb")

    # Phase 1: Write connection (simulates orchestrator writing state)
    write_conn = duckdb.connect(db_path)
    write_conn.execute(_FULL_SCHEMA_DDL)

    graph = _make_two_node_graph()
    save_plan(graph, write_conn)
    persist_node_status(write_conn, "smoke_spec:1", "in_progress")

    # Close write connection so read-only can open (different access modes
    # require separate processes in DuckDB 1.5.1; we approximate with sequential).
    write_conn.close()

    # Phase 2: Read-only connection (simulates `af status` CLI in a separate process)
    read_conn = duckdb.connect(db_path, read_only=True)

    rows = read_conn.sql("SELECT id, status FROM plan_nodes").fetchall()
    assert len(rows) == 2, f"Expected 2 plan_nodes rows, got {len(rows)}"

    valid_statuses = {
        "pending",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "skipped",
        "cost_blocked",
        "merge_blocked",
    }
    for node_id, status in rows:
        assert status in valid_statuses, f"Node {node_id!r} has invalid status {status!r}"

    # The transitioned node must be visible in read-only view
    in_progress_ids = [nid for nid, status in rows if status == "in_progress"]
    assert len(in_progress_ids) >= 1

    read_conn.close()

    # Phase 3: Write connection resumes (orchestrator continues after CLI read)
    write_conn2 = duckdb.connect(db_path)
    persist_node_status(write_conn2, "smoke_spec:1", "completed")
    persist_node_status(write_conn2, "smoke_spec:2", "in_progress")

    final_rows = write_conn2.sql("SELECT id, status FROM plan_nodes ORDER BY id").fetchall()
    statuses = {nid: status for nid, status in final_rows}
    assert statuses["smoke_spec:1"] == "completed"
    assert statuses["smoke_spec:2"] == "in_progress"

    write_conn2.close()
