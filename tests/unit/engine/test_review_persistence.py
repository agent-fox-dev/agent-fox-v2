"""Unit tests for review finding persistence wiring in session lifecycle.

Tests that archetype session output is routed to the correct insert function
(Skeptic→insert_findings, Verifier→insert_verdicts, Oracle→insert_drift_findings),
that parse failures emit a review.parse_failure audit event, and that retry
context is assembled correctly from active findings.

Test Spec: TS-53-1, TS-53-2, TS-53-3, TS-53-5, TS-53-8, TS-53-9
Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1, 53-REQ-1.E1,
              53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

# ---------------------------------------------------------------------------
# TS-53-1: Skeptic output parsed via engine.review_parser and persisted
# ---------------------------------------------------------------------------


class TestSkepticOutputParsedAndPersisted:
    """TS-53-1: Skeptic session output is parsed using engine.review_parser."""

    def test_skeptic_uses_extract_json_array(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-1: _persist_review_findings calls extract_json_array for Skeptic.

        This test will fail until Task Group 3 wires extract_json_array from
        engine.review_parser into session_lifecycle.py.
        """
        output = (
            "Here are the findings:\n"
            '[{"severity": "major", "description": "Missing null check",'
            ' "requirement_ref": "03-REQ-1.1"}]'
        )
        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
        )

        # Patch extract_json_array as imported in session_lifecycle.
        # This will raise AttributeError until Task Group 3 adds the import.
        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
        ) as mock_extract:
            mock_extract.return_value = [
                {
                    "severity": "major",
                    "description": "Missing null check",
                    "requirement_ref": "03-REQ-1.1",
                }
            ]
            runner._persist_review_findings(output, "03_api:2:1", 1)

        mock_extract.assert_called_once_with(output)

    def test_skeptic_end_to_end_finding_persisted(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-1: Skeptic output persisted to DuckDB (bare JSON array format)."""
        output = json.dumps(
            [
                {
                    "severity": "major",
                    "description": "Missing null check",
                    "requirement_ref": "03-REQ-1.1",
                }
            ]
        )
        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
        )

        # Patch extract_json_array in session_lifecycle (fails until TG3)
        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=[
                {
                    "severity": "major",
                    "description": "Missing null check",
                    "requirement_ref": "03-REQ-1.1",
                }
            ],
        ):
            runner._persist_review_findings(output, "03_api:2:1", 1)

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT severity, description FROM review_findings"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "major"
        assert rows[0][1] == "Missing null check"


# ---------------------------------------------------------------------------
# TS-53-2: Verifier output parsed via engine.review_parser and persisted
# ---------------------------------------------------------------------------


class TestVerifierOutputParsedAndPersisted:
    """TS-53-2: Verifier session output is parsed using engine.review_parser."""

    def test_verifier_uses_extract_json_array(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-2: _persist_review_findings calls extract_json_array for Verifier."""
        _verdict_item = {
            "requirement_id": "03-REQ-1.1",
            "verdict": "PASS",
            "evidence": "Tests pass",
        }
        output = json.dumps([_verdict_item])
        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="verifier",
            knowledge_db=knowledge_db,
        )

        # Patch extract_json_array in session_lifecycle (fails until TG3)
        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
        ) as mock_extract:
            mock_extract.return_value = [_verdict_item]
            runner._persist_review_findings(output, "03_api:2:1", 1)

        mock_extract.assert_called_once_with(output)

    def test_verifier_end_to_end_verdict_persisted(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-2: Verifier output persisted to DuckDB."""
        _verdict_item = {
            "requirement_id": "03-REQ-1.1",
            "verdict": "PASS",
            "evidence": "Tests pass",
        }
        output = json.dumps([_verdict_item])
        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="verifier",
            knowledge_db=knowledge_db,
        )

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=[_verdict_item],
        ):
            runner._persist_review_findings(output, "03_api:2:1", 1)

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT requirement_id, verdict FROM verification_results"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "03-REQ-1.1"
        assert rows[0][1] == "PASS"


# ---------------------------------------------------------------------------
# TS-53-3: Oracle output parsed via engine.review_parser and persisted
# ---------------------------------------------------------------------------


class TestOracleOutputParsedAndPersisted:
    """TS-53-3: Oracle session output is parsed using engine.review_parser."""

    def test_oracle_uses_extract_json_array(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-3: _persist_review_findings calls extract_json_array for Oracle."""
        output = json.dumps(
            [
                {
                    "severity": "critical",
                    "description": "API endpoint missing",
                    "spec_ref": "03-REQ-2.1",
                    "artifact_ref": "routes.py",
                }
            ]
        )
        runner = NodeSessionRunner(
            "03_api:0",
            AgentFoxConfig(),
            archetype="oracle",
            knowledge_db=knowledge_db,
        )

        # Patch extract_json_array in session_lifecycle (fails until TG3)
        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
        ) as mock_extract:
            mock_extract.return_value = [
                {
                    "severity": "critical",
                    "description": "API endpoint missing",
                    "spec_ref": "03-REQ-2.1",
                    "artifact_ref": "routes.py",
                }
            ]
            runner._persist_review_findings(output, "03_api:0:1", 1)

        mock_extract.assert_called_once_with(output)

    def test_oracle_end_to_end_drift_persisted(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-3: Oracle output persisted to DuckDB."""
        output = json.dumps(
            [
                {
                    "severity": "critical",
                    "description": "API endpoint missing",
                    "spec_ref": "03-REQ-2.1",
                    "artifact_ref": "routes.py",
                }
            ]
        )
        runner = NodeSessionRunner(
            "03_api:0",
            AgentFoxConfig(),
            archetype="oracle",
            knowledge_db=knowledge_db,
        )

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=[
                {
                    "severity": "critical",
                    "description": "API endpoint missing",
                    "spec_ref": "03-REQ-2.1",
                    "artifact_ref": "routes.py",
                }
            ],
        ):
            runner._persist_review_findings(output, "03_api:0:1", 1)

        rows = knowledge_db._conn.execute(  # type: ignore[union-attr]
            "SELECT severity, description FROM drift_findings"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "critical"


# ---------------------------------------------------------------------------
# TS-53-5: Parse failure emits review.parse_failure audit event
# ---------------------------------------------------------------------------


class TestParseFailureEmitsAuditEvent:
    """TS-53-5: Unparseable archetype output triggers a review.parse_failure event."""

    def test_review_parse_failure_event_type_exists(self) -> None:
        """AuditEventType.REVIEW_PARSE_FAILURE must exist with correct value.

        This test fails until Task Group 2 adds REVIEW_PARSE_FAILURE to
        AuditEventType.
        """
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE"), (
            "AuditEventType.REVIEW_PARSE_FAILURE is not defined. Add it to audit.py in Task Group 2."
        )
        assert AuditEventType.REVIEW_PARSE_FAILURE == "review.parse_failure"

    def test_parse_failure_emits_warning_event(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-5: review.parse_failure event is emitted on unparseable output."""
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE"), "AuditEventType.REVIEW_PARSE_FAILURE not yet defined"

        emitted_events = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted_events.append(e)

        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
            sink_dispatcher=mock_sink,
            run_id="test_run_001",
        )

        runner._persist_review_findings("This is just prose with no JSON", "03_api:2", 1)

        failure_events = [e for e in emitted_events if e.event_type == "review.parse_failure"]
        assert len(failure_events) == 1, (
            f"Expected 1 review.parse_failure event, got {len(failure_events)}: {emitted_events}"
        )
        assert failure_events[0].severity == AuditSeverity.WARNING

    def test_parse_failure_payload_contains_raw_output(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-5: review.parse_failure payload contains the raw output."""
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE")

        emitted_events = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted_events.append(e)

        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
            sink_dispatcher=mock_sink,
            run_id="test_run_002",
        )

        prose = "no json here"
        runner._persist_review_findings(prose, "03_api:2", 1)

        failure_events = [e for e in emitted_events if e.event_type == "review.parse_failure"]
        assert len(failure_events) == 1
        raw = failure_events[0].payload.get("raw_output", "")
        assert prose in raw, f"Expected raw_output to contain the prose, got: {raw!r}"

    def test_parse_failure_truncates_long_output(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-5: Raw output in the audit payload is truncated to 2000 characters."""
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE")

        emitted_events = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted_events.append(e)

        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
            sink_dispatcher=mock_sink,
            run_id="test_run_003",
        )

        long_output = "x" * 5000  # 5000 chars, not valid JSON
        runner._persist_review_findings(long_output, "03_api:2", 1)

        failure_events = [e for e in emitted_events if e.event_type == "review.parse_failure"]
        assert len(failure_events) == 1
        raw = failure_events[0].payload.get("raw_output", "")
        assert len(raw) <= 2000, f"raw_output should be truncated to 2000 chars, got {len(raw)}"

    def test_parse_failure_does_not_raise(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-5: Parse failures must not raise exceptions (run must not block).

        Also verifies that a review.parse_failure event is emitted (not just a log).
        """
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE"), "AuditEventType.REVIEW_PARSE_FAILURE not yet defined"
        emitted_events: list = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted_events.append(e)

        runner = NodeSessionRunner(
            "03_api:2",
            AgentFoxConfig(),
            archetype="skeptic",
            knowledge_db=knowledge_db,
            sink_dispatcher=mock_sink,
            run_id="test_run_004",
        )
        # Must not raise
        runner._persist_review_findings("no json here at all", "03_api:2", 1)

        # Should emit a failure event
        failure_events = [e for e in emitted_events if e.event_type == "review.parse_failure"]
        assert len(failure_events) == 1


# ---------------------------------------------------------------------------
# TS-53-8: Retry context includes active critical/major findings
# ---------------------------------------------------------------------------


class TestRetryContextIncludesActiveFindings:
    """TS-53-8: _build_retry_context returns a block with critical/major findings."""

    def test_method_exists_on_runner(self, knowledge_db: KnowledgeDB) -> None:
        """_build_retry_context must exist on NodeSessionRunner.

        This test fails until Task Group 3 adds the method.
        """
        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )
        assert hasattr(runner, "_build_retry_context"), (
            "NodeSessionRunner._build_retry_context is not defined. Add it in Task Group 3."
        )

    def test_critical_finding_in_context(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-8: Active critical finding appears in the retry context string."""
        critical_finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Missing null check",
            requirement_ref="03-REQ-1.1",
            spec_name="03_api",
            task_group="2",
            session_id="test_session",
        )
        insert_findings(knowledge_db._conn, [critical_finding])  # type: ignore[arg-type]

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )

        context = runner._build_retry_context("03_api")

        assert "Missing null check" in context
        assert "critical" in context.lower()

    def test_major_finding_in_context(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-8: Active major finding appears in the retry context string."""
        major_finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="major",
            description="Missing error handling",
            requirement_ref="03-REQ-2.1",
            spec_name="03_api",
            task_group="2",
            session_id="test_session",
        )
        insert_findings(knowledge_db._conn, [major_finding])  # type: ignore[arg-type]

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )

        context = runner._build_retry_context("03_api")

        assert "Missing error handling" in context
        assert "major" in context.lower()

    def test_context_contains_spec_name_or_req_ref(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-8: Context block is structured and contains spec name."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Broken interface",
            requirement_ref="03-REQ-1.1",
            spec_name="03_api",
            task_group="2",
            session_id="sess",
        )
        insert_findings(knowledge_db._conn, [finding])  # type: ignore[arg-type]

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )

        context = runner._build_retry_context("03_api")

        # Context should reference either spec name or requirement ref
        assert "03_api" in context or "03-REQ-1.1" in context


# ---------------------------------------------------------------------------
# TS-53-9: Retry context is empty when no critical/major findings
# ---------------------------------------------------------------------------


class TestRetryContextEmptyWhenNoFindings:
    """TS-53-9: _build_retry_context returns empty string when no active findings."""

    def test_empty_context_no_findings(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-9: Returns empty string when no active findings exist."""
        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )
        context = runner._build_retry_context("03_api")
        assert context == ""

    def test_empty_context_only_minor_findings(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-9: Minor findings are excluded from retry context."""
        minor_finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="minor",
            description="Minor formatting issue",
            requirement_ref=None,
            spec_name="03_api",
            task_group="2",
            session_id="sess",
        )
        insert_findings(knowledge_db._conn, [minor_finding])  # type: ignore[arg-type]

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )
        context = runner._build_retry_context("03_api")

        assert "Minor formatting issue" not in context

    def test_empty_context_only_observation_findings(self, knowledge_db: KnowledgeDB) -> None:
        """TS-53-9: Observation-level findings are excluded from retry context."""
        obs_finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="observation",
            description="Could add more comments",
            requirement_ref=None,
            spec_name="03_api",
            task_group="2",
            session_id="sess",
        )
        insert_findings(knowledge_db._conn, [obs_finding])  # type: ignore[arg-type]

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=knowledge_db,
        )
        context = runner._build_retry_context("03_api")

        assert "Could add more comments" not in context

    def test_empty_string_when_no_knowledge_db(self) -> None:
        """_build_retry_context returns empty string gracefully if no DB."""
        mock_kb = MagicMock(spec=KnowledgeDB)
        mock_kb.connection = MagicMock(side_effect=RuntimeError("no db"))

        runner = NodeSessionRunner(
            "03_api:3",
            AgentFoxConfig(),
            archetype="coder",
            knowledge_db=mock_kb,
        )
        # Should not raise, should return empty or handle gracefully
        context = runner._build_retry_context("03_api")
        assert context == ""
