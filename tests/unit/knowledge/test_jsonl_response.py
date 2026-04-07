"""Unit tests for JSONL response field logging.

Validates that JsonlSink.record_session_outcome() writes the response
field to JSONL records, handles empty responses, and truncates responses
exceeding 100,000 characters.

Test Spec: TS-84-1, TS-84-2, TS-84-E1
Requirements: 84-REQ-1.1, 84-REQ-1.2, 84-REQ-1.E1
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_fox.knowledge.jsonl_sink import JsonlSink
from agent_fox.knowledge.sink import SessionOutcome


def _read_last_jsonl_record(directory: Path) -> dict:
    """Read the last JSONL line from the most recent file in directory."""
    jsonl_files = sorted(directory.glob("*.jsonl"))
    assert jsonl_files, "No JSONL files found"
    lines = jsonl_files[-1].read_text().strip().splitlines()
    assert lines, "JSONL file is empty"
    return json.loads(lines[-1])


class TestJsonlResponseField:
    """TS-84-1: JSONL sink writes response field."""

    def test_response_field_written(self, tmp_path: Path) -> None:
        """Verify record_session_outcome includes response field in JSONL record."""
        sink = JsonlSink(tmp_path, session_id="test")
        outcome = SessionOutcome(
            response='{"findings": [{"severity": "critical"}]}',
            node_id="spec:0",
            status="completed",
        )
        sink.record_session_outcome(outcome)
        sink.close()

        record = _read_last_jsonl_record(tmp_path)
        assert "response" in record
        assert record["response"] == outcome.response

    def test_response_field_preserves_content(self, tmp_path: Path) -> None:
        """Verify response field exactly matches the SessionOutcome.response value."""
        response_text = '{"findings": [{"severity": "major", "description": "test"}]}'
        sink = JsonlSink(tmp_path, session_id="test")
        outcome = SessionOutcome(
            response=response_text,
            node_id="s:0",
            status="completed",
        )
        sink.record_session_outcome(outcome)
        sink.close()

        record = _read_last_jsonl_record(tmp_path)
        assert record["response"] == response_text


class TestJsonlEmptyResponse:
    """TS-84-2: JSONL sink writes empty response as empty string."""

    def test_empty_response_written_as_empty_string(self, tmp_path: Path) -> None:
        """Verify empty response is written as '', not omitted."""
        sink = JsonlSink(tmp_path, session_id="test")
        outcome = SessionOutcome(response="", node_id="spec:0", status="completed")
        sink.record_session_outcome(outcome)
        sink.close()

        record = _read_last_jsonl_record(tmp_path)
        assert "response" in record
        assert record["response"] == ""


class TestJsonlResponseTruncation:
    """TS-84-E1: Response truncation at 100k characters."""

    def test_long_response_truncated(self, tmp_path: Path) -> None:
        """Verify response > 100,000 chars is truncated with [truncated] marker."""
        long_response = "x" * 150_000
        sink = JsonlSink(tmp_path, session_id="test")
        outcome = SessionOutcome(
            response=long_response,
            node_id="spec:0",
            status="completed",
        )
        sink.record_session_outcome(outcome)
        sink.close()

        record = _read_last_jsonl_record(tmp_path)
        assert record["response"].endswith("[truncated]")
        assert len(record["response"]) == 100_011  # 100,000 + len("[truncated]")

    def test_response_at_limit_not_truncated(self, tmp_path: Path) -> None:
        """Verify response of exactly 100,000 chars is NOT truncated."""
        exact_response = "x" * 100_000
        sink = JsonlSink(tmp_path, session_id="test")
        outcome = SessionOutcome(
            response=exact_response,
            node_id="spec:0",
            status="completed",
        )
        sink.record_session_outcome(outcome)
        sink.close()

        record = _read_last_jsonl_record(tmp_path)
        assert record["response"] == exact_response
        assert not record["response"].endswith("[truncated]")
