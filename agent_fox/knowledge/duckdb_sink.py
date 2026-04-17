"""DuckDB sink: session outcomes (always-on), tool signals (debug-only).

Requirements: 11-REQ-5.1, 11-REQ-5.2, 11-REQ-5.3, 11-REQ-5.4, 11-REQ-5.E1,
              38-REQ-3.1, 40-REQ-5.1, 40-REQ-5.2
"""

from __future__ import annotations

import json
import logging

import duckdb  # noqa: F401

from agent_fox.knowledge.audit import AuditEvent
from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError

logger = logging.getLogger("agent_fox.knowledge.duckdb_sink")


class DuckDBSink:
    """SessionSink implementation backed by DuckDB.

    Session outcomes and tool signals are always written.
    The ``debug`` parameter is retained for API compatibility but is no
    longer used to gate tool telemetry writes (fixes #282).
    DuckDB errors propagate to the caller (38-REQ-3.1).
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        debug: bool = False,
    ) -> None:
        self._conn = conn
        self._debug = debug  # retained for API compatibility

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Insert a single row into session_outcomes.

        Multiple touched paths are stored as a comma-delimited string in the
        touched_path column so that each session produces exactly one row
        (fixes #457 — per-file row explosion).  If touched_paths is empty,
        touched_path is stored as NULL.
        DuckDB errors propagate to the caller (38-REQ-3.1).
        """
        touched_path: str | None = ",".join(outcome.touched_paths) if outcome.touched_paths else None
        self._conn.execute(
            """
            INSERT INTO session_outcomes
                (id, spec_name, task_group, node_id, touched_path,
                 status, input_tokens, output_tokens, duration_ms,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(outcome.id),
                outcome.spec_name,
                outcome.task_group,
                outcome.node_id,
                touched_path,
                outcome.status,
                outcome.input_tokens,
                outcome.output_tokens,
                outcome.duration_ms,
                outcome.created_at,
            ],
        )

    def record_tool_call(self, call: ToolCall) -> None:
        """Insert a row into tool_calls (always-on).

        DuckDB errors propagate to the caller (38-REQ-3.1).
        """
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

    def record_tool_error(self, error: ToolError) -> None:
        """Insert a row into tool_errors (always-on).

        DuckDB errors propagate to the caller (38-REQ-3.1).
        """
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

    def emit_audit_event(self, event: AuditEvent) -> None:
        """Insert audit event into audit_events table.

        DuckDB errors propagate to the caller (38-REQ-3.1).
        Requirements: 40-REQ-5.1, 40-REQ-5.2
        """
        self._conn.execute(
            """
            INSERT INTO audit_events
                (id, timestamp, run_id, event_type, node_id, session_id,
                 archetype, severity, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(event.id),
                event.timestamp,
                event.run_id,
                event.event_type.value,
                event.node_id,
                event.session_id,
                event.archetype,
                event.severity.value,
                json.dumps(event.payload),
            ],
        )

    def close(self) -> None:
        """No-op. Connection lifecycle is managed by KnowledgeDB."""
        pass
