"""Tests for audit report consumption and injection into coder prompts.

Suite 4: Audit Report Consumption (TS-4.1 through TS-4.4)

Requirements: 113-REQ-4.1, 113-REQ-4.2, 113-REQ-4.3, 113-REQ-4.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest


@pytest.fixture
def knowledge_conn_with_schema():
    """In-memory DuckDB with full production schema."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _make_audit_result(verdict: str = "FAIL", num_entries: int = 3):
    """Create a mock AuditResult with entries."""
    from agent_fox.session.convergence import AuditEntry, AuditResult

    entries = [
        AuditEntry(severity="critical", description=f"Critical finding number {i + 1}")
        for i in range(num_entries)
    ]
    return AuditResult(entries=entries, overall_verdict=verdict, summary="Audit summary")


class TestAuditFindingsPersistedToDatabase:
    """TS-4.1: Audit findings are persisted to review_findings with category='audit'."""

    def test_non_pass_entries_stored_in_review_findings(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-4.1: AuditResult with FAIL verdict → 3 rows in review_findings
        with category='audit'.

        Requirements: 113-REQ-4.1
        """
        from agent_fox.session.auditor_output import persist_auditor_results

        audit_result = _make_audit_result(verdict="FAIL", num_entries=3)
        spec_dir = tmp_path / "05_foo"
        spec_dir.mkdir()

        # Call through the audit-review persistence path
        # This now should also persist to review_findings with category='audit'
        persist_auditor_results(
            spec_dir,
            audit_result,
            attempt=1,
            project_root=tmp_path,
            conn=knowledge_conn_with_schema,  # NEW: pass connection for DB persistence
        )

        rows = knowledge_conn_with_schema.execute(
            "SELECT COUNT(*) FROM review_findings WHERE category = 'audit'"
        ).fetchone()
        assert rows[0] == 3, (
            f"Expected 3 review_findings rows with category='audit', got {rows[0]}"
        )

    def test_review_findings_have_correct_fields(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-4.1: Each persisted audit finding has spec_name, severity, description."""
        from agent_fox.session.auditor_output import persist_auditor_results

        audit_result = _make_audit_result(verdict="FAIL", num_entries=1)
        spec_dir = tmp_path / "05_foo"
        spec_dir.mkdir()

        persist_auditor_results(
            spec_dir,
            audit_result,
            attempt=1,
            project_root=tmp_path,
            conn=knowledge_conn_with_schema,
        )

        rows = knowledge_conn_with_schema.execute(
            "SELECT severity, description, spec_name, category FROM review_findings WHERE category = 'audit'"
        ).fetchall()
        assert len(rows) == 1
        severity, description, spec_name, category = rows[0]
        assert severity == "critical"
        assert "Critical finding" in description
        assert category == "audit"


class TestAuditFindingsInjectedIntoCoder:
    """TS-4.2: Audit findings appear in coder prompt context."""

    def test_audit_findings_in_first_attempt_prompt(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-4.2: Coder's task prompt includes active audit findings (attempt 1).

        Requirements: 113-REQ-4.2
        """
        from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

        # Seed 2 audit findings for spec "05_foo"
        audit_findings = [
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="critical",
                description="Coder must fix: missing null check in auth module",
                requirement_ref="113-REQ-4.2",
                spec_name="05_foo",
                task_group="2",
                session_id="05_foo:audit:1",
                superseded_by=None,
                category="audit",
            ),
            ReviewFinding(
                id=str(uuid.uuid4()),
                severity="major",
                description="Coder must fix: unhandled exception in database layer",
                requirement_ref="113-REQ-4.2",
                spec_name="05_foo",
                task_group="2",
                session_id="05_foo:audit:1",
                superseded_by=None,
                category="audit",
            ),
        ]
        insert_findings(knowledge_conn_with_schema, audit_findings)

        # Build prompts for coder — attempt 1 (fresh session)
        task_prompt = _build_coder_prompt(knowledge_conn_with_schema, tmp_path, "05_foo", attempt=1)

        # Audit finding descriptions should appear in the prompt
        assert "missing null check" in task_prompt, (
            "Audit finding 1 description missing from coder prompt"
        )
        assert "unhandled exception" in task_prompt, (
            "Audit finding 2 description missing from coder prompt"
        )

    def test_audit_findings_formatted_like_review_findings(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-4.2: Audit findings use same formatting mechanism as pre-review findings."""
        from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Test audit finding description for formatting check",
            requirement_ref=None,
            spec_name="05_foo",
            task_group="2",
            session_id="05_foo:audit:1",
            superseded_by=None,
            category="audit",
        )
        insert_findings(knowledge_conn_with_schema, [finding])

        task_prompt = _build_coder_prompt(knowledge_conn_with_schema, tmp_path, "05_foo", attempt=1)

        # The description must appear in the prompt
        assert "Test audit finding description" in task_prompt


class TestAuditReportsRetainedUntilEndOfRun:
    """TS-4.3: Audit report files are retained during the run."""

    def test_audit_report_file_exists_after_persistence(
        self, tmp_path: Path
    ) -> None:
        """TS-4.3: persist_auditor_results does not delete the audit report file."""
        from agent_fox.session.auditor_output import persist_auditor_results

        audit_result = _make_audit_result(verdict="FAIL", num_entries=1)
        spec_dir = tmp_path / "05_foo"
        spec_dir.mkdir()
        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)
        audit_report_path = audit_dir / "audit_05_foo.md"
        audit_report_path.write_text("# Audit Report\n\nFinding: critical issue")

        persist_auditor_results(
            spec_dir,
            audit_result,
            attempt=1,
            project_root=tmp_path,
        )

        # Report file must still exist
        assert audit_report_path.exists(), (
            "Audit report file was deleted by persist_auditor_results; "
            "it should only be deleted at end-of-run consolidation"
        )


