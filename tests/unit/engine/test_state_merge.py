"""Tests for state merging on plan hash mismatch.

Verifies that _load_or_init_state carries forward completed/skipped
statuses from old state when the plan hash changes, preventing
already-finished tasks from being re-executed.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.engine.engine import _load_or_init_state, _seed_node_states_from_graph
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.engine.state_init import _init_attempt_tracker
from agent_fox.graph.types import Node, NodeStatus, TaskGraph


def _make_state(
    plan_hash: str = "old_hash",
    node_states: dict[str, str] | None = None,
    total_sessions: int = 0,
    total_cost: float = 0.0,
    session_history: list[SessionRecord] | None = None,
    blocked_reasons: dict[str, str] | None = None,
) -> ExecutionState:
    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states or {},
        session_history=session_history or [],
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
        blocked_reasons=blocked_reasons or {},
    )


def _make_graph(**statuses: str) -> TaskGraph:
    """Build a TaskGraph. Keys are node IDs, values are status strings."""
    nodes = {
        nid: Node(
            id=nid,
            spec_name="s",
            group_number=1,
            title=nid,
            optional=False,
            status=NodeStatus(status),
        )
        for nid, status in statuses.items()
    }
    return TaskGraph(nodes=nodes, edges=[], order=list(statuses.keys()))


class TestSeedNodeStates:
    """Unit tests for _seed_node_states_from_graph helper."""

    def test_pending_by_default(self) -> None:
        graph = _make_graph(a="pending", b="pending")
        result = _seed_node_states_from_graph(graph)
        assert result == {"a": "pending", "b": "pending"}

    def test_honours_completed(self) -> None:
        graph = _make_graph(a="completed", b="pending")
        result = _seed_node_states_from_graph(graph)
        assert result["a"] == "completed"
        assert result["b"] == "pending"

    def test_honours_skipped(self) -> None:
        graph = _make_graph(a="skipped")
        result = _seed_node_states_from_graph(graph)
        assert result["a"] == "skipped"

    def test_ignores_other_statuses(self) -> None:
        graph = _make_graph(a="failed", b="blocked", c="in_progress")
        result = _seed_node_states_from_graph(graph)
        assert all(v == "pending" for v in result.values())


class TestHashMatch:
    """When plan hash matches, existing state is reused (no regression)."""

    def test_reuses_existing_state(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="same",
            node_states={"a": "completed", "b": "pending"},
            total_sessions=5,
        )
        manager.save(old)

        graph = _make_graph(a="pending", b="pending")
        result = _load_or_init_state(manager, "same", graph)

        assert result.node_states["a"] == "completed"
        assert result.total_sessions == 5

    def test_adds_new_nodes_as_pending(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        old = _make_state(plan_hash="same", node_states={"a": "completed"})
        manager.save(old)

        graph = _make_graph(a="pending", b="pending")
        result = _load_or_init_state(manager, "same", graph)

        assert result.node_states["a"] == "completed"
        assert result.node_states["b"] == "pending"


class TestHashMismatchMerge:
    """When plan hash differs, completed/skipped are carried forward."""

    def test_completed_carried_forward(self, tmp_state_path: Path) -> None:
        """Core fix: completed tasks survive plan rebuild."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "completed", "b": "completed"},
        )
        manager.save(old)

        # Plan rebuilt with stale tasks.md — both show pending
        graph = _make_graph(a="pending", b="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "completed"
        assert result.node_states["b"] == "completed"

    def test_skipped_carried_forward(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "skipped"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "skipped"

    def test_new_nodes_start_pending(self, tmp_state_path: Path) -> None:
        """Nodes not in old state get seeded from plan."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "completed"},
        )
        manager.save(old)

        graph = _make_graph(a="pending", new_node="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "completed"
        assert result.node_states["new_node"] == "pending"

    def test_new_nodes_honour_plan_completed(self, tmp_state_path: Path) -> None:
        """New nodes with [x] in tasks.md get completed from plan."""
        manager = StateManager(tmp_state_path)
        old = _make_state(plan_hash="old", node_states={})
        manager.save(old)

        graph = _make_graph(new_node="completed")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["new_node"] == "completed"

    def test_removed_nodes_dropped(self, tmp_state_path: Path) -> None:
        """Nodes no longer in plan are not in result."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "completed", "removed": "completed"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert "removed" not in result.node_states
        assert result.node_states["a"] == "completed"

    def test_failed_not_carried_forward(self, tmp_state_path: Path) -> None:
        """Failed tasks get a fresh start on plan change."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "failed"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "pending"

    def test_blocked_not_carried_forward(self, tmp_state_path: Path) -> None:
        """Blocked tasks get a fresh start on plan change."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "blocked"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "pending"

    def test_in_progress_not_carried_forward(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "in_progress"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "pending"

    def test_plan_hash_updated(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        old = _make_state(plan_hash="old", node_states={"a": "completed"})
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new_hash", graph)

        assert result.plan_hash == "new_hash"

    def test_session_history_preserved(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        record = SessionRecord(
            node_id="a",
            attempt=1,
            status="completed",
            input_tokens=100,
            output_tokens=200,
            cost=0.5,
            duration_ms=5000,
            error_message=None,
            timestamp="2026-03-01T10:00:00Z",
        )
        old = _make_state(
            plan_hash="old",
            node_states={"a": "completed"},
            session_history=[record],
            total_sessions=1,
            total_cost=0.5,
        )
        manager.save(old)

        graph = _make_graph(a="pending", b="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert len(result.session_history) == 1
        assert result.total_sessions == 1
        assert result.total_cost == 0.5

    def test_blocked_reasons_pruned(self, tmp_state_path: Path) -> None:
        """Blocked reasons for removed nodes are dropped."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "completed", "gone": "blocked"},
            blocked_reasons={"gone": "upstream failed"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert "gone" not in result.blocked_reasons

    def test_blocked_reasons_cleared_for_reset_nodes(
        self, tmp_state_path: Path
    ) -> None:
        """Blocked reasons are cleared for nodes reset to pending during
        plan merge — stale reasons would cause immediate re-blocking."""
        manager = StateManager(tmp_state_path)
        old = _make_state(
            plan_hash="old",
            node_states={"a": "blocked"},
            blocked_reasons={"a": "upstream failed"},
        )
        manager.save(old)

        graph = _make_graph(a="pending")
        result = _load_or_init_state(manager, "new", graph)

        assert result.node_states["a"] == "pending"
        assert "a" not in result.blocked_reasons


class TestInitAttemptTracker:
    """_init_attempt_tracker skips reset (pending) tasks."""

    def test_pending_tasks_excluded(self) -> None:
        """Tasks reset to pending must start with attempt 0."""
        state = _make_state(
            node_states={"a": "pending", "b": "completed"},
            session_history=[
                SessionRecord(
                    node_id="a",
                    attempt=3,
                    status="failed",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0,
                    duration_ms=0,
                    error_message="boom",
                    timestamp="2026-03-01T09:00:00Z",
                ),
                SessionRecord(
                    node_id="b",
                    attempt=1,
                    status="completed",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0,
                    duration_ms=0,
                    error_message=None,
                    timestamp="2026-03-01T09:01:00Z",
                ),
            ],
        )

        tracker = _init_attempt_tracker(state)

        # "a" is pending (was reset) — should not be in tracker
        assert "a" not in tracker
        # "b" is completed — should retain its attempt count
        assert tracker["b"] == 1


class TestNoExistingState:
    """When no state.jsonl exists, seed entirely from plan.json."""

    def test_fresh_state_from_plan(self, tmp_state_path: Path) -> None:
        manager = StateManager(tmp_state_path)
        graph = _make_graph(a="completed", b="pending")

        result = _load_or_init_state(manager, "hash", graph)

        assert result.node_states["a"] == "completed"
        assert result.node_states["b"] == "pending"
        assert result.plan_hash == "hash"
        assert result.total_sessions == 0
