"""Unit tests for the insights CLI command (formerly findings).

Validates the `agent-fox insights` command: graceful handling when
no database exists, empty results message, end-to-end command
invocation with filters, and that the rename is correct.

Test Spec: TS-84-E3, TS-84-E4
Requirements: 84-REQ-4.E1, 84-REQ-4.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import duckdb
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.cli.findings import findings_cmd
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
