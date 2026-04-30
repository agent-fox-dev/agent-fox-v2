"""Unit tests for timeout-aware escalation in SessionResultHandler.

Test Spec: TS-75-1 through TS-75-15, TS-75-21 through TS-75-23
Requirements: 75-REQ-1.1, 75-REQ-1.2, 75-REQ-1.3, 75-REQ-1.E1,
              75-REQ-2.1, 75-REQ-2.2, 75-REQ-2.3, 75-REQ-2.4,
              75-REQ-2.E1, 75-REQ-2.E2,
              75-REQ-3.1, 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.4,
              75-REQ-3.5, 75-REQ-3.E1,
              75-REQ-5.1, 75-REQ-5.2, 75-REQ-5.3
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _EventCaptureSink:
    """Minimal sink that captures audit events for assertion."""

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

    def find_events(self, event_type: Any) -> list[Any]:
        """Return all events matching the given type."""
        return [e for e in self.events if e.event_type == event_type]


def _make_record(
    status: str,
    *,
    node_id: str = "node1",
    error_message: str | None = None,
    attempt: int = 1,
) -> SessionRecord:
    """Create a minimal SessionRecord for testing."""
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


def _make_mock_ladder(
    *,
    is_exhausted: bool = False,
    should_retry: bool = True,
    escalation_count: int = 0,
    attempt_count: int = 1,
) -> MagicMock:
    """Create a mock EscalationLadder with configurable behavior."""
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
    sink: _EventCaptureSink | None = None,
) -> tuple[
    SessionResultHandler,
    MagicMock,
    ExecutionState,
    dict[str, int],
    dict[str, str | None],
]:
    """Create a minimal SessionResultHandler with mocked dependencies.

    Returns (handler, mock_ladder, state, attempt_tracker, error_tracker).
    The mock_ladder is the escalation ladder for node_id.
    """
    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})

    mock_ladder = _make_mock_ladder(is_exhausted=is_exhausted)
    routing_ladders: dict[str, Any] = {node_id: mock_ladder}

    from agent_fox.knowledge.sink import SinkDispatcher

    if sink is not None:
        sink_dispatcher: SinkDispatcher | None = SinkDispatcher([sink])  # type: ignore[list-item]
    else:
        sink_dispatcher = None

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders=routing_ladders,
        retries_before_escalation=1,
        max_retries=2,
        task_callback=None,
        sink=sink_dispatcher,
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
# TS-75-1: Timeout Routed to Timeout Handler
# Requirement: 75-REQ-1.1
# ---------------------------------------------------------------------------


class TestTimeoutRouting:
    """TS-75-1: Status 'timeout' routes to timeout handler, not escalation."""

    def test_timeout_does_not_call_record_failure(self) -> None:
        """TS-75-1: Timeout status should NOT invoke the escalation ladder."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("timeout")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # After implementation: timeout should NOT hit the escalation ladder.
        # Currently this FAILS because _handle_failure() calls record_failure().
        assert mock_ladder.record_failure.call_count == 0

    def test_timeout_sets_node_to_pending(self) -> None:
        """TS-75-1: Timeout with retries remaining should reset node to pending."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("timeout")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Node should be returned to pending for retry.
        assert handler._graph_sync.node_states["node1"] == "pending"

    def test_timeout_increments_retry_counter(self) -> None:
        """TS-75-1: Timeout increments the timeout retry counter."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("timeout")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._get_node_state("node1").timeout_retries == 1


# ---------------------------------------------------------------------------
# TS-75-2: Non-Timeout Failure Uses Escalation Ladder
# Requirement: 75-REQ-1.2
# ---------------------------------------------------------------------------


class TestNonTimeoutFailureRouting:
    """TS-75-2: Status 'failed' routes to the escalation ladder."""

    def test_failed_status_calls_record_failure(self) -> None:
        """TS-75-2: 'failed' status must invoke escalation ladder's record_failure."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("failed")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 1

    def test_failed_status_does_not_increment_timeout_counter(self) -> None:
        """TS-75-2: 'failed' status does not increment timeout retry counter."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("failed")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._get_node_state("node1").timeout_retries == 0


