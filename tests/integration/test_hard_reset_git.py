"""Integration tests for hard reset git operations.

Test Spec: TS-35-1, TS-35-10, TS-35-12
Requirements: 35-REQ-1.1, 35-REQ-3.5, 35-REQ-4.1, 35-REQ-4.2, 35-REQ-4.3

These tests use real git repositories in temporary directories to verify
end-to-end rollback behavior including git reset --hard and ancestor checks.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager

# ---------------------------------------------------------------------------
# Git repo helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, check: bool = True) -> str:
    """Run a git command in the given repo and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    """Initialize a bare-minimum git repo with a develop branch."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")

    # Initial commit on main
    (path / "README.md").write_text("# Test\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial commit")

    # Create develop branch
    _git(path, "checkout", "-b", "develop")
    return path


def _commit_file(repo: Path, filename: str, content: str, message: str) -> str:
    """Create/update a file, commit it, and return the commit SHA."""
    (repo / filename).write_text(content)
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _get_head(repo: Path, branch: str = "HEAD") -> str:
    """Return the current HEAD SHA for a branch."""
    return _git(repo, "rev-parse", branch)


def _make_plan_json(nodes: dict, order: list[str] | None = None) -> str:
    """Build minimal plan.json."""
    full_nodes = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        full_nodes[nid] = {
            "id": nid,
            "spec_name": parts[0],
            "group_number": int(parts[1]),
            "title": props.get("title", f"Task {nid}"),
            "optional": False,
            "status": props.get("status", "pending"),
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
            "order": order or list(nodes.keys()),
        }
    )


def _write_state(
    state_path: Path,
    node_states: dict[str, str],
    session_history: list[SessionRecord] | None = None,
) -> None:
    """Write an ExecutionState to state.jsonl."""
    state = ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        session_history=session_history or [],
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )
    StateManager(state_path).save(state)


def _make_session_record(
    node_id: str,
    commit_sha: str = "",
    status: str = "completed",
) -> SessionRecord:
    """Create a SessionRecord with defaults."""
    return SessionRecord(
        node_id=node_id,
        attempt=1,
        status=status,
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=5000,
        error_message=None,
        timestamp="2026-03-01T10:00:00Z",
        model="test-model",
        files_touched=[],
        commit_sha=commit_sha,
    )


# ===========================================================================
# TS-35-1: Commit SHA Captured After Harvest
# Requirement: 35-REQ-1.1
# ===========================================================================


class TestCommitShaCaptured:
    """TS-35-1: Verify that commit_sha is captured after successful harvest.

    This is an integration-level test that verifies the contract:
    after a successful harvest merges code into develop, the
    SessionRecord should contain the develop HEAD SHA.

    Since _run_and_harvest requires a full session setup, we test
    the _capture_develop_head helper directly with a real git repo.
    """

    def test_capture_develop_head(self, tmp_path: Path) -> None:
        """_capture_develop_head returns 40-char hex SHA of develop HEAD."""
        from agent_fox.engine.session_lifecycle import _capture_develop_head

        repo = _init_repo(tmp_path / "repo")
        _commit_file(repo, "task1.py", "print('hello')", "task 1 commit")
        expected_sha = _get_head(repo, "develop")

        import asyncio

        sha = asyncio.run(_capture_develop_head(repo))

        assert len(sha) == 40
        assert sha == expected_sha

    def test_capture_returns_empty_on_failure(self, tmp_path: Path) -> None:
        """_capture_develop_head returns '' when git fails."""
        from agent_fox.engine.session_lifecycle import _capture_develop_head

        # Non-existent directory => git will fail
        bad_path = tmp_path / "nonexistent"

        import asyncio

        sha = asyncio.run(_capture_develop_head(bad_path))

        assert sha == ""


# ===========================================================================
# TS-35-10: Full Hard Reset Rolls Back Develop
# Requirement: 35-REQ-3.5
# ===========================================================================


class TestFullHardResetRollback:
    """TS-35-10: develop is reset to commit before earliest tracked task."""

    def test_develop_rolled_back_to_pre_task(self, tmp_path: Path) -> None:
        """Develop HEAD equals predecessor of earliest commit_sha."""
        from agent_fox.engine.reset import hard_reset_all

        repo = _init_repo(tmp_path / "repo")

        # Initial state before any tasks
        pre_task_sha = _get_head(repo, "develop")

        # Simulate 3 tasks committed sequentially
        sha1 = _commit_file(repo, "task1.py", "# task 1", "task 1")
        sha2 = _commit_file(repo, "task2.py", "# task 2", "task 2")
        sha3 = _commit_file(repo, "task3.py", "# task 3", "task 3")

        # Set up .agent-fox structure
        agent_dir = repo / ".agent-fox"
        agent_dir.mkdir(exist_ok=True)
        state_path = agent_dir / "state.jsonl"
        plan_path = agent_dir / "plan.json"
        worktrees_dir = agent_dir / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        memory_path = agent_dir / "memory.jsonl"
        memory_path.write_text("")

        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}, "s:3": {"title": "T3"}}
        plan_path.write_text(_make_plan_json(nodes))

        history = [
            _make_session_record("s:1", commit_sha=sha1),
            _make_session_record("s:2", commit_sha=sha2),
            _make_session_record("s:3", commit_sha=sha3),
        ]
        _write_state(
            state_path,
            {"s:1": "completed", "s:2": "completed", "s:3": "completed"},
            session_history=history,
        )

        result = hard_reset_all(state_path, plan_path, worktrees_dir, repo, memory_path)

        # Develop should be at pre_task_sha (predecessor of earliest commit)
        new_head = _get_head(repo, "develop")
        assert new_head == pre_task_sha
        assert result.rollback_sha == pre_task_sha


# ===========================================================================
# TS-35-12: Partial Hard Reset Rolls Back to Task Boundary
# Requirement: 35-REQ-4.1, 35-REQ-4.2, 35-REQ-4.3
# ===========================================================================


class TestPartialHardResetRollback:
    """TS-35-12: Partial hard reset rolls back to before the target task."""

    def test_rollback_to_task_boundary(self, tmp_path: Path) -> None:
        """Develop HEAD equals predecessor of target task's commit_sha.

        After rolling back to before task 2:
        - Task 2 and 3 should be reset
        - Task 1 should remain completed
        """
        from agent_fox.engine.reset import hard_reset_task

        repo = _init_repo(tmp_path / "repo")

        # Simulate 3 tasks committed sequentially
        sha1 = _commit_file(repo, "task1.py", "# task 1", "task 1")
        sha2 = _commit_file(repo, "task2.py", "# task 2", "task 2")
        sha3 = _commit_file(repo, "task3.py", "# task 3", "task 3")

        # sha1's parent (predecessor of sha1) is what task 1 is "at"
        pre_task2_sha = _git(repo, "rev-parse", f"{sha2}~1")

        # Set up .agent-fox structure
        agent_dir = repo / ".agent-fox"
        agent_dir.mkdir(exist_ok=True)
        state_path = agent_dir / "state.jsonl"
        plan_path = agent_dir / "plan.json"
        worktrees_dir = agent_dir / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        memory_path = agent_dir / "memory.jsonl"
        memory_path.write_text("")

        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}, "s:3": {"title": "T3"}}
        plan_path.write_text(_make_plan_json(nodes))

        history = [
            _make_session_record("s:1", commit_sha=sha1),
            _make_session_record("s:2", commit_sha=sha2),
            _make_session_record("s:3", commit_sha=sha3),
        ]
        _write_state(
            state_path,
            {"s:1": "completed", "s:2": "completed", "s:3": "completed"},
            session_history=history,
        )

        result = hard_reset_task(
            "s:2", state_path, plan_path, worktrees_dir, repo, memory_path
        )

        # Develop should be at sha1 (predecessor of task 2's commit)
        new_head = _get_head(repo, "develop")
        assert new_head == pre_task2_sha
        assert result.rollback_sha == pre_task2_sha

        # Task 2 and 3 should be reset
        assert "s:2" in result.reset_tasks
        assert "s:3" in result.reset_tasks

        # Task 1 should NOT be reset (its commit is ancestor of new HEAD)
        assert "s:1" not in result.reset_tasks

        # Verify state file
        state = StateManager(state_path).load()
        assert state is not None
        assert state.node_states["s:1"] == "completed"
        assert state.node_states["s:2"] == "pending"
        assert state.node_states["s:3"] == "pending"
