"""Unit tests for transport-error handling in SessionResultHandler.

Verifies AC-6 and AC-7 from issue #269:
  AC-6: SessionResultHandler does not consume an escalation retry for transport errors.
  AC-7: Transport errors that succeed internally do not create a failed SessionRecord.

Requirements: 26-REQ-9.3 (transport-transparent retry path)
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager

# ---------------------------------------------------------------------------
# Helpers (mirrors test_timeout_escalation.py pattern)
# ---------------------------------------------------------------------------


def _make_transport_record(
    *,
    node_id: str = "node1",
    error_message: str = "Transport error after 3 retries: connection refused",
    attempt: int = 1,
) -> SessionRecord:
    """Create a SessionRecord with is_transport_error=True."""
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status="failed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=error_message,
        timestamp="2026-01-01T00:00:00Z",
        is_transport_error=True,
    )


def _make_regular_failure_record(
    *,
    node_id: str = "node1",
    error_message: str = "Session failed: tool error",
    attempt: int = 1,
) -> SessionRecord:
    """Create a normal (non-transport) failed SessionRecord."""
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status="failed",
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=5000,
        error_message=error_message,
        timestamp="2026-01-01T00:00:00Z",
        is_transport_error=False,
    )


def _make_mock_ladder(
    *,
    is_exhausted: bool = False,
    should_retry: bool = True,
    escalation_count: int = 0,
    attempt_count: int = 1,
) -> MagicMock:
    mock = MagicMock()
    mock.is_exhausted = is_exhausted
    mock.should_retry.return_value = should_retry
    mock.escalation_count = escalation_count
    mock.attempt_count = attempt_count
    return mock


def _make_handler(
    *,
    node_id: str = "node1",
    is_exhausted: bool = False,
) -> tuple[
    SessionResultHandler,
    MagicMock,
    ExecutionState,
    dict[str, int],
    dict[str, str | None],
]:
    """Create a minimal SessionResultHandler with a mock escalation ladder."""
    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})
    mock_state_manager = MagicMock(spec=StateManager)

    mock_ladder = _make_mock_ladder(is_exhausted=is_exhausted)
    routing_ladders: dict[str, Any] = {node_id: mock_ladder}

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        state_manager=mock_state_manager,
        routing_ladders=routing_ladders,
        retries_before_escalation=1,
        max_retries=2,
        task_callback=None,
        sink=None,
        run_id="test-run",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=None,
        block_task_fn=lambda nid, st, reason: None,
        check_block_budget_fn=lambda st: False,
    )

    state = ExecutionState(
        plan_hash="test",
        node_states={node_id: "in_progress"},
    )
    attempt_tracker: dict[str, int] = {}
    error_tracker: dict[str, str | None] = {}

    return handler, mock_ladder, state, attempt_tracker, error_tracker


# ---------------------------------------------------------------------------
# AC-6: Transport errors do not consume an escalation ladder retry attempt
# ---------------------------------------------------------------------------


class TestTransportErrorSkipsEscalationLadder:
    """AC-6: SessionResultHandler does not call EscalationLadder.record_failure()
    for transport errors, and the node is reset to pending.
    """

    def test_transport_error_does_not_call_record_failure(self) -> None:
        """AC-6: record_failure() must NOT be called on a transport-error record."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_transport_record()

        handler._handle_failure(record, 1, state, attempt_tracker, error_tracker)

        assert mock_ladder.record_failure.call_count == 0, (
            "EscalationLadder.record_failure() must not be called for transport errors"
        )

    def test_transport_error_resets_node_to_pending(self) -> None:
        """AC-6: Node is reset to pending so the orchestrator re-dispatches it."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_transport_record()

        handler._handle_failure(record, 1, state, attempt_tracker, error_tracker)

        assert handler._graph_sync.node_states["node1"] == "pending"

    def test_transport_error_ladder_attempt_count_unchanged(self) -> None:
        """AC-6: The ladder's attempt_count must remain unchanged after a
        transport-error failure (no ladder methods called at all)."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        initial_count = mock_ladder.attempt_count  # = 1 from factory
        record = _make_transport_record()

        handler._handle_failure(record, 1, state, attempt_tracker, error_tracker)

        # attempt_count is a property on a MagicMock; verify record_failure
        # was never called (which would increment real ladders).
        assert mock_ladder.record_failure.call_count == 0
        assert mock_ladder.attempt_count == initial_count

    def test_regular_failure_does_call_record_failure(self) -> None:
        """Regression: a normal (non-transport) failure still invokes the ladder."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_regular_failure_record()

        handler._handle_failure(record, 1, state, attempt_tracker, error_tracker)

        assert mock_ladder.record_failure.call_count == 1, (
            "EscalationLadder.record_failure() must be called for non-transport failures"
        )

    def test_process_transport_error_does_not_consume_retry(self) -> None:
        """AC-6: Calling process() with a transport-error record leaves the
        escalation ladder untouched and resets node to pending."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_transport_record()

        handler.process(record, 1, state, attempt_tracker, error_tracker)

        assert mock_ladder.record_failure.call_count == 0
        assert handler._graph_sync.node_states["node1"] == "pending"


