"""Unit tests for the insights CLI command (formerly findings).

Validates the `agent-fox insights` command: graceful handling when
no database exists, empty results message, end-to-end command
invocation with filters, and that the rename is correct.

Also validates the `--dismiss` flag (592-AC-3, 592-AC-4).

Test Spec: TS-84-E3, TS-84-E4
Requirements: 84-REQ-4.E1, 84-REQ-4.E2, 592-AC-3, 592-AC-4
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import duckdb
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.cli.findings import findings_cmd
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import (
    DriftFinding,
    ReviewFinding,
    insert_drift_findings,
    insert_findings,
)
from tests.unit.knowledge.conftest import SCHEMA_DDL


class TestInsightsCommandRegistration:
    """Verify the command is registered as 'insights', not 'findings'."""

    def test_insights_command_accepted(self, cli_runner: CliRunner) -> None:
        """AC-1: `agent-fox insights` is a valid command."""
        result = cli_runner.invoke(main, ["insights", "--help"])
        assert result.exit_code == 0
        assert "No such command" not in result.output

    def test_findings_command_rejected(self, cli_runner: CliRunner) -> None:
        """AC-2: `agent-fox findings` is no longer a valid command."""
        result = cli_runner.invoke(main, ["findings"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_insights_has_all_flags(self, cli_runner: CliRunner) -> None:
        """AC-3: All former 'findings' flags are present under 'insights'."""
        result = cli_runner.invoke(main, ["insights", "--help"])
        assert result.exit_code == 0
        for flag in ("--spec", "--severity", "--archetype", "--run", "--json"):
            assert flag in result.output

    def test_click_command_name_is_insights(self) -> None:
        """AC-4: The @click.command decorator uses name 'insights'."""
        assert findings_cmd.name == "insights"


class TestFindingsNoDatabase:
    """TS-84-E3: No knowledge DB for insights command."""

    def test_no_db_prints_message(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Verify graceful exit when no DB exists."""
        fake_db_path = tmp_path / "nonexistent.duckdb"

        with patch(
            "agent_fox.cli.findings.DEFAULT_DB_PATH",
            fake_db_path,
        ):
            result = cli_runner.invoke(findings_cmd)

        assert result.exit_code == 0
        assert "No knowledge database found" in result.output


class TestFindingsEmptyResults:
    """TS-84-E4: Empty query result message."""

    def test_no_matches_prints_message(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Verify message when no findings match filters."""
        db_path = tmp_path / "knowledge.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(SCHEMA_DDL)
        conn.close()

        with patch(
            "agent_fox.cli.findings.DEFAULT_DB_PATH",
            db_path,
        ):
            result = cli_runner.invoke(findings_cmd, ["--spec", "nonexistent"])

        assert result.exit_code == 0
        assert "No findings match" in result.output


class TestInsightsDismissFlag:
    """592-AC-3 / 592-AC-4: --dismiss flag dismisses a finding or exits non-zero."""

    def _make_db(self, tmp_path: Path) -> tuple[Path, duckdb.DuckDBPyConnection]:
        """Create a tmp DB with the full production schema and return (path, conn)."""
        db_path = tmp_path / "knowledge.duckdb"
        conn = duckdb.connect(str(db_path))
        run_migrations(conn)
        return db_path, conn

    def test_dismiss_review_finding_exits_zero(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """AC-3: --dismiss prints description and exits 0 for a known active finding."""
        db_path, conn = self._make_db(tmp_path)
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Smoke tests missing for spec 120",
            requirement_ref="120-REQ-1.1",
            spec_name="120_spec",
            task_group="0",
            session_id="120_spec:0:1",
        )
        insert_findings(conn, [finding])
        conn.close()

        with patch("agent_fox.cli.findings.DEFAULT_DB_PATH", db_path):
            result = cli_runner.invoke(findings_cmd, ["--dismiss", finding.id, "false positive"])

        assert result.exit_code == 0, f"Expected exit_code=0, got {result.exit_code}; output: {result.output}"
        assert "Smoke tests missing for spec 120" in result.output
        assert "Dismissed" in result.output

    def test_dismiss_finding_no_longer_active(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """AC-3: After dismiss, the finding no longer appears in a subsequent insights query."""
        db_path, conn = self._make_db(tmp_path)
        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Stale critical finding",
            requirement_ref=None,
            spec_name="test_spec",
            task_group="1",
            session_id="test_spec:1:1",
        )
        insert_findings(conn, [finding])
        conn.close()

        with patch("agent_fox.cli.findings.DEFAULT_DB_PATH", db_path):
            # Dismiss the finding
            dismiss_result = cli_runner.invoke(findings_cmd, ["--dismiss", finding.id, "tests implemented"])
            assert dismiss_result.exit_code == 0

            # Re-query — finding should be absent
            query_result = cli_runner.invoke(findings_cmd, ["--spec", "test_spec"])

        assert "Stale critical finding" not in query_result.output

    def test_dismiss_drift_finding(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """AC-3: --dismiss also works for drift findings (oracle archetype)."""
        db_path, conn = self._make_db(tmp_path)
        finding = DriftFinding(
            id=str(uuid.uuid4()),
            severity="major",
            description="Oracle drift: spec diverges from code",
            spec_ref="84-REQ-1.1",
            artifact_ref="agent_fox/cli/findings.py",
            spec_name="84_spec",
            task_group="3",
            session_id="84_spec:3:1",
        )
        insert_drift_findings(conn, [finding])
        conn.close()

        with patch("agent_fox.cli.findings.DEFAULT_DB_PATH", db_path):
            result = cli_runner.invoke(findings_cmd, ["--dismiss", finding.id, "fixed in PR #42"])

        assert result.exit_code == 0
        assert "Oracle drift: spec diverges from code" in result.output

    def test_dismiss_unknown_id_exits_nonzero(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """AC-4: --dismiss with an unknown ID exits non-zero with 'not found' in output."""
        db_path, conn = self._make_db(tmp_path)
        conn.close()

        unknown_id = str(uuid.uuid4())
        with patch("agent_fox.cli.findings.DEFAULT_DB_PATH", db_path):
            result = cli_runner.invoke(findings_cmd, ["--dismiss", unknown_id, "some reason"])

        assert result.exit_code != 0, f"Expected non-zero exit, got {result.exit_code}"
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "not found" in combined.lower(), f"Expected 'not found' in output, got: {combined!r}"

    def test_dismiss_flag_visible_in_help(self, cli_runner: CliRunner) -> None:
        """The --dismiss option appears in the help text."""
        result = cli_runner.invoke(findings_cmd, ["--help"])
        assert result.exit_code == 0
        assert "--dismiss" in result.output
