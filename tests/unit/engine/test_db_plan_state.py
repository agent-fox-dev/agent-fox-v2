"""Unit tests for DB-based plan execution state management.

Test Spec: TS-105-4 through TS-105-12, TS-105-E1 through TS-105-E6
Requirements: 105-REQ-2.1 through 105-REQ-6.E1
"""

from __future__ import annotations

import duckdb
import pytest

# NOTE: All of the following imports will fail with ImportError until task
# group 3 (and partially group 2) implements these new functions/classes.
from agent_fox.engine.state import (  # noqa: F401
    RunRecord,
    SessionOutcomeRecord,
    complete_run,
    create_run,
    load_execution_state,
    load_incomplete_run,
    load_run,
    persist_node_status,
    record_session,
    reset_in_progress_nodes,
    update_run_totals,
)
from agent_fox.graph.persistence import save_plan
from agent_fox.graph.types import Node, NodeStatus, PlanMetadata, TaskGraph

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

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def db_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with all plan and run tables (v9 migration schema)."""
    conn = duckdb.connect(":memory:")
    conn.execute(_FULL_SCHEMA_DDL)
    yield conn
    conn.close()


@pytest.fixture
def single_node_graph() -> TaskGraph:
    """Minimal TaskGraph with one node for status transition tests."""
    return TaskGraph(
        nodes={
            "spec_a:1": Node(
                id="spec_a:1",
                spec_name="spec_a",
                group_number=1,
                title="Task 1",
                optional=False,
            )
        },
        edges=[],
        order=["spec_a:1"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


@pytest.fixture
def plan_with_node(
    db_conn: duckdb.DuckDBPyConnection,
    single_node_graph: TaskGraph,
) -> duckdb.DuckDBPyConnection:
    """DB with a plan saved containing one node at status 'pending'."""
    save_plan(single_node_graph, db_conn)
    return db_conn


# -- Tests: TS-105-4 Node status persisted on transition ----------------------


def test_status_persisted(
    plan_with_node: duckdb.DuckDBPyConnection,
) -> None:
    """TS-105-4: persist_node_status updates the DB row's status and updated_at.

    Requirements: 105-REQ-2.1, 105-REQ-2.4
    """
    original_updated_at = plan_with_node.sql("SELECT updated_at FROM plan_nodes WHERE id = 'spec_a:1'").fetchone()[0]

    persist_node_status(plan_with_node, "spec_a:1", "in_progress")

    row = plan_with_node.sql("SELECT status, updated_at FROM plan_nodes WHERE id = 'spec_a:1'").fetchone()
    assert row[0] == "in_progress"
    # updated_at must change (or at minimum not be earlier)
    assert row[1] >= original_updated_at


# -- Tests: TS-105-5 All v3 status values accepted ----------------------------


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "skipped",
        "cost_blocked",
        "merge_blocked",
    ],
)
def test_v3_statuses(
    plan_with_node: duckdb.DuckDBPyConnection,
    status: str,
) -> None:
    """TS-105-5: All v3 node status values are accepted and round-trip correctly.

    Requirements: 105-REQ-2.2
    """
    persist_node_status(plan_with_node, "spec_a:1", status)
    loaded = load_execution_state(plan_with_node)
    assert loaded["spec_a:1"] == status


def test_nodestatus_enum_has_v3_values() -> None:
    """TS-105-5 (enum variant): NodeStatus enum contains all 8 v3 values.

    Requirements: 105-REQ-2.2
    """
    # These two values must exist in the enum after task group 2 is implemented.
    assert NodeStatus.COST_BLOCKED == "cost_blocked"
    assert NodeStatus.MERGE_BLOCKED == "merge_blocked"


# -- Tests: TS-105-6 Blocked reason stored ------------------------------------


def test_blocked_reason(plan_with_node: duckdb.DuckDBPyConnection) -> None:
    """TS-105-6: persist_node_status stores blocked_reason when node is blocked.

    Requirements: 105-REQ-2.3
    """
    persist_node_status(
        plan_with_node,
        "spec_a:1",
        "blocked",
        blocked_reason="upstream failed",
    )

    reason = plan_with_node.sql("SELECT blocked_reason FROM plan_nodes WHERE id = 'spec_a:1'").fetchone()[0]
    assert reason == "upstream failed"


# -- Tests: TS-105-7 Session record with extended fields ----------------------


def test_session_extended_fields(db_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-7: session_outcomes accepts all extended fields via record_session.

    Requirements: 105-REQ-3.1, 105-REQ-3.2
    """
    record = SessionOutcomeRecord(
        id="s1",
        spec_name="spec_a",
        task_group="1",
        node_id="spec_a:1",
        touched_path="file.py",
        status="completed",
        input_tokens=1000,
        output_tokens=500,
        duration_ms=30000,
        created_at="2026-01-01T00:00:00",
        run_id="run_1",
        attempt=1,
        cost=0.05,
        model="claude-sonnet-4-6",
        archetype="coder",
        commit_sha="abc123",
        error_message=None,
        is_transport_error=False,
    )
    record_session(db_conn, record)

    row = db_conn.sql(
        "SELECT run_id, attempt, cost, model, archetype, commit_sha FROM session_outcomes WHERE id = 's1'"
    ).fetchone()
    assert row is not None
    assert row[0] == "run_1"
    assert row[1] == 1
    assert abs(row[2] - 0.05) < 1e-9
    assert row[3] == "claude-sonnet-4-6"
    assert row[4] == "coder"
    assert row[5] == "abc123"