# ---------------------------------------------------------------------------
# TS-75-3: Timeout Detected by Status String
# Requirement: 75-REQ-1.3
# ---------------------------------------------------------------------------


class TestStatusStringDetection:
    """TS-75-3: Only status == 'timeout' triggers timeout handling."""

    def test_only_timeout_status_triggers_timeout_handler(self) -> None:
        """TS-75-3: 'timeout' triggers timeout handler; 'failed'/'completed' do not."""
        timeout_handler_invocations: dict[str, int] = {}

        for status in ("timeout", "failed", "completed"):
            handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
            record = _make_record(status)

            handler.process(
                record,
                attempt=1,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

            count = handler._get_node_state("node1").timeout_retries
            timeout_handler_invocations[status] = count

        assert timeout_handler_invocations["timeout"] == 1
        assert timeout_handler_invocations["failed"] == 0
        assert timeout_handler_invocations["completed"] == 0


# ---------------------------------------------------------------------------
# TS-75-4: Failed Status With "timeout" in Error Message
# Requirement: 75-REQ-1.E1
# ---------------------------------------------------------------------------


class TestFailedWithTimeoutInMessage:
    """TS-75-4: 'failed' status with 'timeout' in error message uses ladder."""

    def test_failed_with_timeout_in_error_uses_ladder(self) -> None:
        """TS-75-4: status='failed', error='Connection timeout' → escalation ladder."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record(
            "failed",
            error_message="Connection timeout after 30s",
        )

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Must still call record_failure (not timeout handler).
        assert mock_ladder.record_failure.call_count == 1

    def test_failed_with_timeout_in_error_no_timeout_counter(self) -> None:
        """TS-75-4: status='failed' with timeout in message → counter stays 0."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record(
            "failed",
            error_message="Connection timeout after 30s",
        )

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._get_node_state("node1").timeout_retries == 0


# ---------------------------------------------------------------------------
# TS-75-5: Timeout Counter Increments Independently
# Requirements: 75-REQ-2.1, 75-REQ-2.2
# ---------------------------------------------------------------------------


class TestTimeoutCounterIndependence:
    """TS-75-5: Timeout retry counter is independent of escalation ladder."""

    def test_two_timeouts_increment_counter_twice(self) -> None:
        """TS-75-5: Two timeout records increment the counter to 2."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        for attempt_n in (1, 2):
            # Simulate the dispatch loop: node goes back to in_progress before
            # each result is processed (except the very first call where _make_handler
            # already sets the node to in_progress).
            if attempt_n > 1:
                handler._graph_sync.node_states["node1"] = "in_progress"
            record = _make_record("timeout", attempt=attempt_n)
            handler.process(
                record,
                attempt=attempt_n,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        assert handler._get_node_state("node1").timeout_retries == 2

    def test_timeouts_dont_affect_ladder_attempt_count(self) -> None:
        """TS-75-5: Timeouts must NOT increment the escalation ladder attempt count."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        initial_count = mock_ladder.attempt_count

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Currently FAILS: record_failure IS called, which would change ladder state.
        assert mock_ladder.record_failure.call_count == 0
        assert mock_ladder.attempt_count == initial_count


# ---------------------------------------------------------------------------
# TS-75-6: Retry at Same Tier When Counter Below Max
# Requirement: 75-REQ-2.3
# ---------------------------------------------------------------------------


class TestRetryAtSameTier:
    """TS-75-6: Timeout retry resets node to pending at same model tier."""

    def test_timeout_retry_resets_node_to_pending(self) -> None:
        """TS-75-6: After a timeout retry, node state must be 'pending'."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("timeout")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._graph_sync.node_states["node1"] == "pending"

    def test_timeout_retry_does_not_escalate_tier(self) -> None:
        """TS-75-6: Timeout retry must NOT trigger tier escalation."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()
        record = _make_record("timeout")

        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # record_failure must NOT be called — currently FAILS.
        assert mock_ladder.record_failure.call_count == 0


