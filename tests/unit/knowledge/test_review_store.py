"""Unit tests for review_store.py: schema, CRUD, supersession.

Test Spec: TS-27-1, TS-27-2, TS-27-6, TS-27-7, TS-27-8, TS-27-E1, TS-27-E2, TS-27-E5
Requirements: 27-REQ-1.1, 27-REQ-1.E1, 27-REQ-2.1, 27-REQ-2.E1,
              27-REQ-4.1, 27-REQ-4.2, 27-REQ-4.3, 27-REQ-4.E1

Issue #553: observation/minor findings are stored but never retrieved.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.migrations import Migration
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    VerificationResult,
    insert_findings,
    insert_verdicts,
    query_active_findings,
    query_active_verdicts,
    query_findings_by_session,
    query_verdicts_by_session,
)


def _make_finding(
    *,
    severity: str = "major",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "session-1",
    requirement_ref: str | None = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=requirement_ref,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


def _make_verdict(
    *,
    requirement_id: str = "27-REQ-1.1",
    verdict: str = "PASS",
    evidence: str | None = "Tests pass",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "session-1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence=evidence,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


class TestReviewFindingsTableCreated:
    """TS-27-1: review_findings table exists after schema creation."""

    def test_review_findings_table_created(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """review_findings table exists with expected columns."""
        rows = schema_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'review_findings' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in rows]
        assert "id" in columns
        assert "severity" in columns
        assert "description" in columns
        assert "requirement_ref" in columns
        assert "spec_name" in columns
        assert "task_group" in columns
        assert "session_id" in columns
        assert "superseded_by" in columns
        assert "created_at" in columns


class TestVerificationResultsTableCreated:
    """TS-27-2: verification_results table exists after schema creation."""

    def test_verification_results_table_created(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """verification_results table exists with expected columns."""
        rows = schema_conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'verification_results' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in rows]
        assert "id" in columns
        assert "requirement_id" in columns
        assert "verdict" in columns
        assert "evidence" in columns
        assert "spec_name" in columns
        assert "task_group" in columns
        assert "session_id" in columns
        assert "superseded_by" in columns
        assert "created_at" in columns


class TestInsertFindingsSupersession:
    """TS-27-6: insert findings with supersession."""

    def test_insert_findings_supersession(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """New findings supersede existing active records for same spec/task_group."""
        # Insert first batch
        f1 = _make_finding(description="First finding", session_id="s1")
        insert_findings(schema_conn, [f1])

        # Verify first batch is active
        active = query_active_findings(schema_conn, "test_spec")
        assert len(active) == 1
        assert active[0].description == "First finding"

        # Insert second batch (supersedes first)
        f2 = _make_finding(description="Second finding", session_id="s2")
        insert_findings(schema_conn, [f2])

        # Verify only second batch is active
        active = query_active_findings(schema_conn, "test_spec")
        assert len(active) == 1
        assert active[0].description == "Second finding"

        # Verify first batch is superseded
        all_rows = schema_conn.execute(
            "SELECT description, superseded_by FROM review_findings ORDER BY description"
        ).fetchall()
        assert len(all_rows) == 2
        first = next(r for r in all_rows if r[0] == "First finding")
        assert first[1] is not None  # superseded_by is set


class TestInsertVerdictsSupersession:
    """TS-27-7: insert verdicts with supersession."""

    def test_insert_verdicts_supersession(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """New verdicts supersede existing active records."""
        v1 = _make_verdict(verdict="FAIL", session_id="s1")
        insert_verdicts(schema_conn, [v1])

        active = query_active_verdicts(schema_conn, "test_spec")
        assert len(active) == 1
        assert active[0].verdict == "FAIL"

        v2 = _make_verdict(verdict="PASS", session_id="s2")
        insert_verdicts(schema_conn, [v2])

        active = query_active_verdicts(schema_conn, "test_spec")
        assert len(active) == 1
        assert active[0].verdict == "PASS"


class TestNoRecordsToSupersede:
    """TS-27-E5: no existing records to supersede."""

    def test_no_records_to_supersede(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """Insert works cleanly when no prior records exist."""
        f1 = _make_finding(description="First ever finding")
        count = insert_findings(schema_conn, [f1])
        assert count == 1

        active = query_active_findings(schema_conn, "test_spec")
        assert len(active) == 1


class TestMigrationFailureRaises:
    """TS-27-E1: migration failure raises KnowledgeStoreError."""

    def test_migration_failure_raises(self) -> None:
        """KnowledgeStoreError raised if migration fails."""
        from agent_fox.knowledge.migrations import apply_pending_migrations

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            );
            INSERT INTO schema_version (version, description) VALUES (1, 'initial');
        """)

        def _failing_migration(c: duckdb.DuckDBPyConnection) -> None:
            raise RuntimeError("Simulated migration failure")

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [
                Migration(
                    version=2,
                    description="failing migration",
                    apply=_failing_migration,
                )
            ],
        ):
            with pytest.raises(KnowledgeStoreError, match="Migration to version 2 failed"):
                apply_pending_migrations(conn)

        conn.close()


