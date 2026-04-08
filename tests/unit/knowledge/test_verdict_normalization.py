"""Tests for PARTIAL/non-standard verdict normalization (issue #266).

Verifies that:
- validate_verdict maps PARTIAL and other non-standard values to FAIL (AC-2)
- AuditEventType.VERDICT_NORMALIZED exists with the expected value (AC-3)
- parse_verification_results emits VERDICT_NORMALIZED audit event (AC-4)
- PARTIAL verdicts are persisted as FAIL, not dropped (AC-5)
"""

from __future__ import annotations

from typing import Any

from agent_fox.knowledge.audit import AuditEvent, AuditEventType
from agent_fox.knowledge.review_store import validate_verdict
from agent_fox.session.review_parser import parse_verification_results

# ---------------------------------------------------------------------------
# AC-2: validate_verdict maps non-standard verdicts to FAIL
# ---------------------------------------------------------------------------


class TestValidateVerdictNormalization:
    """AC-2: validate_verdict returns FAIL for non-standard input."""

    def test_partial_normalized_to_fail(self) -> None:
        """validate_verdict('PARTIAL') returns 'FAIL'."""
        assert validate_verdict("PARTIAL") == "FAIL"

    def test_conditional_normalized_to_fail(self) -> None:
        """validate_verdict('CONDITIONAL') returns 'FAIL'."""
        assert validate_verdict("CONDITIONAL") == "FAIL"

    def test_maybe_normalized_to_fail(self) -> None:
        """validate_verdict('MAYBE') returns 'FAIL'."""
        assert validate_verdict("MAYBE") == "FAIL"

    def test_pass_accepted(self) -> None:
        """validate_verdict('PASS') returns 'PASS'."""
        assert validate_verdict("PASS") == "PASS"

    def test_fail_accepted(self) -> None:
        """validate_verdict('FAIL') returns 'FAIL'."""
        assert validate_verdict("FAIL") == "FAIL"

    def test_lowercase_pass_accepted(self) -> None:
        """validate_verdict('pass') is normalized and returned as 'PASS'."""
        assert validate_verdict("pass") == "PASS"

    def test_lowercase_fail_accepted(self) -> None:
        """validate_verdict('fail') is normalized and returned as 'FAIL'."""
        assert validate_verdict("fail") == "FAIL"

    def test_mixed_case_partial_normalized_to_fail(self) -> None:
        """validate_verdict('Partial') is normalized to FAIL."""
        assert validate_verdict("Partial") == "FAIL"

    def test_return_type_is_str_never_none(self) -> None:
        """validate_verdict always returns a str, never None."""
        result = validate_verdict("PARTIAL")
        assert isinstance(result, str)
        assert result is not None

    def test_warning_logged_for_non_standard(self, caplog: Any) -> None:
        """A warning is logged when a verdict is normalized."""
        import logging

        with caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.review_store"):
            validate_verdict("PARTIAL")
        assert any("PARTIAL" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# AC-3: AuditEventType.VERDICT_NORMALIZED exists
# ---------------------------------------------------------------------------


class TestVerdictNormalizedAuditEventType:
    """AC-3: VERDICT_NORMALIZED is a valid AuditEventType member."""

    def test_verdict_normalized_exists(self) -> None:
        """AuditEventType.VERDICT_NORMALIZED exists."""
        assert hasattr(AuditEventType, "VERDICT_NORMALIZED")

    def test_verdict_normalized_value(self) -> None:
        """AuditEventType.VERDICT_NORMALIZED equals 'review.verdict_normalized'."""
        assert AuditEventType.VERDICT_NORMALIZED == "review.verdict_normalized"

    def test_verdict_normalized_is_str(self) -> None:
        """AuditEventType.VERDICT_NORMALIZED is a string (StrEnum)."""
        assert isinstance(AuditEventType.VERDICT_NORMALIZED, str)


# ---------------------------------------------------------------------------
# AC-4: parse_verification_results emits VERDICT_NORMALIZED audit event
# ---------------------------------------------------------------------------


class TestParseVerificationResultsAuditEvent:
    """AC-4: VERDICT_NORMALIZED event emitted when verdict is coerced."""

    def test_partial_emits_verdict_normalized_event(self) -> None:
        """parse_verification_results emits VERDICT_NORMALIZED for PARTIAL verdict."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "01-REQ-1.1", "verdict": "PARTIAL", "evidence": "Some tests pass"}]

        results = parse_verification_results(
            objs,
            "test_spec",
            "1",
            "sess-123",
            emit_audit_event=emitted.append,
        )

        assert len(results) == 1
        assert results[0].verdict == "FAIL"
        assert len(emitted) == 1
        event = emitted[0]
        assert event.event_type == AuditEventType.VERDICT_NORMALIZED
        assert event.payload["original_verdict"] == "PARTIAL"
        assert event.payload["normalized_verdict"] == "FAIL"

    def test_audit_event_contains_requirement_id(self) -> None:
        """VERDICT_NORMALIZED event payload includes requirement_id."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "02-REQ-2.3", "verdict": "PARTIAL"}]

        parse_verification_results(
            objs,
            "spec",
            "2",
            "session-abc",
            emit_audit_event=emitted.append,
        )

        assert len(emitted) == 1
        assert emitted[0].payload["requirement_id"] == "02-REQ-2.3"

    def test_no_event_for_valid_pass_verdict(self) -> None:
        """No VERDICT_NORMALIZED event is emitted for valid PASS verdicts."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "03-REQ-1.1", "verdict": "PASS"}]

        parse_verification_results(
            objs,
            "spec",
            "1",
            "session",
            emit_audit_event=emitted.append,
        )

        assert len(emitted) == 0

    def test_no_event_for_valid_fail_verdict(self) -> None:
        """No VERDICT_NORMALIZED event is emitted for valid FAIL verdicts."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "03-REQ-1.1", "verdict": "FAIL"}]

        parse_verification_results(
            objs,
            "spec",
            "1",
            "session",
            emit_audit_event=emitted.append,
        )

        assert len(emitted) == 0

    def test_no_audit_callback_does_not_raise(self) -> None:
        """parse_verification_results works without emit_audit_event callback."""
        objs = [{"requirement_id": "01-REQ-1.1", "verdict": "PARTIAL"}]

        results = parse_verification_results(objs, "spec", "1", "session")

        assert len(results) == 1
        assert results[0].verdict == "FAIL"

    def test_conditional_verdict_emits_event(self) -> None:
        """VERDICT_NORMALIZED event is emitted for CONDITIONAL verdict too."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "04-REQ-1.1", "verdict": "CONDITIONAL"}]

        parse_verification_results(
            objs,
            "spec",
            "1",
            "session",
            emit_audit_event=emitted.append,
        )

        assert len(emitted) == 1
        assert emitted[0].payload["original_verdict"] == "CONDITIONAL"
        assert emitted[0].payload["normalized_verdict"] == "FAIL"

    def test_audit_event_session_id_set(self) -> None:
        """VERDICT_NORMALIZED event has session_id populated from the call context."""
        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "R1", "verdict": "PARTIAL"}]

        parse_verification_results(
            objs,
            "spec",
            "1",
            "my-session-id",
            emit_audit_event=emitted.append,
        )

        assert emitted[0].session_id == "my-session-id"

    def test_audit_event_is_warning_severity(self) -> None:
        """VERDICT_NORMALIZED event has WARNING severity."""
        from agent_fox.knowledge.audit import AuditSeverity

        emitted: list[AuditEvent] = []
        objs = [{"requirement_id": "R1", "verdict": "PARTIAL"}]

        parse_verification_results(
            objs,
            "spec",
            "1",
            "session",
            emit_audit_event=emitted.append,
        )

        assert emitted[0].severity == AuditSeverity.WARNING


# ---------------------------------------------------------------------------
# AC-5: PARTIAL verdicts are persisted as FAIL, not dropped
# ---------------------------------------------------------------------------


class TestPartialVerdictPersistence:
    """AC-5: All verdicts (including PARTIAL) appear in the result list as FAIL."""

    def test_three_verdicts_all_persisted(self) -> None:
        """Three input verdicts (PASS, FAIL, PARTIAL) produce three result records."""
        objs = [
            {"requirement_id": "01-REQ-1.1", "verdict": "PASS", "evidence": "Tests pass"},
            {"requirement_id": "01-REQ-1.2", "verdict": "FAIL", "evidence": "Test missing"},
            {"requirement_id": "01-REQ-1.3", "verdict": "PARTIAL", "evidence": "Only some criteria met"},
        ]

        results = parse_verification_results(objs, "01_project_setup", "8", "session-xyz")

        assert len(results) == 3

    def test_partial_verdict_stored_as_fail(self) -> None:
        """The PARTIAL input record is stored with verdict='FAIL'."""
        objs = [
            {"requirement_id": "01-REQ-1.1", "verdict": "PASS"},
            {"requirement_id": "01-REQ-1.2", "verdict": "FAIL"},
            {"requirement_id": "01-REQ-1.3", "verdict": "PARTIAL"},
        ]

        results = parse_verification_results(objs, "spec", "1", "session")

        partial_results = [r for r in results if r.requirement_id == "01-REQ-1.3"]
        assert len(partial_results) == 1
        assert partial_results[0].verdict == "FAIL"

    def test_pass_and_fail_verdicts_unchanged(self) -> None:
        """PASS and FAIL verdicts are preserved as-is alongside PARTIAL."""
        objs = [
            {"requirement_id": "R-PASS", "verdict": "PASS"},
            {"requirement_id": "R-FAIL", "verdict": "FAIL"},
            {"requirement_id": "R-PARTIAL", "verdict": "PARTIAL"},
        ]

        results = parse_verification_results(objs, "spec", "1", "session")

        by_req = {r.requirement_id: r.verdict for r in results}
        assert by_req["R-PASS"] == "PASS"
        assert by_req["R-FAIL"] == "FAIL"
        assert by_req["R-PARTIAL"] == "FAIL"

    def test_multiple_partial_verdicts_all_stored(self) -> None:
        """Multiple PARTIAL verdicts are all stored (reproduces parking-fee-service scenario)."""
        objs = [{"requirement_id": f"02-REQ-{i}.1", "verdict": "PARTIAL"} for i in range(1, 4)]

        results = parse_verification_results(objs, "02_data_broker", "7", "session")

        assert len(results) == 3
        assert all(r.verdict == "FAIL" for r in results)