# ---------------------------------------------------------------------------
# TS-75-7: Fall Through When Counter Reaches Max
# Requirement: 75-REQ-2.4
# ---------------------------------------------------------------------------


class TestTimeoutFallThrough:
    """TS-75-7: When timeout retries exhausted, escalation ladder is invoked."""

    def test_exhausted_timeout_counter_calls_record_failure(self) -> None:
        """TS-75-7: After max timeout retries, next timeout calls record_failure()."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        handler._get_node_state("node1").timeout_retries = 2

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=3,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 1


# ---------------------------------------------------------------------------
# TS-75-8: Mixed Timeout and Logical Failures
# Requirement: 75-REQ-2.E1
# ---------------------------------------------------------------------------


class TestMixedTimeoutAndFailures:
    """TS-75-8: Timeout and failure counters are independent when mixed."""

    def test_mixed_events_maintain_independent_counters(self) -> None:
        """TS-75-8: timeout x2 + failed x2 → timeout_retries=2, ladder_failures=2."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        # First timeout (node starts as in_progress from _make_handler)
        handler.process(
            _make_record("timeout", attempt=1),
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )
        # Between calls the dispatch loop re-dispatches the node to in_progress.
        handler._graph_sync.node_states["node1"] = "in_progress"
        # First failure
        handler.process(
            _make_record("failed", attempt=2),
            attempt=2,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )
        handler._graph_sync.node_states["node1"] = "in_progress"
        # Second timeout
        handler.process(
            _make_record("timeout", attempt=3),
            attempt=3,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )
        handler._graph_sync.node_states["node1"] = "in_progress"
        # Second failure
        handler.process(
            _make_record("failed", attempt=4),
            attempt=4,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert handler._get_node_state("node1").timeout_retries == 2
        # record_failure should only be called for the 'failed' records.
        assert mock_ladder.record_failure.call_count == 2


# ---------------------------------------------------------------------------
# TS-75-9: Zero Max Timeout Retries Skips Handling
# Requirement: 75-REQ-2.E2
# ---------------------------------------------------------------------------


class TestZeroMaxTimeoutRetries:
    """TS-75-9: max_timeout_retries=0 → timeout goes directly to escalation."""

    def test_zero_max_retries_calls_record_failure_immediately(self) -> None:
        """TS-75-9: When max_timeout_retries=0, timeout hits the escalation ladder."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        # Signal to the handler that max_timeout_retries is 0.
        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 0

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 1

    def test_zero_max_retries_no_timeout_counter_increment(self) -> None:
        """TS-75-9: When max_timeout_retries=0, timeout counter stays at 0."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 0

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        # Counter must not be incremented.
        assert handler._get_node_state("node1").timeout_retries == 0


# ---------------------------------------------------------------------------
# TS-75-10: Max Turns Extended by Multiplier
# Requirement: 75-REQ-3.1
# ---------------------------------------------------------------------------


class TestMaxTurnsExtension:
    """TS-75-10: _extend_node_params() multiplies max_turns and rounds up."""

    def test_max_turns_multiplied_and_rounded_up(self) -> None:
        """TS-75-10: original=200, multiplier=1.5 → extended=300."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.max_turns = 200
        ns.has_max_turns = True
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0
        ns.timeout = 30

        handler._extend_node_params("node1")

        assert ns.max_turns == 300


# ---------------------------------------------------------------------------
# TS-75-11: Session Timeout Extended by Multiplier
# Requirement: 75-REQ-3.2
# ---------------------------------------------------------------------------


class TestSessionTimeoutExtension:
    """TS-75-11: _extend_node_params() multiplies session_timeout and rounds up."""

    def test_session_timeout_multiplied_and_rounded_up(self) -> None:
        """TS-75-11: original_timeout=30, multiplier=1.5 → extended=45."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.timeout = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0
        ns.max_turns = 200
        ns.has_max_turns = True

        handler._extend_node_params("node1")

        assert ns.timeout == 45


# ---------------------------------------------------------------------------
# TS-75-12: Timeout Clamped to Ceiling
# Requirement: 75-REQ-3.3
# ---------------------------------------------------------------------------


class TestTimeoutCeiling:
    """TS-75-12: Extended timeout is clamped to ceiling."""

    def test_two_retries_clamp_to_ceiling(self) -> None:
        """TS-75-12: original=30, mult=1.5, ceil=2.0: retry1→45, retry2→60 (clamped)."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.timeout = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0
        ns.max_turns = 200
        ns.has_max_turns = True

        # After first retry:
        handler._extend_node_params("node1")  # 45
        assert ns.timeout == 45

        # After second retry: ceil(45 * 1.5) = 68, ceiling = ceil(30 * 2.0) = 60
        handler._extend_node_params("node1")  # clamped to 60
        assert ns.timeout == 60


# ---------------------------------------------------------------------------
# TS-75-13: Unlimited Turns Not Modified
# Requirement: 75-REQ-3.4
# ---------------------------------------------------------------------------


class TestUnlimitedTurnsPreservation:
    """TS-75-13: max_turns=None stays None after timeout retry."""

    def test_none_max_turns_not_modified(self) -> None:
        """TS-75-13: If max_turns is None, it must remain None after extension."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.max_turns = None
        ns.has_max_turns = True
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0
        ns.timeout = 30

        handler._extend_node_params("node1")

        assert ns.max_turns is None


# ---------------------------------------------------------------------------
# TS-75-14: Per-Node Parameter Isolation
# Requirement: 75-REQ-3.5
# ---------------------------------------------------------------------------


class TestPerNodeParameterIsolation:
    """TS-75-14: Extending one node's params does not affect other nodes."""

    def test_extending_node1_does_not_affect_node2(self) -> None:
        """TS-75-14: node1 extension is isolated; node2 must not appear in dicts."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.max_turns = 200
        ns.has_max_turns = True
        ns.timeout = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0

        handler._extend_node_params("node1")

        assert ns.timeout is not None
        assert "node2" not in handler._node_retry_states


# ---------------------------------------------------------------------------
# TS-75-15: Ceiling Clamp
# Requirement: 75-REQ-3.E1
# ---------------------------------------------------------------------------


class TestCeilingClamp:
    """TS-75-15: Ceiling clamp prevents timeout exceeding original * ceiling_factor."""

    def test_ceiling_clamp_when_multiplier_exceeds_ceiling(self) -> None:
        """TS-75-15: original=20, multiplier=2.0, ceiling=1.5 → clamped to 30."""
        handler, _, _, _, _ = _make_handler()

        # original_timeout=20, multiplier=2.0: ceil(20 * 2.0) = 40
        # ceiling = ceil(20 * 1.5) = 30 → clamped to 30
        ns = handler._get_node_state("node1")
        ns.timeout = 20
        handler._timeout_multiplier = 2.0
        handler._timeout_ceiling_factor = 1.5
        ns.max_turns = 100
        ns.has_max_turns = True

        handler._extend_node_params("node1")

        assert ns.timeout == 30


# ---------------------------------------------------------------------------
# TS-75-20: Multiplier 1.0 No Extension (parameter math test)
# Requirement: 75-REQ-4.E1
# ---------------------------------------------------------------------------


class TestMultiplierOneNoExtensionHandler:
    """TS-75-20: Multiplier=1.0 → timeout retries use same params as original."""

    def test_multiplier_one_no_change_to_turns(self) -> None:
        """TS-75-20: With multiplier=1.0, max_turns is unchanged after extension."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.max_turns = 200
        ns.has_max_turns = True
        ns.timeout = 30
        handler._timeout_multiplier = 1.0
        handler._timeout_ceiling_factor = 2.0

        handler._extend_node_params("node1")

        assert ns.max_turns == 200

    def test_multiplier_one_no_change_to_timeout(self) -> None:
        """TS-75-20: With multiplier=1.0, session_timeout unchanged after extend."""
        handler, _, _, _, _ = _make_handler()

        ns = handler._get_node_state("node1")
        ns.max_turns = 200
        ns.has_max_turns = True
        ns.timeout = 30
        handler._timeout_multiplier = 1.0
        handler._timeout_ceiling_factor = 2.0

        handler._extend_node_params("node1")

        assert ns.timeout == 30


# ---------------------------------------------------------------------------
# TS-75-21: Timeout Retry Audit Event
# Requirement: 75-REQ-5.1
# ---------------------------------------------------------------------------


class TestTimeoutRetryAuditEvent:
    """TS-75-21: SESSION_TIMEOUT_RETRY event is emitted on timeout retry."""

    def test_timeout_retry_emits_audit_event(self) -> None:
        """TS-75-21: Processing a timeout record emits SESSION_TIMEOUT_RETRY event."""
        from agent_fox.knowledge.audit import AuditEventType

        # Currently FAILS: SESSION_TIMEOUT_RETRY doesn't exist.
        event_type = AuditEventType.SESSION_TIMEOUT_RETRY

        sink = _EventCaptureSink()
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(sink=sink)

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        events = sink.find_events(event_type)
        assert len(events) >= 1

    def test_timeout_retry_event_has_required_payload_fields(self) -> None:
        """TS-75-21: SESSION_TIMEOUT_RETRY event payload has timeout_retry_count."""
        from agent_fox.knowledge.audit import AuditEventType

        event_type = AuditEventType.SESSION_TIMEOUT_RETRY  # Currently FAILS

        sink = _EventCaptureSink()
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(sink=sink)

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        events = sink.find_events(event_type)
        assert len(events) >= 1
        payload = events[0].payload
        assert "timeout_retry_count" in payload
        assert "extended_timeout" in payload


# ---------------------------------------------------------------------------
# TS-75-22: Exhaustion Warning Log
# Requirement: 75-REQ-5.2
# ---------------------------------------------------------------------------


class TestExhaustionWarningLog:
    """TS-75-22: Warning logged when timeout retries are exhausted."""

    def test_warning_logged_on_timeout_exhaustion(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-75-22: Warning mentioning exhaustion is emitted when retries run out."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler()

        handler._get_node_state("node1").timeout_retries = 2
        handler._max_timeout_retries = 2

        record = _make_record("timeout")

        with caplog.at_level(logging.WARNING):
            handler.process(
                record,
                attempt=3,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        # At least one warning must mention exhaustion.
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("exhausted" in msg.lower() or "timeout" in msg.lower() for msg in warning_messages), (
            f"Expected exhaustion warning, got: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# TS-75-23: Audit Event Payload Contains Original and Extended Values
# Requirement: 75-REQ-5.3
# ---------------------------------------------------------------------------


class TestAuditEventPayloadValues:
    """TS-75-23: SESSION_TIMEOUT_RETRY payload contains before/after values."""

    def test_payload_contains_original_and_extended_timeout(self) -> None:
        """TS-75-23: Payload includes original_timeout and extended_timeout."""
        from agent_fox.knowledge.audit import AuditEventType

        event_type = AuditEventType.SESSION_TIMEOUT_RETRY  # Currently FAILS

        sink = _EventCaptureSink()
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(sink=sink)

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        events = sink.find_events(event_type)
        assert len(events) >= 1
        payload = events[0].payload
        assert "original_timeout" in payload
        assert "extended_timeout" in payload
        assert "original_max_turns" in payload
        assert "extended_max_turns" in payload

    def test_payload_values_are_correct(self) -> None:
        """TS-75-23: Payload values match expected extended parameters."""
        from agent_fox.knowledge.audit import AuditEventType

        event_type = AuditEventType.SESSION_TIMEOUT_RETRY  # Currently FAILS

        sink = _EventCaptureSink()
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(sink=sink)

        ns = handler._get_node_state("node1")
        ns.max_turns = 200
        ns.has_max_turns = True
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        events = sink.find_events(event_type)
        assert len(events) >= 1
        payload = events[0].payload
        # original_timeout from config (default 30), extended = ceil(30 * 1.5) = 45
        assert payload.get("extended_timeout") == 45
        # original_max_turns=200, extended = ceil(200 * 1.5) = 300
        assert payload.get("extended_max_turns") == 300
