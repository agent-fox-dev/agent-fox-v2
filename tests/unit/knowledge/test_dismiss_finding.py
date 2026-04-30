"""Unit tests for dismiss_finding_by_id in review_store.

Validates manual dismissal of findings across review_findings,
drift_findings, and verification_results tables.

Requirements: 592-AC-1, 592-AC-2
"""

from __future__ import annotations

import uuid

from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    dismiss_finding_by_id,
    insert_drift_findings,
    insert_findings,
    insert_verdicts,
    query_active_findings,
)


class TestDismissReviewFinding:
    """AC-1: dismiss_finding_by_id sets superseded_by to 'dismissed:...' on review_findings."""

    def test_dismiss_active_review_finding(self, knowledge_conn) -> None:
        """Dismissing an active review finding marks it superseded and returns description."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Missing smoke tests for spec 120",
            requirement_ref="120-REQ-1.1",
            spec_name="120_spec",
            task_group="0",
            session_id="120_spec:0:1",
        )
        insert_findings(knowledge_conn, [finding])

        result = dismiss_finding_by_id(knowledge_conn, finding.id, "Tests were implemented after finding was created")

        assert result is not None
        assert "critical" in result
        assert "Missing smoke tests for spec 120" in result

        # Verify the row is now superseded
        row = knowledge_conn.execute(
            "SELECT superseded_by FROM review_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[0].startswith("dismissed:")

        # Verify it no longer appears in active queries
        active = query_active_findings(knowledge_conn, "120_spec")
        assert not any(f.id == finding.id for f in active)

    def test_dismiss_sets_marker_with_timestamp(self, knowledge_conn) -> None:
        """The superseded_by marker begins with 'dismissed:' followed by an ISO timestamp."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="major",
            description="Some finding",
            requirement_ref=None,
            spec_name="test_spec",
            task_group="1",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        dismiss_finding_by_id(knowledge_conn, finding.id, "false positive")

        row = knowledge_conn.execute(
            "SELECT superseded_by FROM review_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        assert row is not None
        marker = row[0]
        assert marker.startswith("dismissed:"), f"Expected 'dismissed:...' marker, got: {marker!r}"
        # The part after 'dismissed:' should be parseable as an ISO datetime
        timestamp_part = marker.removeprefix("dismissed:")
        # Just check it's non-empty and contains typical ISO chars
        assert len(timestamp_part) > 10
        assert "T" in timestamp_part or "-" in timestamp_part


class TestDismissDriftFinding:
    """AC-1: dismiss_finding_by_id sets superseded_by on drift_findings."""

    def test_dismiss_active_drift_finding(self, knowledge_conn) -> None:
        """Dismissing an active drift finding marks it superseded and returns description."""
        finding = DriftFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Spec says auth required but code has no auth check",
            spec_ref="84-REQ-2.1",
            artifact_ref="agent_fox/cli/findings.py",
            spec_name="84_spec",
            task_group="2",
            session_id="84_spec:2:1",
        )
        insert_drift_findings(knowledge_conn, [finding])

        result = dismiss_finding_by_id(knowledge_conn, finding.id, "Auth was added in PR #100")

        assert result is not None
        assert "critical" in result
        assert "Spec says auth required" in result

        # Verify the row is now superseded
        row = knowledge_conn.execute(
            "SELECT superseded_by FROM drift_findings WHERE id::VARCHAR = ?",
            [finding.id],
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[0].startswith("dismissed:")


class TestDismissVerificationResult:
    """AC-1: dismiss_finding_by_id sets superseded_by on verification_results."""

    def test_dismiss_active_verification_result(self, knowledge_conn) -> None:
        """Dismissing an active verification result marks it superseded and returns description."""
        verdict = VerificationResult(
            id=str(uuid.uuid4()),
            requirement_id="84-REQ-3.1",
            verdict="FAIL",
            evidence="Test file not found",
            spec_name="84_spec",
            task_group="3",
            session_id="84_spec:3:1",
        )
        insert_verdicts(knowledge_conn, [verdict])

        result = dismiss_finding_by_id(knowledge_conn, verdict.id, "Test was added in later session")

        assert result is not None
        assert "FAIL" in result
        assert "84-REQ-3.1" in result

        row = knowledge_conn.execute(
            "SELECT superseded_by FROM verification_results WHERE id::VARCHAR = ?",
            [verdict.id],
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[0].startswith("dismissed:")


class TestDismissUnknownId:
    """AC-2: dismiss_finding_by_id returns None for unknown IDs without modifying the DB."""

    def test_unknown_id_returns_none(self, knowledge_conn) -> None:
        """Calling dismiss with an ID not in any table returns None."""
        unknown_id = str(uuid.uuid4())
        result = dismiss_finding_by_id(knowledge_conn, unknown_id, "some reason")
        assert result is None

    def test_unknown_id_makes_no_db_changes(self, knowledge_conn) -> None:
        """No rows are modified when the finding ID does not exist."""
        # Insert a known finding to ensure it is NOT affected
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Known finding",
            requirement_ref=None,
            spec_name="test_spec",
            task_group="1",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        unknown_id = str(uuid.uuid4())
        dismiss_finding_by_id(knowledge_conn, unknown_id, "reason")

        # The known finding should remain active
        active = query_active_findings(knowledge_conn, "test_spec")
        assert any(f.id == finding.id for f in active)

    def test_already_superseded_finding_treated_as_not_found(self, knowledge_conn) -> None:
        """A finding that is already superseded cannot be dismissed again."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Already superseded finding",
            requirement_ref=None,
            spec_name="test_spec",
            task_group="1",
            session_id="test_spec:1:1",
        )
        # Insert with superseded_by already set
        knowledge_conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, "
            " spec_name, task_group, session_id, superseded_by, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, 'some-session', CURRENT_TIMESTAMP)",
            [
                finding.id,
                finding.severity,
                finding.description,
                finding.requirement_ref,
                finding.spec_name,
                finding.task_group,
                finding.session_id,
            ],
        )

        result = dismiss_finding_by_id(knowledge_conn, finding.id, "redundant dismissal")
        assert result is None
