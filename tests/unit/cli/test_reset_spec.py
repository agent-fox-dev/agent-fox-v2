"""CLI tests for spec-scoped reset (--spec option).

Test Spec: TS-50-8 through TS-50-11
Requirements: 50-REQ-2.1, 50-REQ-2.2, 50-REQ-3.1, 50-REQ-3.2, 50-REQ-3.4
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.reset import reset_cmd
from agent_fox.engine.state import ExecutionState
from tests.unit.engine.conftest import write_plan_to_db


def _setup_project(
    tmp_path: Path,
    node_states: dict[str, str],
    nodes: dict[str, dict[str, str]] | None = None,
) -> None:
    """Create .agent-fox directory structure (state loaded from DB mock)."""
    agent_dir = tmp_path / ".agent-fox"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "worktrees").mkdir()


def _make_state(node_states: dict[str, str]) -> ExecutionState:
    """Create an ExecutionState for test mocking."""
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# TS-50-8: Mutual exclusivity with --hard
# Requirement: 50-REQ-2.1
# ---------------------------------------------------------------------------


class TestMutualExclusivityHard:
    """TS-50-8: --spec combined with --hard produces an error."""

    def test_spec_and_hard_error(self, tmp_path: Path) -> None:
        """Non-zero exit and mutually exclusive error message."""
        node_states = {"alpha:1": "completed"}
        _setup_project(tmp_path, node_states)

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=MagicMock()),
            patch("agent_fox.engine.reset.load_state_from_db", return_value=_make_state(node_states)),
        ):
            result = runner.invoke(reset_cmd, ["--spec", "alpha", "--hard"], catch_exceptions=False)

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()


# ---------------------------------------------------------------------------
# TS-50-9: Mutual exclusivity with task_id
# Requirement: 50-REQ-2.2
# ---------------------------------------------------------------------------


class TestMutualExclusivityTaskId:
    """TS-50-9: --spec combined with a positional task_id produces an error."""

    def test_spec_and_task_id_error(self, tmp_path: Path) -> None:
        """Non-zero exit and mutually exclusive error message."""
        node_states = {"alpha:1": "completed"}
        _setup_project(tmp_path, node_states)

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=MagicMock()),
            patch("agent_fox.engine.reset.load_state_from_db", return_value=_make_state(node_states)),
        ):
            result = runner.invoke(
                reset_cmd,
                ["--spec", "alpha", "alpha:1"],
                catch_exceptions=False,
            )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()


# ---------------------------------------------------------------------------
# TS-50-10: Confirmation required
# Requirement: 50-REQ-3.1, 50-REQ-3.2
# ---------------------------------------------------------------------------


class TestConfirmationRequired:
    """TS-50-10: Without --yes, confirmation is prompted."""

    def test_decline_aborts(self, tmp_path: Path) -> None:
        """Declining confirmation leaves state unchanged."""
        node_states = {"alpha:1": "completed"}
        _setup_project(tmp_path, node_states)
        state = _make_state(node_states)

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=MagicMock()),
            patch("agent_fox.engine.reset.load_state_from_db", return_value=state),
        ):
            runner.invoke(reset_cmd, ["--spec", "alpha"], input="n\n", catch_exceptions=False)

        # State should be unchanged (decline aborts before modifying)
        assert state.node_states["alpha:1"] == "completed"


# ---------------------------------------------------------------------------
# TS-50-11: JSON output
# Requirement: 50-REQ-3.4
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """TS-50-11: JSON mode outputs structured result."""

    def test_json_output_keys(self, tmp_path: Path) -> None:
        """Valid JSON with required keys."""
        node_states = {"alpha:1": "completed"}
        nodes = {"alpha:1": {"title": "Task alpha:1", "spec_name": "alpha"}}
        _setup_project(tmp_path, node_states, nodes=nodes)

        # Create specs dir for tasks.md checkbox reset
        specs_dir = tmp_path / ".specs" / "alpha"
        specs_dir.mkdir(parents=True)
        (specs_dir / "tasks.md").write_text("- [x] 1. Task\n")

        db_conn = write_plan_to_db(nodes, [])

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=db_conn),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=_make_state(node_states)),
            patch(
                "agent_fox.engine.reset._cleanup_task",
                return_value=(None, None),
            ),
        ):
            # Pass --json via ctx.obj
            result = runner.invoke(
                reset_cmd,
                ["--spec", "alpha"],
                catch_exceptions=False,
                obj={"json": True},
            )

        data = json.loads(result.output)
        assert "reset_tasks" in data
        assert "cleaned_worktrees" in data
        assert "cleaned_branches" in data
