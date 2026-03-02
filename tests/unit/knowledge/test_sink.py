"""Tests for SessionSink protocol and SinkDispatcher.

Test Spec: TS-11-11 (dispatcher multi-sink), TS-11-12 (protocol structural typing)
Edge cases: TS-11-E4 (dispatcher fault isolation)
Requirements: 11-REQ-4.1, 11-REQ-4.2, 11-REQ-4.3
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.jsonl_sink import JsonlSink
from agent_fox.knowledge.sink import (
    SessionOutcome,
    SessionSink,
    SinkDispatcher,
    ToolCall,
    ToolError,
)

# -- Mock sink for testing ---------------------------------------------------


class MockSink:
    """A simple mock sink that counts received events."""

    def __init__(self) -> None:
        self.outcomes_received: int = 0
        self.tool_calls_received: int = 0
        self.tool_errors_received: int = 0
        self.closed: bool = False

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        self.outcomes_received += 1

    def record_tool_call(self, call: ToolCall) -> None:
        self.tool_calls_received += 1

    def record_tool_error(self, error: ToolError) -> None:
        self.tool_errors_received += 1

    def close(self) -> None:
        self.closed = True


class FailingSink:
    """A sink that always raises RuntimeError on every method."""

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        raise RuntimeError("sink failure")

    def record_tool_call(self, call: ToolCall) -> None:
        raise RuntimeError("sink failure")

    def record_tool_error(self, error: ToolError) -> None:
        raise RuntimeError("sink failure")

    def close(self) -> None:
        raise RuntimeError("sink failure")


class TestSinkDispatcherMultiSink:
    """TS-11-11: SinkDispatcher dispatches to multiple sinks.

    Requirement: 11-REQ-4.3
    """

    def test_dispatches_outcome_to_all_sinks(self) -> None:
        """Verify both sinks receive the session outcome."""
        mock1 = MockSink()
        mock2 = MockSink()
        dispatcher = SinkDispatcher([mock1, mock2])  # type: ignore[list-item]
        dispatcher.record_session_outcome(SessionOutcome(status="completed"))
        assert mock1.outcomes_received == 1
        assert mock2.outcomes_received == 1

    def test_dispatches_tool_call_to_all_sinks(self) -> None:
        """Verify both sinks receive tool call events."""
        mock1 = MockSink()
        mock2 = MockSink()
        dispatcher = SinkDispatcher([mock1, mock2])  # type: ignore[list-item]
        dispatcher.record_tool_call(ToolCall(tool_name="bash"))
        assert mock1.tool_calls_received == 1
        assert mock2.tool_calls_received == 1

    def test_dispatches_tool_error_to_all_sinks(self) -> None:
        """Verify both sinks receive tool error events."""
        mock1 = MockSink()
        mock2 = MockSink()
        dispatcher = SinkDispatcher([mock1, mock2])  # type: ignore[list-item]
        dispatcher.record_tool_error(ToolError(tool_name="bash"))
        assert mock1.tool_errors_received == 1
        assert mock2.tool_errors_received == 1

    def test_close_calls_all_sinks(self) -> None:
        """Verify close() is called on all sinks."""
        mock1 = MockSink()
        mock2 = MockSink()
        dispatcher = SinkDispatcher([mock1, mock2])  # type: ignore[list-item]
        dispatcher.close()
        assert mock1.closed is True
        assert mock2.closed is True

    def test_add_appends_sink(self) -> None:
        """Verify add() makes the sink receive subsequent events."""
        mock = MockSink()
        dispatcher = SinkDispatcher()
        dispatcher.add(mock)  # type: ignore[arg-type]
        dispatcher.record_session_outcome(SessionOutcome(status="completed"))
        assert mock.outcomes_received == 1


class TestSessionSinkProtocolStructuralTyping:
    """TS-11-12: SessionSink protocol structural typing.

    Requirements: 11-REQ-4.1, 11-REQ-5.1, 11-REQ-6.1
    """

    def test_duckdb_sink_isinstance(self) -> None:
        """Verify DuckDBSink satisfies the SessionSink protocol."""
        conn = duckdb.connect(":memory:")
        sink = DuckDBSink(conn)
        assert isinstance(sink, SessionSink)
        conn.close()

    def test_jsonl_sink_isinstance(self, tmp_path: Path) -> None:
        """Verify JsonlSink satisfies the SessionSink protocol."""
        sink = JsonlSink(directory=tmp_path)
        assert isinstance(sink, SessionSink)

    def test_mock_sink_isinstance(self) -> None:
        """Verify that a mock sink also satisfies the protocol."""
        mock = MockSink()
        assert isinstance(mock, SessionSink)


# -- Edge Case Tests ---------------------------------------------------------


class TestSinkDispatcherFaultIsolation:
    """TS-11-E4: SinkDispatcher isolates sink failures.

    Requirement: 11-REQ-4.3
    """

    def test_failing_sink_does_not_block_other_sinks(self) -> None:
        """Verify a failing sink does not prevent others from receiving events."""
        failing = FailingSink()
        mock = MockSink()
        dispatcher = SinkDispatcher(
            [failing, mock]  # type: ignore[list-item]
        )
        dispatcher.record_session_outcome(SessionOutcome(status="completed"))
        assert mock.outcomes_received == 1

    def test_failing_sink_does_not_block_tool_calls(self) -> None:
        """Verify tool call dispatch continues past a failing sink."""
        failing = FailingSink()
        mock = MockSink()
        dispatcher = SinkDispatcher(
            [failing, mock]  # type: ignore[list-item]
        )
        dispatcher.record_tool_call(ToolCall(tool_name="bash"))
        assert mock.tool_calls_received == 1

    def test_failing_sink_does_not_block_tool_errors(self) -> None:
        """Verify tool error dispatch continues past a failing sink."""
        failing = FailingSink()
        mock = MockSink()
        dispatcher = SinkDispatcher(
            [failing, mock]  # type: ignore[list-item]
        )
        dispatcher.record_tool_error(ToolError(tool_name="read"))
        assert mock.tool_errors_received == 1

    def test_failing_sink_does_not_block_close(self) -> None:
        """Verify close continues past a failing sink."""
        failing = FailingSink()
        mock = MockSink()
        dispatcher = SinkDispatcher(
            [failing, mock]  # type: ignore[list-item]
        )
        dispatcher.close()
        assert mock.closed is True