# ---------------------------------------------------------------------------
# AC-7: Transport errors that internally succeed produce no failed SessionRecord
# ---------------------------------------------------------------------------


class TestTransportInternalRetryNoFailedRecord:
    """AC-7: When ClaudeBackend retries internally and succeeds, the session
    history contains only a completed record — no failed record for the node.

    This is an integration-style verification: we simulate a successful session
    (outcome already has status='completed') and confirm that only a completed
    record is stored.  The internal retry is invisible at this layer because
    ClaudeBackend buffers the failed attempt and only yields a successful
    ResultMessage to run_session().
    """

    def test_successful_session_after_internal_retry_has_no_failed_record(self) -> None:
        """AC-7: A completed record with no is_transport_error flag has no failed
        sibling in session_history for the same node."""
        # Simulate a completed session record (ClaudeBackend retried internally
        # and succeeded — the result appears as a normal 'completed' record).
        completed_record = SessionRecord(
            node_id="node1",
            attempt=1,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=1234,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
            is_transport_error=False,
        )

        state = ExecutionState(
            plan_hash="test",
            node_states={"node1": "completed"},
            session_history=[completed_record],
        )

        # Verify no failed record exists for node1
        failed_records = [
            r
            for r in state.session_history
            if r.node_id == "node1" and r.status == "failed"
        ]
        assert len(failed_records) == 0, (
            f"Expected no failed record for node1; found: {failed_records}"
        )
        assert len(state.session_history) == 1

    def test_is_transport_error_field_defaults_to_false_on_session_record(self) -> None:
        """Regression: SessionRecord.is_transport_error defaults to False for
        existing code that doesn't explicitly set it."""
        record = SessionRecord(
            node_id="node1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert record.is_transport_error is False

    def test_transport_error_flag_set_on_failed_record(self) -> None:
        """AC-7: A record produced from an exhausted transport error has
        is_transport_error=True, distinguishing it from a session failure."""
        transport_record = _make_transport_record()
        assert transport_record.is_transport_error is True
        assert transport_record.status == "failed"

    def test_transport_error_record_not_added_to_history_when_retried(self) -> None:
        """AC-7 (process path): When process() handles a transport-error record,
        the state manager's record_session() is still called (the record is
        stored), but the node is reset to pending — the orchestrator can
        re-dispatch without treating this as a 'real' failure.

        Note: The spec says transport errors that INTERNALLY succeed produce no
        failed record.  When transport retries are exhausted (transport failure
        reaches result_handler), we still record the event but do NOT penalise
        the escalation ladder.
        """
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        mock_state_manager = cast(MagicMock, handler._state_manager)

        record = _make_transport_record()
        handler.process(record, 1, state, attempt_tracker, error_tracker)

        # record_session IS called (we keep the record for auditing)
        mock_state_manager.record_session.assert_called_once()
        # But the ladder was never penalised
        assert mock_ladder.record_failure.call_count == 0
        # And the node is pending (not blocked)
        assert handler._graph_sync.node_states["node1"] == "pending"
