"""Tests for audit sink implementations, protocol extension, and migration.

Test Spec: TS-40-7 through TS-40-16
Requirements: 40-REQ-3.1, 40-REQ-3.2, 40-REQ-3.3, 40-REQ-4.1, 40-REQ-4.2,
              40-REQ-4.E1, 40-REQ-5.1, 40-REQ-5.2, 40-REQ-6.1, 40-REQ-6.2,
              40-REQ-6.3, 40-REQ-6.4, 40-REQ-6.E1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
import pytest
from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditJsonlSink,
    AuditSeverity,
)

from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.migrations import MIGRATIONS
from agent_fox.knowledge.sink import (
    SessionOutcome,
    SessionSink,
    SinkDispatcher,
    ToolCall,
    ToolError,
)

# -- Mock sinks for audit event testing -------------------------------------


class AuditMockSink:
    """A mock sink that records audit events."""

    def __init__(self) -> None:
        self.audit_events: list[AuditEvent] = []

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        pass

    def record_tool_call(self, call: ToolCall) -> None:
        pass

    def record_tool_error(self, error: ToolError) -> None:
        pass

    def emit_audit_event(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    def close(self) -> None:
        pass


class AuditFailingSink:
    """A sink that raises on emit_audit_event."""

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        pass

    def record_tool_call(self, call: ToolCall) -> None:
        pass

    def record_tool_error(self, error: ToolError) -> None:
        pass

    def emit_audit_event(self, event: AuditEvent) -> None:
        raise RuntimeError("audit sink failure")

    def close(self) -> None:
        pass


# -- TS-40-9: SessionSink Protocol ------------------------------------------


class TestSessionSinkProtocol:
    """TS-40-9: SessionSink protocol includes emit_audit_event.

    Requirement: 40-REQ-4.1
    """

    def test_has_method(self) -> None:
        """SessionSink protocol includes emit_audit_event method."""
        assert hasattr(SessionSink, "emit_audit_event")


# -- TS-40-10, TS-40-11: SinkDispatcher Audit --------------------------------


class TestSinkDispatcherAudit:
    """TS-40-10, TS-40-11: SinkDispatcher dispatches emit_audit_event.

    Requirements: 40-REQ-4.2, 40-REQ-4.E1
    """

    def test_dispatches(self) -> None:
        """TS-40-10: emit_audit_event dispatched to all registered sinks."""
        sink1 = AuditMockSink()
        sink2 = AuditMockSink()
        dispatcher = SinkDispatcher([sink1, sink2])  # type: ignore[list-item]
        event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        dispatcher.emit_audit_event(event)
        assert len(sink1.audit_events) == 1
        assert sink1.audit_events[0] is event
        assert len(sink2.audit_events) == 1
        assert sink2.audit_events[0] is event

    def test_swallows_failures(self) -> None:
        """TS-40-11: Failing sink does not block other sinks."""
        failing = AuditFailingSink()
        working = AuditMockSink()
        dispatcher = SinkDispatcher([failing, working])  # type: ignore[list-item]
        event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        dispatcher.emit_audit_event(event)  # should not raise
        assert len(working.audit_events) == 1
        assert working.audit_events[0] is event


# -- TS-40-12: DuckDBSink Audit ----------------------------------------------


class TestDuckDBSinkAudit:
    """TS-40-12: DuckDBSink inserts audit events.

    Requirements: 40-REQ-5.1, 40-REQ-5.2
    """

    def test_inserts(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """DuckDBSink.emit_audit_event inserts a row into audit_events."""
        sink = DuckDBSink(knowledge_conn)
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_START,
            payload={"plan_hash": "abc123"},
        )
        sink.emit_audit_event(event)
        row = knowledge_conn.execute(
            "SELECT * FROM audit_events WHERE id = ?", [str(event.id)]
        ).fetchone()
        assert row is not None

    def test_json_payload(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Payload is serialized as JSON."""
        sink = DuckDBSink(knowledge_conn)
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_START,
            payload={"plan_hash": "abc123", "total_nodes": 5},
        )
        sink.emit_audit_event(event)
        row = knowledge_conn.execute(
            "SELECT payload FROM audit_events WHERE id = ?", [str(event.id)]
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload["plan_hash"] == "abc123"
        assert payload["total_nodes"] == 5

    def test_all_fields_stored(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """All AuditEvent fields are stored correctly."""
        sink = DuckDBSink(knowledge_conn)
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_FAIL,
            severity=AuditSeverity.ERROR,
            node_id="spec/1",
            session_id="sess-123",
            archetype="coder",
            payload={"error_message": "fail"},
        )
        sink.emit_audit_event(event)
        row = knowledge_conn.execute(
            "SELECT run_id, event_type, severity, node_id, session_id, archetype "
            "FROM audit_events WHERE id = ?",
            [str(event.id)],
        ).fetchone()
        assert row is not None
        assert row[0] == "r1"
        assert row[1] == "session.fail"
        assert row[2] == "error"
        assert row[3] == "spec/1"
        assert row[4] == "sess-123"
        assert row[5] == "coder"


# -- TS-40-13 through TS-40-16: AuditJsonlSink --------------------------------


class TestAuditJsonlSink:
    """TS-40-13 through TS-40-16: AuditJsonlSink implementation.

    Requirements: 40-REQ-6.1, 40-REQ-6.2, 40-REQ-6.3, 40-REQ-6.4, 40-REQ-6.E1
    """

    def test_creates_dir(self, tmp_path: Path) -> None:
        """TS-40-13: AuditJsonlSink creates directory on init."""
        audit_dir = tmp_path / ".agent-fox" / "audit"
        assert not audit_dir.exists()
        AuditJsonlSink(audit_dir, "r1")
        assert audit_dir.exists()

    def test_writes_lines(self, tmp_path: Path) -> None:
        """TS-40-14: emit_audit_event appends valid JSON lines."""
        audit_dir = tmp_path / "audit"
        sink = AuditJsonlSink(audit_dir, "r1")
        event1 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        event2 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_COMPLETE)
        sink.emit_audit_event(event1)
        sink.emit_audit_event(event2)
        file_path = audit_dir / "audit_r1.jsonl"
        lines = file_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_json_format(self, tmp_path: Path) -> None:
        """TS-40-14: Each line has correct JSON format with all fields."""
        audit_dir = tmp_path / "audit"
        sink = AuditJsonlSink(audit_dir, "r1")
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_START,
            payload={"key": "value"},
        )
        sink.emit_audit_event(event)
        file_path = audit_dir / "audit_r1.jsonl"
        parsed = json.loads(file_path.read_text().strip())
        assert "id" in parsed
        assert "timestamp" in parsed
        assert "event_type" in parsed
        assert parsed["event_type"] == "run.start"
        assert "payload" in parsed
        assert parsed["payload"]["key"] == "value"
        assert "run_id" in parsed
        assert "severity" in parsed
        assert "node_id" in parsed
        assert "session_id" in parsed
        assert "archetype" in parsed

    def test_noop_methods(self, tmp_path: Path) -> None:
        """TS-40-15: Other SessionSink methods are no-ops."""
        audit_dir = tmp_path / "audit"
        sink = AuditJsonlSink(audit_dir, "r1")
        # These should not raise
        sink.record_session_outcome(SessionOutcome())
        sink.record_tool_call(ToolCall())
        sink.record_tool_error(ToolError())
        sink.close()
        # No audit file should be created by these methods
        file_path = audit_dir / "audit_r1.jsonl"
        assert not file_path.exists()

    def test_write_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TS-40-16: Write failure logs warning but does not raise."""
        # Use a path that will fail on write
        sink = AuditJsonlSink(Path("/nonexistent/path/audit"), "r1")
        event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        with caplog.at_level(logging.WARNING):
            sink.emit_audit_event(event)  # should not raise
        assert any("Failed to write audit event" in r.message for r in caplog.records)


# -- TS-40-7, TS-40-8: Migration Tests ----------------------------------------


class TestMigration:
    """TS-40-7, TS-40-8: DuckDB v6 migration for audit_events.

    Requirements: 40-REQ-3.1, 40-REQ-3.2, 40-REQ-3.3
    """

    def test_creates_table(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-7: Migration v6 creates audit_events table with correct columns."""
        result = knowledge_conn.execute("SELECT * FROM audit_events LIMIT 0")
        columns = {desc[0] for desc in result.description}
        expected = {
            "id",
            "timestamp",
            "run_id",
            "event_type",
            "node_id",
            "session_id",
            "archetype",
            "severity",
            "payload",
        }
        assert expected <= columns

    def test_creates_indexes(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-7: Indexes on run_id and event_type exist."""
        # DuckDB stores index info in duckdb_indexes()
        indexes = knowledge_conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'audit_events'"
        ).fetchall()
        index_names = {row[0] for row in indexes}
        assert "idx_audit_run_id" in index_names
        assert "idx_audit_event_type" in index_names

    def test_registered(self) -> None:
        """TS-40-8: v6 migration is registered in MIGRATIONS list."""
        versions = [m.version for m in MIGRATIONS]
        assert 6 in versions
