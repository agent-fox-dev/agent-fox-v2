"""Tests for oracle drift context rendering.

Test Spec: TS-32-10, TS-32-E6
Requirements: 32-REQ-8.1, 32-REQ-8.2, 32-REQ-8.E1
"""

from __future__ import annotations

import uuid

import duckdb
import pytest


def _create_drift_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create drift_findings table for testing."""
    from tests.unit.knowledge.conftest import create_schema

    create_schema(conn)
    # The drift_findings table will be created by migration;
    # create it directly for tests.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_findings (
            id UUID PRIMARY KEY,
            severity VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            spec_ref VARCHAR,
            artifact_ref VARCHAR,
            spec_name VARCHAR NOT NULL,
            task_group VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            superseded_by UUID,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


@pytest.fixture
def drift_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with drift_findings table."""
    conn = duckdb.connect(":memory:")
    _create_drift_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


def _make_drift_finding(
    severity: str = "major",
    description: str = "Test drift",
    spec_name: str = "test_spec",
    session_id: str = "s1",
    spec_ref: str | None = None,
    artifact_ref: str | None = None,
):
    """Create a DriftFinding for testing."""
    from agent_fox.knowledge.review_store import DriftFinding

    return DriftFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        spec_ref=spec_ref,
        artifact_ref=artifact_ref,
        spec_name=spec_name,
        task_group="0",
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# TS-32-10: Render Drift Context
# Requirements: 32-REQ-8.1, 32-REQ-8.2
# ---------------------------------------------------------------------------


class TestRenderDriftContext:
    """Verify drift findings are rendered as grouped markdown."""

    def test_render_drift_context(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-32-10: Rendered output has header, severity groups, descriptions."""
        from agent_fox.knowledge.review_store import insert_drift_findings
        from agent_fox.session.prompt import render_drift_context

        critical = _make_drift_finding(
            severity="critical",
            description="File deleted",
        )
        minor = _make_drift_finding(
            severity="minor",
            description="Param renamed",
        )
        insert_drift_findings(drift_conn, [critical, minor])

        result = render_drift_context(drift_conn, "test_spec")
        assert result is not None
        assert "## Oracle Drift Report" in result
        assert "### Critical Findings" in result
        assert "File deleted" in result
        assert "Param renamed" in result

    def test_render_includes_all_severities(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """All severity groups appear in the rendered output."""
        from agent_fox.knowledge.review_store import insert_drift_findings
        from agent_fox.session.prompt import render_drift_context

        findings = [
            _make_drift_finding(severity="critical", description="crit1"),
            _make_drift_finding(severity="major", description="maj1"),
            _make_drift_finding(severity="minor", description="min1"),
            _make_drift_finding(severity="observation", description="obs1"),
        ]
        insert_drift_findings(drift_conn, findings)

        result = render_drift_context(drift_conn, "test_spec")
        assert result is not None
        assert "### Critical Findings" in result
        assert "### Major Findings" in result
        assert "### Minor Findings" in result
        assert "### Observations" in result


# ---------------------------------------------------------------------------
# TS-32-E6: No Drift Findings - Context Omitted
# Requirement: 32-REQ-8.E1
# ---------------------------------------------------------------------------


class TestNoDriftFindings:
    """render_drift_context returns None when no findings exist."""

    def test_no_findings(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-32-E6: No findings -> None returned."""
        from agent_fox.session.prompt import render_drift_context

        result = render_drift_context(drift_conn, "spec_with_no_findings")
        assert result is None
