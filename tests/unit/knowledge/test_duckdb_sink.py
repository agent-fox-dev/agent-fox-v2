"""Tests for DuckDB sink implementation.

Test Spec: TS-11-7 (always-on outcomes), TS-11-8 (tool telemetry always-on),
           TS-11-9 (multiple touched paths)
Edge cases: TS-11-E3 (write failure non-fatal), TS-11-E7 (empty touched paths)
Requirements: 11-REQ-5.1, 11-REQ-5.2, 11-REQ-5.3, 11-REQ-5.4, 11-REQ-5.E1

Updated for spec 38: Tests now use the shared knowledge_conn fixture
(38-REQ-5.3) instead of creating inline duckdb.connect() connections.
"""

from __future__ import annotations

import duckdb
import pytest

from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError
from tests.unit.knowledge.conftest import create_schema


class TestDuckDBSinkRecordsSessionOutcome:
    """TS-11-7: DuckDB sink records session outcome (always-on).

    Requirements: 11-REQ-5.1, 11-REQ-5.2
    """

    def test_records_outcome_with_debug_false(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify outcome is written even with debug=False."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        outcome = SessionOutcome(
            spec_name="test_spec",
            task_group="1",
            node_id="test_spec/1",
            touched_paths=["src/main.py"],
            status="completed",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=30000,
        )
        sink.record_session_outcome(outcome)

        rows = knowledge_conn.execute("SELECT spec_name, status FROM session_outcomes").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "test_spec"
        assert rows[0][1] == "completed"

    def test_records_outcome_with_debug_true(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify outcome is written with debug=True."""
        sink = DuckDBSink(knowledge_conn, debug=True)

        outcome = SessionOutcome(
            spec_name="debug_spec",
            status="failed",
        )
        sink.record_session_outcome(outcome)

        rows = knowledge_conn.execute("SELECT spec_name, status FROM session_outcomes").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "debug_spec"
        assert rows[0][1] == "failed"


class TestDuckDBSinkToolTelemetryAlwaysOn:
    """AC-3, AC-4: DuckDB sink records tool signals regardless of debug flag.

    Requirements: 11-REQ-5.3, 11-REQ-5.4 (superseded by fix #282)

    Tool telemetry is now always-on. The ``debug`` parameter is retained
    for API compatibility but no longer gates tool_calls / tool_errors writes.
    """

    def test_tool_calls_written_when_debug_false(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify tool_calls and tool_errors ARE written even with debug=False (AC-3, AC-4)."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        sink.record_tool_call(ToolCall(tool_name="bash"))
        sink.record_tool_error(ToolError(tool_name="bash"))

        assert knowledge_conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 1  # type: ignore[index]
        assert knowledge_conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == 1  # type: ignore[index]

    def test_tool_calls_written_when_debug_true(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify tool_calls and tool_errors are written when debug=True."""
        sink = DuckDBSink(knowledge_conn, debug=True)

        sink.record_tool_call(ToolCall(tool_name="bash"))
        sink.record_tool_error(ToolError(tool_name="bash"))

        assert knowledge_conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 1  # type: ignore[index]
        assert knowledge_conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == 1  # type: ignore[index]

    def test_tool_name_is_persisted(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify tool_name is correctly stored in the tool_calls row."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        sink.record_tool_call(ToolCall(tool_name="Read"))

        row = knowledge_conn.execute("SELECT tool_name FROM tool_calls").fetchone()
        assert row is not None
        assert row[0] == "Read"


class TestDuckDBSinkMultipleTouchedPaths:
    """TS-11-9: DuckDB sink handles multiple touched paths.

    Requirement: 11-REQ-5.2
    Updated: fixes #457 — multiple paths must produce exactly one row (not N rows).
    """

    def test_creates_one_row_for_multiple_paths(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify 3 touched paths produce exactly 1 row with comma-delimited touched_path (AC-1, AC-2)."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        outcome = SessionOutcome(
            spec_name="multi",
            touched_paths=["a.py", "b.py", "c.py"],
            status="completed",
        )
        sink.record_session_outcome(outcome)

        rows = knowledge_conn.execute("SELECT touched_path FROM session_outcomes").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "a.py,b.py,c.py"

    def test_no_metric_duplication_for_multiple_paths(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify duration/token sums are not inflated when multiple files are touched (AC-4)."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        outcome = SessionOutcome(
            spec_name="metrics",
            touched_paths=["x.py", "y.py"],
            status="completed",
            duration_ms=5000,
            input_tokens=100,
            output_tokens=200,
        )
        sink.record_session_outcome(outcome)

        row = knowledge_conn.execute(
            "SELECT SUM(duration_ms), SUM(input_tokens), SUM(output_tokens) FROM session_outcomes"
        ).fetchone()
        assert row == (5000, 100, 200)

    def test_original_uuid_preserved(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify the session UUID is preserved on the single inserted row (AC-5)."""
        import uuid

        some_uuid = uuid.uuid4()
        sink = DuckDBSink(knowledge_conn, debug=False)

        outcome = SessionOutcome(
            id=some_uuid,
            spec_name="uuid_check",
            touched_paths=["p.py", "q.py", "r.py"],
            status="completed",
        )
        sink.record_session_outcome(outcome)

        result = knowledge_conn.execute("SELECT id FROM session_outcomes").fetchall()
        assert len(result) == 1
        assert str(result[0][0]) == str(some_uuid)


# -- Edge Case Tests ---------------------------------------------------------


class TestDuckDBSinkWriteFailurePropagates:
    """TS-11-E3 (superseded by 38-REQ-3.1): DuckDB sink errors propagate.

    Requirement: 38-REQ-3.1 (supersedes 11-REQ-5.E1)

    Note: These tests deliberately close the connection to trigger errors,
    so they cannot use the knowledge_conn fixture (whose teardown would fail).
    """

    def test_closed_connection_raises(self) -> None:
        """Verify write to closed connection raises (38-REQ-3.1)."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=False)
        conn.close()  # force failure

        with pytest.raises(duckdb.ConnectionException):
            sink.record_session_outcome(SessionOutcome(status="completed"))

    def test_tool_call_on_closed_conn_raises(self) -> None:
        """Verify tool call on closed connection raises (38-REQ-3.1)."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=False)  # always-on; debug flag irrelevant
        conn.close()

        with pytest.raises(duckdb.ConnectionException):
            sink.record_tool_call(ToolCall(tool_name="bash"))

    def test_tool_error_on_closed_conn_raises(self) -> None:
        """Verify tool error on closed connection raises (38-REQ-3.1)."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=False)  # always-on; debug flag irrelevant
        conn.close()

        with pytest.raises(duckdb.ConnectionException):
            sink.record_tool_error(ToolError(tool_name="bash"))


class TestDuckDBSinkEmptyTouchedPaths:
    """TS-11-E7: DuckDB sink handles empty touched paths.

    Requirement: 11-REQ-5.2
    """

    def test_empty_paths_creates_one_null_row(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify empty touched_paths creates one row with NULL touched_path."""
        sink = DuckDBSink(knowledge_conn, debug=False)

        sink.record_session_outcome(SessionOutcome(status="failed", touched_paths=[]))

        rows = knowledge_conn.execute("SELECT touched_path FROM session_outcomes").fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
