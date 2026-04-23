"""Unit tests for the reset engine.

Test Spec: TS-07-11, TS-07-12, TS-07-E6, TS-07-E7, TS-07-E8, TS-07-E9
Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-5.1, 07-REQ-5.2,
              07-REQ-4.E1, 07-REQ-4.E2, 07-REQ-5.E1, 07-REQ-5.E2
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.reset import (
    _task_id_to_branch_name,
    _task_id_to_worktree_path,
    hard_reset_all,
    reset_all,
    reset_spec,
    reset_task,
)
from agent_fox.engine.state import ExecutionState
from tests.unit.engine.conftest import write_plan_to_db

# -- Helpers ---------------------------------------------------------------


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

    def test_resets_incomplete_tasks(self, tmp_path: Path) -> None:
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
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state(
            {
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "failed",
                "s:4": "blocked",
                "s:5": "in_progress",
            },
        )

        (worktrees_dir / "s" / "3").mkdir(parents=True)
        (worktrees_dir / "s" / "5").mkdir(parents=True)

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(worktrees_dir, repo_path, db_conn=db_conn)

        assert len(result.reset_tasks) == 3
        assert "s:1" not in result.reset_tasks
        assert "s:2" not in result.reset_tasks
        assert "s:3" in result.reset_tasks
        assert "s:4" in result.reset_tasks
        assert "s:5" in result.reset_tasks

    def test_completed_tasks_not_reset(self, tmp_path: Path) -> None:
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
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "completed", "s:2": "completed", "s:3": "failed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(worktrees_dir, repo_path, db_conn=db_conn)

        assert "s:1" not in result.reset_tasks
        assert "s:2" not in result.reset_tasks

    def test_worktree_directories_cleaned(self, tmp_path: Path) -> None:
        """Worktree directories for reset tasks are removed."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "failed"})

        wt_dir = worktrees_dir / "s" / "1"
        wt_dir.mkdir(parents=True)
        (wt_dir / "somefile.py").write_text("content")

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(worktrees_dir, repo_path, db_conn=db_conn)

        assert len(result.reset_tasks) == 1
        assert not wt_dir.exists()


# ---------------------------------------------------------------------------
# TS-07-12: Single-task reset unblocks downstream
# Requirements: 07-REQ-5.1, 07-REQ-5.2
# ---------------------------------------------------------------------------


class TestSingleTaskReset:
    """TS-07-12: Single-task reset with cascade unblock."""

    def test_reset_single_task(self, tmp_path: Path) -> None:
        """Single task is reset to pending."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "failed", "s:2": "pending"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", worktrees_dir, repo_path, db_conn=db_conn)

        assert "s:1" in result.reset_tasks

    def test_cascade_unblocks_downstream(self, tmp_path: Path) -> None:
        """Downstream tasks are unblocked when sole blocker is reset."""
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
        db_conn = write_plan_to_db(nodes, edges, order=["s:4", "s:1", "s:2", "s:3"])
        state = _make_state(
            {"s:1": "failed", "s:2": "blocked", "s:3": "blocked", "s:4": "completed"},
        )

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", worktrees_dir, repo_path, db_conn=db_conn)

        assert "s:1" in result.reset_tasks
        assert "s:2" in result.unblocked_tasks
        assert "s:3" in result.unblocked_tasks

    def test_no_cascade_when_other_blockers_exist(self, tmp_path: Path) -> None:
        """Downstream task is NOT unblocked if other blockers remain."""
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
        db_conn = write_plan_to_db(nodes, edges, order=["s:1", "s:2", "s:3"])
        state = _make_state({"s:1": "failed", "s:2": "failed", "s:3": "blocked"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", worktrees_dir, repo_path, db_conn=db_conn)

        assert "s:1" in result.reset_tasks
        assert "s:3" not in result.unblocked_tasks


# ---------------------------------------------------------------------------
# TS-07-E6: Reset with no incomplete tasks
# Requirement: 07-REQ-4.E1
# ---------------------------------------------------------------------------


class TestResetNothingToReset:
    """TS-07-E6: Reset exits cleanly when nothing to reset."""

    def test_empty_result_when_all_completed_or_pending(self, tmp_path: Path) -> None:
        """Reset returns empty result when no incomplete tasks exist."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "completed", "s:2": "pending"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(worktrees_dir, repo_path, db_conn=db_conn)

        assert len(result.reset_tasks) == 0


