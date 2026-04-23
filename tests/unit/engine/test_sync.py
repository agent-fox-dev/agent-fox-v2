"""Graph sync tests: ready task detection, cascade blocking, stall detection.

Test Spec: TS-04-2 (ready tasks), TS-04-6 (cascade blocking linear),
           TS-04-7 (cascade blocking diamond), TS-04-E10 (stall detection)
Requirements: 04-REQ-1.1, 04-REQ-3.1, 04-REQ-3.2, 04-REQ-3.E1,
              04-REQ-10.1, 04-REQ-10.2, 04-REQ-10.E1
"""

from __future__ import annotations

import logging

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

    def test_cascade_continues_through_in_progress_to_block_pending_dependents(
        self,
    ) -> None:
        """Cascade blocking must reach pending nodes beyond an in_progress intermediate.

        Regression test for issue #481: when a node is blocked, the BFS cascade
        must continue through any in_progress dependents so that their pending
        dependents are blocked.  Without this fix, those pending nodes remain
        unblocked and are dispatched when the in_progress node completes —
        defeating the quality gate entirely.

        Scenario (mirrors 02_data_broker blocking):
          coder:1 is blocked (reviewer found critical findings).
          audit-review is in_progress (already executing, cannot be stopped).
          coder:2 through coder:N are pending (not yet dispatched).
          After the fix, coder:2..N are blocked at cascade time, not dispatched
          when audit-review completes.
        """
        # Graph: coder:1 -> audit-review (in_progress) -> coder:2 -> verifier (pending)
        node_states = {
            "coder:1": "pending",
            "audit-review": "in_progress",
            "coder:2": "pending",
            "verifier": "pending",
        }
        edges = {
            "audit-review": ["coder:1"],
            "coder:2": ["audit-review"],
            "verifier": ["coder:2"],
        }

        sync = GraphSync(node_states, edges)
        cascade_blocked = sync.mark_blocked("coder:1", "reviewer: 5 critical findings")

        # coder:1 itself is blocked
        assert sync.node_states["coder:1"] == "blocked"

        # audit-review is in_progress and must NOT be forcibly blocked —
        # it is already executing and will complete normally.
        assert sync.node_states["audit-review"] == "in_progress"
        assert "audit-review" not in cascade_blocked

        # coder:2 and verifier are pending dependents downstream of the
        # in_progress node.  They MUST be blocked so they are never dispatched.
        assert sync.node_states["coder:2"] == "blocked", (
            "coder:2 should be blocked via cascade through in_progress audit-review"
        )
        assert "coder:2" in cascade_blocked
        assert sync.node_states["verifier"] == "blocked", (
            "verifier should be blocked via cascade through in_progress audit-review"
        )
        assert "verifier" in cascade_blocked


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

    def test_not_stalled_when_promotable_deferred(self) -> None:
        """Not stalled when deferred nodes can be promoted."""
        node_states = {
            "A": "completed",
            "B": "deferred",
        }
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.is_stalled() is False

    def test_stalled_when_deferred_deps_not_met(self) -> None:
        """Stalled when deferred nodes exist but deps are not completed."""
        node_states = {
            "A": "blocked",
            "B": "deferred",
        }
        edges = {"B": ["A"]}

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


class TestPromoteDeferred:
    """Tests for GraphSync.promote_deferred()."""

    def test_promote_deferred_node_to_pending(self) -> None:
        """Deferred node with completed deps is promoted to pending."""
        node_states = {
            "A": "completed",
            "B": "deferred",
        }
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)
        promoted = sync.promote_deferred(limit=5)

        assert promoted == ["B"]
        assert sync.node_states["B"] == "pending"

    def test_promote_respects_limit(self) -> None:
        """Only promote up to the specified limit."""
        node_states = {
            "A": "completed",
            "B": "deferred",
            "C": "deferred",
            "D": "deferred",
        }
        edges = {"B": ["A"], "C": ["A"], "D": ["A"]}

        sync = GraphSync(node_states, edges)
        promoted = sync.promote_deferred(limit=2)

        assert len(promoted) == 2
        assert all(sync.node_states[p] == "pending" for p in promoted)
        deferred_remaining = [
            nid for nid, s in sync.node_states.items() if s == "deferred"
        ]
        assert len(deferred_remaining) == 1

    def test_promote_skips_unmet_deps(self) -> None:
        """Deferred nodes with incomplete deps are not promoted."""
        node_states = {
            "A": "pending",
            "B": "deferred",
        }
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)
        promoted = sync.promote_deferred(limit=5)

        assert promoted == []
        assert sync.node_states["B"] == "deferred"

    def test_promote_no_deferred_nodes(self) -> None:
        """Returns empty list when no deferred nodes exist."""
        node_states = {"A": "pending", "B": "completed"}
        edges = {"A": ["B"]}

        sync = GraphSync(node_states, edges)
        promoted = sync.promote_deferred(limit=5)

        assert promoted == []

    def test_promoted_nodes_become_ready(self) -> None:
        """Promoted nodes appear in ready_tasks() after promotion."""
        node_states = {
            "A": "completed",
            "B": "deferred",
        }
        edges = {"B": ["A"]}

        sync = GraphSync(node_states, edges)

        assert sync.ready_tasks() == []

        sync.promote_deferred(limit=1)

        assert sync.ready_tasks() == ["B"]

    def test_deferred_nodes_excluded_from_ready(self) -> None:
        """Deferred nodes do not appear in ready_tasks()."""
        node_states = {
            "A": "completed",
            "B": "deferred",
            "C": "pending",
        }
        edges = {"B": ["A"], "C": ["A"]}

        sync = GraphSync(node_states, edges)
        ready = sync.ready_tasks()

        assert "C" in ready
        assert "B" not in ready


