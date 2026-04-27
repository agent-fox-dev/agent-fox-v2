"""Fixtures for reporting and reset engine tests.

Provides helpers to create DuckDB-backed plans and execution states with
various task states, session records, and dependency structures.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.engine.state import ExecutionState, SessionRecord

# -- State file helpers -------------------------------------------------------


def make_session_record(
    node_id: str = "test_spec:1",
    attempt: int = 1,
    status: str = "completed",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cost: float = 0.10,
    duration_ms: int = 5000,
    error_message: str | None = None,
    timestamp: str | None = None,
    model: str = "STANDARD",
    files_touched: list[str] | None = None,
) -> SessionRecord:
    """Create a SessionRecord with sensible defaults."""
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        duration_ms=duration_ms,
        error_message=error_message,
        timestamp=timestamp,
        model=model,
        files_touched=files_touched or [],
    )


def make_execution_state(
    node_states: dict[str, str] | None = None,
    session_history: list[SessionRecord] | None = None,
    plan_hash: str = "abc123",
) -> ExecutionState:
    """Create an ExecutionState with computed totals.

    Automatically calculates total_input_tokens, total_output_tokens,
    total_cost, and total_sessions from session_history.
    """
    if node_states is None:
        node_states = {"test_spec:1": "pending"}
    if session_history is None:
        session_history = []

    total_input = sum(r.input_tokens for r in session_history)
    total_output = sum(r.output_tokens for r in session_history)
    total_cost = sum(r.cost for r in session_history)
    total_sessions = len(session_history)

    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states,
        session_history=session_history,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
        run_status="running",
    )


@contextmanager
def mock_state(state: ExecutionState):
    """Context manager to mock load_state_from_db to return the given state."""
    with patch("agent_fox.reporting.standup.load_state_from_db", return_value=state):
        yield


# -- Plan DB helpers ----------------------------------------------------------


def write_plan_to_db(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]] | None = None,
    order: list[str] | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> duckdb.DuckDBPyConnection:
    """Write a plan to an in-memory DuckDB and return the connection.

    Mirrors the engine conftest helper but is self-contained for
    reporting tests.
    """
    from agent_fox.graph.persistence import save_plan
    from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
    from agent_fox.knowledge.migrations import run_migrations

    if edges is None:
        edges = []

    if conn is None:
        conn = duckdb.connect(":memory:")
        run_migrations(conn)

    node_objs: dict[str, Node] = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        spec_name = parts[0] if len(parts) > 1 else "test_spec"
        group_number = int(parts[-1]) if parts[-1].isdigit() else 1
        node_objs[nid] = Node(
            id=nid,
            spec_name=props.get("spec_name", spec_name),
            group_number=props.get("group_number", group_number),
            title=props.get("title", f"Task {nid}"),
            optional=props.get("optional", False),
            status=NodeStatus(props.get("status", "pending")),
            subtask_count=props.get("subtask_count", 0),
            body=props.get("body", ""),
            archetype=props.get("archetype", "coder"),
            mode=props.get("mode"),
            instances=props.get("instances", 1),
        )

    edge_objs = [
        Edge(source=e["source"], target=e["target"], kind=e.get("kind", "dependency"))
        for e in edges
    ]
    graph = TaskGraph(
        nodes=node_objs,
        edges=edge_objs,
        order=order if order is not None else list(nodes.keys()),
        metadata=PlanMetadata(
            created_at="2026-01-01T00:00:00",
            fast_mode=False,
            filtered_spec=None,
            version="0.1.0",
        ),
    )
    save_plan(graph, conn)
    return conn


# -- Shared fixtures ----------------------------------------------------------


@pytest.fixture
def tmp_worktrees_dir(tmp_path) -> "Path":
    """Return a path to a temporary worktrees directory."""
    from pathlib import Path

    wtdir = tmp_path / ".agent-fox" / "worktrees"
    wtdir.mkdir(parents=True, exist_ok=True)
    return wtdir


def hours_ago(n: int) -> str:
    """Return an ISO 8601 timestamp for n hours ago."""
    return (datetime.now(UTC) - timedelta(hours=n)).isoformat()
