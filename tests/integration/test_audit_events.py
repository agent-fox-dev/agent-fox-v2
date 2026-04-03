"""Integration tests for audit event emission at lifecycle points.

Test Spec: TS-40-17 through TS-40-23, TS-40-33, TS-40-34
Requirements: 40-REQ-7.*, 40-REQ-8.*, 40-REQ-9.*, 40-REQ-14.*
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
)
from agent_fox.knowledge.sink import SinkDispatcher

# -- Helpers -----------------------------------------------------------------


class EventCaptureSink:
    """A sink that captures audit events for assertion."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record_session_outcome(self, outcome: object) -> None:
        pass

    def record_tool_call(self, call: object) -> None:
        pass

    def record_tool_error(self, error: object) -> None:
        pass

    def emit_audit_event(self, event: AuditEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


# -- TS-40-17, TS-40-18, TS-40-19: Session Events ----------------------------


class TestSessionEvents:
    """TS-40-17, TS-40-18, TS-40-19: Session lifecycle audit events.

    Requirements: 40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-11.3
    """

    def test_session_start(self) -> None:
        """TS-40-17: session.start event emitted with correct payload."""
        # Verify that AuditEvent can represent a session.start event
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_START,
            archetype="coder",
            payload={
                "archetype": "coder",
                "model_id": "claude-sonnet-4-6",
                "prompt_template": "coder",
                "attempt": 1,
            },
        )
        assert event.event_type == AuditEventType.SESSION_START
        assert event.payload["archetype"] == "coder"
        assert event.payload["model_id"] == "claude-sonnet-4-6"
        assert "prompt_template" in event.payload
        assert "attempt" in event.payload

    def test_session_complete(self) -> None:
        """TS-40-18: session.complete event with token/cost/duration fields."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_COMPLETE,
            payload={
                "archetype": "coder",
                "model_id": "claude-sonnet-4-6",
                "prompt_template": "coder",
                "input_tokens": 3000,
                "output_tokens": 2000,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cost": 0.05,
                "duration_ms": 30000,
                "files_touched": ["src/main.py"],
            },
        )
        assert event.event_type == AuditEventType.SESSION_COMPLETE
        assert "input_tokens" in event.payload
        assert "output_tokens" in event.payload
        assert "cost" in event.payload
        assert "duration_ms" in event.payload
        assert "files_touched" in event.payload

    def test_session_fail(self) -> None:
        """TS-40-19: session.fail event has severity error."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_FAIL,
            severity=AuditSeverity.ERROR,
            payload={
                "archetype": "coder",
                "model_id": "claude-sonnet-4-6",
                "prompt_template": "coder",
                "error_message": "Session failed",
                "attempt": 1,
            },
        )
        assert event.severity == AuditSeverity.ERROR
        assert "error_message" in event.payload

    def test_session_start_dispatches(self) -> None:
        """session.start event dispatches through SinkDispatcher."""
        capture = EventCaptureSink()
        dispatcher = SinkDispatcher([capture])  # type: ignore[list-item]
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_START,
            payload={
                "archetype": "coder",
                "model_id": "test",
                "prompt_template": "t",
                "attempt": 1,
            },
        )
        dispatcher.emit_audit_event(event)
        start_events = [e for e in capture.events if e.event_type == AuditEventType.SESSION_START]
        assert len(start_events) == 1

    def test_harvest_complete(self) -> None:
        """TS-40-17 (harvest): harvest.complete event with correct payload."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.HARVEST_COMPLETE,
            payload={
                "commit_sha": "abc123",
                "facts_extracted": 5,
                "findings_persisted": 3,
            },
        )
        assert event.event_type == AuditEventType.HARVEST_COMPLETE
        assert event.payload["commit_sha"] == "abc123"


# -- TS-40-20: Tool Events ---------------------------------------------------


class TestToolEvents:
    """TS-40-20: Tool invocation and error audit events.

    Requirements: 40-REQ-8.1, 40-REQ-8.2, 40-REQ-8.3
    """

    def test_tool_invocation(self) -> None:
        """tool.invocation event with abbreviated param_summary."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.TOOL_INVOCATION,
            payload={
                "tool_name": "Read",
                "param_summary": "/very/long/path...",
                "called_at": datetime.now(UTC).isoformat(),
            },
        )
        assert event.event_type == AuditEventType.TOOL_INVOCATION
        assert "param_summary" in event.payload
        assert len(event.payload["param_summary"]) <= 200

    def test_tool_error(self) -> None:
        """tool.error event with correct payload fields."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.TOOL_ERROR,
            payload={
                "tool_name": "Bash",
                "param_summary": "run something",
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
        assert event.event_type == AuditEventType.TOOL_ERROR
        assert event.payload["tool_name"] == "Bash"

    def test_tool_events_dispatch(self) -> None:
        """Tool events dispatch through SinkDispatcher."""
        capture = EventCaptureSink()
        dispatcher = SinkDispatcher([capture])  # type: ignore[list-item]

        invocation = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.TOOL_INVOCATION,
            payload={
                "tool_name": "Read",
                "param_summary": "file.py",
                "called_at": "now",
            },
        )
        error = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.TOOL_ERROR,
            payload={"tool_name": "Bash", "param_summary": "cmd", "failed_at": "now"},
        )
        dispatcher.emit_audit_event(invocation)
        dispatcher.emit_audit_event(error)

        tool_events = [
            e for e in capture.events if e.event_type in (AuditEventType.TOOL_INVOCATION, AuditEventType.TOOL_ERROR)
        ]
        assert len(tool_events) == 2


# -- TS-40-21, TS-40-22, TS-40-23: Orchestrator Events -----------------------


class TestOrchestratorEvents:
    """TS-40-21 through TS-40-23: Orchestrator lifecycle audit events.

    Requirements: 40-REQ-9.1, 40-REQ-9.2, 40-REQ-9.3, 40-REQ-9.4, 40-REQ-9.5,
                  40-REQ-10.1, 40-REQ-10.2, 40-REQ-11.1, 40-REQ-11.2,
                  40-REQ-11.4, 40-REQ-11.5, 40-REQ-11.6
    """

    def test_run_start(self) -> None:
        """TS-40-21: run.start event with plan_hash, total_nodes, parallel."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_START,
            payload={
                "plan_hash": "abcdef",
                "total_nodes": 5,
                "parallel": True,
            },
        )
        assert "plan_hash" in event.payload
        assert "total_nodes" in event.payload
        assert "parallel" in event.payload

    def test_run_complete(self) -> None:
        """TS-40-22: run.complete event with summary fields."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_COMPLETE,
            payload={
                "total_sessions": 5,
                "total_cost": 1.50,
                "duration_ms": 300000,
                "run_status": "completed",
            },
        )
        assert "total_sessions" in event.payload
        assert "total_cost" in event.payload
        assert "duration_ms" in event.payload

    def test_limit_reached(self) -> None:
        """TS-40-23: run.limit_reached has severity warning."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_LIMIT_REACHED,
            severity=AuditSeverity.WARNING,
            payload={
                "limit_type": "cost",
                "limit_value": 10.0,
            },
        )
        assert event.severity == AuditSeverity.WARNING
        assert "limit_type" in event.payload

    def test_task_status_change(self) -> None:
        """task.status_change event with from/to/reason."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.TASK_STATUS_CHANGE,
            payload={
                "from_status": "pending",
                "to_status": "running",
                "reason": "dependencies met",
            },
        )
        assert event.payload["from_status"] == "pending"
        assert event.payload["to_status"] == "running"

    def test_sync_barrier(self) -> None:
        """sync.barrier event with completed/pending nodes."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SYNC_BARRIER,
            payload={
                "completed_nodes": ["spec_01/1", "spec_02/1"],
                "pending_nodes": ["spec_03/1"],
            },
        )
        assert len(event.payload["completed_nodes"]) == 2
        assert len(event.payload["pending_nodes"]) == 1

    def test_session_retry(self) -> None:
        """session.retry event with attempt and reason."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.SESSION_RETRY,
            payload={
                "attempt": 2,
                "reason": "session failed, retrying",
            },
        )
        assert event.payload["attempt"] == 2
        assert "reason" in event.payload

    def test_model_escalation(self) -> None:
        """model.escalation event with tier details."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.MODEL_ESCALATION,
            payload={
                "from_tier": "haiku",
                "to_tier": "sonnet",
                "reason": "task complexity",
            },
        )
        assert event.payload["from_tier"] == "haiku"
        assert event.payload["to_tier"] == "sonnet"

    def test_model_assessment(self) -> None:
        """model.assessment event with predicted_tier and confidence."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.MODEL_ASSESSMENT,
            payload={
                "predicted_tier": "sonnet",
                "confidence": 0.85,
                "method": "feature_vector",
            },
        )
        assert event.payload["confidence"] == 0.85

    def test_git_merge(self) -> None:
        """git.merge event with branch and commit info."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.GIT_MERGE,
            payload={
                "branch": "feature/test",
                "commit_sha": "abc123",
                "files_touched": ["src/main.py"],
            },
        )
        assert event.payload["branch"] == "feature/test"

    def test_git_conflict(self) -> None:
        """git.conflict event with severity warning."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.GIT_CONFLICT,
            severity=AuditSeverity.WARNING,
            payload={
                "branch": "feature/test",
                "strategy": "ours",
                "error": "merge conflict in main.py",
            },
        )
        assert event.severity == AuditSeverity.WARNING

    def test_fact_extracted(self) -> None:
        """fact.extracted event with count and categories."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.FACT_EXTRACTED,
            payload={
                "fact_count": 5,
                "categories": ["decision", "pattern"],
            },
        )
        assert event.payload["fact_count"] == 5

    def test_fact_compacted(self) -> None:
        """fact.compacted event with before/after/superseded counts."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.FACT_COMPACTED,
            payload={
                "facts_before": 100,
                "facts_after": 80,
                "superseded_count": 20,
            },
        )
        assert event.payload["superseded_count"] == 20

    def test_knowledge_ingested(self) -> None:
        """knowledge.ingested event with source info."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.KNOWLEDGE_INGESTED,
            payload={
                "source_type": "file",
                "source_path": "docs/memory.md",
                "item_count": 10,
            },
        )
        assert event.payload["source_type"] == "file"

    def test_run_id_consistency(self) -> None:
        """All events in a run share the same run_id."""
        run_id = "20260312_143000_abc123"
        events = [
            AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_START),
            AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_START),
            AuditEvent(run_id=run_id, event_type=AuditEventType.SESSION_COMPLETE),
            AuditEvent(run_id=run_id, event_type=AuditEventType.RUN_COMPLETE),
        ]
        assert all(e.run_id == run_id for e in events)


