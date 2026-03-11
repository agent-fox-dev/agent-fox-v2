"""Graph sync tests: ready task detection, cascade blocking, stall detection.

Test Spec: TS-04-2 (ready tasks), TS-04-6 (cascade blocking linear),
           TS-04-7 (cascade blocking diamond), TS-04-E10 (stall detection)
Requirements: 04-REQ-1.1, 04-REQ-3.1, 04-REQ-3.2, 04-REQ-3.E1,
              04-REQ-10.1, 04-REQ-10.2, 04-REQ-10.E1
"""

from __future__ import annotations

from agent_fox.engine.graph_sync import GraphSync


class TestReadyTasksIdentified:
    """TS-04-2: Ready tasks identified correctly from graph.

    Verify GraphSync.ready_tasks() returns only tasks whose
    dependencies are all completed.
    """

    def test_only_root_is_ready_initially(self) -> None:
        """Before any execution, only tasks with no deps are ready."""
        # Graph: A -> B, A -> C (A has no deps; B and C depend on A)
        node_states = {"A": "pending", "B": "pending", "C": "pending"}
        edges = {"B": ["A"], "C": ["A"]}  # node -> list of dependencies

        sync = GraphSync(node_states, edges)
        ready = sync.ready_tasks()

        assert ready == ["A"]

    def test_dependents_ready_after_dep_completed(self) -> None:
        """After A is completed, B and C become ready."""
        node_states = {"A": "pending", "B": "pending", "C": "pending"}
        edges = {"B": ["A"], "C": ["A"]}

        sync = GraphSync(node_states, edges)

        # Before: only A is ready
        assert sync.ready_tasks() == ["A"]

        # Mark A completed
        sync.mark_completed("A")
        ready = sync.ready_tasks()

        assert set(ready) == {"B", "C"}

    def test_task_not_ready_with_incomplete_dep(self) -> None:
        """A task is not ready if any dependency is not completed."""
        # A -> B -> C
        node_states = {"A": "completed", "B": "pending", "C": "pending"}
        edges = {"B": ["A"], "C": ["B"]}

        sync = GraphSync(node_states, edges)
        ready = sync.ready_tasks()

        assert ready == ["B"]
        assert "C" not in ready

    def test_no_deps_all_ready(self) -> None:
        """Tasks with no dependencies are all ready initially."""
        node_states = {"A": "pending", "B": "pending", "C": "pending"}
        edges: dict[str, list[str]] = {}  # no dependencies

        sync = GraphSync(node_states, edges)
        ready = sync.ready_tasks()

        assert set(ready) == {"A", "B", "C"}


class TestCascadeBlockingLinear:
    """TS-04-6: Cascade blocking propagates to all dependents.

    Graph: A -> B -> C -> D. A is completed. B fails and is blocked.
    """

    def test_cascade_blocks_all_downstream(self) -> None:
        """Blocking B cascades to C and D."""
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "pending",
            "D": "pending",
        }
        # edges: who depends on whom (node -> its dependencies)
        edges = {"B": ["A"], "C": ["B"], "D": ["C"]}

        sync = GraphSync(node_states, edges)
        cascade_blocked = sync.mark_blocked("B", "retries exhausted")

        assert set(cascade_blocked) == {"C", "D"}
        assert sync.node_states["B"] == "blocked"
        assert sync.node_states["C"] == "blocked"
        assert sync.node_states["D"] == "blocked"

    def test_cascade_records_blocking_reason(self) -> None:
        """Each cascade-blocked task records the blocking reason."""
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "pending",
            "D": "pending",
        }
        edges = {"B": ["A"], "C": ["B"], "D": ["C"]}

        sync = GraphSync(node_states, edges)
        sync.mark_blocked("B", "retries exhausted")

        # All blocked nodes should be "blocked"
        assert sync.node_states["B"] == "blocked"
        assert sync.node_states["C"] == "blocked"
        assert sync.node_states["D"] == "blocked"

    def test_completed_tasks_not_cascade_blocked(self) -> None:
        """Already completed tasks are not affected by cascade blocking."""
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "pending",
        }
        edges = {"B": ["A"], "C": ["B"]}

        sync = GraphSync(node_states, edges)
        sync.mark_blocked("B", "failed")

        assert sync.node_states["A"] == "completed"

    def test_in_progress_tasks_not_cascade_blocked(self) -> None:
        """In-progress tasks are not affected by cascade blocking.

        Tasks that are actively executing should finish their session;
        their result is processed when they complete.
        """
        # Graph: A -> B, A -> C, B -> D, C -> D
        # A is completed, B fails and is blocked, C is in_progress
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "in_progress",
            "D": "pending",
        }
        # D depends on both B and C
        edges = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}

        sync = GraphSync(node_states, edges)
        cascade_blocked = sync.mark_blocked("B", "retries exhausted")

        # C is in_progress and should NOT be cascade-blocked
        assert sync.node_states["C"] == "in_progress"
        assert "C" not in cascade_blocked

        # D depends on B (blocked), but D also depends on C (in_progress).
        # D should be cascade-blocked because B is blocked.
        assert sync.node_states["D"] == "blocked"
        assert "D" in cascade_blocked


