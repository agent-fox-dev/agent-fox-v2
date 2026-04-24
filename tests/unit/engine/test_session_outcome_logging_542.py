"""Unit tests for session outcome DB write logging — issue #542.

Verifies that DB write failures and missing knowledge_db_conn are logged at
WARNING level so they are visible in normal operation, not silently swallowed.

AC-1: Session DB write failures in ResultHandler are logged at WARNING.
AC-2: Node-status persist failures in ResultHandler are logged at WARNING.
AC-3: A startup WARNING is emitted when ResultHandler is constructed without
      a knowledge_db_conn.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_record(node_id: str = "spec:group:coder") -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        attempt=1,
        status="completed",
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=1234,
        error_message=None,
        timestamp="2026-01-01T00:00:00Z",
    )


def _make_handler(*, knowledge_db_conn: Any = None) -> SessionResultHandler:
    """Construct a minimal SessionResultHandler."""
    node_id = "spec:group:coder"
    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})
    mock_ladder = MagicMock()
    mock_ladder.is_exhausted = False
    mock_ladder.should_retry.return_value = False
    mock_ladder.escalation_count = 0
    mock_ladder.attempt_count = 1

    return SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders={node_id: mock_ladder},
        retries_before_escalation=1,
        max_retries=2,
        task_callback=None,
        sink=None,
        run_id="test-run-542",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=knowledge_db_conn,
        block_task_fn=lambda nid, st, reason: None,
        check_block_budget_fn=lambda st: False,
    )


# ---------------------------------------------------------------------------
# AC-1: Session DB write failure → WARNING
# ---------------------------------------------------------------------------


class TestSessionDbWriteFailureLogsWarning:
    """AC-1: record_session DB failure is logged at WARNING, not DEBUG."""

    def test_write_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When record_session raises, a WARNING is emitted."""
        mock_conn = MagicMock()
        # Construct with a non-None conn to enter the DB write path.
        # caplog is at WARNING so startup warning (AC-3) won't trigger here
        # (knowledge_db_conn is provided).
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.result_handler"):
            handler = _make_handler(knowledge_db_conn=mock_conn)
            caplog.clear()

            state = ExecutionState(
                plan_hash="test",
                node_states={"spec:group:coder": "in_progress"},
            )

            # record_session is imported inside the try block as _record_session_db;
            # patching the source in agent_fox.engine.state makes it raise.
            with patch(
                "agent_fox.engine.state.record_session",
                side_effect=RuntimeError("schema mismatch"),
            ):
                handler.process(
                    _make_completed_record(),
                    1,
                    state,
                    {},
                    {},
                )

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failed to record session to DB" in m for m in warning_msgs), (
            f"Expected WARNING 'Failed to record session to DB'; got: {warning_msgs}"
        )

    def test_write_failure_not_at_debug_only(self, caplog: pytest.LogCaptureFixture) -> None:
        """AC-1: The failure message must NOT appear only at DEBUG level."""
        mock_conn = MagicMock()
        with caplog.at_level(logging.DEBUG, logger="agent_fox.engine.result_handler"):
            handler = _make_handler(knowledge_db_conn=mock_conn)
            caplog.clear()

            state = ExecutionState(
                plan_hash="test",
                node_states={"spec:group:coder": "in_progress"},
            )

            with patch(
                "agent_fox.engine.state.record_session",
                side_effect=RuntimeError("constraint violation"),
            ):
                handler.process(
                    _make_completed_record(),
                    1,
                    state,
                    {},
                    {},
                )

        matching = [
            r for r in caplog.records if "Failed to record session to DB" in r.message
        ]
        assert matching, "Expected log entry for 'Failed to record session to DB'"
        assert all(r.levelno >= logging.WARNING for r in matching), (
            "All 'Failed to record session to DB' entries must be at WARNING or above"
        )


# ---------------------------------------------------------------------------
# AC-2: Node-status persist failure → WARNING
# ---------------------------------------------------------------------------


class TestNodeStatusPersistFailureLogsWarning:
    """AC-2: persist_node_status failure is logged at WARNING."""

    def test_persist_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When persist_node_status raises, a WARNING is emitted."""
        mock_conn = MagicMock()
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.result_handler"):
            handler = _make_handler(knowledge_db_conn=mock_conn)
            caplog.clear()

            state = ExecutionState(
                plan_hash="test",
                node_states={"spec:group:coder": "in_progress"},
            )

            # Let the session record write succeed, but persist_node_status fail.
            with (
                patch("agent_fox.engine.state.record_session"),
                patch("agent_fox.engine.state.update_run_totals"),
                patch(
                    "agent_fox.engine.state.persist_node_status",
                    side_effect=RuntimeError("DB closed"),
                ),
            ):
                handler.process(
                    _make_completed_record(),
                    1,
                    state,
                    {},
                    {},
                )

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failed to persist node status" in m for m in warning_msgs), (
            f"Expected WARNING 'Failed to persist node status'; got: {warning_msgs}"
        )


# ---------------------------------------------------------------------------
# AC-3: Startup WARNING when knowledge_db_conn is None
# ---------------------------------------------------------------------------


class TestStartupWarningWhenNoKnowledgeDbConn:
    """AC-3: Constructing ResultHandler with knowledge_db_conn=None emits a WARNING."""

    def test_init_with_none_conn_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """WARNING is emitted during __init__ when knowledge_db_conn is None."""
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.result_handler"):
            _make_handler(knowledge_db_conn=None)

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("knowledge_db_conn" in m for m in warning_msgs), (
            f"Expected WARNING mentioning 'knowledge_db_conn'; got: {warning_msgs}"
        )

    def test_init_with_valid_conn_does_not_emit_none_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No 'knowledge_db_conn is None' warning when conn is provided."""
        mock_conn = MagicMock()
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.result_handler"):
            _make_handler(knowledge_db_conn=mock_conn)

        # Must not have the "will not be recorded" startup warning
        startup_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "will not be recorded" in r.message
        ]
        assert not startup_warnings, (
            f"Unexpected startup warning when conn is provided: {startup_warnings}"
        )
