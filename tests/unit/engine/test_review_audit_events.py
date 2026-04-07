"""Unit tests for review findings persistence audit events.

Validates that persist_review_findings() emits the correct audit events
after successful insertion: review.findings_persisted for skeptic,
review.verdicts_persisted for verifier, review.drift_persisted for oracle.
Also validates that audit emission failure does not propagate.

Test Spec: TS-84-3, TS-84-4, TS-84-5, TS-84-E2
Requirements: 84-REQ-2.1, 84-REQ-2.2, 84-REQ-2.3, 84-REQ-2.E1
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import duckdb

from agent_fox.engine.review_persistence import persist_review_findings
from agent_fox.knowledge.audit import AuditEventType


def _make_skeptic_transcript(findings: list[dict]) -> str:
    """Create a transcript containing a JSON array of skeptic findings."""
    return json.dumps(findings)


def _make_verifier_transcript(verdicts: list[dict]) -> str:
    """Create a transcript containing a JSON array of verifier verdicts."""
    return json.dumps(verdicts)


def _make_oracle_transcript(drift_findings: list[dict]) -> str:
    """Create a transcript containing a JSON array of oracle drift findings."""
    return json.dumps(drift_findings)


class TestSkepticFindingsPersistedAuditEvent:
    """TS-84-3: review.findings_persisted event emitted for skeptic."""

    def test_findings_persisted_event_emitted(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify review.findings_persisted event is emitted after successful insertion."""
        mock_sink = MagicMock()

        transcript = _make_skeptic_transcript([{"severity": "critical", "description": "missing guard"}])

        persist_review_findings(
            transcript,
            "my_spec:1",
            1,
            archetype="skeptic",
            spec_name="my_spec",
            task_group="1",
            knowledge_db_conn=knowledge_conn,
            sink=mock_sink,
            run_id="test-run",
        )

        # Find the findings_persisted audit event call
        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [c for c in calls if c.args[0].event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED]
        assert len(persisted_events) == 1

        event = persisted_events[0].args[0]
        assert event.payload["archetype"] == "skeptic"
        assert event.payload["count"] == 1
        assert event.payload["severity_summary"]["critical"] == 1

    def test_findings_persisted_event_has_spec_name(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify audit event payload contains spec_name."""
        mock_sink = MagicMock()

        transcript = _make_skeptic_transcript(
            [
                {"severity": "critical", "description": "issue A"},
                {"severity": "major", "description": "issue B"},
            ]
        )

        persist_review_findings(
            transcript,
            "my_spec:2",
            1,
            archetype="skeptic",
            spec_name="my_spec",
            task_group="2",
            knowledge_db_conn=knowledge_conn,
            sink=mock_sink,
            run_id="test-run",
        )

        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [c for c in calls if c.args[0].event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED]
        assert len(persisted_events) == 1

        event = persisted_events[0].args[0]
        assert event.payload["spec_name"] == "my_spec"
        assert event.payload["count"] == 2
        assert event.payload["severity_summary"] == {"critical": 1, "major": 1}


class TestVerifierVerdictsPersistedAuditEvent:
    """TS-84-4: review.verdicts_persisted event emitted for verifier."""

    def test_verdicts_persisted_event_emitted(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify review.verdicts_persisted event with pass/fail counts."""
        mock_sink = MagicMock()

        transcript = _make_verifier_transcript(
            [
                {"requirement_id": "REQ-1.1", "verdict": "PASS"},
                {"requirement_id": "REQ-1.2", "verdict": "FAIL"},
            ]
        )

        persist_review_findings(
            transcript,
            "my_spec:1",
            1,
            archetype="verifier",
            spec_name="my_spec",
            task_group="1",
            knowledge_db_conn=knowledge_conn,
            sink=mock_sink,
            run_id="test-run",
        )

        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [c for c in calls if c.args[0].event_type == AuditEventType.REVIEW_VERDICTS_PERSISTED]
        assert len(persisted_events) == 1

        event = persisted_events[0].args[0]
        assert event.payload["count"] == 2
        assert event.payload["pass_count"] == 1
        assert event.payload["fail_count"] == 1


class TestOracleDriftPersistedAuditEvent:
    """TS-84-5: review.drift_persisted event emitted for oracle."""

    def test_drift_persisted_event_emitted(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify review.drift_persisted event with severity summary."""
        mock_sink = MagicMock()

        transcript = _make_oracle_transcript([{"severity": "major", "description": "spec divergence"}])

        persist_review_findings(
            transcript,
            "my_spec:1",
            1,
            archetype="oracle",
            spec_name="my_spec",
            task_group="1",
            knowledge_db_conn=knowledge_conn,
            sink=mock_sink,
            run_id="test-run",
        )

        calls = mock_sink.emit_audit_event.call_args_list
        persisted_events = [c for c in calls if c.args[0].event_type == AuditEventType.REVIEW_DRIFT_PERSISTED]
        assert len(persisted_events) == 1

        event = persisted_events[0].args[0]
        assert event.payload["count"] == 1
        assert event.payload["severity_summary"]["major"] == 1


class TestAuditEmissionFailureResilience:
    """TS-84-E2: Audit emission failure does not raise."""

    def test_audit_emission_failure_does_not_propagate(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify that if audit event emission raises, findings are still persisted.

        The emit_audit_event mock raises RuntimeError. The system should:
        1. Still insert findings into DuckDB
        2. Attempt to emit the REVIEW_FINDINGS_PERSISTED event (which fails)
        3. Not propagate the exception
        """
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = RuntimeError("audit broken")

        transcript = _make_skeptic_transcript([{"severity": "critical", "description": "test finding"}])

        # Should not raise
        persist_review_findings(
            transcript,
            "my_spec:1",
            1,
            archetype="skeptic",
            spec_name="my_spec",
            task_group="1",
            knowledge_db_conn=knowledge_conn,
            sink=mock_sink,
            run_id="test-run",
        )

        # Findings should still be in the database
        rows = knowledge_conn.execute("SELECT COUNT(*) FROM review_findings").fetchone()
        assert rows is not None
        assert rows[0] == 1

        # The system should have attempted to emit a REVIEW_FINDINGS_PERSISTED event
        # (which would have raised, but been caught)
        persisted_calls = [
            c
            for c in mock_sink.emit_audit_event.call_args_list
            if c.args[0].event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED
        ]
        assert len(persisted_calls) >= 1, "Expected at least one REVIEW_FINDINGS_PERSISTED emission attempt"
