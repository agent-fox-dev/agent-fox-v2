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
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.reporting.standup import (
    AgentActivity,
    QueueSummary,
    StandupReport,
)
from agent_fox.reporting.status import StatusReport


def _make_status_report(**overrides):
    """Create a minimal StatusReport dataclass for tests."""
    defaults = {
        "counts": {"completed": 0, "in_progress": 0, "pending": 0, "failed": 0},
        "total_tasks": 0,
        "memory_total": 0,
        "memory_by_category": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0.0,
        "problem_tasks": [],
        "per_spec": {},
    }
    defaults.update(overrides)
    return StatusReport(**defaults)  # type: ignore[arg-type]


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
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["--json", "status"])
            # Exit code 2 means Click usage error
            assert result.exit_code != 2, f"--json caused usage error: {result.output}"


# ---------------------------------------------------------------------------
# TS-23-2: Default mode unchanged
# ---------------------------------------------------------------------------


class TestDefaultModeUnchanged:
    """TS-23-2: Without --json, output is human-readable."""

    def test_default_mode_is_not_json(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """Output without --json is not valid JSON."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["status"])
            with pytest.raises(json.JSONDecodeError):
                json.loads(result.output)


# ---------------------------------------------------------------------------
# TS-23-3: Banner suppressed in JSON mode
# ---------------------------------------------------------------------------


class TestBannerSuppressed:
    """TS-23-3: Banner does not appear in JSON mode."""

    def test_banner_suppressed_json_mode(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """stdout does not contain banner markers."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["--json", "status"])
            assert "/\\_/\\" not in result.output
            assert "agent-fox v" not in result.output


# ---------------------------------------------------------------------------
# TS-23-4: No non-JSON text on stdout
# ---------------------------------------------------------------------------


class TestNoNonJsonStdout:
    """TS-23-4: All stdout content is valid JSON in JSON mode."""

    def test_stdout_is_valid_json(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """json.loads(stdout) succeeds."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["--json", "status"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-5: Status command JSON output
# ---------------------------------------------------------------------------


class TestStatusJson:
    """TS-23-5: status --json emits a JSON object."""

    def test_status_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """status with --json produces valid JSON."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report(
                counts={"completed": 2, "in_progress": 1, "pending": 3, "failed": 0},
                total_tasks=6,
                memory_total=10,
                memory_by_category={"pattern": 5, "decision": 5},
                input_tokens=1500,
                output_tokens=500,
                estimated_cost=0.05,
            )
            result = cli_runner.invoke(main, ["--json", "status"])
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
        specs_dir = tmp_project / ".specs"
        specs_dir.mkdir()
        spec_dir = specs_dir / "01_test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text(
            "# Requirements\n\n## Requirement 1\n\n1. [01-REQ-1.1] THE system SHALL do something.\n"
        )
        (spec_dir / "design.md").write_text("# Design\n\n## Overview\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task one\n")
        (spec_dir / "test_spec.md").write_text("# Test Spec\n")

        result = cli_runner.invoke(main, ["--json", "lint-specs"])
        data = json.loads(result.output)
        assert "findings" in data
        assert "summary" in data


# ---------------------------------------------------------------------------
# TS-23-8: Plan command JSON output
# ---------------------------------------------------------------------------


class TestPlanJson:
    """TS-23-8: plan --json emits the execution plan as JSON."""

    def test_plan_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """plan with --json produces valid JSON."""
        # Create a minimal spec with tasks
        specs_dir = tmp_project / ".specs"
        specs_dir.mkdir()
        spec_dir = specs_dir / "01_test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")
        (spec_dir / "design.md").write_text("# Design\n")
        (spec_dir / "test_spec.md").write_text("# Tests\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1. First task\n  - [ ] 1.1 Subtask\n")

        result = cli_runner.invoke(main, ["--json", "plan"])
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-12: Init command JSON output
# ---------------------------------------------------------------------------


class TestInitJson:
    """TS-23-12: init --json emits {"status": "ok"}."""

    def test_init_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """init with --json produces {"status": "ok"}."""
        with patch("agent_fox.workspace.init_project._ensure_develop_branch"):
            result = cli_runner.invoke(main, ["--json", "init"])
            data = json.loads(result.output)
            assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# TS-23-13: Reset command JSON output
