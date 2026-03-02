"""Property tests for sink protocol compliance and debug gating.

Test Spec: TS-11-P3 (sink protocol compliance), TS-11-P4 (debug gating invariant)
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


class TestDebugGatingInvariant:
    """TS-11-P4: Debug gating invariant.

    For any N tool calls and M tool errors (1 <= N, M <= 10), tool_calls
    and tool_errors tables remain empty when debug=False.

    Property 5 from design.md.
    """

    @given(
        n=st.integers(min_value=1, max_value=10),
        m=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    def test_no_tool_signals_when_debug_false(self, n: int, m: int) -> None:
        """Tool signal tables are empty after N calls and M errors with debug=False."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        sink = DuckDBSink(conn, debug=False)

        for _ in range(n):
            sink.record_tool_call(ToolCall(tool_name="test"))
        for _ in range(m):
            sink.record_tool_error(ToolError(tool_name="test"))

        assert conn.execute(
            "SELECT COUNT(*) FROM tool_calls"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM tool_errors"
        ).fetchone()[0] == 0

        conn.close()
