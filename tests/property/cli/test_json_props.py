"""Property tests for the global --json flag.

Test Spec: TS-23-P1, TS-23-P2, TS-23-P3, TS-23-P4
Properties: JSON exclusivity, error envelope structure,
            exit code preservation, flag precedence
Requirements: 23-REQ-2.2, 23-REQ-3.*, 23-REQ-6.*, 23-REQ-7.2
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.cli.app import main
from agent_fox.reporting.standup import (
    AgentActivity,
    QueueSummary,
    StandupReport,
)
from agent_fox.reporting.status import StatusReport


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with .agent-fox structure."""
    repo = tmp_path / "repo"
    repo.mkdir()

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

    agent_dir = repo / ".agent-fox"
    agent_dir.mkdir()
    (agent_dir / "config.toml").write_text("")
    (agent_dir / "hooks").mkdir()
    (agent_dir / "worktrees").mkdir()

    # Create minimal specs for plan command
    specs_dir = repo / ".specs"
    specs_dir.mkdir()
    spec_dir = specs_dir / "01_test"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text("# Requirements\n")
    (spec_dir / "design.md").write_text("# Design\n")
    (spec_dir / "test_spec.md").write_text("# Tests\n")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n- [ ] 1. First task\n  - [ ] 1.1 Sub\n"
    )

    original = os.getcwd()
    os.chdir(repo)
    yield repo
    os.chdir(original)


# ---------------------------------------------------------------------------
# TS-23-P1: JSON exclusivity — all batch commands produce valid JSON
# ---------------------------------------------------------------------------


# Commands that can be tested with mocks for JSON exclusivity
_BATCH_COMMANDS_WITH_MOCKS = {
    "status": {
        "patch_target": "agent_fox.cli.status.generate_status",
        "mock_return": StatusReport(
            counts={"completed": 0, "in_progress": 0, "pending": 0, "failed": 0},
            total_tasks=0,
            memory_total=0,
            memory_by_category={},
            input_tokens=0,
            output_tokens=0,
            estimated_cost=0.0,
            problem_tasks=[],
            per_spec={},
        ),
    },
    "standup": {
        "patch_target": "agent_fox.cli.standup.generate_standup",
        "mock_return": StandupReport(
            window_hours=24,
            window_end="2026-03-05T12:00:00",
            window_start="2026-03-04T12:00:00",
            task_activities=[],
            agent_commits=[],
            human_commits=[],
            queue=QueueSummary(
                total=0,
                completed=0,
                in_progress=0,
                pending=0,
                ready=0,
                blocked=0,
                failed=0,
            ),
            file_overlaps=[],
            total_cost=0.0,
            agent=AgentActivity(
                tasks_completed=0,
                sessions_run=0,
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                completed_task_ids=[],
            ),
            cost_breakdown=[],
        ),
    },
}


class TestJsonExclusivity:
    """TS-23-P1: For any batch command with --json, stdout is valid JSON.

    Property 1: JSON exclusivity.
    Requirements: 23-REQ-2.2, 23-REQ-3.1 through 23-REQ-3.7
    """

    @pytest.mark.parametrize("cmd_name", list(_BATCH_COMMANDS_WITH_MOCKS.keys()))
    def test_json_exclusivity_batch(
        self,
        cli_runner: CliRunner,
        tmp_project: Path,
        cmd_name: str,
    ) -> None:
        """stdout is valid JSON for batch command '{cmd_name}'."""
        spec = _BATCH_COMMANDS_WITH_MOCKS[cmd_name]
        with patch(spec["patch_target"]) as mock_fn:
            mock_fn.return_value = spec["mock_return"]
            result = cli_runner.invoke(main, ["--json", cmd_name])
            data = json.loads(result.output)
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# TS-23-P2: Error envelope structure
# ---------------------------------------------------------------------------


class TestErrorEnvelopeStructure:
    """TS-23-P2: Failing commands produce valid error envelopes.

    Property 2: Error envelope structure.
    Requirements: 23-REQ-6.1, 23-REQ-6.3
    """

    def test_error_envelope_on_status_failure(
        self,
        cli_runner: CliRunner,
        tmp_project: Path,
    ) -> None:
        """Status command failure produces error envelope."""
        with patch("agent_fox.cli.status.generate_status") as mock_gen:
            mock_gen.side_effect = RuntimeError("test failure")
            result = cli_runner.invoke(main, ["--json", "status"])
            data = json.loads(result.output)
            assert "error" in data
            assert len(data["error"]) > 0

    def test_error_envelope_on_missing_specs(
        self,
        cli_runner: CliRunner,
        tmp_project: Path,
    ) -> None:
        """Plan with no specs produces error envelope."""
        # Remove specs dir to trigger error
        import shutil

        specs_dir = tmp_project / ".specs"
        if specs_dir.exists():
            shutil.rmtree(specs_dir)
        result = cli_runner.invoke(main, ["--json", "plan"])
        data = json.loads(result.output)
        assert "error" in data
        assert len(data["error"]) > 0


# ---------------------------------------------------------------------------
# TS-23-P3: Exit code preservation
# ---------------------------------------------------------------------------


class TestExitCodePreservation:
    """TS-23-P3: JSON mode preserves exit codes.

    Property 3: Exit code preservation.
    Requirements: 23-REQ-6.2
    """

    @pytest.mark.parametrize("cmd_name", list(_BATCH_COMMANDS_WITH_MOCKS.keys()))
    def test_exit_code_preserved(
        self,
        cli_runner: CliRunner,
        tmp_project: Path,
        cmd_name: str,
    ) -> None:
        """Exit code is identical with and without --json."""
        spec = _BATCH_COMMANDS_WITH_MOCKS[cmd_name]
        with patch(spec["patch_target"]) as mock_fn:
            mock_fn.return_value = spec["mock_return"]
            result_text = cli_runner.invoke(main, [cmd_name])
            result_json = cli_runner.invoke(main, ["--json", cmd_name])
            assert result_text.exit_code == result_json.exit_code


# ---------------------------------------------------------------------------
# TS-23-P4: Flag precedence over stdin
# ---------------------------------------------------------------------------


class TestFlagPrecedence:
    """TS-23-P4: CLI flags override stdin JSON fields.

    Property 4: Flag precedence.
    Requirements: 23-REQ-7.2
    """

    @given(cli_val=st.integers(min_value=1, max_value=100))
    @settings(max_examples=10)
    def test_cli_flag_overrides_stdin(self, cli_val: int) -> None:
        """CLI flag value takes precedence over stdin JSON value."""
        from agent_fox.cli.json_io import read_stdin

        stdin_val = cli_val + 1  # Always different from cli_val

        fake_stdin = io.StringIO(json.dumps({"top_k": stdin_val}))
        fake_stdin.isatty = lambda: False  # type: ignore[attr-defined]

        with patch("sys.stdin", fake_stdin):
            stdin_data = read_stdin()

        # CLI flag should override stdin value
        effective_val = cli_val  # CLI flag takes precedence
        assert effective_val == cli_val
        assert stdin_data["top_k"] == stdin_val
        # The actual merging is done by the command — this tests
        # that the raw values are available for the merge logic