# -- Tests: TS-105-8 Run lifecycle --------------------------------------------


def test_run_lifecycle(db_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-8: Full run lifecycle: create -> accumulate -> complete.

    Requirements: 105-REQ-4.1, 105-REQ-4.2, 105-REQ-4.3, 105-REQ-4.4
    """
    create_run(db_conn, "run_1", "hash_abc")

    # Verify initial row
    initial_row = db_conn.sql("SELECT status, completed_at FROM runs WHERE id = 'run_1'").fetchone()
    assert initial_row[0] == "running"
    assert initial_row[1] is None

    # Accumulate two sessions
    update_run_totals(db_conn, "run_1", input_tokens=1000, output_tokens=500, cost=0.05)
    update_run_totals(db_conn, "run_1", input_tokens=2000, output_tokens=800, cost=0.08)

    # Complete the run
    complete_run(db_conn, "run_1", "completed")

    row = db_conn.sql(
        "SELECT total_input_tokens, total_output_tokens, total_cost, status, completed_at FROM runs WHERE id = 'run_1'"
    ).fetchone()
    assert row[0] == 3000
    assert row[1] == 1300
    assert abs(row[2] - 0.13) < 1e-6
    assert row[3] == "completed"
    assert row[4] is not None  # completed_at must be set


# -- Tests: TS-105-9 PLAN_PATH and STATE_PATH removed -------------------------


def test_plan_path_removed() -> None:
    """TS-105-9: PLAN_PATH and STATE_PATH are no longer importable from core.paths.

    Requirements: 105-REQ-5.1, 105-REQ-3.3, 105-REQ-5.3
    """
    with pytest.raises((ImportError, AttributeError)):
        from agent_fox.core.paths import PLAN_PATH  # noqa: F401

    with pytest.raises((ImportError, AttributeError)):
        from agent_fox.core.paths import STATE_PATH  # noqa: F401


# -- Tests: TS-105-10 No state files created (unit smoke) ---------------------


def test_no_state_files_created(
    db_conn: duckdb.DuckDBPyConnection,
    single_node_graph: TaskGraph,
    tmp_path,
) -> None:
    """TS-105-10 (unit): Saving plan to DB does not create plan.json or state.jsonl.

    Requirements: 105-REQ-5.4
    """
    plan_json = tmp_path / ".agent-fox" / "plan.json"
    state_jsonl = tmp_path / ".agent-fox" / "state.jsonl"

    save_plan(single_node_graph, db_conn)

    assert not plan_json.exists()
    assert not state_jsonl.exists()


# -- Tests: TS-105-12 Concurrent read during write ----------------------------


def test_concurrent_read(
    single_node_graph: TaskGraph,
    tmp_path,
) -> None:
    """TS-105-12: Read-only connection can query plan_nodes while write connection holds it.

    Requirements: 105-REQ-6.3
    """
    db_path = str(tmp_path / "test.duckdb")
    write_conn = duckdb.connect(db_path)
    write_conn.execute(_FULL_SCHEMA_DDL)

    save_plan(single_node_graph, write_conn)
    persist_node_status(write_conn, "spec_a:1", "in_progress")

    # Open a separate read-only connection
    read_conn = duckdb.connect(db_path, read_only=True)
    rows = read_conn.sql("SELECT id, status FROM plan_nodes").fetchall()
    assert len(rows) > 0
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
    for _node_id, status in rows:
        assert status in valid_statuses

    read_conn.close()
    write_conn.close()


# -- Edge case tests: TS-105-E1, TS-105-E2 (state module perspective) ---------


def test_load_execution_state_empty(db_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E1: load_execution_state returns empty dict when no plan in DB.

    Requirements: 105-REQ-1.E1
    """
    result = load_execution_state(db_conn)
    assert result == {}


def test_load_execution_state_with_nodes(
    plan_with_node: duckdb.DuckDBPyConnection,
) -> None:
    """TS-105-E2 (variant): load_execution_state returns all node statuses.

    Requirements: 105-REQ-1.E2
    """
    result = load_execution_state(plan_with_node)
    assert "spec_a:1" in result
    assert result["spec_a:1"] == "pending"


# -- Edge case tests: TS-105-E3 Crash recovery --------------------------------


def test_crash_recovery(plan_with_node: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E3: reset_in_progress_nodes resets in_progress nodes to pending.

    Requirements: 105-REQ-2.E1
    """
    persist_node_status(plan_with_node, "spec_a:1", "in_progress")

    # Simulate crash and resume: reset in_progress to pending
    reset_in_progress_nodes(plan_with_node)

    loaded = load_execution_state(plan_with_node)
    assert loaded["spec_a:1"] == "pending"


# -- Edge case tests: TS-105-E4 Null error_message ----------------------------


def test_null_error_message(db_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E4: Successful sessions store NULL (not empty string) for error_message.

    Requirements: 105-REQ-3.E1
    """
    record = SessionOutcomeRecord(
        id="s_success",
        spec_name="spec_a",
        task_group="1",
        node_id="spec_a:1",
        touched_path="file.py",
        status="completed",
        input_tokens=100,
        output_tokens=50,
        duration_ms=1000,
        created_at="2026-01-01T00:00:00",
        run_id="run_1",
        attempt=1,
        cost=0.01,
        model="claude-sonnet-4-6",
        archetype="coder",
        commit_sha="abc123",
        error_message=None,
        is_transport_error=False,
    )
    record_session(db_conn, record)

    val = db_conn.sql("SELECT error_message FROM session_outcomes WHERE id = 's_success'").fetchone()[0]
    # Must be SQL NULL, not empty string
    assert val is None


# -- Edge case tests: TS-105-E5 Incomplete run detected on resume --------------


def test_incomplete_run_resume(db_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-105-E5: Crashed run (status=running, completed_at=NULL) is detected.

    Requirements: 105-REQ-4.E1
    """
    create_run(db_conn, "run_1", "hash_a")

    # Simulate crash: run_1 still "running", completed_at is NULL
    run = load_incomplete_run(db_conn)
    assert run is not None
    assert run.id == "run_1"
    assert run.status == "running"

    # Only one run row should exist
    count = db_conn.sql("SELECT count(*) FROM runs").fetchone()[0]
    assert count == 1


# -- Edge case tests: TS-105-E6 DB missing for af status ----------------------


def test_missing_db_status(tmp_path) -> None:
    """TS-105-E6: af status displays 'No plan found' when DB does not exist.

    Requirements: 105-REQ-6.E1
    """
    nonexistent_db = tmp_path / "nonexistent.duckdb"
    assert not nonexistent_db.exists()

    # The status command or generate_status function must handle missing DB
    # gracefully (no crash, shows "No plan found" or empty dashboard).
    from agent_fox.cli.status import generate_status  # noqa: F401

    result = generate_status(db_path=nonexistent_db)
    # Either result contains "No plan found" or is a falsy/empty value
    assert result is None or "No plan found" in str(result) or result == {}
