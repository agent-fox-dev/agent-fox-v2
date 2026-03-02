"""CLI entry point tests.

Test Spec: TS-01-1 (version), TS-01-2 (help), TS-01-E1 (unknown subcommand),
           TS-14-5 (banner on subcommand), TS-14-6 (quiet suppresses banner),
           TS-14-E3 (version skips banner)
Requirements: 01-REQ-1.1, 01-REQ-1.E1, 14-REQ-4.1, 14-REQ-4.2, 14-REQ-4.E1
"""

from __future__ import annotations

import re

from click.testing import CliRunner

from agent_fox import __version__
from agent_fox.cli.app import main


class TestCLIVersion:
    """TS-01-1: CLI displays version."""

    def test_version_flag_exits_zero(self, cli_runner: CliRunner) -> None:
        """--version exits with code 0."""
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_version_flag_shows_version(self, cli_runner: CliRunner) -> None:
        """--version output contains a version string."""
        result = cli_runner.invoke(main, ["--version"])
        # Should contain something like "0.1.0" or a semver pattern
        assert re.search(r"\d+\.\d+\.\d+", result.output), (
            f"Expected version string in output, got: {result.output!r}"
        )


class TestCLIHelp:
    """TS-01-2: CLI displays help."""

    def test_help_flag_exits_zero(self, cli_runner: CliRunner) -> None:
        """--help exits with code 0."""
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_help_lists_init_command(self, cli_runner: CliRunner) -> None:
        """--help output lists the 'init' subcommand."""
        result = cli_runner.invoke(main, ["--help"])
        assert "init" in result.output, (
            f"Expected 'init' in help output, got: {result.output!r}"
        )


class TestCLIUnknownSubcommand:
    """TS-01-E1: Unknown subcommand prints error and exits with code 2."""

    def test_unknown_subcommand_exits_two(self, cli_runner: CliRunner) -> None:
        """Unknown subcommand exits with code 2."""
        result = cli_runner.invoke(main, ["nonexistent"])
        assert result.exit_code == 2

    def test_unknown_subcommand_shows_error(self, cli_runner: CliRunner) -> None:
        """Unknown subcommand produces error output."""
        result = cli_runner.invoke(main, ["nonexistent"])
        # Click typically says "No such command" or similar
        combined = result.output + (result.stderr or "")
        has_error_msg = (
            "no such command" in combined.lower()
            or "nonexistent" in combined.lower()
        )
        assert has_error_msg, (
            f"Expected error about unknown command, got: {combined!r}"
        )


class TestBannerOnSubcommand:
    """TS-14-5: Banner displays on subcommand invocation.

    Requirement: 14-REQ-4.1
    """

    def test_banner_appears_with_subcommand(self, cli_runner: CliRunner) -> None:
        """Banner (fox art + version line) appears when a subcommand is invoked."""
        result = cli_runner.invoke(main, ["status"])

        assert "agent-fox v" in result.output, (
            f"Expected version line in subcommand output, got:\n{result.output!r}"
        )
        assert "/\\_/\\" in result.output, (
            f"Expected fox art in subcommand output, got:\n{result.output!r}"
        )

    def test_banner_appears_without_subcommand(self, cli_runner: CliRunner) -> None:
        """Banner also appears when invoked with no subcommand."""
        result = cli_runner.invoke(main, [])

        assert "agent-fox v" in result.output, (
            f"Expected version line in bare invocation, got:\n{result.output!r}"
        )
        assert "/\\_/\\" in result.output, (
            f"Expected fox art in bare invocation, got:\n{result.output!r}"
        )


class TestBannerQuietSuppression:
    """TS-14-6: --quiet suppresses banner.

    Requirement: 14-REQ-4.2
    """

    def test_quiet_suppresses_banner(self, cli_runner: CliRunner) -> None:
        """--quiet flag suppresses both fox art and version line."""
        result = cli_runner.invoke(main, ["--quiet"])

        assert "agent-fox v" not in result.output, (
            f"Version line should not appear with --quiet, got:\n{result.output!r}"
        )
        assert "/\\_/\\" not in result.output, (
            f"Fox art should not appear with --quiet, got:\n{result.output!r}"
        )

    def test_quiet_with_subcommand_suppresses_banner(
        self, cli_runner: CliRunner
    ) -> None:
        """--quiet also suppresses banner when used with a subcommand."""
        result = cli_runner.invoke(main, ["--quiet", "status"])

        assert "/\\_/\\" not in result.output, (
            f"Fox art should not appear with --quiet, got:\n{result.output!r}"
        )


class TestVersionFlagSkipsBanner:
    """TS-14-E3: --version shows only version, no banner.

    Requirement: 14-REQ-4.E1
    """

    def test_version_flag_shows_version_not_banner(
        self, cli_runner: CliRunner
    ) -> None:
        """--version output contains version string but no fox art."""
        result = cli_runner.invoke(main, ["--version"])

        assert __version__ in result.output, (
            f"Expected version string in output, got:\n{result.output!r}"
        )
        assert "/\\_/\\" not in result.output, (
            f"Fox art should not appear with --version, got:\n{result.output!r}"
        )
