"""CLI tests for reset command.

Test Spec: TS-07-E9
Requirement: 07-REQ-5.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from agent_fox.cli.reset import reset_cmd
from agent_fox.engine.state import ExecutionState
from tests.unit.engine.conftest import write_plan_to_db


def _setup_project(tmp_path: Path, node_states: dict[str, str]) -> None:
    """Create .agent-fox directory structure (state loaded from DB mock)."""
    agent_dir = tmp_path / ".agent-fox"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "worktrees").mkdir()


class TestResetCompletedTaskCLI:
    """CLI-level test for 07-REQ-5.E2: user-visible warning on completed task."""

    def test_completed_task_prints_warning(self, tmp_path: Path) -> None:
        """Resetting a completed task prints a user-facing warning."""
        node_states = {"s:1": "completed"}
        _setup_project(tmp_path, node_states)

        state = ExecutionState(
            plan_hash="abc123",
            node_states=node_states,
            started_at="2026-03-01T09:00:00Z",
            updated_at="2026-03-01T10:00:00Z",
        )
        nodes = {tid: {"title": f"Task {tid}"} for tid in node_states}
        db_conn = write_plan_to_db(nodes, [])

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=db_conn),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = runner.invoke(reset_cmd, ["s:1"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Completed tasks cannot be reset" in result.output

    def test_completed_task_no_generic_message(self, tmp_path: Path) -> None:
        """Completed task warning replaces the generic 'Nothing to reset'."""
        node_states = {"s:1": "completed"}
        _setup_project(tmp_path, node_states)

        state = ExecutionState(
            plan_hash="abc123",
            node_states=node_states,
            started_at="2026-03-01T09:00:00Z",
            updated_at="2026-03-01T10:00:00Z",
        )
        nodes = {tid: {"title": f"Task {tid}"} for tid in node_states}
        db_conn = write_plan_to_db(nodes, [])

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=db_conn),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = runner.invoke(reset_cmd, ["s:1"], catch_exceptions=False)

        assert "Nothing to reset" not in result.output
