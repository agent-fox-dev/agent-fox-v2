"""Unit tests for AgentTraceSink and truncate_tool_input.

Test Spec: TS-103-1 through TS-103-11, TS-103-14
Requirements: 103-REQ-1.2, 103-REQ-1.3, 103-REQ-1.E1, 103-REQ-1.E2,
              103-REQ-2.1, 103-REQ-2.2, 103-REQ-3.1, 103-REQ-3.2,
              103-REQ-4.1, 103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1,
              103-REQ-5.1, 103-REQ-6.1, 103-REQ-8.1, 103-REQ-8.2, 103-REQ-8.E1
"""

from __future__ import annotations

import json
import logging
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.agent_trace import AgentTraceSink
from agent_fox.knowledge.audit import enforce_audit_retention

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUN_ID = "20260414_120000_abc123"
NODE_ID = "05_feature:coder:1"
MODEL_ID = "claude-sonnet-4-6"
ARCHETYPE = "coder"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_lines(path: Path) -> list[str]:
    """Read non-empty lines from a JSONL file."""
    return [line for line in path.read_text().split("\n") if line.strip()]


def _last_event(path: Path) -> dict:
    """Parse the last JSON line in the trace file."""
    lines = _read_lines(path)
    return json.loads(lines[-1])


def _trace_path(audit_dir: Path, run_id: str = RUN_ID) -> Path:
    """Return the expected trace file path for a given run_id."""
    return audit_dir / f"agent_{run_id}.jsonl"


def _minimal_session_init(sink: AgentTraceSink, *, run_id: str = RUN_ID) -> None:
    """Emit a minimal session.init event."""
    sink.record_session_init(
        run_id=run_id,
        node_id=NODE_ID,
        model_id=MODEL_ID,
        archetype=ARCHETYPE,
        system_prompt="sys",
        task_prompt="task",
    )


# ---------------------------------------------------------------------------
# TS-103-1: File creation on first write
# ---------------------------------------------------------------------------


class TestFileCreation:
    """TS-103-1: AgentTraceSink creates file at correct path on first write.

    Requirements: 103-REQ-1.2
    """

    def test_creates_file_on_first_write(self, tmp_path: Path) -> None:
        """Trace file is created at the canonical path on first event."""
        sink = AgentTraceSink(tmp_path, RUN_ID)
        _minimal_session_init(sink)

        path = _trace_path(tmp_path)
        assert path.exists()
        lines = _read_lines(path)
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# TS-103-2: JSONL format — one JSON object per line
# ---------------------------------------------------------------------------


class TestJsonlFormat:
    """TS-103-2: Each event is a valid JSON object on its own line, flushed.

    Requirements: 103-REQ-1.3
    """

    def test_jsonl_format(self, tmp_path: Path) -> None:
        """Three events produce exactly three valid JSONL lines."""
        sink = AgentTraceSink(tmp_path, RUN_ID)

        sink.record_session_init(
            run_id=RUN_ID,
            node_id=NODE_ID,
            model_id=MODEL_ID,
            archetype=ARCHETYPE,
            system_prompt="sys",
            task_prompt="task",
        )
        sink.record_assistant_message(
            run_id=RUN_ID,
            node_id=NODE_ID,
            content="I'll start by reading the code.",
        )
        sink.record_session_result(
            run_id=RUN_ID,
            node_id=NODE_ID,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            duration_ms=1000,
            is_error=False,
            error_message=None,
        )

        path = _trace_path(tmp_path)
        lines = _read_lines(path)
        assert len(lines) == 3

        events = [json.loads(line) for line in lines]
        assert events[0]["event_type"] == "session.init"
        assert events[1]["event_type"] == "assistant.message"
        assert events[2]["event_type"] == "session.result"


# ---------------------------------------------------------------------------
# TS-103-3: Audit directory created if missing
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    """TS-103-3: AgentTraceSink creates audit_dir on first write.

    Requirements: 103-REQ-1.E1
    """

    def test_creates_missing_directory(self, tmp_path: Path) -> None:
        """Sink creates a missing audit directory on first write."""
        audit_dir = tmp_path / "nonexistent" / "audit"
        assert not audit_dir.exists()

        sink = AgentTraceSink(audit_dir, RUN_ID)
        _minimal_session_init(sink)

        assert audit_dir.exists()
        assert _trace_path(audit_dir).exists()


# ---------------------------------------------------------------------------
# TS-103-4: Write failure is logged, not raised
# ---------------------------------------------------------------------------