# ---------------------------------------------------------------------------


class TestResetJson:
    """TS-23-13: reset --json emits a JSON summary."""

    def test_reset_json_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """reset with --json produces valid JSON."""
        with patch("agent_fox.cli.reset.reset_all") as mock_reset:
            mock_reset.return_value = MagicMock(
                reset_tasks=["task1"],
                unblocked_tasks=["task2"],
                cleaned_worktrees=[],
                cleaned_branches=[],
                skipped_completed=False,
            )
            result = cli_runner.invoke(main, ["--json", "reset", "--yes"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-14: Code command JSONL output
# ---------------------------------------------------------------------------


class TestCodeJsonl:
    """TS-23-14: code --json emits JSONL."""

    def test_code_jsonl_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """code with --json produces JSONL (one JSON object per line)."""
        mock_state = MagicMock(
            node_states={"task1": "completed"},
            total_input_tokens=1000,
            total_output_tokens=500,
            total_cost=0.05,
            run_status="completed",
        )

        async def _fake_run_code(*args, **kwargs):
            return mock_state

        with (
            patch("agent_fox.cli.code.run_code", side_effect=_fake_run_code),
            patch("agent_fox.ui.progress.ProgressDisplay"),
        ):
            # Plan file is required
            plan_path = tmp_project / ".agent-fox" / "plan.json"
            plan_path.write_text('{"nodes": {}, "edges": [], "metadata": {}}')

            result = cli_runner.invoke(main, ["--json", "code"])
            lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
            for line in lines:
                data = json.loads(line)
                assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-16: Fix command JSONL output
# ---------------------------------------------------------------------------


class TestFixJsonl:
    """TS-23-16: fix --json emits JSONL events."""

    def test_fix_jsonl_output(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """fix with --json produces JSONL lines."""
        from agent_fox.fix.fix import TerminationReason

        mock_result = MagicMock(
            termination_reason=TerminationReason.ALL_FIXED,
            passes=[],
            total_cost=0.0,
        )
        with (
            patch("agent_fox.cli.fix.detect_checks") as mock_checks,
            patch("agent_fox.cli.fix.asyncio.run") as mock_run,
            patch("agent_fox.cli.fix.render_fix_report"),
        ):
            mock_checks.return_value = [MagicMock()]
            mock_run.return_value = mock_result

            result = cli_runner.invoke(main, ["--json", "fix"])
            lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
            for line in lines:
                data = json.loads(line)
                assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-17: Error envelope on failure
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
# TS-23-21: --format removed from status
# ---------------------------------------------------------------------------


class TestFormatRemovedStatus:
    """TS-23-21: status --format json produces Click usage error."""

    def test_format_removed_status(self, cli_runner: CliRunner) -> None:
        """status --format json exits with code 2."""
        result = cli_runner.invoke(main, ["status", "--format", "json"])
        assert result.exit_code == 2


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
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["--json", "--verbose", "status"])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-E2: Logs go to stderr in JSON mode
# ---------------------------------------------------------------------------


class TestLogsToStderr:
    """TS-23-E2: Log messages go to stderr, not stdout."""

    def test_logs_to_stderr_json_mode(self, cli_runner: CliRunner, tmp_project: Path) -> None:
        """stdout contains only JSON — no log lines."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.return_value = _make_status_report()
            result = cli_runner.invoke(main, ["--json", "status"])
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
            patch("agent_fox.cli.code.asyncio.run") as mock_run,
        ):
            mock_run.side_effect = KeyboardInterrupt()

            plan_path = tmp_project / ".agent-fox" / "plan.json"
            plan_path.write_text('{"nodes": {}, "edges": [], "metadata": {}}')

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
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.side_effect = RuntimeError("unexpected boom")
            result = cli_runner.invoke(main, ["--json", "status"])
            data = json.loads(result.output)
            assert "error" in data
            assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TS-23-E8: --format produces usage error
# ---------------------------------------------------------------------------


class TestFormatUsageError:
    """TS-23-E8: Removed --format flag produces Click usage error."""

    def test_format_yaml_usage_error(self, cli_runner: CliRunner) -> None:
        """status --format yaml exits with code 2."""
        result = cli_runner.invoke(main, ["status", "--format", "yaml"])
        assert result.exit_code == 2
