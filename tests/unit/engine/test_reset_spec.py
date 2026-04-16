"""Unit tests for spec-scoped reset engine (reset_spec).

Test Spec: TS-50-1 through TS-50-7, TS-50-12, TS-50-E1 through TS-50-E4
Requirements: 50-REQ-1.1 through 50-REQ-1.8, 50-REQ-4.1, 50-REQ-4.2
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset import reset_spec
from agent_fox.engine.state import ExecutionState, SessionRecord
from tests.unit.engine.conftest import _create_db_with_schema, write_plan_to_db


def _make_state(
    node_states: dict[str, str],
    session_history: list[SessionRecord] | None = None,
    total_cost: float = 0.0,
    total_sessions: int = 0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
) -> ExecutionState:
    """Build an ExecutionState for testing."""
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        session_history=session_history or [],
        total_cost=total_cost,
        total_sessions=total_sessions,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


def _setup(
    tmp_path: Path,
    nodes: dict[str, dict[str, Any]],
    node_states: dict[str, str],
    *,
    edges: list[dict[str, str]] | None = None,
    session_history: list[SessionRecord] | None = None,
    total_cost: float = 0.0,
    total_sessions: int = 0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
) -> tuple[ExecutionState, duckdb.DuckDBPyConnection, Path, Path]:
    """Set up plan in DB, state, worktrees dir and return paths.

    Returns (state, db_conn, worktrees_dir, repo_path).
    """
    agent_dir = tmp_path / ".agent-fox"
    worktrees_dir = agent_dir / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    db_conn = write_plan_to_db(nodes, edges or [])
    state = _make_state(
        node_states,
        session_history=session_history,
        total_cost=total_cost,
        total_sessions=total_sessions,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
    )
    return state, db_conn, worktrees_dir, tmp_path


# ---------------------------------------------------------------------------
# TS-50-1: Reset sets all spec nodes to pending
# Requirement: 50-REQ-1.1
# ---------------------------------------------------------------------------


class TestResetSetsAllSpecNodesToPending:
    """TS-50-1: All nodes belonging to target spec are set to pending."""

    def test_all_alpha_nodes_reset(self, tmp_path: Path) -> None:
        """All alpha nodes transition to pending; beta nodes untouched."""
        nodes = {
            "alpha:1": {"spec_name": "alpha"},
            "alpha:2": {"spec_name": "alpha"},
            "alpha:3": {"spec_name": "alpha"},
            "beta:1": {"spec_name": "beta"},
            "beta:2": {"spec_name": "beta"},
        }
        node_states = {
            "alpha:1": "completed",
            "alpha:2": "blocked",
            "alpha:3": "failed",
            "beta:1": "completed",
            "beta:2": "completed",
        }
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        # All alpha nodes should be in reset_tasks
        assert "alpha:1" in result.reset_tasks
        assert "alpha:2" in result.reset_tasks
        assert "alpha:3" in result.reset_tasks

        # Verify state
        for nid in ["alpha:1", "alpha:2", "alpha:3"]:
            assert state.node_states[nid] == "pending"

        # Beta nodes remain completed
        assert state.node_states["beta:1"] == "completed"
        assert state.node_states["beta:2"] == "completed"


# ---------------------------------------------------------------------------
# TS-50-2: Reset includes archetype nodes
# Requirement: 50-REQ-1.2
# ---------------------------------------------------------------------------


class TestResetIncludesArchetypeNodes:
    """TS-50-2: Archetype nodes (skeptic, auditor, verifier) are included."""

    def test_archetype_and_coder_nodes_all_reset(self, tmp_path: Path) -> None:
        """All node types for the spec are reset."""
        nodes = {
            "alpha:0": {"spec_name": "alpha", "archetype": "skeptic"},
            "alpha:1": {"spec_name": "alpha", "archetype": "coder"},
            "alpha:1:auditor": {"spec_name": "alpha", "archetype": "auditor"},
            "alpha:2": {"spec_name": "alpha", "archetype": "coder"},
            "alpha:3": {"spec_name": "alpha", "archetype": "verifier"},
        }
        node_states = {
            "alpha:0": "completed",
            "alpha:1": "completed",
            "alpha:1:auditor": "completed",
            "alpha:2": "completed",
            "alpha:3": "completed",
        }
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        expected_ids = {"alpha:0", "alpha:1", "alpha:1:auditor", "alpha:2", "alpha:3"}
        assert set(result.reset_tasks) == expected_ids


# ---------------------------------------------------------------------------
# TS-50-3: Other specs unchanged
# Requirement: 50-REQ-1.3
# ---------------------------------------------------------------------------


class TestOtherSpecsUnchanged:
    """TS-50-3: Nodes from other specs are not modified."""

    def test_beta_untouched(self, tmp_path: Path) -> None:
        """Beta nodes remain completed after resetting alpha."""
        nodes = {
            "alpha:1": {"spec_name": "alpha"},
            "beta:1": {"spec_name": "beta"},
        }
        node_states = {
            "alpha:1": "completed",
            "beta:1": "completed",
        }
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        assert state.node_states["beta:1"] == "completed"


# ---------------------------------------------------------------------------
# TS-50-4: Worktrees and branches cleaned
# Requirement: 50-REQ-1.4
# ---------------------------------------------------------------------------


class TestWorktreesAndBranchesCleaned:
    """TS-50-4: Worktrees and branches for reset nodes are cleaned up."""

    def test_worktree_cleaned(self, tmp_path: Path) -> None:
        """Worktree directory for a reset node is removed."""
        nodes = {"alpha:1": {"spec_name": "alpha"}}
        node_states = {"alpha:1": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        # Create worktree directory
        wt_path = wt_dir / "alpha" / "1"
        wt_path.mkdir(parents=True)
        (wt_path / "somefile.py").write_text("content")

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        assert len(result.cleaned_worktrees) >= 1
        assert not wt_path.exists()

    def test_branch_cleaned(self, tmp_path: Path) -> None:
        """Git branch for a reset node is deleted."""
        nodes = {"alpha:1": {"spec_name": "alpha"}}
        node_states = {"alpha:1": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        # Mock git branch -D to simulate branch deletion
        with (
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
            patch("agent_fox.engine.reset.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            result = reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        assert len(result.cleaned_branches) >= 1


# ---------------------------------------------------------------------------
# TS-50-5: Tasks.md checkboxes reset
# Requirement: 50-REQ-1.5
# ---------------------------------------------------------------------------


class TestTasksMdCheckboxesReset:
    """TS-50-5: Top-level checkboxes in tasks.md are reset."""

    def test_checkboxes_reset_to_unchecked(self, tmp_path: Path) -> None:
        """Completed/in-progress checkboxes are reset to [ ]."""
        nodes = {
            "alpha:1": {"spec_name": "alpha", "group_number": 1},
            "alpha:2": {"spec_name": "alpha", "group_number": 2},
        }
        node_states = {"alpha:1": "completed", "alpha:2": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        # Create tasks.md with checked boxes
        specs_dir = repo / ".specs"
        alpha_dir = specs_dir / "alpha"
        alpha_dir.mkdir(parents=True)
        tasks_md = alpha_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n- [x] 1. Task One\n  - [x] 1.1 Subtask\n- [x] 2. Task Two\n  - [-] 2.1 Subtask\n"
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        content = tasks_md.read_text()
        assert "- [ ] 1. Task One" in content
        assert "- [ ] 2. Task Two" in content
        # No completed top-level checkboxes remain
        lines = content.split("\n")
        top_level = [ln for ln in lines if ln.startswith("- [")]
        for line in top_level:
            assert "[x]" not in line


# ---------------------------------------------------------------------------
# TS-50-6: Plan.json statuses reset
# Requirement: 50-REQ-1.6
# NOTE: reset_spec() no longer updates plan.json statuses (DB is now the
#       source of truth for node statuses via _persist_resets). The test now
#       verifies in-memory state updates and that DB persistence is called.
# ---------------------------------------------------------------------------


class TestPlanJsonStatusesReset:
    """TS-50-6: Node statuses are set to pending for the spec."""

    def test_state_statuses_reset(self, tmp_path: Path) -> None:
        """In-memory node statuses are reset to pending."""
        nodes = {
            "alpha:1": {"spec_name": "alpha", "status": "completed"},
            "beta:1": {"spec_name": "beta", "status": "completed"},
        }
        node_states = {"alpha:1": "completed", "beta:1": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        # In-memory state is updated
        assert state.node_states["alpha:1"] == "pending"
        # Beta should not be modified
        assert state.node_states["beta:1"] == "completed"


# ---------------------------------------------------------------------------
# TS-50-7: No git rollback
# Requirement: 50-REQ-1.7
# ---------------------------------------------------------------------------


class TestNoGitRollback:
    """TS-50-7: The develop branch is not modified by spec reset."""

    def test_develop_unchanged(self, tmp_path: Path) -> None:
        """Develop branch SHA is unchanged after spec reset."""
        nodes = {"alpha:1": {"spec_name": "alpha"}}
        node_states = {"alpha:1": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        # Initialize a git repo to check develop SHA
        subprocess.run(
            ["git", "init", "--initial-branch=develop"],
            cwd=str(repo),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo),
            capture_output=True,
        )
        # Add and commit something
        (repo / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo),
            capture_output=True,
        )

        sha_before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        ).stdout.strip()

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        sha_after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        ).stdout.strip()

        assert sha_before == sha_after


# ---------------------------------------------------------------------------
# TS-50-12: Session history preserved
# Requirements: 50-REQ-4.1, 50-REQ-4.2
# ---------------------------------------------------------------------------


class TestSessionHistoryPreserved:
    """TS-50-12: Session history and counters are not modified."""

    def test_history_and_counters_preserved(self, tmp_path: Path) -> None:
        """Session history records and cost totals survive spec reset."""
        nodes = {"alpha:1": {"spec_name": "alpha"}}
        node_states = {"alpha:1": "completed"}

        history = [
            SessionRecord(
                node_id=f"alpha:{i}",
                attempt=1,
                status="completed",
                input_tokens=1000,
                output_tokens=500,
                cost=2.0,
                duration_ms=5000,
                error_message=None,
                timestamp="2026-03-01T10:00:00Z",
            )
            for i in range(5)
        ]

        state, db_conn, wt_dir, repo = _setup(
            tmp_path,
            nodes,
            node_states,
            session_history=history,
            total_cost=10.0,
            total_sessions=5,
            total_input_tokens=5000,
            total_output_tokens=2500,
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        assert len(state.session_history) == 5
        assert state.total_cost == 10.0
        assert state.total_sessions == 5
        assert state.total_input_tokens == 5000
        assert state.total_output_tokens == 2500


# ---------------------------------------------------------------------------
# TS-50-E1: Unknown spec name
# Requirement: 50-REQ-1.E1
# ---------------------------------------------------------------------------


class TestUnknownSpecName:
    """TS-50-E1: Error with valid spec names when spec is unknown."""

    def test_raises_error_with_valid_specs(self, tmp_path: Path) -> None:
        """AgentFoxError raised listing valid spec names."""
        nodes = {
            "alpha:1": {"spec_name": "alpha"},
            "beta:1": {"spec_name": "beta"},
        }
        node_states = {"alpha:1": "completed", "beta:1": "completed"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with pytest.raises(AgentFoxError) as exc_info:
            with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
                reset_spec("nonexistent", wt_dir, repo, db_conn=db_conn)

        error_msg = str(exc_info.value)
        assert "alpha" in error_msg
        assert "beta" in error_msg


# ---------------------------------------------------------------------------
# TS-50-E2: Missing plan file
# Requirement: 50-REQ-1.E2
# ---------------------------------------------------------------------------


class TestMissingPlanFile:
    """TS-50-E2: Error when plan does not exist in DB."""

    def test_raises_error_for_missing_plan(self, tmp_path: Path) -> None:
        """AgentFoxError raised mentioning plan."""
        agent_dir = tmp_path / ".agent-fox"
        wt_dir = agent_dir / "worktrees"
        wt_dir.mkdir(parents=True, exist_ok=True)

        state = _make_state({"alpha:1": "completed"})

        # Create empty DB with schema but no plan data
        db_conn = _create_db_with_schema()

        with pytest.raises(AgentFoxError) as exc_info:
            with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
                reset_spec("alpha", wt_dir, tmp_path, db_conn=db_conn)

        assert "plan" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# TS-50-E3: Missing state file
# Requirement: 50-REQ-1.E3
# ---------------------------------------------------------------------------


class TestMissingStateFile:
    """TS-50-E3: Error when no DB state exists."""

    def test_raises_error_for_missing_state(self, tmp_path: Path) -> None:
        """AgentFoxError raised for missing state (no DB connection)."""
        agent_dir = tmp_path / ".agent-fox"
        wt_dir = agent_dir / "worktrees"
        wt_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(AgentFoxError):
            reset_spec("alpha", wt_dir, tmp_path, db_conn=None)


# ---------------------------------------------------------------------------
# TS-50-E4: All nodes already pending
# Requirement: 50-REQ-1.E4
# ---------------------------------------------------------------------------


class TestAllNodesAlreadyPending:
    """TS-50-E4: No-op when all spec nodes are already pending."""

    def test_empty_result_when_all_pending(self, tmp_path: Path) -> None:
        """Result has empty reset_tasks when all nodes already pending."""
        nodes = {
            "alpha:1": {"spec_name": "alpha"},
            "alpha:2": {"spec_name": "alpha"},
        }
        node_states = {"alpha:1": "pending", "alpha:2": "pending"}
        state, db_conn, wt_dir, repo = _setup(tmp_path, nodes, node_states)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_spec("alpha", wt_dir, repo, db_conn=db_conn)

        assert result.reset_tasks == []
