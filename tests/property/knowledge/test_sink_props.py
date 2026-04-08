"""Property tests for sink protocol compliance and tool telemetry invariants.

Test Spec: TS-11-P3 (sink protocol compliance), TS-11-P4 (tool telemetry always-on)
Properties: Property 3 and Property 5 from design.md
Requirements: 11-REQ-4.1, 11-REQ-5.1, 11-REQ-5.3, 11-REQ-5.4, 11-REQ-6.1
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.jsonl_sink import JsonlSink
from agent_fox.knowledge.sink import SessionSink, ToolCall, ToolError
from tests.unit.knowledge.conftest import create_schema


class TestSinkProtocolCompliance:
    """TS-11-P3: Sink protocol compliance.

    For any sink class in [DuckDBSink, JsonlSink], isinstance(instance,
    SessionSink) is True.

    Property 3 from design.md.
    """

    def test_duckdb_sink_satisfies_protocol(self) -> None:
        """DuckDBSink satisfies the SessionSink protocol."""
        conn = duckdb.connect(":memory:")
        instance = DuckDBSink(conn)
        assert isinstance(instance, SessionSink)
        conn.close()

    def test_jsonl_sink_satisfies_protocol(self) -> None:
        """JsonlSink satisfies the SessionSink protocol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            instance = JsonlSink(directory=Path(tmpdir))
            assert isinstance(instance, SessionSink)


class TestToolTelemetryAlwaysOnInvariant:
    """TS-11-P4: Tool telemetry always-on invariant (fixes #282).

    For any N tool calls and M tool errors (1 <= N, M <= 10), tool_calls
    and tool_errors tables contain exactly N and M rows respectively,
    regardless of the debug flag value.

    Property 5 from design.md (updated: always-on replaces debug-gating).
    """

    @given(
        n=st.integers(min_value=1, max_value=10),
        m=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    def test_tool_signals_written_when_debug_false(self, n: int, m: int) -> None:
        """N tool calls and M errors produce exactly N+M rows with debug=False (AC-3)."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=False)

        for _ in range(n):
            sink.record_tool_call(ToolCall(tool_name="test"))
        for _ in range(m):
            sink.record_tool_error(ToolError(tool_name="test"))

        assert conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == n  # type: ignore[index]
        assert conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == m  # type: ignore[index]

        conn.close()

    @given(
        n=st.integers(min_value=1, max_value=10),
        m=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    def test_tool_signals_written_when_debug_true(self, n: int, m: int) -> None:
        """N tool calls and M errors produce exactly N+M rows with debug=True."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=True)

        for _ in range(n):
            sink.record_tool_call(ToolCall(tool_name="test"))
        for _ in range(m):
            sink.record_tool_error(ToolError(tool_name="test"))

        assert conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == n  # type: ignore[index]
        assert conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == m  # type: ignore[index]

        conn.close()
