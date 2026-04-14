"""Integration tests for the review archetype persistence pipeline.

Tests end-to-end finding/verdict/drift persistence with supersession,
review-only graph construction, and summary output formatting using
real in-memory DuckDB instances.

Test Spec: TS-53-4, TS-53-10, TS-53-13
Requirements: 53-REQ-1.2, 53-REQ-2.2, 53-REQ-3.2, 53-REQ-6.1, 53-REQ-6.5
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

# NOTE: build_review_only_graph does not yet exist in graph.injection.
# All tests in this file will fail with ImportError until Task Group 4
# implements the function.
from agent_fox.graph.injection import build_review_only_graph
from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    insert_drift_findings,
    insert_findings,
    insert_verdicts,
    query_active_findings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    spec_name: str = "03_api",
    task_group: str = "2",
    severity: str = "major",
    description: str = "Test finding",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id="test_session",
    )


def _make_verdict(
    spec_name: str = "03_api",
    task_group: str = "2",
    verdict: str = "PASS",
    requirement_id: str = "03-REQ-1.1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence="test evidence",
        spec_name=spec_name,
        task_group=task_group,
        session_id="test_session",
    )


def _make_drift(
    spec_name: str = "03_api",
    task_group: str = "2",
    severity: str = "major",
) -> DriftFinding:
    return DriftFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description="Drift finding",
        spec_ref=None,
        artifact_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id="test_session",
    )


# ---------------------------------------------------------------------------
# TS-53-4: Supersession on re-insert
# ---------------------------------------------------------------------------


class TestFindingSupersession:
    """TS-53-4: Inserting new findings supersedes prior active findings."""

    def test_prior_finding_superseded(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-53-4: Old finding has superseded_by set after new insert."""
        old_finding = _make_finding()
        insert_findings(knowledge_conn, [old_finding])

        new_finding = _make_finding()
        insert_findings(knowledge_conn, [new_finding])

        old_row = knowledge_conn.execute(
            "SELECT superseded_by::VARCHAR FROM review_findings WHERE id = ?::UUID",
            [old_finding.id],
        ).fetchone()
        assert old_row is not None
        assert old_row[0] is not None, "Prior finding should have superseded_by set"

    def test_new_finding_active(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-53-4: New finding has superseded_by = NULL (still active)."""
        old_finding = _make_finding()
        insert_findings(knowledge_conn, [old_finding])

        new_finding = _make_finding()
        insert_findings(knowledge_conn, [new_finding])

        new_row = knowledge_conn.execute(
            "SELECT superseded_by FROM review_findings WHERE id = ?::UUID",
            [new_finding.id],
        ).fetchone()
        assert new_row is not None
        assert new_row[0] is None, "New finding should have superseded_by = NULL"

    def test_only_latest_batch_active(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-53-4: After 3 insert rounds, only the last batch is active."""
        for i in range(3):
            batch = [_make_finding(description=f"Round {i} finding")]
            insert_findings(knowledge_conn, batch)

        active = query_active_findings(knowledge_conn, "03_api")
        assert len(active) == 1
        assert active[0].description == "Round 2 finding"

    def test_verdict_supersession(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-53-4: Verdicts are superseded on re-insert for same spec+task_group."""
        old_verdict = _make_verdict(verdict="FAIL")
        insert_verdicts(knowledge_conn, [old_verdict])

        new_verdict = _make_verdict(verdict="PASS")
        insert_verdicts(knowledge_conn, [new_verdict])

        old_row = knowledge_conn.execute(
            "SELECT superseded_by::VARCHAR FROM verification_results WHERE id = ?::UUID",
            [old_verdict.id],
        ).fetchone()
        assert old_row is not None
        assert old_row[0] is not None, "Prior verdict should be superseded"

    def test_drift_finding_supersession(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """TS-53-4: Drift findings are superseded on re-insert for same spec+task."""
        old_drift = _make_drift()
        insert_drift_findings(knowledge_conn, [old_drift])

        new_drift = _make_drift()
        insert_drift_findings(knowledge_conn, [new_drift])

        old_row = knowledge_conn.execute(
            "SELECT superseded_by::VARCHAR FROM drift_findings WHERE id = ?::UUID",
            [old_drift.id],
        ).fetchone()
        assert old_row is not None
        assert old_row[0] is not None, "Prior drift finding should be superseded"


# ---------------------------------------------------------------------------
# TS-53-10: Review-only graph has no coder nodes
# ---------------------------------------------------------------------------


class TestReviewOnlyGraphNoCoder:
    """TS-53-10: build_review_only_graph excludes coder nodes."""

    def test_no_coder_nodes_in_graph(self, tmp_path: Path) -> None:
        """TS-53-10: Review-only graph contains no coder archetype nodes."""
        # Create spec with source files and requirements.md
        spec_dir = tmp_path / ".specs" / "03_api"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "sample.py").write_text("# code\n")

        graph = build_review_only_graph(tmp_path / ".specs", archetypes_config=None)

        node_archetypes = {n.archetype for n in graph.nodes.values()}
        assert "coder" not in node_archetypes

    def test_review_archetypes_present(self, tmp_path: Path) -> None:
        """TS-53-10: Reviewer and Verifier nodes are present."""
        spec_dir = tmp_path / ".specs" / "03_api"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "sample.py").write_text("# code\n")

        graph = build_review_only_graph(tmp_path / ".specs", archetypes_config=None)

        node_archetypes = {n.archetype for n in graph.nodes.values()}
        assert "reviewer" in node_archetypes
        assert "verifier" in node_archetypes


# ---------------------------------------------------------------------------
# TS-53-13: Review-only summary output
# ---------------------------------------------------------------------------


class TestReviewOnlySummaryOutput:
    """TS-53-13: Review-only run prints a summary with counts by category."""

    def test_summary_contains_finding_counts(
        self, knowledge_conn: duckdb.DuckDBPyConnection, capsys: pytest.CaptureFixture
    ) -> None:
        """TS-53-13: Summary includes finding counts by severity."""
        from agent_fox.graph.injection import print_review_only_summary

        # Insert 2 critical findings
        for _ in range(2):
            insert_findings(knowledge_conn, [_make_finding(severity="critical")])

        # Insert 1 PASS verdict and 1 FAIL verdict
        insert_verdicts(knowledge_conn, [_make_verdict(verdict="PASS", requirement_id="03-REQ-1.1")])
        insert_verdicts(knowledge_conn, [_make_verdict(verdict="FAIL", requirement_id="03-REQ-2.1")])

        # Insert 1 major drift finding
        insert_drift_findings(knowledge_conn, [_make_drift(severity="major")])

        print_review_only_summary(knowledge_conn)
        output = capsys.readouterr().out

        assert "critical" in output.lower()
        assert "PASS" in output or "pass" in output.lower()
        assert "FAIL" in output or "fail" in output.lower()
        assert "major" in output.lower()
