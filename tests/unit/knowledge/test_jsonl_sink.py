"""Tests for JSONL sink implementation.

Test Spec: TS-11-10 (writes events to file)
Edge cases: TS-11-E6 (empty touched paths)
Requirements: 11-REQ-6.1, 11-REQ-6.2
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_fox.knowledge.jsonl_sink import JsonlSink
from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError


class TestJsonlSinkWritesEvents:
    """TS-11-10: JSONL sink writes events to file.

    Requirements: 11-REQ-6.1, 11-REQ-6.2
    """

    def test_writes_all_event_types(self, tmp_path: Path) -> None:
        """Verify session outcome, tool call, and tool error are written."""
        sink = JsonlSink(directory=tmp_path, session_id="test-session")
        sink.record_session_outcome(
            SessionOutcome(spec_name="s1", status="completed")
        )
        sink.record_tool_call(ToolCall(tool_name="bash"))
        sink.record_tool_error(ToolError(tool_name="read"))
        sink.close()

        jsonl_files = list(tmp_path.glob("*.jsonl"))
        assert len(jsonl_files) == 1

        lines = jsonl_files[0].read_text().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            data = json.loads(line)
            assert "event_type" in data

    def test_event_types_are_correct(self, tmp_path: Path) -> None:
        """Verify each event has the correct event_type field."""
        sink = JsonlSink(directory=tmp_path, session_id="test-session-2")
        sink.record_session_outcome(
            SessionOutcome(spec_name="s1", status="completed")
        )
        sink.record_tool_call(ToolCall(tool_name="bash"))
        sink.record_tool_error(ToolError(tool_name="read"))
        sink.close()

        jsonl_files = list(tmp_path.glob("*.jsonl"))
        lines = jsonl_files[0].read_text().strip().split("\n")
        event_types = [json.loads(line)["event_type"] for line in lines]
        assert "session_outcome" in event_types
        assert "tool_call" in event_types
        assert "tool_error" in event_types


# -- Edge Case Tests ---------------------------------------------------------


class TestJsonlSinkEmptyTouchedPaths:
    """TS-11-E6: JSONL sink handles empty touched_paths.

    Requirement: 11-REQ-6.2
    """

    def test_empty_touched_paths_written(self, tmp_path: Path) -> None:
        """Verify session outcome with empty touched_paths produces valid JSON."""
        sink = JsonlSink(directory=tmp_path, session_id="test")
        sink.record_session_outcome(
            SessionOutcome(status="failed", touched_paths=[])
        )
        sink.close()

        jsonl_files = list(tmp_path.glob("*.jsonl"))
        assert len(jsonl_files) == 1

        lines = jsonl_files[0].read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["touched_paths"] == []
