"""Tests for security-category finding blocking (issue #277).

Validates that critical findings with category='security' always block
regardless of numeric threshold, that the category field round-trips
through DuckDB, that parse_review_findings auto-detects security keywords,
that converge_skeptic_records preserves category, and that an audit event
is emitted on security-based blocking.

Test Spec: AC-1 through AC-9
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb

from agent_fox.engine.blocking import evaluate_review_blocking
from agent_fox.engine.state import SessionRecord
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
    query_findings_by_session,
)
from agent_fox.session.convergence import converge_skeptic_records
from agent_fox.session.review_parser import parse_review_findings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    severity: str = "critical",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "test_spec:1:1",
    category: str | None = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
        category=category,
    )


def _make_session_record(
    node_id: str = "test_spec:1",
    archetype: str = "skeptic",
    attempt: int = 1,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        archetype=archetype,
        attempt=attempt,
        status="completed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=None,
        timestamp="2026-01-01T00:00:00",
    )


def _make_archetypes_config(block_threshold: int = 3):
    config = MagicMock()
    config.reviewer_config.pre_review_block_threshold = block_threshold
    config.reviewer_config.drift_review_block_threshold = block_threshold
    return config


# ---------------------------------------------------------------------------
# AC-1: ReviewFinding has optional category field
# ---------------------------------------------------------------------------


class TestReviewFindingCategoryField:
    """AC-1: ReviewFinding dataclass includes an optional 'category' field."""

    def test_category_stored_when_provided(self) -> None:
        """category='security' is stored and retrievable."""
        finding = _make_finding(category="security")
        assert finding.category == "security"

    def test_category_defaults_to_none(self) -> None:
        """category defaults to None when not provided."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="major",
            description="Some finding",
            requirement_ref=None,
            spec_name="test_spec",
            task_group="1",
            session_id="session-1",
        )
        assert finding.category is None

    def test_category_other_values(self) -> None:
        """category accepts arbitrary string values."""
        finding = _make_finding(category="performance")
        assert finding.category == "performance"


# ---------------------------------------------------------------------------
# AC-2: DuckDB review_findings table has a 'category' column
# ---------------------------------------------------------------------------


