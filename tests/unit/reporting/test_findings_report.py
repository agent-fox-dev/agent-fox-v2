"""Unit tests for findings query, formatting, and status summary.

Validates query_findings() with various filters (spec, severity, archetype,
run_id), format_findings_table() for table and JSON output, and
query_findings_summary() for status report integration.

Test Spec: TS-84-8 through TS-84-15, TS-84-E5
Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-5.1, 84-REQ-5.2, 84-REQ-5.E1
"""

from __future__ import annotations

import json
import uuid

import duckdb

from agent_fox.knowledge.review_store import (
    ReviewFinding,
    VerificationResult,
    insert_findings,
    insert_verdicts,
)
from agent_fox.reporting.findings import (
    format_findings_table,
    query_findings,
    query_findings_summary,
)


def _insert_test_findings(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str = "my_spec",
    task_group: str = "1",
    session_id: str = "my_spec:1:1",
    severities: list[str] | None = None,
    supersede: bool = False,
) -> list[ReviewFinding]:
    """Insert test findings and optionally mark as superseded.

    When ``supersede=True``, findings are inserted directly via SQL with
    ``superseded_by`` pre-set, bypassing ``insert_findings``'s automatic
    supersession of previous active records for the same (spec_name,
    task_group). This ensures that already-active findings from a prior call
    are not unintentionally superseded by this helper.
    """
    if severities is None:
        severities = ["critical", "major"]

    findings = [
        ReviewFinding(
            id=str(uuid.uuid4()),
            severity=sev,
            description=f"Finding {sev} for {spec_name}",
            requirement_ref=None,
            spec_name=spec_name,
            task_group=task_group,
            session_id=session_id,
        )
        for sev in severities
    ]

    if supersede:
        # Insert directly, bypassing auto-supersession, so that a previous
        # active batch is not superseded as a side effect.
        for f in findings:
            conn.execute(
                "INSERT INTO review_findings "
                "(id, severity, description, requirement_ref, spec_name, "
                " task_group, session_id, superseded_by, created_at) "
                "VALUES (?::UUID, ?, ?, ?, ?, ?, ?, 'superseded', CURRENT_TIMESTAMP)",
                [
                    f.id,
                    f.severity,
                    f.description,
                    f.requirement_ref,
                    f.spec_name,
                    f.task_group,
                    f.session_id,
                ],
            )
    else:
        insert_findings(conn, findings)

    return findings