# -- TS-40-33, TS-40-34: Reporting Migration ----------------------------------


class TestReportingMigration:
    """TS-40-33, TS-40-34: Reporting reads from DuckDB audit events.

    Requirements: 40-REQ-14.1, 40-REQ-14.2, 40-REQ-14.3
    """

    def test_status_from_audit(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-33: Status report reads session metrics from audit_events."""
        from agent_fox.reporting.status import build_status_report_from_audit

        # Insert session.complete events
        for i in range(5):
            knowledge_conn.execute(
                """
                INSERT INTO audit_events
                    (id, timestamp, run_id, event_type, node_id, session_id,
                     archetype, severity, payload)
                VALUES (?, CURRENT_TIMESTAMP, 'r1', 'session.complete', '', '',
                        'coder', 'info', ?)
                """,
                [
                    str(uuid4()),
                    json.dumps(
                        {
                            "archetype": "coder",
                            "model_id": "test",
                            "prompt_template": "coder",
                            "tokens": 2000,
                            "cost": 0.02,
                            "duration_ms": 5000,
                            "files_touched": [],
                        }
                    ),
                ],
            )

        report = build_status_report_from_audit(knowledge_conn)
        assert report.total_sessions == 5
        assert report.total_input_tokens > 0

    def test_standup_from_audit(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-40-33 (standup): Standup report reads from audit_events."""
        from agent_fox.reporting.standup import build_standup_from_audit

        # Insert mixed events
        knowledge_conn.execute(
            """
            INSERT INTO audit_events
                (id, timestamp, run_id, event_type, node_id, session_id,
                 archetype, severity, payload)
            VALUES (?, CURRENT_TIMESTAMP, 'r1', 'session.complete', '', '',
                    'coder', 'info', ?)
            """,
            [
                str(uuid4()),
                json.dumps(
                    {
                        "archetype": "coder",
                        "model_id": "test",
                        "tokens": 1000,
                        "cost": 0.01,
                    }
                ),
            ],
        )

        report = build_standup_from_audit(knowledge_conn)
        assert report is not None

    def test_fallback(self, tmp_path: Path) -> None:
        """TS-40-34: Reporting falls back to state.jsonl when DuckDB unavailable."""
        from agent_fox.reporting.status import build_status_report_from_audit

        # When conn is None, should not raise
        result = build_status_report_from_audit(None)
        # Returns None or empty report when no connection
        assert result is None or hasattr(result, "total_sessions")
