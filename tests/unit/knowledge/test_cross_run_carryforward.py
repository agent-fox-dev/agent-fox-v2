"""Unit tests for cross-run finding carry-forward.

Tests verify that unresolved findings from prior runs are surfaced as
[PRIOR-RUN] items, capped at a configurable limit, and NOT tracked in
finding_injections. Edge cases cover empty runs, all-superseded findings,
and missing tables.

Test Spec: TS-120-11, TS-120-12, TS-120-13, TS-120-E7, TS-120-E8
Requirements: 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.3, 120-REQ-4.4,
              120-REQ-4.5, 120-REQ-4.E1, 120-REQ-4.E2, 120-REQ-4.E3
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
from agent_fox.knowledge.migrations import run_migrations


def _query_prior_run_findings(*args, **kwargs):
    """Deferred import of query_prior_run_findings (not yet implemented)."""
    from agent_fox.knowledge.review_store import query_prior_run_findings

    return query_prior_run_findings(*args, **kwargs)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full migrated schema."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def provider_db(provider_conn: duckdb.DuckDBPyConnection) -> KnowledgeDB:
    """KnowledgeDB wrapper around provider_conn."""
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = provider_conn
    return db


def _make_provider(
    provider_db: KnowledgeDB,
    run_id: str | None = None,
) -> FoxKnowledgeProvider:
    """Construct FoxKnowledgeProvider, optionally setting run_id."""
    provider = FoxKnowledgeProvider(provider_db, KnowledgeProviderConfig())
    if run_id is not None:
        provider.set_run_id(run_id)
    return provider


def _create_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    plan_hash: str = "hash1",
) -> None:
    """Create a run record in the runs table."""
    from agent_fox.engine.state import create_run

    create_run(conn, run_id, plan_hash)


def _complete_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str = "stalled",
) -> None:
    """Complete a run record."""
    from agent_fox.engine.state import complete_run

    complete_run(conn, run_id, status)


def _insert_finding_direct(
    conn: duckdb.DuckDBPyConnection,
    *,
    finding_id: str | None = None,
    spec_name: str = "test_spec",
    task_group: str = "1",
    severity: str = "critical",
    description: str = "Test issue",
    session_id: str = "prior_session",
    superseded_by: str | None = None,
) -> str:
    """Insert a finding directly into review_findings (bypasses supersession)."""
    fid = finding_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO review_findings "
        "(id, severity, description, requirement_ref, spec_name, task_group, "
        "session_id, category, created_at, superseded_by) "
        "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, CURRENT_TIMESTAMP, ?)",
        [fid, severity, description, spec_name, task_group, session_id, superseded_by],
    )
    return fid


def _insert_verdict_direct(
    conn: duckdb.DuckDBPyConnection,
    *,
    verdict_id: str | None = None,
    requirement_id: str = "REQ-1.1",
    verdict: str = "FAIL",
    evidence: str | None = None,
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "prior_session",
    superseded_by: str | None = None,
) -> str:
    """Insert a verdict directly into verification_results."""
    vid = verdict_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO verification_results "
        "(id, requirement_id, verdict, evidence, spec_name, task_group, "
        "session_id, created_at, superseded_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        [vid, requirement_id, verdict, evidence, spec_name, task_group, session_id, superseded_by],
    )
    return vid


# ---------------------------------------------------------------------------
# TS-120-11: Prior-run findings surfaced (120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.5)
# ---------------------------------------------------------------------------


class TestPriorRunFindingsSurfaced:
    """Verify active findings from a prior run appear as [PRIOR-RUN] items."""

    def test_prior_run_finding_appears(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        # Create and complete a prior run
        _create_run(provider_conn, "prior_run_id")
        _complete_run(provider_conn, "prior_run_id", "stalled")

        # Insert a finding created during the prior run
        _insert_finding_direct(
            provider_conn,
            spec_name="test_spec",
            task_group="1",
            severity="critical",
            description="Unresolved from prior run",
            session_id="prior_session",
        )

        # Create current run
        _create_run(provider_conn, "current_run_id")

        provider = _make_provider(provider_db, run_id="current_run_id")
        result = provider.retrieve("test_spec", "test", task_group="1")
        assert any(
            "[PRIOR-RUN]" in item and "Unresolved from prior run" in item
            for item in result
        )

    def test_prior_run_fail_verdicts_appear(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """120-REQ-4.5: Prior-run FAIL verdicts included in context."""
        # Create and complete a prior run
        _create_run(provider_conn, "prior_run_id")
        _complete_run(provider_conn, "prior_run_id", "stalled")

        # Insert a FAIL verdict during the prior run
        _insert_verdict_direct(
            provider_conn,
            requirement_id="REQ-5.E3",
            verdict="FAIL",
            evidence="Assertion failed",
            spec_name="test_spec",
            session_id="prior_session",
        )

        # Create current run
        _create_run(provider_conn, "current_run_id")

        provider = _make_provider(provider_db, run_id="current_run_id")
        result = provider.retrieve("test_spec", "test", task_group="1")
        assert any(
            "[PRIOR-RUN]" in item and "REQ-5.E3" in item
            for item in result
        )


# ---------------------------------------------------------------------------
# TS-120-12: Prior-run findings capped at limit (120-REQ-4.3)
# ---------------------------------------------------------------------------


class TestPriorRunFindingsCapped:
    """Verify prior-run findings are capped at max_items."""

    def test_capped_at_max_items(
        self,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        # Create and complete a prior run
        _create_run(provider_conn, "prior_run_id")
        _complete_run(provider_conn, "prior_run_id", "stalled")

        # Insert 10 findings
        for i in range(10):
            sev = "critical" if i < 3 else "major"
            _insert_finding_direct(
                provider_conn,
                spec_name="test_spec",
                severity=sev,
                description=f"Finding {i}",
                session_id="prior_session",
            )

        # Create current run
        _create_run(provider_conn, "current_run_id")

        results = _query_prior_run_findings(
            provider_conn, "test_spec", "current_run_id", max_items=5
        )
        assert len(results) == 5
        # All critical findings should come first
        assert all(r.severity == "critical" for r in results[:3])


# ---------------------------------------------------------------------------
# TS-120-13: Prior-run findings not tracked in finding_injections (120-REQ-4.4)
# ---------------------------------------------------------------------------


class TestPriorRunFindingsNotTracked:
    """Verify prior-run items are not recorded in finding_injections."""

    def test_no_injection_tracking(
        self,
        provider_db: KnowledgeDB,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        # Create and complete a prior run
        _create_run(provider_conn, "prior_run_id")
        _complete_run(provider_conn, "prior_run_id", "stalled")

        prior_finding_id = _insert_finding_direct(
            provider_conn,
            spec_name="test_spec",
            severity="critical",
            description="Prior issue",
            session_id="prior_session",
        )

        # Create current run
        _create_run(provider_conn, "current_run_id")

        provider = _make_provider(provider_db, run_id="current_run_id")
        provider.retrieve("test_spec", "test", task_group="1", session_id="sess-1")

        rows = provider_conn.execute(
            "SELECT * FROM finding_injections WHERE finding_id = ?", [prior_finding_id]
        ).fetchall()
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# TS-120-E7: No prior runs in database (120-REQ-4.E1, 120-REQ-4.E3)
# ---------------------------------------------------------------------------


class TestNoPriorRuns:
    """Empty prior-run context when no prior runs exist."""

    def test_empty_prior_run_findings(
        self,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        # Only current run exists
        _create_run(provider_conn, "current_run")

        result = _query_prior_run_findings(
            provider_conn, "test_spec", "current_run", max_items=5
        )
        assert result == []


# ---------------------------------------------------------------------------
# TS-120-E8: All prior findings superseded (120-REQ-4.E2)
# ---------------------------------------------------------------------------


class TestAllPriorSuperseded:
    """Empty prior-run context when all findings are superseded."""

    def test_superseded_returns_empty(
        self,
        provider_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        # Create and complete a prior run
        _create_run(provider_conn, "prior_run_id")
        _complete_run(provider_conn, "prior_run_id", "stalled")

        # Insert a finding and supersede it
        _insert_finding_direct(
            provider_conn,
            spec_name="test_spec",
            severity="critical",
            description="Already fixed",
            session_id="prior_session",
            superseded_by="resolved",
        )

        # Create current run
        _create_run(provider_conn, "current_run_id")

        result = _query_prior_run_findings(
            provider_conn, "test_spec", "current_run_id", max_items=5
        )
        assert result == []


# ---------------------------------------------------------------------------
# TS-120-E9: Missing tables in fresh database (120-REQ-4.E3)
# ---------------------------------------------------------------------------


class TestMissingTablesGraceful:
    """Graceful empty return when review_findings or verification_results table does not exist.

    This exercises a completely different code path from an empty table: a
    missing table raises duckdb.CatalogException, which must be caught and
    handled by returning an empty list.
    """

    def test_missing_review_findings_table(self) -> None:
        """query_prior_run_findings returns [] when review_findings table is absent."""
        conn = duckdb.connect(":memory:")
        try:
            # Create only the runs table (no review_findings)
            conn.execute(
                "CREATE TABLE runs ("
                "  id VARCHAR PRIMARY KEY,"
                "  plan_content_hash VARCHAR NOT NULL,"
                "  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                "  completed_at TIMESTAMP,"
                "  status VARCHAR NOT NULL DEFAULT 'running',"
                "  total_input_tokens BIGINT NOT NULL DEFAULT 0,"
                "  total_output_tokens BIGINT NOT NULL DEFAULT 0,"
                "  total_cost DOUBLE NOT NULL DEFAULT 0.0,"
                "  total_sessions INTEGER NOT NULL DEFAULT 0"
                ")"
            )
            conn.execute(
                "INSERT INTO runs (id, plan_content_hash) VALUES (?, ?)",
                ["current_run", "hash1"],
            )
            result = _query_prior_run_findings(conn, "test_spec", "current_run", max_items=5)
            assert result == []
        finally:
            conn.close()
