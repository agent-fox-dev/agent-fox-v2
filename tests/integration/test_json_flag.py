"""Integration tests for the global --json flag.

Test Spec: TS-23-1 through TS-23-18, TS-23-21 through TS-23-23,
           TS-23-E1 through TS-23-E8
Requirements: 23-REQ-1.*, 23-REQ-2.*, 23-REQ-3.*, 23-REQ-4.*,
              23-REQ-5.*, 23-REQ-6.*, 23-REQ-8.*
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.reporting.standup import (
    AgentActivity,
    QueueSummary,
    StandupReport,
)


def _fake_asyncio_run(
    *,
    return_value: Any = None,
    side_effect: BaseException | None = None,
):
    """Create a fake asyncio.run that either returns a value or raises."""

    def _run(coro, **kwargs):  # noqa: ARG001
        coro.close()
        if side_effect is not None:
            raise side_effect
        return return_value

    return _run


def _make_standup_report(**overrides):
    """Create a minimal StandupReport dataclass for tests."""
    defaults = {
        "window_hours": 24,
        "window_start": "2026-03-04T12:00:00",
        "window_end": "2026-03-05T12:00:00",
        "task_activities": [],
        "agent_commits": [],
        "human_commits": [],
        "queue": QueueSummary(
            total=0,
            completed=0,
            in_progress=0,
            pending=0,
            ready=0,
            blocked=0,
            failed=0,
            ready_task_ids=[],
        ),
        "file_overlaps": [],
        "total_cost": 0.0,
        "agent": AgentActivity(
            tasks_completed=0,
            sessions_run=0,
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            completed_task_ids=[],
        ),
        "cost_breakdown": [],
    }
    defaults.update(overrides)
    return StandupReport(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a minimal project directory with .agent-fox structure."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    readme = repo / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create .agent-fox structure
    agent_dir = repo / ".agent-fox"
    agent_dir.mkdir()
    (agent_dir / "config.toml").write_text("")
    (agent_dir / "hooks").mkdir()
    (agent_dir / "worktrees").mkdir()

    original = os.getcwd()
    os.chdir(repo)
    yield repo
    os.chdir(original)


# ---------------------------------------------------------------------------
# TS-23-1: Global flag accessible to subcommands
# ---------------------------------------------------------------------------


class TestGlobalFlagAccepted:
    """TS-23-1: --json is accepted by the main group."""

    def test_global_flag_accepted(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """--json does not produce a Click usage error."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["--json", "standup"])
            # Exit code 2 means Click usage error
            assert result.exit_code != 2, f"--json caused usage error: {result.output}"


# ---------------------------------------------------------------------------
# TS-23-2: Default mode unchanged
# ---------------------------------------------------------------------------


