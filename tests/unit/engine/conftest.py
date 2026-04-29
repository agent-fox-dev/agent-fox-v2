"""Fixtures for orchestrator engine tests.

Provides mock session runner factory, mock plan builder, temporary state paths,
and helper functions for constructing test graphs and execution states.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pytest

from agent_fox.core.config import OrchestratorConfig

# -- Mock session outcome matching SessionOutcome from spec 03 --------


@dataclass(frozen=True)
class MockSessionOutcome:
    """Minimal session outcome for orchestrator tests."""

    node_id: str
    status: str  # "completed" | "failed" | "timeout"
    input_tokens: int = 100
    output_tokens: int = 200
    cost: float = 0.10
    duration_ms: int = 5000
    error_message: str | None = None
    spec_name: str = "test_spec"
    task_group: int = 1
    archetype: str = "coder"


# -- Mock session runner that records dispatch calls -------------------


@dataclass
class MockSessionRunner:
    """Records all session dispatches and returns pre-configured outcomes.

    Attributes:
        calls: List of (node_id, attempt, previous_error) for each dispatch.
        outcomes: Dict mapping node_id to a list of outcomes (one per attempt).
            If not specified, defaults to a successful outcome.
    """

    calls: list[tuple[str, int, str | None]] = field(default_factory=list)
    outcomes: dict[str, list[MockSessionOutcome]] = field(default_factory=dict)
    default_cost: float = 0.10

    def configure(
        self,
        node_id: str,
        results: list[MockSessionOutcome],
    ) -> None:
        """Configure outcomes for a specific node."""
        self.outcomes[node_id] = results

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None = None,
    ) -> MockSessionOutcome:
        """Record the call and return the configured outcome."""
        self.calls.append((node_id, attempt, previous_error))

        if node_id in self.outcomes:
            # Use the attempt-1 index (0-based), clamping to last
            idx = min(attempt - 1, len(self.outcomes[node_id]) - 1)
            return self.outcomes[node_id][idx]

        # Default: success
        return MockSessionOutcome(
            node_id=node_id,
            status="completed",
            cost=self.default_cost,
        )


# -- Plan builder helpers -----------------------------------------------


def make_plan_json(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]],
    order: list[str] | None = None,
) -> str:
    """Build a plan.json string from node/edge definitions.

    Args:
        nodes: Dict of node_id -> node properties.
        edges: List of {"source": ..., "target": ..., "kind": ...} dicts.
        order: Topological order. Defaults to node keys order.

    Returns:
        JSON string suitable for writing to plan.json.
    """
    full_nodes: dict[str, Any] = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        spec_name = parts[0] if len(parts) > 1 else "test_spec"
        group_number = int(parts[-1]) if parts[-1].isdigit() else 1
        node_data: dict[str, Any] = {
            "id": nid,
            "spec_name": props.get("spec_name", spec_name),
            "group_number": props.get("group_number", group_number),
            "title": props.get("title", f"Task {nid}"),
            "optional": props.get("optional", False),
            "status": props.get("status", "pending"),
            "subtask_count": props.get("subtask_count", 0),
            "body": props.get("body", ""),
            "archetype": props.get("archetype", "coder"),
        }
        if "mode" in props:
            node_data["mode"] = props["mode"]
        full_nodes[nid] = node_data

    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": full_nodes,
        "edges": edges,
        "order": order if order is not None else list(nodes.keys()),
    }
    return json.dumps(plan, indent=2)


def write_plan_file(
    plan_dir: Path,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]],
    order: list[str] | None = None,
) -> Path:
    """Write a plan.json file and return its path."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    plan_path.write_text(make_plan_json(nodes, edges, order))
    return plan_path


# -- Shared fixtures -----------------------------------------------------


@pytest.fixture
def tmp_plan_dir(tmp_path: Path) -> Path:
    """Return a path to a temporary .agent-fox directory for plan.json."""
    plan_dir = tmp_path / ".agent-fox"
    plan_dir.mkdir(parents=True, exist_ok=True)
    return plan_dir


@pytest.fixture
def mock_runner() -> MockSessionRunner:
    """Provide a fresh MockSessionRunner."""
    return MockSessionRunner()


@pytest.fixture
def default_orch_config() -> OrchestratorConfig:
    """Default orchestrator config for tests."""
    return OrchestratorConfig()


@pytest.fixture
def serial_config() -> OrchestratorConfig:
    """Orchestrator config with serial execution (parallelism=1)."""
    return OrchestratorConfig(parallel=1, inter_session_delay=0)


@pytest.fixture
def parallel_config() -> OrchestratorConfig:
    """Orchestrator config with parallel execution (parallelism=4)."""
    return OrchestratorConfig(parallel=4, inter_session_delay=0)


@pytest.fixture
def no_retry_config() -> OrchestratorConfig:
    """Orchestrator config with no retries."""
    return OrchestratorConfig(max_retries=0, inter_session_delay=0)


# -- DuckDB helpers for plan persistence (post-issue-446) ------------------


def _create_db_with_schema() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with plan tables."""
    conn = duckdb.connect(":memory:")
    from agent_fox.knowledge.migrations import run_migrations

    run_migrations(conn)
    return conn


def write_plan_to_db(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]],
    order: list[str] | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> duckdb.DuckDBPyConnection:
    """Write a plan to an in-memory DuckDB and return the connection.

    This replaces ``write_plan_file`` for tests that need plan persistence.
    """
    from agent_fox.graph.persistence import save_plan
    from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph

    if conn is None:
        conn = _create_db_with_schema()

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

    edge_objs = [Edge(source=e["source"], target=e["target"], kind=e.get("kind", "dependency")) for e in edges]
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


@pytest.fixture
def db_conn_with_schema() -> duckdb.DuckDBPyConnection:
    """Provide a fresh in-memory DuckDB with plan tables."""
    conn = _create_db_with_schema()
    yield conn
    conn.close()

@pytest.fixture
def tmp_worktree_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with a develop branch and initial commit.

    Used by dispatch health check tests that need a real git repo.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "develop"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo

