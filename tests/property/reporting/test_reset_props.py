"""Property tests for reset engine.

Test Spec: TS-07-P2 (reset preserves completed), TS-07-P4 (cascade correctness)
Properties: Property 4, Property 5 from design.md
Requirements: 07-REQ-4.1, 07-REQ-5.2
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.reset import (
    _find_sole_blocker_dependents,
    reset_all,
)
from agent_fox.engine.state import ExecutionState
from agent_fox.graph.types import (
    Edge,
    Node,
    NodeStatus,
    PlanMetadata,
    TaskGraph,
)

# -- Hypothesis strategies ---------------------------------------------------


@st.composite
def execution_states_with_completed(draw: st.DrawFn) -> dict[str, str]:
    """Generate node_states dicts that have at least one completed task.

    Returns a dict of node_id -> status where at least one is completed
    and others may be failed, blocked, in_progress, or pending.
    """
    num_nodes = draw(st.integers(min_value=2, max_value=8))
    statuses = ["pending", "completed", "failed", "blocked", "in_progress"]

    # Ensure at least one completed
    node_states: dict[str, str] = {"s:1": "completed"}
    for i in range(2, num_nodes + 1):
        node_states[f"s:{i}"] = draw(st.sampled_from(statuses))

    return node_states


@st.composite
def task_graphs_with_blocker(
    draw: st.DrawFn,
) -> tuple[str, TaskGraph, dict[str, str]]:
    """Generate a task graph where one task blocks one or more others.

    Returns:
        (blocker_id, TaskGraph, node_states) where:
        - blocker_id is the ID of the task to be reset
        - The graph has edges from blocker_id to downstream tasks
        - node_states has the blocker as "failed" and dependents as "blocked"
    """
    # blocker + 1-3 dependents + 0-2 independent completed tasks
    num_deps = draw(st.integers(min_value=1, max_value=3))
    num_completed = draw(st.integers(min_value=0, max_value=2))

    blocker_id = "s:1"
    nodes: dict[str, Node] = {
        blocker_id: Node(
            id=blocker_id,
            spec_name="s",
            group_number=1,
            title="Blocker",
            optional=False,
            status=NodeStatus.FAILED,
        ),
    }
    edges: list[Edge] = []
    order: list[str] = [blocker_id]
    node_states: dict[str, str] = {blocker_id: "failed"}

    # Add dependent tasks
    for i in range(2, 2 + num_deps):
        nid = f"s:{i}"
        nodes[nid] = Node(
            id=nid,
            spec_name="s",
            group_number=i,
            title=f"Dep {i}",
            optional=False,
            status=NodeStatus.BLOCKED,
        )
        edges.append(Edge(source=blocker_id, target=nid, kind="intra_spec"))

        # Some dependents also have another completed predecessor
        if draw(st.booleans()):
            comp_id = f"c:{i}"
            nodes[comp_id] = Node(
                id=comp_id,
                spec_name="c",
                group_number=i,
                title=f"Completed dep {i}",
                optional=False,
                status=NodeStatus.COMPLETED,
            )
            edges.append(Edge(source=comp_id, target=nid, kind="cross_spec"))
            order.append(comp_id)
            node_states[comp_id] = "completed"

        order.append(nid)
        node_states[nid] = "blocked"

    # Add independent completed tasks
    for i in range(100, 100 + num_completed):
        nid = f"s:{i}"
        nodes[nid] = Node(
            id=nid,
            spec_name="s",
            group_number=i,
            title=f"Completed {i}",
            optional=False,
            status=NodeStatus.COMPLETED,
        )
        order.append(nid)
        node_states[nid] = "completed"

    graph = TaskGraph(
        nodes=nodes,
        edges=edges,
        order=order,
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )

    return blocker_id, graph, node_states


# -- Helpers -----------------------------------------------------------------


def _write_plan_from_graph(plan_dir: Path, graph: TaskGraph) -> Path:
    """Serialize a TaskGraph to plan.json for testing."""
    from agent_fox.graph.persistence import save_plan

    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    save_plan(graph, plan_path)
    return plan_path


def _make_state(node_states: dict[str, str]) -> ExecutionState:
    """Create a minimal ExecutionState for test mocking."""
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# TS-07-P2: Reset preserves completed tasks
# Property 4: Full reset never changes completed tasks
# Requirement: 07-REQ-4.1
# ---------------------------------------------------------------------------


class TestResetPreservesCompleted:
    """TS-07-P2: Full reset never changes completed tasks."""

    @given(node_states=execution_states_with_completed())
    @settings(max_examples=50)
    def test_completed_tasks_never_in_reset_list(
        self,
        node_states: dict[str, str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """For any state, completed tasks are absent from reset_tasks."""
        from unittest.mock import MagicMock, patch

        tmp_path = tmp_path_factory.mktemp("reset")
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "plan.json"
        plan_data = {
            "metadata": {
                "created_at": "2026-01-01T00:00:00",
                "fast_mode": False,
                "filtered_spec": None,
                "version": "0.1.0",
            },
            "nodes": {
                nid: {
                    "id": nid,
                    "spec_name": nid.split(":")[0],
                    "group_number": int(nid.split(":")[1]),
                    "title": f"Task {nid}",
                    "optional": False,
                    "status": "pending",
                    "subtask_count": 0,
                    "body": "",
                }
                for nid in node_states
            },
            "edges": [],
            "order": list(node_states.keys()),
        }
        plan_path.write_text(json.dumps(plan_data, indent=2))

        state = _make_state(node_states)
        mock_conn = MagicMock()
        completed_ids = {nid for nid, s in node_states.items() if s == "completed"}

        with patch("agent_fox.engine.reset.load_state_from_db", return_value=state):
            result = reset_all(plan_path, worktrees_dir, repo_path, db_conn=mock_conn)

        assert completed_ids.isdisjoint(set(result.reset_tasks))


# ---------------------------------------------------------------------------
# TS-07-P4: Cascade unblock correctness
# Property 5: Downstream unblocked iff all non-reset preds completed
# Requirement: 07-REQ-5.2
# ---------------------------------------------------------------------------


class TestCascadeUnblockCorrectness:
    """TS-07-P4: Cascade unblock correctness property."""

    @given(data=task_graphs_with_blocker())
    @settings(max_examples=50)
    def test_unblocked_tasks_have_all_preds_completed_or_reset(
        self,
        data: tuple[str, TaskGraph, dict[str, str]],
    ) -> None:
        """For each unblocked task, every predecessor is completed or is
        the reset target."""
        blocker_id, graph, node_states = data

        # Build a mock state-like object for the internal function
        state = ExecutionState(
            plan_hash="abc123",
            node_states=node_states,
        )

        unblockable = _find_sole_blocker_dependents(
            blocker_id,
            graph,
            state,
        )

        for downstream_id in unblockable:
            preds = graph.predecessors(downstream_id)
            for pred in preds:
                assert node_states[pred] == "completed" or pred == blocker_id, (
                    f"Downstream {downstream_id} was unblocked but predecessor "
                    f"{pred} has status {node_states[pred]}, not completed, "
                    f"and is not the reset target {blocker_id}"
                )
