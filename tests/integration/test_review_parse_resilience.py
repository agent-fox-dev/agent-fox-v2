"""Integration tests for review parse resilience: format retry logic.

Tests the end-to-end flow through persist_review_findings when parsing fails
and a format retry is attempted.

Test Spec: TS-74-14, TS-74-17, TS-74-18
Requirements: 74-REQ-3.1, 74-REQ-3.2, 74-REQ-3.3, 74-REQ-3.4, 74-REQ-3.5,
              74-REQ-3.E1, 74-REQ-5.1, 74-REQ-5.2
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.engine.review_persistence import persist_review_findings
from agent_fox.knowledge.audit import AuditEventType

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _EventCaptureSink:
    """Minimal SessionSink that captures emitted audit events."""

    def __init__(self) -> None:
        self.events: list[object] = []

    def emit_audit_event(self, event: object) -> None:
        self.events.append(event)

    def record_session_outcome(self, outcome: object) -> None:
        pass

    def record_tool_call(self, tool_call: object) -> None:
        pass

    def record_tool_error(self, error: object) -> None:
        pass

    def close(self) -> None:
        pass

    def has_event_type(self, event_type: AuditEventType) -> bool:
        return any(getattr(e, "event_type", None) == event_type for e in self.events)

    def get_events_of_type(self, event_type: AuditEventType) -> list[object]:
        return [e for e in self.events if getattr(e, "event_type", None) == event_type]


def _valid_skeptic_transcript() -> str:
    """Return a valid JSON transcript with one finding."""
    return json.dumps(
        {
            "findings": [
                {
                    "severity": "major",
                    "description": "Integration test finding",
                }
            ]
        }
    )


def _invalid_transcript() -> str:
    """Return a transcript with no valid JSON."""
    return "This is my analysis. I found some issues but cannot format them as JSON."


# ---------------------------------------------------------------------------
# TS-74-14: Format retry triggered on parse failure (REQ-3.1, REQ-3.5)
# ---------------------------------------------------------------------------


class TestFormatRetryTriggeredOnParseFailure:
    """TS-74-14: When extraction fails, a format retry is attempted.

    Requirements: 74-REQ-3.1, 74-REQ-3.5
    """

    def test_retry_attempted_when_first_parse_fails(
        self, knowledge_db: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When initial JSON extraction fails, backend receives retry message.

        The session_handle must be called with a retry prompt when extraction
        returns None on the first attempt.
        """
        sink = _EventCaptureSink()

        # Session handle: alive, returns valid JSON on retry
        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value=_valid_skeptic_transcript())

        extract_calls: list[str] = []

        def mock_extract(text: str, **kwargs):  # type: ignore[override]
            extract_calls.append(text)
            if len(extract_calls) == 1:
                return None  # First call fails
            # Second call: valid JSON (findings array)
            return json.loads(_valid_skeptic_transcript())["findings"]

        with patch("agent_fox.engine.review_persistence.extract_json_array", mock_extract):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        # Retry message must have been sent
        assert mock_session.append_user_message.called, "Backend must receive a retry message when initial parse fails"
        # Total extraction attempts: 2 (initial + retry)
        assert len(extract_calls) == 2, f"Expected exactly 2 extraction attempts, got {len(extract_calls)}"


# ---------------------------------------------------------------------------
# TS-74-17: Successful retry suppresses parse failure event (REQ-3.4, REQ-5.1)
# ---------------------------------------------------------------------------


