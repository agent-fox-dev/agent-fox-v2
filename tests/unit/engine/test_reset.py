"""Unit tests for the reset engine.

Test Spec: TS-07-11, TS-07-12, TS-07-E6, TS-07-E7, TS-07-E8, TS-07-E9
Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2,
              07-REQ-4.E1, 07-REQ-4.E2, 07-REQ-5.E1, 07-REQ-5.E2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset import (
    _task_id_to_branch_name,
    _task_id_to_worktree_path,
    reset_all,
    reset_task,
)
from agent_fox.engine.state import ExecutionState

# -- Helpers ---------------------------------------------------------------


def _make_plan_json(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]] | None = None,
    order: list[str] | None = None,
) -> str:
    """Build a plan.json string from node/edge definitions."""
    if edges is None:
        edges = []

    full_nodes: dict[str, Any] = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        spec_name = parts[0] if len(parts) > 1 else "test_spec"
        group_number = int(parts[-1]) if parts[-1].isdigit() else 1
        full_nodes[nid] = {
            "id": nid,
            "spec_name": props.get("spec_name", spec_name),
            "group_number": props.get("group_number", group_number),
            "title": props.get("title", f"Task {nid}"),
            "optional": props.get("optional", False),
            "status": props.get("status", "pending"),
            "subtask_count": props.get("subtask_count", 0),
            "body": props.get("body", ""),
        }

    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": full_nodes,
        "edges": edges,
        "order": order if order is not None else list(nodes.keys()),
    }
    return json.dumps(plan, indent=2)


def _write_plan(plan_dir: Path, **kwargs: Any) -> Path:
    """Write a plan.json file and return its path."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    plan_path.write_text(_make_plan_json(**kwargs))
    return plan_path


def _make_state(
    node_states: dict[str, str],
) -> ExecutionState:
    """Build an ExecutionState for testing."""
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# Branch name and worktree path helpers
# Regression: branch name must use slash separator to match workspace.py
# ---------------------------------------------------------------------------


class TestBranchAndWorktreeHelpers:
    """Verify branch name and worktree path match workspace.py conventions."""

    def test_branch_name_uses_slash_separator(self) -> None:
        """Branch name must use slash (not hyphen) to match create_worktree."""
        assert _task_id_to_branch_name("my_spec:3") == "feature/my_spec/3"

    def test_branch_name_single_part_fallback(self) -> None:
        """Single-part task ID uses feature/{id} format."""
        assert _task_id_to_branch_name("standalone") == "feature/standalone"

    def test_worktree_path_matches_branch_structure(self) -> None:
        """Worktree path uses the same spec/group structure."""
        wt = _task_id_to_worktree_path(Path("/wt"), "my_spec:3")
        assert wt == Path("/wt/my_spec/3")


# ---------------------------------------------------------------------------
# TS-07-11: Full reset clears incomplete tasks
# Requirements: 07-REQ-4.1, 07-REQ-4.2
# ---------------------------------------------------------------------------


