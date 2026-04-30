"""CLI tests for the standup command.

AC-1: --output flag no longer exists.
AC-2: Standup output goes to stdout when no --output flag is passed.
AC-3: standup_cmd function signature has no 'output' parameter.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.cli.standup import standup_cmd


class TestStandupOutputFlagRemoved:
    """AC-1: The --output option no longer exists on the standup command."""

    def test_output_flag_raises_usage_error(self, cli_runner: CliRunner) -> None:
        """Passing --output raises exit code 2 (UsageError / no such option)."""
        result = cli_runner.invoke(main, ["standup", "--output", "out.txt"])
        assert result.exit_code == 2
        assert "No such option" in result.output

    def test_output_not_in_help(self, cli_runner: CliRunner) -> None:
        """--output does not appear in standup help text."""
        result = cli_runner.invoke(main, ["standup", "--help"])
        assert result.exit_code == 0
        assert "--output" not in result.output


class TestStandupOutputToStdout:
    """AC-2: Standup output is written to stdout when --output is absent."""

    def test_standup_writes_to_stdout(self, cli_runner: CliRunner, tmp_path) -> None:
        """Standup output appears in result.output and no extra file is created."""
        mock_report = MagicMock()
        mock_formatter = MagicMock()
        mock_formatter.format_standup.return_value = "## Standup Report\n"

        with (
            patch("agent_fox.cli.standup.generate_standup", return_value=mock_report),
            patch("agent_fox.cli.standup.get_formatter", return_value=mock_formatter),
            patch("agent_fox.cli.standup.DEFAULT_DB_PATH", tmp_path / "nonexistent.db"),
        ):
            result = cli_runner.invoke(main, ["standup"])

        assert result.exit_code == 0
        assert result.output  # non-empty


class TestStandupCmdSignature:
    """AC-3: standup_cmd function signature does not include 'output'."""

    def test_output_not_in_params(self) -> None:
        """The 'output' parameter is not present in standup_cmd's signature."""
        sig = inspect.signature(standup_cmd.callback)  # type: ignore[union-attr]
        assert "output" not in sig.parameters
