"""Unit tests for lookup_finding_by_id in reporting.findings.

Validates retrieval of a FindingRow by ID across review_findings,
drift_findings, and verification_results tables.

Requirements: 592-AC-5
"""

from __future__ import annotations

import uuid

from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    insert_drift_findings,
    insert_findings,
    insert_verdicts,
)
from agent_fox.reporting.findings import lookup_finding_by_id


class TestLookupReviewFinding:
    """lookup_finding_by_id finds review_findings rows with archetype='skeptic'."""

    def test_finds_review_finding_by_id(self, knowledge_conn) -> None:
        """Returns a FindingRow with archetype='skeptic' for a review finding."""
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Missing error handling",
            requirement_ref="01-REQ-1.1",
            spec_name="test_spec",
            task_group="1",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        result = lookup_finding_by_id(knowledge_conn, finding.id)

        assert result is not None
        assert result.id == finding.id
        assert result.archetype == "skeptic"
        assert result.severity == "critical"
        assert result.description == "Missing error handling"
        assert result.spec_name == "test_spec"

    def test_finds_superseded_review_finding(self, knowledge_conn) -> None:
        """lookup_finding_by_id returns a row even if it is superseded."""
        finding_id = str(uuid.uuid4())
        knowledge_conn.execute(
            "INSERT INTO review_findings "
            "(id, severity, description, requirement_ref, "
            " spec_name, task_group, session_id, superseded_by, created_at) "
            "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, 'some-session', CURRENT_TIMESTAMP)",
            [finding_id, "major", "Superseded finding", None, "test_spec", "1", "test_spec:1:1"],
        )

        result = lookup_finding_by_id(knowledge_conn, finding_id)

        assert result is not None
        assert result.id == finding_id
        assert result.archetype == "skeptic"


class TestLookupDriftFinding:
    """lookup_finding_by_id finds drift_findings rows with archetype='oracle'."""

    def test_finds_drift_finding_by_id(self, knowledge_conn) -> None:
        """Returns a FindingRow with archetype='oracle' for a drift finding."""
        finding = DriftFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Spec-code mismatch on auth flow",
            spec_ref="84-REQ-2.1",
            artifact_ref="agent_fox/cli/findings.py",
            spec_name="84_spec",
            task_group="2",
            session_id="84_spec:2:1",
        )
        insert_drift_findings(knowledge_conn, [finding])

        result = lookup_finding_by_id(knowledge_conn, finding.id)

        assert result is not None
        assert result.id == finding.id
        assert result.archetype == "oracle"
        assert result.description == "Spec-code mismatch on auth flow"


class TestLookupVerificationResult:
    """lookup_finding_by_id finds verification_results rows with archetype='verifier'."""

    def test_finds_verification_result_by_id(self, knowledge_conn) -> None:
        """Returns a FindingRow with archetype='verifier' for a verification result."""
        verdict = VerificationResult(
            id=str(uuid.uuid4()),
            requirement_id="84-REQ-3.1",
            verdict="FAIL",
            evidence="Test not found",
            spec_name="84_spec",
            task_group="3",
            session_id="84_spec:3:1",
        )
        insert_verdicts(knowledge_conn, [verdict])

        result = lookup_finding_by_id(knowledge_conn, verdict.id)

        assert result is not None
        assert result.id == verdict.id
        assert result.archetype == "verifier"
        assert result.severity == "major"  # FAIL maps to major
        assert "84-REQ-3.1" in result.description
        assert "FAIL" in result.description


class TestLookupUnknownId:
    """lookup_finding_by_id returns None when the ID is not found in any table."""

    def test_unknown_id_returns_none(self, knowledge_conn) -> None:
        """Returns None for an ID not present in any finding table."""
        result = lookup_finding_by_id(knowledge_conn, str(uuid.uuid4()))
        assert result is None

    def test_none_conn_returns_none(self) -> None:
        """Returns None when conn is None."""
        result = lookup_finding_by_id(None, str(uuid.uuid4()))  # type: ignore[arg-type]
        assert result is None