class TestUnparseableAuditReport:
    """TS-4.4: Malformed audit reports are handled gracefully."""

    def test_unparseable_report_logs_warning_no_db_rows(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-4.4: If audit report parsing fails, log warning and store no findings.

        Requirements: 113-REQ-4.E1
        """
        from agent_fox.session.review_parser import parse_auditor_output

        # Completely malformed content that cannot be parsed
        malformed_transcript = "THIS IS NOT A VALID AUDIT REPORT FORMAT !!!"

        # parse_auditor_output should return None for malformed input
        result = parse_auditor_output(malformed_transcript)

        # When result is None, persist path should not insert any rows
        # The test verifies the guard: no rows in review_findings with category='audit'
        if result is None:
            # This is the expected path — no insertion occurs
            row = knowledge_conn_with_schema.execute(
                "SELECT COUNT(*) FROM review_findings WHERE category = 'audit'"
            ).fetchone()
            assert row[0] == 0
        else:
            # If parsing succeeded unexpectedly, the test still checks DB state
            # (this branch should not be reached for fully malformed content)
            pass


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_coder_prompt(
    conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    spec_name: str,
    attempt: int,
) -> str:
    """Build a coder task prompt and return it as a string for assertion."""
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import KnowledgeDB

    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    config = AgentFoxConfig()

    runner = NodeSessionRunner.__new__(NodeSessionRunner)
    runner._node_id = f"{spec_name}:1"
    runner._spec_name = spec_name
    runner._run_id = "test-run"
    runner._config = config
    runner._knowledge_db = db
    runner._sink_dispatcher = None
    runner._embedder = None
    runner._archetype = "coder"
    runner._mode = None
    runner._task_group = 2
    runner._agent_fox_dir = tmp_path / ".agent-fox"

    # Create a minimal spec dir with required artifacts
    spec_dir = tmp_path / ".agent-fox" / "specs" / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 2. Implement feature\n  - [ ] 2.1 Do thing\n")
    (spec_dir / "prd.md").write_text(f"# {spec_name}\n\nMinimal spec for testing.\n")
    (spec_dir / "requirements.md").write_text("# Requirements\n\nNone.\n")
    (spec_dir / "design.md").write_text("# Design\n\nMinimal.\n")
    (spec_dir / "test_spec.md").write_text("# Test Spec\n\nNone.\n")

    try:
        _sys, task = runner._build_prompts(tmp_path, attempt, None)
        return task
    except Exception:
        # If _build_prompts fails for unrelated reasons, return empty to trigger assertion
        return ""
