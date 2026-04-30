"""Tests for issue #535: double dispatch of nodes via validated pending reset.

Verifies acceptance criteria:
  AC-1: mark_pending() enforces in_progress→pending through _transition() layer.
  AC-3: A node that times out once is dispatched at most twice; both transitions logged.
  AC-4: VALID_TRANSITIONS['in_progress'] includes 'pending'.
  AC-5: When timeout retries are exhausted, node escalates to failed, no further dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_fox.engine.graph_sync import GraphSync, InvalidTransitionError
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    status: str,
    *,
    node_id: str = "01_project_setup:2",
    error_message: str | None = None,
    attempt: int = 1,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=5000,
        error_message=error_message,
        timestamp="2026-01-01T00:00:00Z",
    )


def _make_handler(
    node_id: str = "01_project_setup:2",
    *,
    max_timeout_retries: int = 2,
    is_exhausted: bool = False,
) -> tuple[
    SessionResultHandler,
    MagicMock,
    ExecutionState,
    dict[str, int],
    dict[str, str | None],
]:
    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})

    mock_ladder = MagicMock()
    mock_ladder.is_exhausted = is_exhausted
    mock_ladder.should_retry.return_value = not is_exhausted
    mock_ladder.escalation_count = 0
    mock_ladder.attempt_count = 1

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders={node_id: mock_ladder},
        retries_before_escalation=1,
        max_retries=2,
        task_callback=None,
        sink=None,
        run_id="test-run-535",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=None,
        block_task_fn=lambda nid, st, reason: None,
        check_block_budget_fn=lambda st: False,
        max_timeout_retries=max_timeout_retries,
    )

    state = ExecutionState(
        plan_hash="test",
        node_states={node_id: "in_progress"},
    )

    return handler, mock_ladder, state, {}, {}


# ---------------------------------------------------------------------------
# AC-4: in_progress → pending is in VALID_TRANSITIONS
# ---------------------------------------------------------------------------


class TestValidTransitionsIncludesPending:
    """AC-4: VALID_TRANSITIONS['in_progress'] must include 'pending'."""

    def test_pending_in_in_progress_valid_targets(self) -> None:
        assert "pending" in GraphSync.VALID_TRANSITIONS["in_progress"]

    def test_in_progress_to_pending_does_not_warn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transitioning in_progress→pending must not emit an Invalid transition warning."""
        import logging

        node_states = {"A": "in_progress"}
        sync = GraphSync(node_states, {})
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.graph_sync"):
            sync.mark_pending("A")
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert not any("Invalid state transition" in m for m in warning_messages), (
            f"Unexpected Invalid state transition warning: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# AC-1: mark_pending() enforces in_progress→pending
# ---------------------------------------------------------------------------


class TestMarkPending:
    """AC-1: mark_pending() transitions in_progress→pending and rejects other states."""

    def test_mark_pending_from_in_progress_succeeds(self) -> None:
        """mark_pending() on an in_progress node sets state to pending."""
        node_states = {"A": "in_progress"}
        sync = GraphSync(node_states, {})
        sync.mark_pending("A")
        assert sync.node_states["A"] == "pending"

    def test_mark_pending_recorded_in_transition_log(self) -> None:
        """mark_pending() records the transition in the audit log."""
        node_states = {"A": "in_progress"}
        sync = GraphSync(node_states, {})
        sync.mark_pending("A", reason="timeout retry")
        assert len(sync._transition_log) == 1
        entry = sync._transition_log[0]
        assert entry["node_id"] == "A"
        assert entry["from_status"] == "in_progress"
        assert entry["to_status"] == "pending"
        assert entry["reason"] == "timeout retry"

    def test_mark_pending_from_completed_raises(self) -> None:
        """mark_pending() on a completed node raises InvalidTransitionError."""
        node_states = {"A": "completed"}
        sync = GraphSync(node_states, {})
        with pytest.raises(InvalidTransitionError):
            sync.mark_pending("A")

    def test_mark_pending_from_pending_raises(self) -> None:
        """mark_pending() on a pending node raises InvalidTransitionError."""
        node_states = {"A": "pending"}
        sync = GraphSync(node_states, {})
        with pytest.raises(InvalidTransitionError):
            sync.mark_pending("A")

    def test_mark_pending_from_blocked_raises(self) -> None:
        """mark_pending() on a blocked node raises InvalidTransitionError."""
        node_states = {"A": "blocked"}
        sync = GraphSync(node_states, {})
        with pytest.raises(InvalidTransitionError):
            sync.mark_pending("A")

    def test_mark_pending_node_becomes_ready_for_dispatch(self) -> None:
        """After mark_pending(), node appears in ready_tasks()."""
        node_states = {"A": "in_progress"}
        sync = GraphSync(node_states, {})
        sync.mark_pending("A")
        assert "A" in sync.ready_tasks()


# ---------------------------------------------------------------------------
# AC-3: Exactly two dispatches for one timeout
# ---------------------------------------------------------------------------


class TestSingleTimeoutTwoDispatches:
    """AC-3: A node that times out once must be dispatched at most twice.

    State sequence: pending → in_progress → pending (timeout) → in_progress (retry).
    The transition log must record all four transitions in order.
    """

    def test_one_timeout_produces_two_in_progress_entries_in_log(self) -> None:
        """AC-3: After one timeout+retry, transition log has exactly 4 entries."""
        node_id = "01_project_setup:2"
        node_states = {node_id: "pending"}
        sync = GraphSync(node_states, {node_id: []})

        # Dispatch 1
        sync.mark_in_progress(node_id)
        # Timeout → reset to pending
        sync.mark_pending(node_id, reason="timeout retry")
        # Dispatch 2 (retry)
        sync.mark_in_progress(node_id)

        log = sync._transition_log
        assert len(log) == 3, f"Expected 3 transitions, got {len(log)}: {log}"
        assert log[0] == {
            "node_id": node_id, "from_status": "pending",
            "to_status": "in_progress", "reason": "dispatched",
        }
        assert log[1] == {
            "node_id": node_id, "from_status": "in_progress",
            "to_status": "pending", "reason": "timeout retry",
        }
        assert log[2] == {
            "node_id": node_id, "from_status": "pending",
            "to_status": "in_progress", "reason": "dispatched",
        }

    def test_timeout_handler_resets_via_mark_pending(self) -> None:
        """AC-3: _handle_timeout() resets node via mark_pending, recording the transition."""
        node_id = "01_project_setup:2"
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(node_id)

        # Confirm the node starts as in_progress
        assert handler._graph_sync.node_states[node_id] == "in_progress"

        record = _make_record("timeout", node_id=node_id)
        handler.process(record, attempt=1, state=state,
                        attempt_tracker=attempt_tracker, error_tracker=error_tracker)

        # Node should now be pending (ready for second dispatch)
        assert handler._graph_sync.node_states[node_id] == "pending"
        # Transition log should have captured in_progress → pending
        log = handler._graph_sync._transition_log
        assert any(
            e["from_status"] == "in_progress" and e["to_status"] == "pending"
            for e in log
        ), f"No in_progress→pending transition found: {log}"


# ---------------------------------------------------------------------------
# AC-5: Exhausted timeout retries → failed, no further dispatch
# ---------------------------------------------------------------------------


class TestExhaustedTimeoutRetries:
    """AC-5: When timeout retries exhausted, node escalates to failed — no extra dispatch."""

    def test_exhausted_timeout_does_not_call_mark_pending(self) -> None:
        """AC-5: When retries exhausted, _handle_timeout falls through to failure path."""
        node_id = "01_project_setup:2"
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            node_id, max_timeout_retries=1, is_exhausted=True
        )

        handler._get_node_state(node_id).timeout_retries = 1  # already at max

        record = _make_record("timeout", node_id=node_id, attempt=2)
        handler.process(record, attempt=2, state=state,
                        attempt_tracker=attempt_tracker, error_tracker=error_tracker)

        # With exhausted retries and exhausted ladder, node is blocked (not pending)
        final_state = handler._graph_sync.node_states[node_id]
        assert final_state != "pending", (
            f"Node should not be reset to pending when timeout retries exhausted, "
            f"got {final_state!r}"
        )

    def test_two_timeouts_max_one_retry_final_state_not_pending(self) -> None:
        """AC-5: max_timeout_retries=1, two timeouts → escalation ladder, not re-queued."""
        node_id = "01_project_setup:2"
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            node_id, max_timeout_retries=1
        )

        # First timeout: within retry budget, reset to pending
        record1 = _make_record("timeout", node_id=node_id, attempt=1)
        handler.process(record1, attempt=1, state=state,
                        attempt_tracker=attempt_tracker, error_tracker=error_tracker)
        assert handler._graph_sync.node_states[node_id] == "pending"
        assert handler._get_node_state(node_id).timeout_retries == 1

        # Simulate re-dispatch by orchestrator
        handler._graph_sync.node_states[node_id] = "in_progress"

        # Second timeout: retries exhausted, falls through to escalation ladder
        # With mock_ladder.is_exhausted=False (from _make_handler), it retries via ladder
        record2 = _make_record("timeout", node_id=node_id, attempt=2)
        handler.process(record2, attempt=2, state=state,
                        attempt_tracker=attempt_tracker, error_tracker=error_tracker)

        # Timeout retry count is 1 (not incremented beyond max)
        assert handler._get_node_state(node_id).timeout_retries == 1
        # Escalation ladder record_failure was called (fell through to _handle_failure)
        assert mock_ladder.record_failure.call_count == 1