class TestCascadeBlockingDiamond:
    """TS-04-7: Cascade blocking with diamond dependency.

    Graph: A -> B, A -> C, B -> D, C -> D. A is completed.
    B fails and is blocked.
    """

    def test_diamond_downstream_blocked_when_one_path_blocked(self) -> None:
        """D is blocked because B is blocked, even though C is still pending."""
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "pending",
            "D": "pending",
        }
        # D depends on both B and C
        edges = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}

        sync = GraphSync(node_states, edges)
        sync.mark_blocked("B", "failed")

        assert sync.node_states["D"] == "blocked"

    def test_diamond_c_not_blocked_when_b_blocked(self) -> None:
        """C should not be blocked when B is blocked (no dependency)."""
        node_states = {
            "A": "completed",
            "B": "pending",
            "C": "pending",
            "D": "pending",
        }
        edges = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}

        sync = GraphSync(node_states, edges)
        sync.mark_blocked("B", "failed")

        # C does not depend on B, so it should remain pending
        assert sync.node_states["C"] == "pending"


class TestStallDetection:
    """TS-04-E10: Stall detection.

    Verify GraphSync.is_stalled() returns True when no progress is possible.
    """

    def test_stalled_when_all_blocked(self) -> None:
        """Returns True when all tasks are blocked and none in-progress."""
        node_states = {"A": "blocked", "B": "blocked"}
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is True

    def test_not_stalled_when_tasks_ready(self) -> None:
        """Returns False when there are ready tasks."""
        node_states = {"A": "pending", "B": "pending"}
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is False

    def test_not_stalled_when_tasks_in_progress(self) -> None:
        """Returns False when tasks are in-progress."""
        node_states = {"A": "in_progress", "B": "pending"}
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is False

    def test_not_stalled_when_all_completed(self) -> None:
        """Returns False when all tasks are completed (not a stall)."""
        node_states = {"A": "completed", "B": "completed"}
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is False

    def test_stalled_mix_of_blocked_and_completed(self) -> None:
        """Stalled when some completed but rest are blocked, none pending."""
        node_states = {
            "A": "completed",
            "B": "blocked",
            "C": "blocked",
        }
        edges = {"B": ["A"], "C": ["B"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is True

    def test_summary_returns_status_counts(self) -> None:
        """Verify summary() returns correct counts per status."""
        node_states = {
            "A": "completed",
            "B": "blocked",
            "C": "pending",
            "D": "in_progress",
        }
        edges: dict[str, list[str]] = {}

        sync = GraphSync(node_states, edges)
        summary = sync.summary()

        assert summary["completed"] == 1
        assert summary["blocked"] == 1
        assert summary["pending"] == 1
        assert summary["in_progress"] == 1