class TestMigrationAlreadyAppliedSkips:
    """TS-27-E2: migration already applied skips without error."""

    def test_migration_already_applied_skips(self) -> None:
        """Running migration twice does not error."""
        from agent_fox.knowledge.migrations import apply_pending_migrations

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            );
            INSERT INTO schema_version (version, description) VALUES (1, 'initial');
        """)

        # Run migration twice — second run should be a no-op
        apply_pending_migrations(conn)
        apply_pending_migrations(conn)

        # Verify version is recorded
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert version is not None
        assert version[0] == 22
        conn.close()


class TestQueryBySession:
    """Query findings/verdicts by session_id for convergence."""

    def test_query_findings_by_session(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """Findings can be queried by session_id."""
        f1 = _make_finding(description="Finding 1", session_id="s1")
        f2 = _make_finding(description="Finding 2", session_id="s2")
        insert_findings(schema_conn, [f1])
        # Need different task_group to avoid supersession
        f2b = ReviewFinding(
            id=f2.id,
            severity=f2.severity,
            description=f2.description,
            requirement_ref=f2.requirement_ref,
            spec_name=f2.spec_name,
            task_group="2",
            session_id=f2.session_id,
        )
        insert_findings(schema_conn, [f2b])

        results = query_findings_by_session(schema_conn, "s1")
        assert len(results) == 1
        assert results[0].description == "Finding 1"

    def test_query_verdicts_by_session(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """Verdicts can be queried by session_id."""
        v1 = _make_verdict(session_id="s1")
        v2 = _make_verdict(session_id="s2", requirement_id="27-REQ-2.1")
        insert_verdicts(schema_conn, [v1])
        v2b = VerificationResult(
            id=v2.id,
            requirement_id=v2.requirement_id,
            verdict=v2.verdict,
            evidence=v2.evidence,
            spec_name=v2.spec_name,
            task_group="2",
            session_id=v2.session_id,
        )
        insert_verdicts(schema_conn, [v2b])

        results = query_verdicts_by_session(schema_conn, "s1")
        assert len(results) == 1
        assert results[0].requirement_id == "27-REQ-1.1"


# ---------------------------------------------------------------------------
# Regression tests for issue #188: table name allowlist validation
# ---------------------------------------------------------------------------


class TestTableNameValidation:
    """Validate that SQL helper functions reject disallowed table names."""

    def test_validate_table_name_accepts_allowed(self) -> None:
        from agent_fox.knowledge.review_store import _validate_table_name

        for name in ("review_findings", "drift_findings", "verification_results"):
            _validate_table_name(name)  # should not raise

    def test_validate_table_name_rejects_unknown(self) -> None:
        from agent_fox.knowledge.review_store import _validate_table_name

        with pytest.raises(ValueError, match="not in the allowed set"):
            _validate_table_name("users; DROP TABLE --")

    def test_supersede_rejects_bad_table(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.review_store import _supersede_active_records

        with pytest.raises(ValueError, match="not in the allowed set"):
            _supersede_active_records(schema_conn, "evil_table", "spec", "1", "marker")

    def test_insert_with_supersession_rejects_bad_table(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        from agent_fox.knowledge.review_store import _insert_with_supersession

        with pytest.raises(ValueError, match="not in the allowed set"):
            _insert_with_supersession(
                schema_conn,
                table="evil_table",
                columns="id",
                records=[],
                value_extractor=lambda r: [],
                record_type_label="test",
            )


# ---------------------------------------------------------------------------
# AC-4: _insert_with_supersession supersedes per task_group, not just the
# first record's task_group.
# ---------------------------------------------------------------------------


class TestInsertWithSupersessionPerTaskGroup:
    """AC-4: multi-group batch supersedes all matching prior records."""

    def test_cross_group_batch_supersedes_both_task_groups(
        self, schema_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A batch spanning task_group='1' and '2' supersedes prior records
        for BOTH groups, not just the first record's group."""
        # Seed: one active finding per group from 'old' session
        old_g1 = _make_finding(
            description="Old group-1 finding",
            task_group="1",
            session_id="old",
        )
        old_g2 = _make_finding(
            description="Old group-2 finding",
            task_group="2",
            session_id="old",
        )
        insert_findings(schema_conn, [old_g1])
        insert_findings(schema_conn, [old_g2])

        # Verify both are active before the new insert
        active_before = query_active_findings(schema_conn, "test_spec")
        assert len(active_before) == 2

        # New batch spans both groups, session='new'
        new_g1 = _make_finding(
            description="New group-1 finding",
            task_group="1",
            session_id="new",
        )
        new_g2 = _make_finding(
            description="New group-2 finding",
            task_group="2",
            session_id="new",
        )
        insert_findings(schema_conn, [new_g1, new_g2])

        # Only the two new findings should be active
        active_after = query_active_findings(schema_conn, "test_spec")
        assert len(active_after) == 2
        descriptions = {f.description for f in active_after}
        assert descriptions == {"New group-1 finding", "New group-2 finding"}

        # Both old findings must be superseded by 'new'
        all_rows = schema_conn.execute(
            "SELECT description, superseded_by FROM review_findings ORDER BY description"
        ).fetchall()
        old_rows = [r for r in all_rows if r[0].startswith("Old")]
        assert len(old_rows) == 2, "Both old findings should be present"
        for row in old_rows:
            assert row[1] == "new", (
                f"Old finding '{row[0]}' should have superseded_by='new', got '{row[1]}'"
            )


