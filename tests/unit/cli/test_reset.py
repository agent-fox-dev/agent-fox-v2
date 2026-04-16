"""CLI tests for reset command.

Test Spec: TS-07-E9
Requirement: 07-REQ-5.E2
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.reset import reset_cmd
from agent_fox.engine.state import ExecutionState


def _make_plan_json(nodes: dict[str, dict[str, str]]) -> str:
    """Build a minimal plan.json string."""
    full_nodes = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        full_nodes[nid] = {
            "id": nid,
            "spec_name": parts[0] if len(parts) > 1 else "test_spec",
            "group_number": int(parts[-1]) if parts[-1].isdigit() else 1,
            "title": props.get("title", f"Task {nid}"),
            "optional": False,
            "status": "pending",
            "subtask_count": 0,
            "body": "",
        }
    return json.dumps(
        {
            "metadata": {
                "created_at": "2026-01-01T00:00:00",
                "fast_mode": False,
                "filtered_spec": None,
                "version": "0.1.0",
            },
            "nodes": full_nodes,
            "edges": [],
            "order": list(nodes.keys()),
        }
    )


def _setup_project(tmp_path: Path, node_states: dict[str, str]) -> None:
    """Create .agent-fox directory with plan file (state loaded from DB mock)."""
    agent_dir = tmp_path / ".agent-fox"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "worktrees").mkdir()

    nodes = {tid: {"title": f"Task {tid}"} for tid in node_states}
    (agent_dir / "plan.json").write_text(_make_plan_json(nodes))


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
        mock_conn = MagicMock()

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=mock_conn),
            patch("agent_fox.engine.reset.load_state_from_db", return_value=state),
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
        mock_conn = MagicMock()

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
            patch("agent_fox.cli.reset._get_db_conn", return_value=mock_conn),
            patch("agent_fox.engine.reset.load_state_from_db", return_value=state),
        ):
            result = runner.invoke(reset_cmd, ["s:1"], catch_exceptions=False)

        assert "Nothing to reset" not in result.output
