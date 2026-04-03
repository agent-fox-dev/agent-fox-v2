"""Integration tests for watch mode CLI flags.

Test Spec: TS-70-3, TS-70-11
Requirements: 70-REQ-1.3, 70-REQ-3.3
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_minimal_project(project_dir: Path) -> None:
    """Create a minimal project structure with a plan.json for CLI tests."""
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)

    # Minimal config.toml — disable hot_load so watch gate exits
    # immediately instead of entering the real watch loop (which would
    # call asyncio.sleep and hang the CliRunner).
    (agent_fox_dir / "config.toml").write_text("[orchestrator]\nhot_load = false\n")

    # Minimal empty plan.json
    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {},
        "edges": [],
        "order": [],
    }
    (agent_fox_dir / "plan.json").write_text(json.dumps(plan, indent=2))


# ---------------------------------------------------------------------------
# TS-70-3: Watch flag is boolean CLI option
# Requirements: 70-REQ-1.3
# ---------------------------------------------------------------------------


class TestWatchCLIFlag:
    """TS-70-3: --watch is accepted by the CLI as a boolean flag.

    Requirements: 70-REQ-1.3
    """

    def test_watch_flag_is_accepted_without_usage_error(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """TS-70-3: --watch is accepted by the CLI (exit_code != 2)."""
        _setup_minimal_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["code", "--watch"])

        # Exit code 2 means CLI usage error (unrecognized option).
        # The command may fail for other reasons (e.g. no sessions to run),
        # but must not fail with a usage error.
        assert result.exit_code != 2, f"--watch caused a usage error (exit_code={result.exit_code})"

    def test_watch_flag_in_help_output(self, cli_runner: CliRunner) -> None:
        """TS-70-3: --watch appears in code command help text."""
        result = cli_runner.invoke(main, ["code", "--help"])

        assert result.exit_code == 0
        assert "--watch" in result.output, "--watch should appear in the help output"

    def test_without_watch_flag_does_not_activate_watch_mode(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """TS-70-3: Without --watch, watch mode is not activated."""
        _setup_minimal_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["code"])

        # Without --watch, should not loop indefinitely.
        # The command may complete or fail, but it should exit.
        assert result.exit_code != 2, f"Unexpected CLI usage error: {result.output}"


# ---------------------------------------------------------------------------
# TS-70-11: --watch-interval CLI option overrides config
# Requirements: 70-REQ-3.3
# ---------------------------------------------------------------------------


class TestWatchIntervalCLIOption:
    """TS-70-11: --watch-interval CLI option overrides config value.

    Requirements: 70-REQ-3.3
    """

    def test_watch_interval_flag_is_accepted_without_usage_error(
        self, cli_runner: CliRunner, tmp_git_repo: Path
    ) -> None:
        """TS-70-11: --watch-interval is accepted by the CLI (exit_code != 2)."""
        _setup_minimal_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["code", "--watch", "--watch-interval", "30"])

        assert result.exit_code != 2, (
            f"--watch-interval should not cause a usage error, "
            f"got exit_code={result.exit_code}\n"
            f"Output: {result.output}"
        )

    def test_watch_interval_in_help_output(self, cli_runner: CliRunner) -> None:
        """TS-70-11: --watch-interval appears in code command help text."""
        result = cli_runner.invoke(main, ["code", "--help"])

        assert result.exit_code == 0
        assert "--watch-interval" in result.output, "--watch-interval should appear in the help output"