# ---------------------------------------------------------------------------
# Issue #553: observation/minor findings must not reach review_findings table
# ---------------------------------------------------------------------------


class TestInsertFindingsDropsNonActionable:
    """AC-1: insert_findings() silently drops observation/minor findings.

    Only critical and major findings are written to the database.
    The return value equals the count of actionable findings only.
    """

    def test_returns_only_actionable_count(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """insert_findings() with mixed severities returns count of actionable only."""
        findings = [
            _make_finding(severity="critical", description="critical finding", task_group="c1"),
            _make_finding(severity="major", description="major finding", task_group="m1"),
            _make_finding(severity="minor", description="minor finding", task_group="mi1"),
            _make_finding(severity="observation", description="observation finding", task_group="o1"),
        ]
        count = insert_findings(schema_conn, findings)
        assert count == 2, f"Expected 2 actionable findings inserted, got {count}"

    def test_observation_and_minor_not_in_db(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """No observation or minor rows appear in review_findings after insert."""
        findings = [
            _make_finding(severity="critical", description="critical finding", task_group="c1"),
            _make_finding(severity="major", description="major finding", task_group="m1"),
            _make_finding(severity="minor", description="minor finding", task_group="mi1"),
            _make_finding(severity="observation", description="observation finding", task_group="o1"),
        ]
        insert_findings(schema_conn, findings)

        dead_rows = schema_conn.execute(
            "SELECT COUNT(*) FROM review_findings WHERE severity IN ('minor', 'observation')"
        ).fetchone()
        assert dead_rows[0] == 0, (
            f"Expected 0 minor/observation rows in DB, found {dead_rows[0]}"
        )

    def test_all_non_actionable_returns_zero(self, schema_conn: duckdb.DuckDBPyConnection) -> None:
        """insert_findings() with only observation/minor findings returns 0."""
        findings = [
            _make_finding(severity="minor", description="minor finding", task_group="mi1"),
            _make_finding(severity="observation", description="obs finding", task_group="o1"),
        ]
        count = insert_findings(schema_conn, findings)
        assert count == 0

        total = schema_conn.execute("SELECT COUNT(*) FROM review_findings").fetchone()
        assert total[0] == 0


class TestQueryActiveFindingsExcludesNonActionable:
    """AC-2: query_active_findings() never returns observation/minor findings.

    This holds even when such rows are present in the DB (legacy data).
    """

    def test_legacy_observation_minor_excluded_from_query(
        self, schema_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Legacy observation/minor rows in DB are excluded from query results."""
        # Insert legacy rows directly via SQL (bypassing insert_findings filter)
        for sev in ("observation", "minor"):
            schema_conn.execute(
                "INSERT INTO review_findings "
                "(id, severity, description, spec_name, task_group, session_id, created_at) "
                "VALUES (gen_random_uuid(), ?, ?, 'spec_01', 'tg_legacy', 'legacy', CURRENT_TIMESTAMP)",
                [sev, f"Legacy {sev} finding"],
            )

        # Also insert an active critical finding via normal path
        crit = _make_finding(
            severity="critical",
            description="Real critical finding",
            spec_name="spec_01",
            task_group="tg_crit",
        )
        insert_findings(schema_conn, [crit])

        results = query_active_findings(schema_conn, "spec_01")
        severities = {f.severity for f in results}
        assert "observation" not in severities, "observation finding leaked into query results"
        assert "minor" not in severities, "minor finding leaked into query results"
        assert any(f.description == "Real critical finding" for f in results), (
            "Expected critical finding to be present"
        )

    def test_only_observation_minor_returns_empty(
        self, schema_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """When only legacy observation/minor rows exist, query returns empty list."""
        for sev in ("observation", "minor"):
            schema_conn.execute(
                "INSERT INTO review_findings "
                "(id, severity, description, spec_name, task_group, session_id, created_at) "
                "VALUES (gen_random_uuid(), ?, ?, 'spec_01', 'tg_legacy', 'legacy', CURRENT_TIMESTAMP)",
                [sev, f"Legacy {sev} finding"],
            )

        results = query_active_findings(schema_conn, "spec_01")
        assert results == [], f"Expected empty list, got {results}"