# ---------------------------------------------------------------------------
# TS-07-E7: Reset with no state file
# Requirement: 07-REQ-4.E2
# ---------------------------------------------------------------------------


class TestResetNoStateFile:
    """TS-07-E7: Reset fails when no execution state exists."""

    def test_no_state_raises_error(self, tmp_path: Path) -> None:
        """AgentFoxError raised when no state exists."""
        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir(parents=True, exist_ok=True)
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(AgentFoxError) as exc_info:
            reset_all(worktrees_dir, tmp_path, db_conn=None)

        assert "code" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# TS-07-E8: Reset unknown task ID
# Requirement: 07-REQ-5.E1
# ---------------------------------------------------------------------------


class TestResetUnknownTask:
    """TS-07-E8: Single-task reset fails for nonexistent task ID."""

    def test_unknown_task_raises_error(self, tmp_path: Path) -> None:
        """AgentFoxError raised with valid task IDs in message."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "completed", "s:2": "pending"})

        with pytest.raises(AgentFoxError) as exc_info:
            with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
                reset_task("nonexistent:99", worktrees_dir, repo_path, db_conn=db_conn)

        error_msg = str(exc_info.value)
        assert any(valid_id in error_msg for valid_id in ["s:1", "s:2"])


# ---------------------------------------------------------------------------
# TS-07-E9: Reset completed task
# Requirement: 07-REQ-5.E2
# ---------------------------------------------------------------------------


class TestResetCompletedTask:
    """TS-07-E9: Resetting a completed task is rejected."""

    def test_completed_task_returns_empty_result(self, tmp_path: Path) -> None:
        """Resetting a completed task makes no changes."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "completed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", worktrees_dir, repo_path, db_conn=db_conn)

        assert len(result.reset_tasks) == 0

    def test_completed_task_populates_skipped_completed(self, tmp_path: Path) -> None:
        """Completed task ID is returned in skipped_completed (07-REQ-5.E2)."""
        plan_dir = tmp_path / ".agent-fox"
        worktrees_dir = plan_dir / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path

        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        state = _make_state({"s:1": "completed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_task("s:1", worktrees_dir, repo_path, db_conn=db_conn)

        assert result.skipped_completed == ["s:1"]


# ---------------------------------------------------------------------------
# Session table cleanup (issue #501)
# ---------------------------------------------------------------------------


def _seed_session_tables(conn, spec_name: str = "s", node_id: str = "s:1") -> None:
    """Populate session-scoped tables with stale data for cleanup tests."""
    now = datetime.now(UTC).isoformat()
    run_id = f"run_stale_{uuid.uuid4().hex[:8]}"
    session_id = f"{node_id}:1"

    conn.execute(
        "INSERT INTO runs (id, plan_content_hash, status, started_at) VALUES (?, ?, 'block_limit', ?)",
        [run_id, "hash123", now],
    )
    conn.execute(
        "INSERT INTO session_outcomes (id, spec_name, task_group, node_id, status, created_at, run_id, archetype) "
        "VALUES (?, ?, '1', ?, 'completed', ?, ?, 'reviewer')",
        [str(uuid.uuid4()), spec_name, node_id, now, run_id],
    )
    conn.execute(
        "INSERT INTO review_findings (id, severity, description, requirement_ref, spec_name, task_group, session_id) "
        "VALUES (?, 'critical', 'stale finding', 'REQ-1', ?, '1', ?)",
        [str(uuid.uuid4()), spec_name, session_id],
    )
    conn.execute(
        "INSERT INTO verification_results (id, requirement_id, verdict, spec_name, task_group, session_id) "
        "VALUES (?, 'REQ-1', 'fail', ?, '1', ?)",
        [str(uuid.uuid4()), spec_name, session_id],
    )
    conn.execute(
        "INSERT INTO drift_findings (id, severity, description, spec_name, task_group, session_id) "
        "VALUES (?, 'major', 'stale drift', ?, '1', ?)",
        [str(uuid.uuid4()), spec_name, session_id],
    )


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


class TestHardResetClearsSessionTables:
    """Issue #501: hard_reset_all must clear session-scoped tables."""

    def test_clears_runs(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "failed"})
        state.session_history = []

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            hard_reset_all(tmp_path / "wt", tmp_path, tmp_path / "mem.jsonl", db_conn=db_conn)

        assert _count(db_conn, "runs") == 0

    def test_clears_session_outcomes(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "failed"})
        state.session_history = []

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            hard_reset_all(tmp_path / "wt", tmp_path, tmp_path / "mem.jsonl", db_conn=db_conn)

        assert _count(db_conn, "session_outcomes") == 0

    def test_clears_review_findings(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "failed"})
        state.session_history = []

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            hard_reset_all(tmp_path / "wt", tmp_path, tmp_path / "mem.jsonl", db_conn=db_conn)

        assert _count(db_conn, "review_findings") == 0

    def test_blocking_history_no_longer_in_session_tables(self) -> None:
        """blocking_history was removed from _SESSION_TABLES_ALL (spec 116)."""
        from agent_fox.engine.reset import _SESSION_TABLES_ALL

        assert "blocking_history" not in _SESSION_TABLES_ALL

    def test_clears_verification_results(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "failed"})
        state.session_history = []

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            hard_reset_all(tmp_path / "wt", tmp_path, tmp_path / "mem.jsonl", db_conn=db_conn)

        assert _count(db_conn, "verification_results") == 0

    def test_clears_drift_findings(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "failed"})
        state.session_history = []

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            hard_reset_all(tmp_path / "wt", tmp_path, tmp_path / "mem.jsonl", db_conn=db_conn)

        assert _count(db_conn, "drift_findings") == 0


