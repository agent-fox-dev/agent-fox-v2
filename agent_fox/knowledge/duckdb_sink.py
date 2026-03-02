"""DuckDB sink: session outcomes (always-on), tool signals (debug-only).

Requirements: 11-REQ-5.1, 11-REQ-5.2, 11-REQ-5.3, 11-REQ-5.4, 11-REQ-5.E1
"""

from __future__ import annotations

import logging

import duckdb  # noqa: F401

from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError

logger = logging.getLogger("agent_fox.knowledge.duckdb_sink")


class DuckDBSink:
    """SessionSink implementation backed by DuckDB.

    Session outcomes are always written. Tool signals (tool_calls,
    tool_errors) are only written when debug=True.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        debug: bool = False,
    ) -> None:
        self._conn = conn
        self._debug = debug

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Insert a row into session_outcomes for each touched path."""
        raise NotImplementedError

    def record_tool_call(self, call: ToolCall) -> None:
        """Insert a row into tool_calls. No-op if debug=False."""
        raise NotImplementedError

    def record_tool_error(self, error: ToolError) -> None:
        """Insert a row into tool_errors. No-op if debug=False."""
        raise NotImplementedError

    def close(self) -> None:
        """No-op. Connection lifecycle is managed by KnowledgeDB."""
        pass
