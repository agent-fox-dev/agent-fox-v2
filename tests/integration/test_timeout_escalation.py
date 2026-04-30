"""Integration tests for timeout-aware escalation.

Test Spec: TS-75-E1, TS-75-E2
Requirements: 75-REQ-2.3, 75-REQ-2.4
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_session_record(
    node_id: str,
    status: str,
    *,
    attempt: int = 1,
    error_message: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=500,
        output_tokens=300,
        cost=0.05,
        duration_ms=30_000,
        error_message=error_message,
        timestamp="2026-01-01T00:00:00Z",
        model=model,
    )


class _EventCaptureSink:
    """Captures audit events for integration assertions."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit_audit_event(self, event: Any) -> None:
        self.events.append(event)

    def record_session_outcome(self, outcome: Any) -> None:
        pass

    def record_tool_call(self, call: Any) -> None:
        pass

    def record_tool_error(self, error: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def events_of_type(self, event_type: Any) -> list[Any]:
        return [e for e in self.events if e.event_type == event_type]


def _make_handler_with_sink(
    node_id: str = "spec:1",
    *,
    max_timeout_retries: int = 2,
    timeout_multiplier: float = 1.5,
    timeout_ceiling_factor: float = 2.0,
    original_timeout: int = 30,
    original_max_turns: int | None = 200,
) -> tuple[
    SessionResultHandler,
    MagicMock,
    ExecutionState,
    _EventCaptureSink,
    dict[str, int],
    dict[str, str | None],
]:
    """Build a SessionResultHandler configured for integration timeout tests."""
    from agent_fox.knowledge.sink import SinkDispatcher

    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})

    mock_ladder = MagicMock()
    mock_ladder.is_exhausted = False
    mock_ladder.should_retry.return_value = True
    mock_ladder.escalation_count = 0
    mock_ladder.attempt_count = 1

    routing_ladders: dict[str, Any] = {node_id: mock_ladder}

    sink = _EventCaptureSink()
    sink_dispatcher: SinkDispatcher = SinkDispatcher([sink])  # type: ignore[list-item]

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders=routing_ladders,
        retries_before_escalation=1,
        max_retries=max_timeout_retries + 3,
        task_callback=None,
        sink=sink_dispatcher,
        run_id="integration-test-run",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=None,
        block_task_fn=lambda nid, st, reason: None,
        check_block_budget_fn=lambda st: False,
    )

    state = ExecutionState(
        plan_hash="integration-test",
        node_states={node_id: "in_progress"},
    )

    attempt_tracker: dict[str, int] = {}
    error_tracker: dict[str, str | None] = {}

    return handler, mock_ladder, state, sink, attempt_tracker, error_tracker


# ---------------------------------------------------------------------------
# TS-75-E1: Single Timeout Then Success
# Requirement: 75-REQ-2.3
# ---------------------------------------------------------------------------