class TestSoftResetClearsSessionTables:
    """Issue #501: soft reset must also clear blocking session state."""

    def test_reset_all_clears_runs(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "blocked"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_all(tmp_path / "wt", tmp_path, db_conn=db_conn)

        assert _count(db_conn, "runs") == 0

    def test_reset_all_clears_review_findings(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "blocked"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_all(tmp_path / "wt", tmp_path, db_conn=db_conn)

        assert _count(db_conn, "review_findings") == 0

    def test_reset_all_clears_session_outcomes(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn)
        state = _make_state({"s:1": "blocked"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_all(tmp_path / "wt", tmp_path, db_conn=db_conn)

        assert _count(db_conn, "session_outcomes") == 0

    def test_reset_task_clears_session_tables(self, tmp_path: Path) -> None:
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn, node_id="s:1")
        state = _make_state({"s:1": "failed", "s:2": "pending"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_task("s:1", tmp_path / "wt", tmp_path, db_conn=db_conn)

        assert _count(db_conn, "runs") == 0
        assert _count(db_conn, "review_findings") == 0


class TestResetSpecClearsSessionTables:
    """Issue #501: reset_spec must clear session tables for the spec."""

    def test_clears_spec_session_data(self, tmp_path: Path) -> None:
        nodes = {
            "a:1": {"title": "T1", "spec_name": "a"},
            "b:1": {"title": "T2", "spec_name": "b"},
        }
        db_conn = write_plan_to_db(nodes, [])
        _seed_session_tables(db_conn, spec_name="a", node_id="a:1")
        _seed_session_tables(db_conn, spec_name="b", node_id="b:1")
        state = _make_state({"a:1": "blocked", "b:1": "pending"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            reset_spec("a", tmp_path / "wt", tmp_path, db_conn=db_conn)

        # Spec "a" data cleared, spec "b" data preserved
        a_findings = db_conn.execute("SELECT count(*) FROM review_findings WHERE spec_name = 'a'").fetchone()[0]
        b_findings = db_conn.execute("SELECT count(*) FROM review_findings WHERE spec_name = 'b'").fetchone()[0]
        assert a_findings == 0
        assert b_findings == 1
        # Runs always fully cleared
        assert _count(db_conn, "runs") == 0
