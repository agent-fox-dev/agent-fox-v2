"""CLI tests for spec-scoped reset (--spec option).

Test Spec: TS-50-8 through TS-50-11
Requirements: 50-REQ-2.1, 50-REQ-2.2, 50-REQ-3.1, 50-REQ-3.2, 50-REQ-3.4
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from agent_fox.cli.reset import reset_cmd
from agent_fox.engine.state import ExecutionState, StateManager


def _make_plan_json(nodes: dict[str, dict[str, str]]) -> str:
    """Build a minimal plan.json string."""
    full_nodes = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        full_nodes[nid] = {
            "id": nid,
            "spec_name": props.get("spec_name", parts[0] if len(parts) > 1 else "test_spec"),
            "group_number": int(parts[-1]) if parts[-1].isdigit() else 0,
            "title": props.get("title", f"Task {nid}"),
            "optional": False,
            "status": props.get("status", "pending"),
            "subtask_count": 0,
            "body": "",
            "archetype": props.get("archetype", "coder"),
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


def _setup_project(
    tmp_path: Path,
    node_states: dict[str, str],
    nodes: dict[str, dict[str, str]] | None = None,
) -> None:
    """Create .agent-fox directory with plan and state files."""
    agent_dir = tmp_path / ".agent-fox"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "worktrees").mkdir()

    if nodes is None:
        nodes = {tid: {"title": f"Task {tid}"} for tid in node_states}
    (agent_dir / "plan.json").write_text(_make_plan_json(nodes))

    state = ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )
    StateManager(agent_dir / "state.jsonl").save(state)


# ---------------------------------------------------------------------------
# TS-50-8: Mutual exclusivity with --hard
# Requirement: 50-REQ-2.1
# ---------------------------------------------------------------------------


class TestMutualExclusivityHard:
    """TS-50-8: --spec combined with --hard produces an error."""

    def test_spec_and_hard_error(self, tmp_path: Path) -> None:
        """Non-zero exit and mutually exclusive error message."""
        _setup_project(tmp_path, {"alpha:1": "completed"})

        runner = CliRunner()
        with patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path):
            result = runner.invoke(
                reset_cmd, ["--spec", "alpha", "--hard"], catch_exceptions=False
            )

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
        _setup_project(tmp_path, {"alpha:1": "completed"})

        runner = CliRunner()
        with patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path):
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
        _setup_project(tmp_path, {"alpha:1": "completed"})

        runner = CliRunner()
        with patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path):
            result = runner.invoke(
                reset_cmd, ["--spec", "alpha"], input="n\n", catch_exceptions=False
            )

        # State should be unchanged
        state = StateManager(tmp_path / ".agent-fox" / "state.jsonl").load()
        assert state is not None
        assert state.node_states["alpha:1"] == "completed"


# ---------------------------------------------------------------------------
# TS-50-11: JSON output
# Requirement: 50-REQ-3.4
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """TS-50-11: JSON mode outputs structured result."""

    def test_json_output_keys(self, tmp_path: Path) -> None:
        """Valid JSON with required keys."""
        _setup_project(tmp_path, {"alpha:1": "completed"})

        # Create specs dir for tasks.md checkbox reset
        specs_dir = tmp_path / ".specs" / "alpha"
        specs_dir.mkdir(parents=True)
        (specs_dir / "tasks.md").write_text("- [x] 1. Task\n")

        runner = CliRunner()
        with (
            patch("agent_fox.cli.reset.Path.cwd", return_value=tmp_path),
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