class TestTransitionValidation:
    """Tests for state transition validation (issue #523)."""

    def test_valid_transition_pending_to_in_progress(self) -> None:
        node_states = {"A": "pending"}
        sync = GraphSync(node_states, {})
        sync.mark_in_progress("A")
        assert sync.node_states["A"] == "in_progress"

    def test_valid_transition_in_progress_to_completed(self) -> None:
        node_states = {"A": "in_progress"}
        sync = GraphSync(node_states, {})
        sync.mark_completed("A")
        assert sync.node_states["A"] == "completed"

    def test_valid_transition_pending_to_blocked(self) -> None:
        node_states = {"A": "pending"}
        sync = GraphSync(node_states, {})
        sync.mark_blocked("A", "test")
        assert sync.node_states["A"] == "blocked"

    def test_valid_transition_deferred_to_pending(self) -> None:
        node_states = {"A": "deferred"}
        sync = GraphSync(node_states, {})
        promoted = sync.promote_deferred(limit=1)
        assert promoted == ["A"]
        assert sync.node_states["A"] == "pending"

    def test_invalid_transition_completed_to_pending_warns(
        self, caplog: logging.LogRecordArgs
    ) -> None:
        """Completed is terminal — transitioning away logs a warning."""
        node_states = {"A": "completed"}
        sync = GraphSync(node_states, {})
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.graph_sync"):  # type: ignore[union-attr]
            sync._transition("A", "pending", reason="reset attempt")
        assert sync.node_states["A"] == "pending"
        assert any("Invalid state transition" in r.message for r in caplog.records)

    def test_invalid_transition_completed_to_in_progress_warns(
        self, caplog: logging.LogRecordArgs
    ) -> None:
        node_states = {"A": "completed"}
        sync = GraphSync(node_states, {})
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.graph_sync"):  # type: ignore[union-attr]
            sync.mark_in_progress("A")
        assert sync.node_states["A"] == "in_progress"
        assert any("Invalid state transition" in r.message for r in caplog.records)

    def test_invalid_transition_pending_to_completed_warns(
        self, caplog: logging.LogRecordArgs
    ) -> None:
        """pending -> completed is not valid (must go via in_progress)."""
        node_states = {"A": "pending"}
        sync = GraphSync(node_states, {})
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.graph_sync"):  # type: ignore[union-attr]
            sync.mark_completed("A")
        assert sync.node_states["A"] == "completed"
        assert any("Invalid state transition" in r.message for r in caplog.records)

    def test_unknown_source_state_no_crash(self) -> None:
        """Unknown source states do not crash — no entry in VALID_TRANSITIONS."""
        node_states = {"A": "mystery"}
        sync = GraphSync(node_states, {})
        sync._transition("A", "pending", reason="recovery")
        assert sync.node_states["A"] == "pending"

    def test_transition_table_completed_is_terminal(self) -> None:
        """Completed has an empty set — no outbound transitions."""
        assert GraphSync.VALID_TRANSITIONS["completed"] == set()


class TestTransitionLogging:
    """Tests for structured transition event logging (issue #523)."""

    def test_transition_log_recorded(self) -> None:
        node_states = {"A": "pending"}
        sync = GraphSync(node_states, {})
        sync.mark_in_progress("A")
        assert len(sync._transition_log) == 1
        entry = sync._transition_log[0]
        assert entry["node_id"] == "A"
        assert entry["from_status"] == "pending"
        assert entry["to_status"] == "in_progress"
        assert entry["reason"] == "dispatched"

    def test_cascade_blocking_logs_all_transitions(self) -> None:
        node_states = {"A": "pending", "B": "pending", "C": "pending"}
        edges = {"B": ["A"], "C": ["B"]}
        sync = GraphSync(node_states, edges)
        sync.mark_blocked("A", "retries exhausted")
        assert len(sync._transition_log) == 3
        node_ids = [e["node_id"] for e in sync._transition_log]
        assert node_ids == ["A", "B", "C"]

    def test_structured_log_message_emitted(
        self, caplog: logging.LogRecordArgs
    ) -> None:
        node_states = {"X": "pending"}
        sync = GraphSync(node_states, {})
        with caplog.at_level(logging.INFO, logger="agent_fox.engine.graph_sync"):  # type: ignore[union-attr]
            sync.mark_in_progress("X")
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("State transition:" in m and "node=X" in m for m in info_messages)
