"""Unit tests for the findings CLI command.

Validates the `agent-fox findings` command: graceful handling when
no database exists, empty results message, and end-to-end command
invocation with filters.

Test Spec: TS-84-E3, TS-84-E4
Requirements: 84-REQ-4.E1, 84-REQ-4.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import duckdb
from click.testing import CliRunner

from agent_fox.cli.findings import findings_cmd
from tests.unit.knowledge.conftest import SCHEMA_DDL


class TestFindingsNoDatabase:
    """TS-84-E3: No knowledge DB for findings command."""

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

    def test_no_matches_prints_message(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
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