class TestTimeoutThenSuccess:
    """TS-75-E1: Timeout → extended retry → success flow."""

    def test_timeout_then_success_final_status_completed(self) -> None:
        """TS-75-E1: After timeout then success, the node is marked completed.

        Simulates: session 1 times out (timeout retry initiated),
        session 2 succeeds.
        """
        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(node_id)

        # Currently FAILS: timeout-aware routing doesn't exist.
        handler._max_timeout_retries = 2  # noqa: SLF001

        # Session 1: times out.
        timeout_record = _make_session_record(node_id, "timeout", attempt=1)
        handler.process(
            timeout_record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # After timeout: node should be pending for retry.
        # Currently FAILS: _handle_failure is called, not _handle_timeout.
        assert handler._graph_sync.node_states[node_id] == "pending"
        assert mock_ladder.record_failure.call_count == 0

        # Session 2: succeeds.
        success_record = _make_session_record(node_id, "completed", attempt=2)
        state.node_states[node_id] = "in_progress"  # simulate dispatch
        handler.process(
            success_record,
            attempt=2,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._graph_sync.node_states[node_id] == "completed"

    def test_timeout_then_success_emits_timeout_retry_event(self) -> None:
        """TS-75-E1: Timeout retry emits SESSION_TIMEOUT_RETRY audit event."""
        from agent_fox.knowledge.audit import AuditEventType

        # Currently FAILS: SESSION_TIMEOUT_RETRY doesn't exist.
        event_type = AuditEventType.SESSION_TIMEOUT_RETRY

        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(node_id)

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 2

        timeout_record = _make_session_record(node_id, "timeout", attempt=1)
        handler.process(
            timeout_record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        events = sink.events_of_type(event_type)
        assert len(events) == 1
        assert events[0].payload.get("timeout_retry_count") == 1

    def test_timeout_extends_session_parameters(self) -> None:
        """TS-75-E1: Extended session timeout is recorded after timeout retry."""
        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(
            node_id,
            timeout_multiplier=1.5,
            original_timeout=30,
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 2

        timeout_record = _make_session_record(node_id, "timeout", attempt=1)
        handler.process(
            timeout_record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Extended timeout for node1 should be ceil(30 * 1.5) = 45.
        assert handler._get_node_state(node_id).timeout == 45


# ---------------------------------------------------------------------------
# TS-75-E2: All Retries Exhaust Then Escalate Then Succeed
# Requirement: 75-REQ-2.4
# ---------------------------------------------------------------------------


class TestTimeoutExhaustionThenEscalation:
    """TS-75-E2: Repeated timeouts → exhaustion → escalation → success."""

    def test_timeout_exhaustion_then_ladder_called(self) -> None:
        """TS-75-E2: After max_timeout_retries timeouts, escalation ladder is used.

        Simulates: 2 timeouts (max_timeout_retries=1) → fall through to ladder.
        """
        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(
            node_id, max_timeout_retries=1
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 1

        # Session 1: timeout (retry 1 of 1 — still within budget).
        timeout1 = _make_session_record(node_id, "timeout", attempt=1)
        handler.process(
            timeout1,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Currently FAILS: record_failure IS called for all failures.
        assert mock_ladder.record_failure.call_count == 0

        # Session 2: timeout again (retries exhausted → fall through to ladder).
        # Simulate the dispatch loop re-queuing the node to in_progress.
        state.node_states[node_id] = "in_progress"
        handler._graph_sync.node_states[node_id] = "in_progress"  # type: ignore[attr-defined]
        timeout2 = _make_session_record(node_id, "timeout", attempt=2)
        handler.process(
            timeout2,
            attempt=2,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Now the escalation ladder must have been invoked.
        assert mock_ladder.record_failure.call_count == 1

    def test_exhausted_retries_warning_then_escalation(self) -> None:
        """TS-75-E2: Exhaustion warning is logged before falling through."""
        import io
        import logging

        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(
            node_id, max_timeout_retries=1
        )

        handler._max_timeout_retries = 1
        handler._get_node_state(node_id).timeout_retries = 1  # pre-exhaust

        timeout_record = _make_session_record(node_id, "timeout", attempt=2)

        log_output = io.StringIO()
        handler_logger = logging.getLogger("agent_fox.engine.result_handler")
        log_handler = logging.StreamHandler(log_output)
        log_handler.setLevel(logging.WARNING)
        handler_logger.addHandler(log_handler)

        try:
            handler.process(
                timeout_record,
                attempt=2,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )
        finally:
            handler_logger.removeHandler(log_handler)

        # After implementation: record_failure is called after exhaustion.
        assert mock_ladder.record_failure.call_count == 1

    def test_two_timeouts_one_success_at_escalated_tier(self) -> None:
        """TS-75-E2: Sequence: timeout → timeout (exhausted) → success at new tier.

        After timeout retries exhaust and escalation occurs, a subsequent
        success should complete the node.
        """
        node_id = "spec:1"
        handler, mock_ladder, state, sink, attempt_tracker, error_tracker = _make_handler_with_sink(
            node_id, max_timeout_retries=1
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 1

        # Session 1: timeout (retry 1 — within budget).
        handler.process(
            _make_session_record(node_id, "timeout", attempt=1),
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Session 2: timeout (exhausted — falls through to escalation).
        # Simulate the dispatch loop re-queuing to in_progress.
        state.node_states[node_id] = "in_progress"
        handler._graph_sync.node_states[node_id] = "in_progress"  # type: ignore[attr-defined]
        handler.process(
            _make_session_record(node_id, "timeout", attempt=2),
            attempt=2,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # After exhaustion, escalation was triggered.
        # Currently FAILS: record_failure is called on every non-success.
        assert mock_ladder.record_failure.call_count == 1

        # Session 3: success at escalated tier.
        state.node_states[node_id] = "in_progress"
        handler._graph_sync.node_states[node_id] = "in_progress"  # type: ignore[attr-defined]
        handler.process(
            _make_session_record(node_id, "completed", attempt=3, model="claude-opus-4-6"),
            attempt=3,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._graph_sync.node_states[node_id] == "completed"