class TestCategoryColumnInSchema:
    """AC-2: review_findings table includes a 'category' column via migration."""

    def test_category_column_exists(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """After applying migrations, category column exists in review_findings."""
        rows = knowledge_conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'review_findings' AND column_name = 'category'"
        ).fetchall()
        assert len(rows) == 1, "category column not found in review_findings"
        col_name, data_type = rows[0]
        assert col_name == "category"
        # DuckDB maps TEXT to VARCHAR internally
        assert data_type.upper() in ("TEXT", "VARCHAR")

    def test_category_column_is_nullable(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """category column is nullable — can insert NULL."""
        finding = _make_finding(category=None)
        insert_findings(knowledge_conn, [finding])
        rows = knowledge_conn.execute(
            "SELECT category FROM review_findings WHERE id = ?::UUID",
            [finding.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None


# ---------------------------------------------------------------------------
# AC-3: parse_review_findings detects security keywords and sets category
# ---------------------------------------------------------------------------


class TestParseReviewFindingsSecurityDetection:
    """AC-3: review_parser auto-classifies findings with security keywords."""

    def test_command_injection_classified_as_security(self) -> None:
        """Findings with 'command injection' in description get category='security'."""
        json_objects = [
            {
                "severity": "critical",
                "description": "command injection vulnerability in image_ref parameter",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert len(findings) == 1
        assert findings[0].category == "security"

    def test_sql_injection_classified_as_security(self) -> None:
        """Findings with 'SQL injection' in description get category='security'."""
        json_objects = [
            {
                "severity": "critical",
                "description": "SQL injection risk in user query builder",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert len(findings) == 1
        assert findings[0].category == "security"

    def test_xss_classified_as_security(self) -> None:
        """Findings with 'XSS' in description get category='security'."""
        json_objects = [
            {
                "severity": "critical",
                "description": "XSS vulnerability in template rendering",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert len(findings) == 1
        assert findings[0].category == "security"

    def test_cross_site_scripting_classified_as_security(self) -> None:
        """Findings with 'cross-site scripting' get category='security'."""
        json_objects = [
            {
                "severity": "major",
                "description": "Cross-site scripting in output encoder",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert len(findings) == 1
        assert findings[0].category == "security"

    def test_non_security_finding_has_no_category(self) -> None:
        """Findings without security keywords have category=None."""
        json_objects = [
            {
                "severity": "major",
                "description": "Missing null check before dereferencing pointer",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert len(findings) == 1
        assert findings[0].category is None

    def test_keyword_detection_is_case_insensitive(self) -> None:
        """Security keyword detection is case-insensitive."""
        json_objects = [
            {
                "severity": "critical",
                "description": "Command Injection via unvalidated user input",
            }
        ]
        findings = parse_review_findings(json_objects, "spec_07", "3", "sess-1")
        assert findings[0].category == "security"


# ---------------------------------------------------------------------------
# AC-4: Security-category critical finding always blocks regardless of threshold
# ---------------------------------------------------------------------------


class TestSecurityCriticalAlwaysBlocks:
    """AC-4: evaluate_review_blocking blocks on security-critical findings."""

    def test_single_security_critical_blocks_with_high_threshold(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """One critical security finding blocks even when threshold=3."""
        finding = _make_finding(
            severity="critical",
            description="command injection in executor",
            session_id="test_spec:1:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        assert decision.coder_node_id == "test_spec:1"


# ---------------------------------------------------------------------------
# AC-5: Non-security critical does NOT bypass threshold
# ---------------------------------------------------------------------------


class TestNonSecurityCriticalRespectsThreshold:
    """AC-5: evaluate_review_blocking respects threshold for non-security criticals."""

    def test_single_non_security_critical_does_not_block_with_high_threshold(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """One critical finding with category=None does not block when threshold=3."""
        finding = _make_finding(
            severity="critical",
            description="Missing error handling in null path",
            session_id="test_spec:1:1",
            category=None,
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is False


# ---------------------------------------------------------------------------
# AC-6: Blocking reason contains 'security' label
# ---------------------------------------------------------------------------


class TestSecurityBlockingReasonLabel:
    """AC-6: Blocking reason string includes 'SECURITY' label."""

    def test_security_block_reason_contains_security_label(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Reason for security-triggered block contains 'security' (case-insensitive)."""
        finding = _make_finding(
            severity="critical",
            description="command injection in podman executor",
            session_id="test_spec:1:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        assert "security" in decision.reason.lower()

    def test_non_security_block_reason_does_not_have_security_label(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Threshold-based block reason does not contain SECURITY label."""
        findings = [
            _make_finding(
                severity="critical",
                description=f"Non-security issue {i}",
                session_id="test_spec:1:1",
                category=None,
            )
            for i in range(4)
        ]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        assert "SECURITY" not in decision.reason
        assert "[SECURITY]" not in decision.reason


# ---------------------------------------------------------------------------
# AC-7: SECURITY_FINDING_BLOCKED audit event is emitted
# ---------------------------------------------------------------------------


class TestSecurityBlockingAuditEvent:
    """AC-7: SECURITY_FINDING_BLOCKED audit event is emitted on security block."""

    def test_security_finding_blocked_audit_event_emitted(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """A SECURITY_FINDING_BLOCKED audit event is emitted when blocking on security."""
        from agent_fox.knowledge.sink import SinkDispatcher

        finding = _make_finding(
            severity="critical",
            description="command injection via image_ref parameter",
            session_id="test_spec:1:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)

        mock_sink = MagicMock(spec=SinkDispatcher)

        decision = evaluate_review_blocking(record, config, knowledge_conn, sink=mock_sink, run_id="test-run")

        assert decision.should_block is True
        # Verify emit_audit_event was called on the sink
        assert mock_sink.emit_audit_event.called
        # Find the security_finding_blocked call
        calls = mock_sink.emit_audit_event.call_args_list
        assert len(calls) >= 1
        emitted_event = calls[0][0][0]  # positional arg to emit_audit_event
        assert "security" in emitted_event.event_type.lower()

    def test_no_audit_event_for_non_security_blocking(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """No SECURITY_FINDING_BLOCKED event is emitted for threshold-based blocking."""
        from agent_fox.knowledge.sink import SinkDispatcher

        findings = [
            _make_finding(
                severity="critical",
                description=f"Non-security issue {i}",
                session_id="test_spec:1:1",
                category=None,
            )
            for i in range(4)
        ]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=3)
        mock_sink = MagicMock(spec=SinkDispatcher)

        decision = evaluate_review_blocking(record, config, knowledge_conn, sink=mock_sink, run_id="test-run")

        assert decision.should_block is True
        # Verify NO security-specific event was emitted
        security_calls = [call for call in mock_sink.emit_audit_event.call_args_list if "security" in str(call).lower()]
        assert len(security_calls) == 0


# ---------------------------------------------------------------------------
# AC-8: converge_skeptic_records preserves category
# ---------------------------------------------------------------------------


class TestConvergencePreservesCategory:
    """AC-8: converge_skeptic_records preserves the category field."""

    def test_security_category_preserved_after_convergence(self) -> None:
        """category='security' is preserved when merging multiple instances."""
        finding = _make_finding(
            severity="critical",
            description="command injection via image_ref",
            session_id="instance-1",
            category="security",
        )
        finding2 = ReviewFinding(
            id=str(uuid.uuid4()),
            severity=finding.severity,
            description=finding.description,
            requirement_ref=finding.requirement_ref,
            spec_name=finding.spec_name,
            task_group=finding.task_group,
            session_id="instance-2",
            category="security",
        )

        instance_findings = [[finding], [finding2]]
        merged, _ = converge_skeptic_records(instance_findings, block_threshold=3)

        assert len(merged) == 1
        assert merged[0].category == "security"

    def test_none_category_preserved_after_convergence(self) -> None:
        """category=None is preserved during convergence."""
        finding = _make_finding(
            severity="major",
            description="non-security issue",
            session_id="instance-1",
            category=None,
        )
        finding2 = ReviewFinding(
            id=str(uuid.uuid4()),
            severity=finding.severity,
            description=finding.description,
            requirement_ref=finding.requirement_ref,
            spec_name=finding.spec_name,
            task_group=finding.task_group,
            session_id="instance-2",
            category=None,
        )

        instance_findings = [[finding], [finding2]]
        merged, _ = converge_skeptic_records(instance_findings, block_threshold=3)

        assert len(merged) == 1
        assert merged[0].category is None


# ---------------------------------------------------------------------------
# AC-9: insert_findings and query_findings_by_session round-trip category
# ---------------------------------------------------------------------------


class TestCategoryRoundTrip:
    """AC-9: category field round-trips through DuckDB insert/query."""

    def test_security_category_round_trips(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Inserting category='security' and querying back returns 'security'."""
        finding = _make_finding(
            severity="critical",
            description="command injection vulnerability",
            session_id="my-session-id",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        results = query_findings_by_session(knowledge_conn, "my-session-id")
        assert len(results) == 1
        assert results[0].category == "security"

    def test_none_category_round_trips(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Inserting category=None and querying back returns None."""
        finding = _make_finding(
            severity="major",
            description="null pointer dereference",
            session_id="my-session-id-2",
            category=None,
        )
        insert_findings(knowledge_conn, [finding])

        results = query_findings_by_session(knowledge_conn, "my-session-id-2")
        assert len(results) == 1
        assert results[0].category is None

    def test_category_preserved_on_supersession(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """category is preserved when a finding is NOT superseded (first insert)."""
        finding = _make_finding(
            severity="critical",
            description="sql injection in user builder",
            session_id="sess-v1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        results = query_findings_by_session(knowledge_conn, "sess-v1")
        assert len(results) == 1
        assert results[0].category == "security"