class TestSuccessfulRetrySuppressesParseFailure:
    """TS-74-17: No REVIEW_PARSE_FAILURE when retry succeeds.

    Requirements: 74-REQ-3.4, 74-REQ-5.1
    """

    def test_no_parse_failure_event_when_retry_succeeds(self, knowledge_db: object) -> None:
        """REVIEW_PARSE_FAILURE must NOT be emitted when retry succeeds."""
        sink = _EventCaptureSink()

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value=_valid_skeptic_transcript())

        call_count = [0]

        def mock_extract(text: str, **kwargs):  # type: ignore[override]
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # First call: fail
            # Second call: success — return the findings array
            return json.loads(_valid_skeptic_transcript())["findings"]

        with patch("agent_fox.engine.review_persistence.extract_json_array", mock_extract):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        assert not sink.has_event_type(AuditEventType.REVIEW_PARSE_FAILURE), (
            "REVIEW_PARSE_FAILURE must not be emitted when retry succeeds"
        )

    def test_retry_success_event_emitted_when_retry_succeeds(self, knowledge_db: object) -> None:
        """REVIEW_PARSE_RETRY_SUCCESS event emitted when retry produces output."""
        sink = _EventCaptureSink()

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value=_valid_skeptic_transcript())

        call_count = [0]

        def mock_extract(text: str, **kwargs):  # type: ignore[override]
            call_count[0] += 1
            if call_count[0] == 1:
                return None
            return json.loads(_valid_skeptic_transcript())["findings"]

        with patch("agent_fox.engine.review_persistence.extract_json_array", mock_extract):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        assert sink.has_event_type(AuditEventType.REVIEW_PARSE_RETRY_SUCCESS), (
            "REVIEW_PARSE_RETRY_SUCCESS event must be emitted when retry succeeds"
        )

        retry_events = sink.get_events_of_type(AuditEventType.REVIEW_PARSE_RETRY_SUCCESS)
        assert len(retry_events) > 0
        event = retry_events[0]
        assert getattr(event, "archetype", None) == "skeptic" or ("archetype" in getattr(event, "payload", {})), (
            "REVIEW_PARSE_RETRY_SUCCESS must include archetype information"
        )


# ---------------------------------------------------------------------------
# TS-74-18: Failed retry emits parse failure with retry_attempted (REQ-3.E1, REQ-5.2)
# ---------------------------------------------------------------------------


class TestFailedRetryEmitsParseFailure:
    """TS-74-18: REVIEW_PARSE_FAILURE emitted with retry_attempted=True.

    Requirements: 74-REQ-3.E1, 74-REQ-5.2
    """

    def test_parse_failure_event_emitted_when_retry_fails(self, knowledge_db: object) -> None:
        """REVIEW_PARSE_FAILURE emitted when both initial parse and retry fail."""
        sink = _EventCaptureSink()

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value="still no json here")

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=None,
        ):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        assert sink.has_event_type(AuditEventType.REVIEW_PARSE_FAILURE), (
            "REVIEW_PARSE_FAILURE must be emitted when both parses fail"
        )

    def test_parse_failure_payload_includes_retry_attempted_true(self, knowledge_db: object) -> None:
        """REVIEW_PARSE_FAILURE payload has retry_attempted=True when retried."""
        sink = _EventCaptureSink()

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value="still no json here")

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=None,
        ):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        failure_events = sink.get_events_of_type(AuditEventType.REVIEW_PARSE_FAILURE)
        assert len(failure_events) > 0

        payload = getattr(failure_events[0], "payload", {})
        assert "retry_attempted" in payload, "REVIEW_PARSE_FAILURE payload must include 'retry_attempted' field"
        assert payload["retry_attempted"] is True, "retry_attempted must be True when retry was attempted"

    def test_parse_failure_payload_includes_strategy_field(self, knowledge_db: object) -> None:
        """REVIEW_PARSE_FAILURE payload has strategy field when retry attempted."""
        sink = _EventCaptureSink()

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value="still no json")

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=None,
        ):
            persist_review_findings(
                transcript=_invalid_transcript(),
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=knowledge_db,
                sink=sink,
                run_id="run1",
                session_handle=mock_session,
            )

        failure_events = sink.get_events_of_type(AuditEventType.REVIEW_PARSE_FAILURE)
        assert len(failure_events) > 0

        payload = getattr(failure_events[0], "payload", {})
        assert "strategy" in payload, "REVIEW_PARSE_FAILURE payload must include 'strategy' field"
        assert "retry" in payload["strategy"], "Strategy field must mention 'retry' when retry was attempted"