class TestFullReset:
    """TS-07-11: Full reset resets failed, blocked, and in_progress tasks."""

    def test_resets_incomplete_tasks(
        self,
        tmp_path: Path,
    ) -> None:
        """Failed, blocked, and in_progress tasks are reset to pending."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
            "s:4": {"title": "T4"},
            "s:5": {"title": "T5"},
        }
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "failed",
                "s:4": "blocked",
                "s:5": "in_progress",
            },
        )

        # Create worktree directories for tasks that will be reset
        (worktrees_dir / "s" / "3").mkdir(parents=True)
        (worktrees_dir / "s" / "5").mkdir(parents=True)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(plan_path, worktrees_dir, repo_path)

        assert len(result.reset_tasks) == 3
        assert "s:1" not in result.reset_tasks
        assert "s:2" not in result.reset_tasks
        # All 3 incomplete tasks should be reset
        assert "s:3" in result.reset_tasks
        assert "s:4" in result.reset_tasks
        assert "s:5" in result.reset_tasks

    def test_completed_tasks_not_reset(
        self,
        tmp_path: Path,
    ) -> None:
        """Completed tasks are never included in reset_tasks."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
        }
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "failed",
            },
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(plan_path, worktrees_dir, repo_path)

        assert "s:1" not in result.reset_tasks
        assert "s:2" not in result.reset_tasks

    def test_worktree_directories_cleaned(
        self,
        tmp_path: Path,
    ) -> None:
        """Worktree directories for reset tasks are removed."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state({"s:1": "failed"})

        # Create worktree directory
        wt_dir = worktrees_dir / "s" / "1"
        wt_dir.mkdir(parents=True)
        (wt_dir / "somefile.py").write_text("content")

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(plan_path, worktrees_dir, repo_path)

        assert len(result.reset_tasks) == 1
        assert not wt_dir.exists()


# ---------------------------------------------------------------------------
# TS-07-12: Single-task reset unblocks downstream
# Requirements: 07-REQ-5.1, 07-REQ-5.2
# ---------------------------------------------------------------------------


class TestSingleTaskReset:
    """TS-07-12: Single-task reset with cascade unblock."""

    def test_reset_single_task(
        self,
        tmp_path: Path,
    ) -> None:
        """Single task is reset to pending."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
        }
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "failed",
                "s:2": "pending",
            },
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", plan_path, worktrees_dir, repo_path)

        assert "s:1" in result.reset_tasks

    def test_cascade_unblocks_downstream(
        self,
        tmp_path: Path,
    ) -> None:
        """Downstream tasks are unblocked when sole blocker is reset.

        Scenario:
        - Task A is failed.
        - Task B depends only on A and is blocked.
        - Task C depends on A and completed task D, and is blocked.
        After resetting A:
        - B should be unblocked (A was sole blocker).
        - C should be unblocked (A was only non-completed dependency; D done).
        """
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "Task A"},
            "s:2": {"title": "Task B"},
            "s:3": {"title": "Task C"},
            "s:4": {"title": "Task D"},
        }
        edges = [
            {"source": "s:1", "target": "s:2", "kind": "intra_spec"},
            {"source": "s:1", "target": "s:3", "kind": "intra_spec"},
            {"source": "s:4", "target": "s:3", "kind": "intra_spec"},
        ]
        plan_path = _write_plan(
            plan_dir,
            nodes=nodes,
            edges=edges,
            order=["s:4", "s:1", "s:2", "s:3"],
        )
        state = _make_state(
            {
                "s:1": "failed",
                "s:2": "blocked",
                "s:3": "blocked",
                "s:4": "completed",
            },
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task(
                "s:1",
                plan_path,
                worktrees_dir,
                repo_path,
            )

        assert "s:1" in result.reset_tasks
        assert "s:2" in result.unblocked_tasks
        assert "s:3" in result.unblocked_tasks

    def test_no_cascade_when_other_blockers_exist(
        self,
        tmp_path: Path,
    ) -> None:
        """Downstream task is NOT unblocked if other blockers remain.

        Scenario:
        - Task A is failed.
        - Task E depends on A and B (where B is also failed).
        After resetting A only:
        - E should NOT be unblocked (B is still failed).
        """
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "Task A"},
            "s:2": {"title": "Task B"},
            "s:3": {"title": "Task E"},
        }
        edges = [
            {"source": "s:1", "target": "s:3", "kind": "intra_spec"},
            {"source": "s:2", "target": "s:3", "kind": "intra_spec"},
        ]
        plan_path = _write_plan(
            plan_dir,
            nodes=nodes,
            edges=edges,
            order=["s:1", "s:2", "s:3"],
        )
        state = _make_state(
            {
                "s:1": "failed",
                "s:2": "failed",
                "s:3": "blocked",
            },
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task(
                "s:1",
                plan_path,
                worktrees_dir,
                repo_path,
            )

        assert "s:1" in result.reset_tasks
        assert "s:3" not in result.unblocked_tasks


# ---------------------------------------------------------------------------
# TS-07-E6: Reset with no incomplete tasks
# Requirement: 07-REQ-4.E1
# ---------------------------------------------------------------------------


class TestResetNothingToReset:
    """TS-07-E6: Reset exits cleanly when nothing to reset."""

    def test_empty_result_when_all_completed_or_pending(
        self,
        tmp_path: Path,
    ) -> None:
        """Reset returns empty result when no incomplete tasks exist."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
        }
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "completed",
                "s:2": "pending",
            },
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(plan_path, worktrees_dir, repo_path)

        assert len(result.reset_tasks) == 0


# ---------------------------------------------------------------------------
# TS-07-E7: Reset with no state file
# Requirement: 07-REQ-4.E2
# ---------------------------------------------------------------------------


class TestResetNoStateFile:
    """TS-07-E7: Reset fails when no execution state exists."""

    def test_no_state_raises_error(
        self,
        tmp_path: Path,
    ) -> None:
        """AgentFoxError raised when no state exists."""
        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir(parents=True, exist_ok=True)
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        plan_path = _write_plan(plan_dir, nodes=nodes)

        with pytest.raises(AgentFoxError) as exc_info:
            reset_all(plan_path, worktrees_dir, repo_path, db_conn=None)

        assert "code" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# TS-07-E8: Reset unknown task ID
# Requirement: 07-REQ-5.E1
# ---------------------------------------------------------------------------


class TestResetUnknownTask:
    """TS-07-E8: Single-task reset fails for nonexistent task ID."""

    def test_unknown_task_raises_error(
        self,
        tmp_path: Path,
    ) -> None:
        """AgentFoxError raised with valid task IDs in message."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
        }
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "completed",
                "s:2": "pending",
            },
        )

        with pytest.raises(AgentFoxError) as exc_info:
            with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
                reset_task(
                    "nonexistent:99",
                    plan_path,
                    worktrees_dir,
                    repo_path,
                )

        # Error message should list valid task IDs
        error_msg = str(exc_info.value)
        assert any(valid_id in error_msg for valid_id in ["s:1", "s:2"])


# ---------------------------------------------------------------------------
# TS-07-E9: Reset completed task
# Requirement: 07-REQ-5.E2
# ---------------------------------------------------------------------------


class TestResetCompletedTask:
    """TS-07-E9: Resetting a completed task is rejected."""

    def test_completed_task_returns_empty_result(
        self,
        tmp_path: Path,
    ) -> None:
        """Resetting a completed task makes no changes."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state({"s:1": "completed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task(
                "s:1",
                plan_path,
                worktrees_dir,
                repo_path,
            )

        assert len(result.reset_tasks) == 0

    def test_completed_task_populates_skipped_completed(
        self,
        tmp_path: Path,
    ) -> None:
        """Completed task ID is returned in skipped_completed (07-REQ-5.E2)."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        plan_path = _write_plan(plan_dir, nodes=nodes)
        state = _make_state({"s:1": "completed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task(
                "s:1",
                plan_path,
                worktrees_dir,
                repo_path,
            )

        assert result.skipped_completed == ["s:1"]
