"""Tests for AuditEvent data model, enums, and run ID generation.

Test Spec: TS-40-1, TS-40-2, TS-40-3, TS-40-4, TS-40-5, TS-40-6, TS-40-E1
Requirements: 40-REQ-1.1, 40-REQ-1.2, 40-REQ-1.3, 40-REQ-1.4,
              40-REQ-1.E1, 40-REQ-2.1, 40-REQ-2.E1
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    generate_run_id,
)


class TestAuditEventModel:
    """TS-40-1: AuditEvent dataclass fields.

    Requirement: 40-REQ-1.1
    """

    def test_fields(self) -> None:
        """AuditEvent has all required fields with correct types and defaults."""
        event = AuditEvent(
            run_id="20260312_143000_abc123",
            event_type=AuditEventType.RUN_START,
        )
        assert isinstance(event.id, UUID)
        assert isinstance(event.timestamp, datetime)
        assert event.severity == AuditSeverity.INFO
        assert event.node_id == ""
        assert event.session_id == ""
        assert event.archetype == ""
        assert event.payload == {}

    def test_auto_populate(self) -> None:
        """TS-40-4: Creating AuditEvent auto-generates id and timestamp.

        Requirement: 40-REQ-1.4
        """
        e1 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        e2 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        assert e1.id != e2.id
        assert (datetime.now(UTC) - e1.timestamp).total_seconds() < 5

    def test_empty_optionals(self) -> None:
        """TS-40-E1: Optional fields default to empty strings.

        Requirement: 40-REQ-1.E1
        """
        event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        assert event.node_id == ""
        assert event.session_id == ""
        assert event.archetype == ""

    def test_custom_payload(self) -> None:
        """AuditEvent accepts custom payload dict."""
        event = AuditEvent(
            run_id="r1",
            event_type=AuditEventType.RUN_START,
            payload={"plan_hash": "abc123", "total_nodes": 5},
        )
        assert event.payload["plan_hash"] == "abc123"
        assert event.payload["total_nodes"] == 5

    def test_frozen(self) -> None:
        """AuditEvent is frozen (immutable)."""
        event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
        try:
            event.run_id = "r2"  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass


class TestAuditEventTypeEnum:
    """TS-40-2: AuditEventType enum completeness.

    Requirement: 40-REQ-1.2
    """

    def test_completeness(self) -> None:
        """AuditEventType has exactly 21 variants matching the spec."""
        expected = {
            "run.start",
            "run.complete",
            "run.limit_reached",
            "session.start",
            "session.complete",
            "session.fail",
            "session.retry",
            "task.status_change",
            "model.escalation",
            "model.assessment",
            "tool.invocation",
            "tool.error",
            "git.merge",
            "git.conflict",
            "harvest.complete",
            "harvest.empty",
            "fact.extracted",
            "fact.compacted",
            "fact.causal_links",
            "knowledge.ingested",
            "sync.barrier",
            "quality_gate.result",
            "review.parse_failure",
        }
        actual = {e.value for e in AuditEventType}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        """AuditEventType values are usable as strings."""
        assert AuditEventType.RUN_START == "run.start"
        assert str(AuditEventType.SESSION_COMPLETE) == "session.complete"


class TestAuditSeverityEnum:
    """TS-40-3: AuditSeverity enum values.

    Requirement: 40-REQ-1.3
    """

    def test_values(self) -> None:
        """AuditSeverity has exactly 4 values."""
        actual = {s.value for s in AuditSeverity}
        assert actual == {"info", "warning", "error", "critical"}

    def test_is_str_enum(self) -> None:
        """AuditSeverity values are usable as strings."""
        assert AuditSeverity.INFO == "info"
        assert AuditSeverity.WARNING == "warning"


class TestRunIdGeneration:
    """TS-40-5, TS-40-6: Run ID format and uniqueness.

    Requirements: 40-REQ-2.1, 40-REQ-2.E1
    """

    def test_format(self) -> None:
        """TS-40-5: generate_run_id() produces correctly formatted IDs."""
        run_id = generate_run_id()
        assert re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", run_id) is not None

    def test_uniqueness(self) -> None:
        """TS-40-6: Two consecutive calls produce different IDs."""
        id1 = generate_run_id()
        id2 = generate_run_id()
        assert id1 != id2

    def test_date_portion_is_current(self) -> None:
        """Run ID date portion matches current UTC date."""
        run_id = generate_run_id()
        date_part = run_id[:8]
        expected = datetime.now(UTC).strftime("%Y%m%d")
        assert date_part == expected
