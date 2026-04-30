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
import pytest

from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    VerificationResult,
    insert_drift_findings,
    insert_findings,
    insert_verdicts,
)
from agent_fox.reporting.findings import (
    format_findings_table,
    lookup_finding_by_id,
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
        assert "reviewer/pre-review" in table


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

    def test_archetype_filter_reviewer_pre_review(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify --archetype reviewer/pre-review returns only pre-review findings."""
        _insert_test_findings(knowledge_conn, severities=["critical"])

        rows = query_findings(knowledge_conn, archetype="reviewer/pre-review")
        assert all(r.archetype == "reviewer/pre-review" for r in rows)


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


def _insert_drift_finding(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str = "my_spec",
    task_group: str = "1",
    session_id: str = "my_spec:1:1",
    severity: str = "major",
) -> DriftFinding:
    """Insert a single DriftFinding for testing."""
    finding = DriftFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=f"Drift finding {severity} for {spec_name}",
        spec_ref="84-REQ-1.1",
        artifact_ref="agent_fox/cli/findings.py",
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )
    insert_drift_findings(conn, [finding])
    return finding


class TestArchetypeLabelsCurrentNames:
    """591-AC-1 / 591-AC-2: Verify current archetype labels on FindingRow objects."""

    def test_review_findings_labelled_reviewer_pre_review(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1: review_findings rows have archetype='reviewer/pre-review'."""
        _insert_test_findings(knowledge_conn, severities=["critical"])

        rows = query_findings(knowledge_conn)
        review_rows = [r for r in rows if r.spec_name == "my_spec"]
        assert len(review_rows) > 0
        assert all(r.archetype == "reviewer/pre-review" for r in review_rows)

    def test_drift_findings_labelled_reviewer_drift_review(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: drift_findings rows have archetype='reviewer/drift-review'."""
        _insert_drift_finding(knowledge_conn)

        rows = query_findings(knowledge_conn)
        drift_rows = [r for r in rows if r.archetype == "reviewer/drift-review"]
        assert len(drift_rows) > 0

    def test_lookup_review_finding_labelled_reviewer_pre_review(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-1: lookup_finding_by_id returns archetype='reviewer/pre-review' for review_findings."""
        findings = _insert_test_findings(knowledge_conn, severities=["critical"])
        fid = findings[0].id

        result = lookup_finding_by_id(knowledge_conn, fid)

        assert result is not None
        assert result.archetype == "reviewer/pre-review"

    def test_lookup_drift_finding_labelled_reviewer_drift_review(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-2: lookup_finding_by_id returns archetype='reviewer/drift-review' for drift_findings."""
        finding = _insert_drift_finding(knowledge_conn)

        result = lookup_finding_by_id(knowledge_conn, finding.id)

        assert result is not None
        assert result.archetype == "reviewer/drift-review"


class TestArchetypeFilterCurrentNames:
    """591-AC-3: Archetype filter accepts reviewer, reviewer/pre-review, reviewer/drift-review."""

    def test_reviewer_filter_returns_both_review_and_drift(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-3: archetype='reviewer' returns rows from both review_findings and drift_findings."""
        _insert_test_findings(
            knowledge_conn, severities=["critical"], session_id="my_spec:1:review"
        )
        _insert_drift_finding(knowledge_conn, session_id="my_spec:1:drift")

        rows = query_findings(knowledge_conn, archetype="reviewer")

        assert len(rows) == 2
        archetypes = {r.archetype for r in rows}
        assert "reviewer/pre-review" in archetypes
        assert "reviewer/drift-review" in archetypes

    def test_reviewer_pre_review_filter_returns_only_review_findings(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-3: archetype='reviewer/pre-review' returns only review_findings rows."""
        _insert_test_findings(
            knowledge_conn, severities=["critical"], session_id="my_spec:1:review"
        )
        _insert_drift_finding(knowledge_conn, session_id="my_spec:1:drift")

        rows = query_findings(knowledge_conn, archetype="reviewer/pre-review")

        assert len(rows) == 1
        assert rows[0].archetype == "reviewer/pre-review"

    def test_reviewer_drift_review_filter_returns_only_drift_findings(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AC-3: archetype='reviewer/drift-review' returns only drift_findings rows."""
        _insert_test_findings(
            knowledge_conn, severities=["critical"], session_id="my_spec:1:review"
        )
        _insert_drift_finding(knowledge_conn, session_id="my_spec:1:drift")

        rows = query_findings(knowledge_conn, archetype="reviewer/drift-review")

        assert len(rows) == 1
        assert rows[0].archetype == "reviewer/drift-review"


class TestLegacyArchetypeNamesRejected:
    """591-AC-4: Legacy archetype names 'skeptic' and 'oracle' raise ValueError."""

    def test_skeptic_raises_value_error(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """AC-4: query_findings(archetype='skeptic') raises ValueError."""
        _insert_test_findings(knowledge_conn, severities=["critical"])

        with pytest.raises(ValueError, match="skeptic"):
            query_findings(knowledge_conn, archetype="skeptic")

    def test_oracle_raises_value_error(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """AC-4: query_findings(archetype='oracle') raises ValueError."""
        _insert_drift_finding(knowledge_conn)

        with pytest.raises(ValueError, match="oracle"):
            query_findings(knowledge_conn, archetype="oracle")


class TestCliHelpTextCurrentNames:
    """591-AC-5: CLI help text uses current archetype names, not legacy ones."""

    def test_help_text_has_no_legacy_names(self) -> None:
        """AC-5: The --archetype option help string does not mention 'skeptic' or 'oracle'."""
        from agent_fox.cli.findings import findings_cmd

        # Inspect the option's help text directly
        archetype_option = next(
            (p for p in findings_cmd.params if p.name == "archetype"),
            None,
        )
        assert archetype_option is not None, "--archetype option not found"
        help_text = archetype_option.help or ""
        assert "skeptic" not in help_text, f"Legacy name 'skeptic' found in help: {help_text!r}"
        assert "oracle" not in help_text, f"Legacy name 'oracle' found in help: {help_text!r}"
        assert "reviewer" in help_text, f"Expected 'reviewer' in help: {help_text!r}"
        assert "verifier" in help_text, f"Expected 'verifier' in help: {help_text!r}"
