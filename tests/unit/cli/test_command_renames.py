"""Tests for CLI command renames: dump -> export, lint-spec -> lint-specs.

Test Spec: TS-59-1 through TS-59-6
Requirements: 59-REQ-1.1, 59-REQ-1.2, 59-REQ-1.3, 59-REQ-1.4,
              59-REQ-1.E1, 59-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main


@pytest.fixture()
def cli_runner() -> CliRunner:
    return CliRunner()


class TestExportReplacedDumpMemory:
    """TS-59-1: `agent-fox export --memory` produces identical output to
    the former `dump --memory`.

    Requirement: 59-REQ-1.1
    """

    def test_export_memory_exits_zero(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """export --memory exits 0 and writes memory summary file."""
        mock_conn = MagicMock()
        with (
            patch(
                "agent_fox.cli.export.DEFAULT_DB_PATH",
                tmp_path / "knowledge.duckdb",
            ),
            patch("agent_fox.cli.export.duckdb") as mock_duckdb,
            patch("agent_fox.cli.export.export_memory") as mock_export,
        ):
            # Simulate the DB file existing
            (tmp_path / "knowledge.duckdb").touch()
            mock_duckdb.connect.return_value = mock_conn

            from agent_fox.knowledge.export import ExportResult

            mock_export.return_value = ExportResult(
                count=5, output_path=tmp_path / "memory.md"
            )

            result = cli_runner.invoke(main, ["export", "--memory"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )


class TestExportReplacedDumpDb:
    """TS-59-2: `agent-fox export --db` produces identical output to
    the former `dump --db`.

    Requirement: 59-REQ-1.2
    """

    def test_export_db_exits_zero(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """export --db exits 0 and writes database dump."""
        mock_conn = MagicMock()
        with (
            patch(
                "agent_fox.cli.export.DEFAULT_DB_PATH",
                tmp_path / "knowledge.duckdb",
            ),
            patch("agent_fox.cli.export.duckdb") as mock_duckdb,
            patch("agent_fox.cli.export.export_db") as mock_export,
        ):
            (tmp_path / "knowledge.duckdb").touch()
            mock_duckdb.connect.return_value = mock_conn

            from agent_fox.knowledge.export import ExportResult

            mock_export.return_value = ExportResult(
                count=3, output_path=tmp_path / "dump.md"
            )

            result = cli_runner.invoke(main, ["export", "--db"])

        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )


class TestLintSpecsReplacedLintSpec:
    """TS-59-3: `agent-fox lint-specs` produces identical output to
    the former `lint-spec`.

    Requirement: 59-REQ-1.3
    """

    def test_lint_specs_command_accepted(self, cli_runner: CliRunner) -> None:
        """lint-specs command is recognized and runs."""
        with patch("agent_fox.cli.lint_specs.run_lint_specs") as mock_lint:
            from agent_fox.spec.lint import LintResult

            mock_lint.return_value = LintResult(
                findings=[], fix_results=[], exit_code=0
            )
            result = cli_runner.invoke(main, ["lint-specs"])

        assert result.exit_code in (0, 1), (
            f"Expected exit code 0 or 1, got {result.exit_code}. "
            f"Output: {result.output}"
        )


class TestLintSpecsAcceptsFlags:
    """TS-59-4: `lint-specs --all` is accepted without error.

    Requirement: 59-REQ-1.4
    """

    def test_lint_specs_all_flag_accepted(self, cli_runner: CliRunner) -> None:
        """lint-specs --all does not produce 'no such option' error."""
        with patch("agent_fox.cli.lint_specs.run_lint_specs") as mock_lint:
            from agent_fox.spec.lint import LintResult

            mock_lint.return_value = LintResult(
                findings=[], fix_results=[], exit_code=0
            )
            result = cli_runner.invoke(main, ["lint-specs", "--all"])

        assert "no such option" not in (result.output or "").lower(), (
            f"Unexpected error: {result.output}"
        )


class TestOldDumpRemoved:
    """TS-59-5: `agent-fox dump` exits with error.

    Requirement: 59-REQ-1.E1
    """

    def test_dump_command_rejected(self, cli_runner: CliRunner) -> None:
        """dump command is no longer recognized."""
        result = cli_runner.invoke(main, ["dump"])
        assert result.exit_code != 0, (
            f"Expected non-zero exit code, got {result.exit_code}"
        )


class TestOldLintSpecRemoved:
    """TS-59-6: `agent-fox lint-spec` exits with error.

    Requirement: 59-REQ-1.E2
    """

    def test_lint_spec_command_rejected(self, cli_runner: CliRunner) -> None:
        """lint-spec command is no longer recognized."""
        result = cli_runner.invoke(main, ["lint-spec"])
        assert result.exit_code != 0, (
            f"Expected non-zero exit code, got {result.exit_code}"
        )