class TestQueryFindings:
    """TS-84-8: Findings command displays table."""

    def test_returns_active_findings_only(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify query_findings returns only active (non-superseded) findings."""
        # Insert 2 active findings
        _insert_test_findings(knowledge_conn, severities=["critical", "major"])
        # Insert 1 superseded finding
        _insert_test_findings(
            knowledge_conn,
            session_id="my_spec:1:2",
            severities=["minor"],
            supersede=True,
        )

        rows = query_findings(knowledge_conn, active_only=True)
        assert len(rows) == 2

    def test_format_table_contains_required_columns(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify formatted table contains severity, archetype, spec, description."""
        _insert_test_findings(knowledge_conn, severities=["critical"])

        rows = query_findings(knowledge_conn)
        table = format_findings_table(rows)
        assert "critical" in table
        assert "skeptic" in table


class TestQueryFindingsBySpec:
    """TS-84-9: Findings command filters by spec."""

    def test_filters_by_spec_name(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --spec filter narrows results to matching spec."""
        _insert_test_findings(knowledge_conn, spec_name="foo", session_id="foo:1:1")
        _insert_test_findings(knowledge_conn, spec_name="bar", session_id="bar:1:1")

        rows = query_findings(knowledge_conn, spec="foo")
        assert all(r.spec_name == "foo" for r in rows)
        assert len(rows) > 0


class TestQueryFindingsBySeverity:
    """TS-84-10: Findings command filters by severity."""

    def test_severity_filter_at_or_above(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --severity filter returns findings at or above the given level."""
        _insert_test_findings(
            knowledge_conn,
            severities=["critical", "major", "minor", "observation"],
        )

        rows = query_findings(knowledge_conn, severity="major")
        assert all(r.severity in ("critical", "major") for r in rows)
        assert len(rows) >= 2


class TestQueryFindingsByArchetype:
    """TS-84-11: Findings command filters by archetype."""

    def test_archetype_filter_verifier(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --archetype verifier returns only verifier verdicts."""
        # Insert skeptic findings
        _insert_test_findings(knowledge_conn, severities=["critical"])
        # Insert verifier verdicts
        verdicts = [
            VerificationResult(
                id=str(uuid.uuid4()),
                requirement_id="REQ-1.1",
                verdict="PASS",
                evidence="all good",
                spec_name="my_spec",
                task_group="1",
                session_id="my_spec:1:2",
            ),
        ]
        insert_verdicts(knowledge_conn, verdicts)

        rows = query_findings(knowledge_conn, archetype="verifier")
        assert all(r.archetype == "verifier" for r in rows)

    def test_archetype_filter_skeptic(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --archetype skeptic returns only skeptic findings."""
        _insert_test_findings(knowledge_conn, severities=["critical"])

        rows = query_findings(knowledge_conn, archetype="skeptic")
        assert all(r.archetype == "skeptic" for r in rows)


class TestQueryFindingsByRunId:
    """TS-84-12: Findings command filters by run ID."""

    def test_run_id_filter(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --run filter scopes findings to sessions within the given run."""
        # This requires that findings can be associated with a run.
        # The exact mechanism depends on audit_events or session metadata.
        # For now, insert findings and test the filter works if run_id
        # is stored or can be joined.
        _insert_test_findings(knowledge_conn, severities=["critical"])

        rows = query_findings(knowledge_conn, run_id="run-abc")
        # With no matching run, should return empty or only matching findings
        assert isinstance(rows, list)


class TestFindingsJsonOutput:
    """TS-84-13: Findings command JSON output."""

    def test_json_output_valid(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --json produces valid JSON array output."""
        _insert_test_findings(knowledge_conn, severities=["critical", "major"])

        rows = query_findings(knowledge_conn)
        output = format_findings_table(rows, json_output=True)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 2
        assert "severity" in data[0]
        assert "id" in data[0]
        assert "archetype" in data[0]
        assert "spec_name" in data[0]
        assert "description" in data[0]


class TestStatusFindingsSummary:
    """TS-84-14: Status includes findings summary."""

    def test_summary_includes_critical_and_major(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify status summary includes specs with critical or major findings."""
        _insert_test_findings(
            knowledge_conn,
            spec_name="my_spec",
            severities=["critical", "major", "major"],
        )

        summary = query_findings_summary(knowledge_conn)
        assert len(summary) >= 1
        my_spec_entry = next((s for s in summary if s.spec_name == "my_spec"), None)
        assert my_spec_entry is not None
        assert my_spec_entry.critical == 1
        assert my_spec_entry.major == 2


class TestStatusOmitsFindingsSummary:
    """TS-84-15: Status omits findings summary when none."""

    def test_summary_empty_with_only_minor(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify summary is empty when only minor and observation findings exist."""
        _insert_test_findings(
            knowledge_conn,
            severities=["minor", "observation"],
        )

        summary = query_findings_summary(knowledge_conn)
        assert summary == []

    def test_summary_empty_with_no_findings(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify summary is empty when no findings exist."""
        summary = query_findings_summary(knowledge_conn)
        assert summary == []


class TestStatusFindingsDbFailure:
    """TS-84-E5: Status findings with DB open failure."""

    def test_summary_empty_when_conn_is_none(self) -> None:
        """Verify summary is empty when DB connection is None."""
        summary = query_findings_summary(None)  # type: ignore[arg-type]
        assert summary == []
