"""DuckDB sink: session outcomes (always-on), tool signals (debug-only).

Requirements: 11-REQ-5.1, 11-REQ-5.2, 11-REQ-5.3, 11-REQ-5.4, 11-REQ-5.E1
"""

from __future__ import annotations

import logging
from uuid import uuid4

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
        """Insert a row into session_outcomes for each touched path.

        If touched_paths is empty, inserts one row with NULL touched_path.
        All writes are best-effort: failures are logged, not raised.
        """
        try:
            paths: list[str | None] = (
                list(outcome.touched_paths) if outcome.touched_paths else [None]
            )
            for i, path in enumerate(paths):
                row_id = outcome.id if i == 0 else uuid4()
                self._conn.execute(
                    """
                    INSERT INTO session_outcomes
                        (id, spec_name, task_group, node_id, touched_path,
                         status, input_tokens, output_tokens, duration_ms,
                         created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(row_id),
                        outcome.spec_name,
                        outcome.task_group,
                        outcome.node_id,
                        path,
                        outcome.status,
                        outcome.input_tokens,
                        outcome.output_tokens,
                        outcome.duration_ms,
                        outcome.created_at,
                    ],
                )
        except Exception:
            logger.warning(
                "Failed to record session outcome",
                exc_info=True,
            )

    def record_tool_call(self, call: ToolCall) -> None:
        """Insert a row into tool_calls. No-op if debug=False."""
        if not self._debug:
            return
        try:
            self._conn.execute(
                """
                INSERT INTO tool_calls
                    (id, session_id, node_id, tool_name, called_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    str(call.id),
                    call.session_id,
                    call.node_id,
                    call.tool_name,
                    call.called_at,
                ],
            )
        except Exception:
            logger.warning(
                "Failed to record tool call",
                exc_info=True,
            )

    def record_tool_error(self, error: ToolError) -> None:
        """Insert a row into tool_errors. No-op if debug=False."""
        if not self._debug:
            return
        try:
            self._conn.execute(
                """
                INSERT INTO tool_errors
                    (id, session_id, node_id, tool_name, failed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    str(error.id),
                    error.session_id,
                    error.node_id,
                    error.tool_name,
                    error.failed_at,
                ],
            )
        except Exception:
            logger.warning(
                "Failed to record tool error",
                exc_info=True,
            )

    def close(self) -> None:
        """No-op. Connection lifecycle is managed by KnowledgeDB."""
        pass
