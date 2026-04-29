"""Unit tests for all-archetype summary generation and retrieval.

Tests verify that _generate_archetype_summary() produces correct summaries
for reviewer and verifier archetypes, and that query_same_spec_summaries()
returns summaries from all archetypes (not just coder).

Test Spec: TS-120-8, TS-120-9, TS-120-10, TS-120-E5, TS-120-E6
Requirements: 120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.3, 120-REQ-3.4,
              120-REQ-3.E1, 120-REQ-3.E2
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import ReviewFinding, VerificationResult
from agent_fox.knowledge.summary_store import (
    SummaryRecord,
    insert_summary,
    query_same_spec_summaries,
)


def _generate_archetype_summary(*args, **kwargs):
    """Deferred import of generate_archetype_summary (not yet implemented)."""
    from agent_fox.knowledge.fox_provider import generate_archetype_summary

    return generate_archetype_summary(*args, **kwargs)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def summary_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full migrated schema."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def summary_db(summary_conn: duckdb.DuckDBPyConnection) -> KnowledgeDB:
    """KnowledgeDB wrapper around summary_conn."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = summary_conn
    return db


def _make_summary(
    *,
    spec_name: str = "test_spec",
    task_group: str = "1",
    run_id: str = "run1",
    archetype: str = "coder",
    attempt: int = 1,
    summary: str = "Did work",
) -> SummaryRecord:
    return SummaryRecord(
        id=str(uuid.uuid4()),
        node_id=f"{spec_name}:{task_group}",
        run_id=run_id,
        spec_name=spec_name,
        task_group=task_group,
        archetype=archetype,
        attempt=attempt,
        summary=summary,
        created_at="2026-04-29T10:00:00",
    )


def _make_finding(
    *,
    severity: str = "critical",
    description: str = "Issue A",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name="test_spec",
        task_group="1",
        session_id="s1",
    )


def _make_verdict(
    *,
    requirement_id: str = "REQ-1.1",
    verdict: str = "PASS",
    evidence: str | None = None,
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence=evidence,
        spec_name="test_spec",
        task_group="1",
        session_id="s1",
    )


# ---------------------------------------------------------------------------
# TS-120-8: Reviewer summary generated and stored (120-REQ-3.1)
# ---------------------------------------------------------------------------


class TestReviewerSummaryGenerated:
    """Verify reviewer sessions produce a summary with finding counts."""

    def test_reviewer_summary_contains_counts(self) -> None:
        findings = [
            _make_finding(severity="critical", description="Issue A"),
            _make_finding(severity="critical", description="Issue B"),
            _make_finding(severity="major", description="Issue C"),
            _make_finding(severity="major", description="Issue D"),
            _make_finding(severity="major", description="Issue E"),
        ]
        summary = _generate_archetype_summary("reviewer", findings=findings)
        assert "2 critical" in summary.lower()
        assert "3 major" in summary.lower()
        assert "Issue A" in summary  # top finding included


# ---------------------------------------------------------------------------
# TS-120-9: Verifier summary generated and stored (120-REQ-3.2)
# ---------------------------------------------------------------------------


class TestVerifierSummaryGenerated:
    """Verify verifier sessions produce a summary with pass/fail counts."""

    def test_verifier_summary_contains_counts(self) -> None:
        verdicts = [
            _make_verdict(requirement_id=f"REQ-{i}.1", verdict="PASS")
            for i in range(1, 11)
        ] + [
            _make_verdict(requirement_id="REQ-5.E3", verdict="FAIL"),
            _make_verdict(requirement_id="REQ-8.E1", verdict="FAIL"),
        ]
        summary = _generate_archetype_summary("verifier", verdicts=verdicts)
        assert "10 pass" in summary.lower()
        assert "2 fail" in summary.lower()
        assert "REQ-5.E3" in summary
        assert "REQ-8.E1" in summary


# ---------------------------------------------------------------------------
# TS-120-10: Same-spec summaries include all archetypes (120-REQ-3.3, 120-REQ-3.4)
# ---------------------------------------------------------------------------


class TestSameSpecIncludesAllArchetypes:
    """Verify query returns reviewer and verifier summaries too."""

    def test_all_archetypes_returned(
        self,
        summary_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        for arch in ["coder", "reviewer", "verifier"]:
            insert_summary(
                summary_conn,
                _make_summary(
                    spec_name="test_spec",
                    task_group="1",
                    run_id="run1",
                    archetype=arch,
                    summary=f"{arch} did X",
                ),
            )
        records = query_same_spec_summaries(summary_conn, "test_spec", "3", "run1")
        assert len(records) == 3
        archetypes = {r.archetype for r in records}
        assert archetypes == {"coder", "reviewer", "verifier"}

    def test_context_prefix_includes_archetype(
        self,
        summary_conn: duckdb.DuckDBPyConnection,
        summary_db: KnowledgeDB,
    ) -> None:
        """120-REQ-3.4: [CONTEXT] prefix includes archetype so downstream sessions
        can distinguish coder summaries from reviewer/verifier summaries."""
        for arch in ["coder", "reviewer", "verifier"]:
            insert_summary(
                summary_conn,
                _make_summary(
                    spec_name="test_spec",
                    task_group="1",
                    run_id="run1",
                    archetype=arch,
                    summary=f"{arch} did X",
                ),
            )
        provider = FoxKnowledgeProvider(summary_db, KnowledgeProviderConfig())
        provider.set_run_id("run1")
        result = provider.retrieve("test_spec", "test", task_group="3")
        context_items = [i for i in result if "[CONTEXT]" in i]
        assert len(context_items) == 3
        # Each item should include its archetype in the prefix
        for arch in ["coder", "reviewer", "verifier"]:
            assert any(arch in item for item in context_items), (
                f"Archetype '{arch}' not found in any [CONTEXT] item: {context_items}"
            )


# ---------------------------------------------------------------------------
# TS-120-E5: Reviewer with zero findings (120-REQ-3.E1)
# ---------------------------------------------------------------------------


class TestReviewerZeroFindings:
    """Reviewer summary generated even with no findings."""

    def test_non_empty_summary_no_findings(self) -> None:
        summary = _generate_archetype_summary("reviewer", findings=[])
        assert len(summary) > 0
        assert "no findings" in summary.lower() or "0 findings" in summary.lower()


# ---------------------------------------------------------------------------
# TS-120-E6: Verifier with zero verdicts (120-REQ-3.E2)
# ---------------------------------------------------------------------------


class TestVerifierZeroVerdicts:
    """Verifier summary generated even with no verdicts."""

    def test_non_empty_summary_no_verdicts(self) -> None:
        summary = _generate_archetype_summary("verifier", verdicts=[])
        assert len(summary) > 0