class TestDefaultModeUnchanged:
    """TS-23-2: Without --json, output is human-readable."""

    def test_default_mode_is_not_json(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """Output without --json is not valid JSON."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["standup"])
            with pytest.raises(json.JSONDecodeError):
                json.loads(result.output)


# ---------------------------------------------------------------------------
# TS-23-3: Banner suppressed in JSON mode
# ---------------------------------------------------------------------------


class TestBannerSuppressed:
    """TS-23-3: Banner does not appear in JSON mode."""

    def test_banner_suppressed_json_mode(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """stdout does not contain banner markers."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["--json", "standup"])
            assert "/\\_/\\" not in result.output
            assert "agent-fox v" not in result.output


# ---------------------------------------------------------------------------
# TS-23-4: No non-JSON text on stdout
# ---------------------------------------------------------------------------


class TestNoNonJsonStdout:
    """TS-23-4: All stdout content is valid JSON in JSON mode."""

    def test_stdout_is_valid_json(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """json.loads(stdout) succeeds."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["--json", "standup"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-6: Standup command JSON output
# ---------------------------------------------------------------------------


class TestStandupJson:
    """TS-23-6: standup --json emits a JSON object."""

    def test_standup_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """standup with --json produces valid JSON."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["--json", "standup"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-7: Lint-spec command JSON output
# ---------------------------------------------------------------------------


class TestLintSpecJson:
    """TS-23-7: lint-specs --json emits findings as JSON."""

    def test_lint_spec_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """lint-specs with --json produces JSON with findings and summary."""
        # Create a minimal spec so lint-specs has something to process
        specs_dir = tmp_project / ".agent-fox" / "specs" / "01_test"
        specs_dir.mkdir(parents=True)
        (specs_dir / "prd.md").write_text("# PRD\n\nA test PRD.\n")
        (specs_dir / "requirements.md").write_text("# Requirements\n\n- 01-REQ-1: Test\n")
        (specs_dir / "design.md").write_text("# Design\n")
        (specs_dir / "test_spec.md").write_text("# Test Spec\n")
        (specs_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1.1 Do thing\n")

        result = cli_runner.invoke(main, ["--json", "lint-specs"])
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-9: Plan command JSON output
# ---------------------------------------------------------------------------


class TestPlanJson:
    """TS-23-9: plan --json emits JSON."""

    def test_plan_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """plan with --json produces valid JSON (even if error envelope)."""
        result = cli_runner.invoke(main, ["--json", "plan"])
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-11: Init command JSON output
# ---------------------------------------------------------------------------


class TestInitJson:
    """TS-23-11: init --json emits JSON."""

    def test_init_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """init with --json produces valid JSON."""
        result = cli_runner.invoke(main, ["--json", "init"])
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-13: Reset command JSON output
# ---------------------------------------------------------------------------


class TestResetJson:
    """TS-23-13: reset --json emits JSON."""

    def test_reset_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """reset --json with --all produces valid JSON."""
        with patch("agent_fox.cli.reset._do_reset") as mock_reset:
            mock_reset.return_value = {"tasks_reset": 0, "sessions_cleared": 0}
            result = cli_runner.invoke(main, ["--json", "reset", "--all"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-15: Code command JSONL streaming
# ---------------------------------------------------------------------------


class TestCodeJsonl:
    """TS-23-15: code --json emits JSONL stream."""

    def test_code_jsonl_streaming(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """code --json with immediate exit emits JSONL lines."""
        with (
            patch("agent_fox.ui.progress.ProgressDisplay"),
            patch(
                "agent_fox.cli.code.asyncio.run",
                side_effect=_fake_asyncio_run(return_value=None),
            ),
        ):
            # DB file is required for plan existence check
            db_path = tmp_project / ".agent-fox" / "knowledge.duckdb"
            db_path.write_text("")

            result = cli_runner.invoke(main, ["--json", "code"])
            for line in result.output.strip().splitlines():
                if line.strip():
                    data = json.loads(line)
                    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-16: Fix command JSONL streaming
# ---------------------------------------------------------------------------


class TestFixJsonl:
    """TS-23-16: fix --json emits JSONL stream."""

    def test_fix_jsonl_streaming(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """fix --json with immediate exit emits JSONL lines."""

        def _close_coro_and_return(coro, **kwargs):  # noqa: ARG001
            coro.close()
            return None

        with (
            patch("agent_fox.cli.fix.detect_checks") as mock_checks,
            patch("agent_fox.cli.fix.asyncio.run") as mock_run,
        ):
            mock_checks.return_value = [MagicMock()]
            mock_run.side_effect = _close_coro_and_return

            result = cli_runner.invoke(main, ["--json", "fix"])
            for line in result.output.strip().splitlines():
                if line.strip():
                    data = json.loads(line)
                    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-17: Error envelope in JSON mode
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    """TS-23-17: Command failure in JSON mode produces error envelope."""

    def test_error_envelope_on_failure(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """Failure emits {"error": "..."}."""
        # plan with no .specs/ should fail
        result = cli_runner.invoke(main, ["--json", "plan"])
        data = json.loads(result.output)
        assert "error" in data
        assert isinstance(data["error"], str)

    def test_no_unstructured_text_on_error(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """No unstructured text mixed into error output."""
        result = cli_runner.invoke(main, ["--json", "plan"])
        # Every line should be valid JSON
        for line in result.output.strip().splitlines():
            if line.strip():
                json.loads(line)


# ---------------------------------------------------------------------------
# TS-23-18: Exit code preserved in JSON mode
# ---------------------------------------------------------------------------


class TestExitCodePreserved:
    """TS-23-18: Exit codes are the same with and without --json."""

    def test_exit_code_preserved(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """Same failing command has same exit code with and without --json."""
        result_text = cli_runner.invoke(main, ["plan"])
        result_json = cli_runner.invoke(main, ["--json", "plan"])
        assert result_text.exit_code == result_json.exit_code


# ---------------------------------------------------------------------------
# TS-23-22: --format removed from standup
# ---------------------------------------------------------------------------


class TestFormatRemovedStandup:
    """TS-23-22: standup --format json produces Click usage error."""

    def test_format_removed_standup(self, cli_runner: CliRunner) -> None:
        """standup --format json exits with code 2."""
        result = cli_runner.invoke(main, ["standup", "--format", "json"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# TS-23-23: --format removed from lint-spec
# ---------------------------------------------------------------------------


class TestFormatRemovedLintSpec:
    """TS-23-23: lint-specs --format json produces Click usage error."""

    def test_format_removed_lint_spec(self, cli_runner: CliRunner) -> None:
        """lint-specs --format json exits with code 2."""
        result = cli_runner.invoke(main, ["lint-specs", "--format", "json"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# TS-23-E1: --json with --verbose
# ---------------------------------------------------------------------------


class TestJsonWithVerbose:
    """TS-23-E1: --json --verbose produces JSON output."""

    def test_json_with_verbose(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """--json --verbose still produces valid JSON on stdout."""
        import logging

        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            # Suppress logging output that leaks into CliRunner's captured stdout
            logging.disable(logging.CRITICAL)
            try:
                result = cli_runner.invoke(main, ["--json", "--verbose", "standup"])
            finally:
                logging.disable(logging.NOTSET)
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-E2: Logs go to stderr in JSON mode
# ---------------------------------------------------------------------------


class TestLogsToStderr:
    """TS-23-E2: Log messages go to stderr, not stdout."""

    def test_logs_to_stderr_json_mode(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """stdout contains only JSON — no log lines."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.return_value = _make_standup_report()
            result = cli_runner.invoke(main, ["--json", "standup"])
            # stdout must be pure JSON
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-E3: Empty data produces valid JSON
# ---------------------------------------------------------------------------


class TestEmptyDataValidJson:
    """TS-23-E3: Command with no data emits valid JSON."""

    def test_empty_data_valid_json(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """plan with empty specs still emits valid JSON."""
        # No .specs/ directory exists -> should produce error envelope or empty
        result = cli_runner.invoke(main, ["--json", "plan"])
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-E4: Streaming interrupted
# ---------------------------------------------------------------------------


class TestStreamingInterrupted:
    """TS-23-E4: Interrupted streaming emits final status object."""

    def test_code_interrupted_emits_status(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """code --json interrupted by KeyboardInterrupt emits status."""
        with (
            patch("agent_fox.ui.progress.ProgressDisplay"),
            patch(
                "agent_fox.cli.code.asyncio.run",
                side_effect=_fake_asyncio_run(side_effect=KeyboardInterrupt()),
            ),
        ):

            # DB file is required for plan existence check
            db_path = tmp_project / ".agent-fox" / "knowledge.duckdb"
            db_path.write_text("")

            result = cli_runner.invoke(main, ["--json", "code"])
            last_line = result.output.strip().splitlines()[-1]
            data = json.loads(last_line)
            assert data["status"] == "interrupted"

    def test_fix_interrupted_emits_status(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """fix --json interrupted by KeyboardInterrupt emits status."""

        def _close_coro_and_raise(coro, **kwargs):  # noqa: ARG001
            """Close the coroutine to avoid 'never awaited' warning."""
            coro.close()
            raise KeyboardInterrupt

        with (
            patch("agent_fox.cli.fix.detect_checks") as mock_checks,
            patch("agent_fox.cli.fix.asyncio.run") as mock_run,
        ):
            mock_checks.return_value = [MagicMock()]
            mock_run.side_effect = _close_coro_and_raise

            result = cli_runner.invoke(main, ["--json", "fix"])
            last_line = result.output.strip().splitlines()[-1]
            data = json.loads(last_line)
            assert data["status"] == "interrupted"


# ---------------------------------------------------------------------------
# TS-23-E5: Unhandled exception in JSON mode
# ---------------------------------------------------------------------------


class TestUnhandledExceptionEnvelope:
    """TS-23-E5: Unhandled exceptions produce error envelope in JSON mode."""

    def test_unhandled_exception_envelope(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """Unexpected exception produces {"error": "..."}."""
        with patch("agent_fox.cli.standup.generate_standup") as mock_gen:
            mock_gen.side_effect = RuntimeError("unexpected boom")
            result = cli_runner.invoke(main, ["--json", "standup"])
            data = json.loads(result.output)
            assert "error" in data
            assert result.exit_code == 1