class TestWriteFailure:
    """TS-103-4: I/O errors during write are swallowed with a warning log.

    Requirements: 103-REQ-1.E2
    """

    def test_write_failure_logged(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Write errors are caught and logged as warnings; no exception propagates."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)

        # Make directory read-only so file creation fails with PermissionError
        old_mode = audit_dir.stat().st_mode
        audit_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            sink = AgentTraceSink(audit_dir, RUN_ID)
            with caplog.at_level(logging.WARNING):
                # Must not raise even though write will fail
                _minimal_session_init(sink)

            warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warning_records) > 0, "Expected a warning to be logged on write failure"
        finally:
            # Restore permissions so tmp_path cleanup succeeds
            audit_dir.chmod(old_mode)


# ---------------------------------------------------------------------------
# TS-103-5: session.init captures prompts verbatim
# ---------------------------------------------------------------------------


class TestSessionInit:
    """TS-103-5: session.init event captures all fields verbatim.

    Requirements: 103-REQ-2.1, 103-REQ-2.2
    """

    def test_session_init_prompts(self, tmp_path: Path) -> None:
        """session.init captures system_prompt and task_prompt verbatim (no truncation)."""
        # Use a large system prompt to verify no truncation occurs
        system_prompt = "You are a coding agent. " * 5000
        task_prompt = "Implement feature X based on the specification."

        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_session_init(
            run_id=RUN_ID,
            node_id=NODE_ID,
            model_id=MODEL_ID,
            archetype=ARCHETYPE,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "session.init"
        assert event["run_id"] == RUN_ID
        assert event["node_id"] == NODE_ID
        assert event["model_id"] == MODEL_ID
        assert event["archetype"] == ARCHETYPE
        # No truncation: exact match
        assert event["system_prompt"] == system_prompt
        assert event["task_prompt"] == task_prompt
        # Timestamp field present
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# TS-103-6: assistant.message captures full content
# ---------------------------------------------------------------------------


class TestAssistantMessage:
    """TS-103-6: assistant.message event captures content verbatim.

    Requirements: 103-REQ-3.1, 103-REQ-3.2
    """

    def test_assistant_message_content(self, tmp_path: Path) -> None:
        """assistant.message captures content exactly, including [thinking] prefix."""
        content = "[thinking] Let me analyze... I'll start by reading the file."

        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_assistant_message(
            run_id=RUN_ID,
            node_id=NODE_ID,
            content=content,
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "assistant.message"
        assert event["run_id"] == RUN_ID
        assert event["node_id"] == NODE_ID
        assert event["content"] == content
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# TS-103-7: tool.use captures name and truncated input
# ---------------------------------------------------------------------------


class TestToolUse:
    """TS-103-7: tool.use event with correct name and truncated string input.

    Requirements: 103-REQ-4.1, 103-REQ-4.2
    """

    def test_tool_use_truncation(self, tmp_path: Path) -> None:
        """String values over 10,000 chars are truncated with ' [truncated]' marker."""
        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_tool_use(
            run_id=RUN_ID,
            node_id=NODE_ID,
            tool_name="Write",
            tool_input={
                "file_path": "/short.py",
                "content": "x" * 20_000,
            },
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "tool.use"
        assert event["tool_name"] == "Write"
        # Short string: no truncation
        assert event["tool_input"]["file_path"] == "/short.py"
        # Long string: truncated to 10,000 chars + marker
        truncated_content = event["tool_input"]["content"]
        assert truncated_content.endswith(" [truncated]")
        assert len(truncated_content) == 10_000 + len(" [truncated]")


# ---------------------------------------------------------------------------
# TS-103-8: Non-string values in tool_input are preserved
# ---------------------------------------------------------------------------


class TestToolUseNonString:
    """TS-103-8: Non-string values in tool_input are passed through unchanged.

    Requirements: 103-REQ-4.3
    """

    def test_tool_use_non_string_preserved(self, tmp_path: Path) -> None:
        """Integers, booleans, and lists in tool_input are not modified."""
        tool_input = {
            "timeout": 5000,
            "force": True,
            "tags": ["a", "b"],
        }
        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_tool_use(
            run_id=RUN_ID,
            node_id=NODE_ID,
            tool_name="Bash",
            tool_input=tool_input,
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["tool_input"]["timeout"] == 5000
        assert event["tool_input"]["force"] is True
        assert event["tool_input"]["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# TS-103-9: Empty tool_input is emitted unchanged
# ---------------------------------------------------------------------------


class TestToolUseEmpty:
    """TS-103-9: Empty tool_input dict is emitted as-is.

    Requirements: 103-REQ-4.E1
    """

    def test_tool_use_empty_input(self, tmp_path: Path) -> None:
        """Empty tool_input results in an event with an empty tool_input dict."""
        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_tool_use(
            run_id=RUN_ID,
            node_id=NODE_ID,
            tool_name="Bash",
            tool_input={},
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "tool.use"
        assert event["tool_input"] == {}


# ---------------------------------------------------------------------------
# TS-103-10: tool.error event on session failure
# ---------------------------------------------------------------------------


class TestToolError:
    """TS-103-10: tool.error event is emitted with correct fields.

    Requirements: 103-REQ-5.1
    """

    def test_tool_error_event(self, tmp_path: Path) -> None:
        """tool.error event captures tool_name and error_message."""
        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_tool_error_trace(
            run_id=RUN_ID,
            node_id=NODE_ID,
            tool_name="Bash",
            error_message="Command failed with exit code 1",
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "tool.error"
        assert event["run_id"] == RUN_ID
        assert event["node_id"] == NODE_ID
        assert event["tool_name"] == "Bash"
        assert event["error_message"] == "Command failed with exit code 1"
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# TS-103-11: session.result captures terminal metrics
# ---------------------------------------------------------------------------


class TestSessionResult:
    """TS-103-11: session.result event contains all metric fields.

    Requirements: 103-REQ-6.1
    """

    def test_session_result_metrics(self, tmp_path: Path) -> None:
        """session.result captures all token usage, duration, and status fields."""
        sink = AgentTraceSink(tmp_path, RUN_ID)
        sink.record_session_result(
            run_id=RUN_ID,
            node_id=NODE_ID,
            status="completed",
            input_tokens=15_000,
            output_tokens=3_200,
            cache_read_input_tokens=8_000,
            cache_creation_input_tokens=2_000,
            duration_ms=30_000,
            is_error=False,
            error_message=None,
        )

        event = _last_event(_trace_path(tmp_path))
        assert event["event_type"] == "session.result"
        assert event["run_id"] == RUN_ID
        assert event["node_id"] == NODE_ID
        assert event["status"] == "completed"
        assert event["input_tokens"] == 15_000
        assert event["output_tokens"] == 3_200
        assert event["cache_read_input_tokens"] == 8_000
        assert event["cache_creation_input_tokens"] == 2_000
        assert event["duration_ms"] == 30_000
        assert event["is_error"] is False
        assert event["error_message"] is None
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# TS-103-14: Audit retention preserves agent_*.jsonl files
# ---------------------------------------------------------------------------


def _make_audit_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the audit_events table in an in-memory DuckDB connection."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id          TEXT PRIMARY KEY,
            timestamp   TIMESTAMP NOT NULL,
            run_id      TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            node_id     TEXT,
            session_id  TEXT,
            archetype   TEXT,
            severity    TEXT,
            payload     TEXT
        )
        """
    )


def _insert_run_events(
    conn: duckdb.DuckDBPyConnection,
    audit_dir: Path,
    run_id: str,
    timestamp: datetime,
    *,
    create_agent_file: bool = True,
) -> None:
    """Insert DuckDB events and create JSONL files for a run."""
    import uuid

    conn.execute(
        """
        INSERT INTO audit_events
            (id, timestamp, run_id, event_type, node_id, session_id,
             archetype, severity, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [str(uuid.uuid4()), timestamp, run_id, "run.start", "", "", "", "info", "{}"],
    )

    # Create audit JSONL file
    audit_file = audit_dir / f"audit_{run_id}.jsonl"
    audit_file.write_text(json.dumps({"run_id": run_id, "event_type": "run.start"}) + "\n")

    # Create agent trace JSONL file
    if create_agent_file:
        agent_file = audit_dir / f"agent_{run_id}.jsonl"
        agent_file.write_text(json.dumps({"event_type": "session.init", "run_id": run_id}) + "\n")


class TestRetentionPreservesAgentFiles:
    """TS-103-14: enforce_audit_retention preserves agent_*.jsonl files.

    Requirements: 103-REQ-8.1, 103-REQ-8.2, 103-REQ-8.E1
    """

    def test_retention_preserves_agent_files(self, tmp_path: Path) -> None:
        """Agent trace files survive audit retention cleanup.

        When max_runs=1, only run_A (the oldest) is pruned:
          - audit_run_A.jsonl → deleted
          - agent_run_A.jsonl → preserved
          - audit_run_B.jsonl → preserved (not pruned)
          - agent_run_B.jsonl → preserved (not pruned)
        """
        conn = duckdb.connect(":memory:")
        _make_audit_schema(conn)
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        run_a = "20260101_000000_aaa001"
        run_b = "20260101_010000_bbb002"

        _insert_run_events(conn, audit_dir, run_a, base_time)
        _insert_run_events(conn, audit_dir, run_b, base_time + timedelta(hours=1))

        # Run retention with max_runs=1 → prunes run_A (older)
        enforce_audit_retention(audit_dir, conn, max_runs=1)

        # Audit file for pruned run: deleted
        assert not (audit_dir / f"audit_{run_a}.jsonl").exists()

        # Agent trace file for pruned run: preserved
        assert (audit_dir / f"agent_{run_a}.jsonl").exists()

        # Both files for non-pruned run: preserved
        assert (audit_dir / f"audit_{run_b}.jsonl").exists()
        assert (audit_dir / f"agent_{run_b}.jsonl").exists()
