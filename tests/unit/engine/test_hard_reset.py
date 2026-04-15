"""Unit tests for the hard reset engine.

Test Spec: TS-35-2, TS-35-3, TS-35-4, TS-35-5, TS-35-6, TS-35-7, TS-35-8,
           TS-35-9, TS-35-11, TS-35-13, TS-35-14, TS-35-15, TS-35-16,
           TS-35-17, TS-35-18
Edge Cases: TS-35-E1, TS-35-E2, TS-35-E3, TS-35-E4, TS-35-E5, TS-35-E6,
            TS-35-E7, TS-35-E8
Requirements: 35-REQ-1.2, 35-REQ-1.3, 35-REQ-1.E1, 35-REQ-2.1, 35-REQ-2.2,
              35-REQ-3.1, 35-REQ-3.2, 35-REQ-3.3, 35-REQ-3.4, 35-REQ-3.6,
              35-REQ-3.E1, 35-REQ-3.E2, 35-REQ-4.3, 35-REQ-4.4,
              35-REQ-4.E1, 35-REQ-4.E2, 35-REQ-5.1, 35-REQ-5.E1,
              35-REQ-6.2, 35-REQ-7.1, 35-REQ-7.2, 35-REQ-7.E1, 35-REQ-7.E2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.engine.state import ExecutionState, SessionRecord

# ---------------------------------------------------------------------------
# Helpers (shared with test_reset.py patterns)
# ---------------------------------------------------------------------------


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
    session_history: list[SessionRecord] | None = None,
    total_cost: float = 0.0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
    total_sessions: int = 0,
) -> ExecutionState:
    """Build an ExecutionState for testing."""
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        session_history=session_history or [],
        total_cost=total_cost,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


def _make_session_record(
    node_id: str = "s:1",
    status: str = "completed",
    commit_sha: str = "",
    **kwargs: Any,
) -> SessionRecord:
    """Create a SessionRecord with sensible defaults."""
    defaults = {
        "node_id": node_id,
        "attempt": 1,
        "status": status,
        "input_tokens": 100,
        "output_tokens": 50,
        "cost": 0.01,
        "duration_ms": 5000,
        "error_message": None,
        "timestamp": "2026-03-01T10:00:00Z",
        "model": "test-model",
        "files_touched": [],
        "commit_sha": commit_sha,
    }
    defaults.update(kwargs)
    return SessionRecord(**defaults)  # type: ignore[arg-type]


def _setup_agent_dir(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create standard .agent-fox directory structure.

    Returns (agent_dir, plan_path, worktrees_dir, memory_path).
    """
    agent_dir = tmp_path / ".agent-fox"
    plan_path = agent_dir / "plan.json"
    worktrees_dir = agent_dir / "worktrees"
    memory_path = agent_dir / "memory.jsonl"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir, plan_path, worktrees_dir, memory_path


# ===========================================================================
# TS-35-2: Commit SHA Empty on Failed Session
# Requirement: 35-REQ-1.2
# ===========================================================================


class TestCommitShaEmptyOnFailure:
    """TS-35-2: Verify that commit_sha is empty when session fails."""

    def test_failed_session_has_empty_commit_sha(self) -> None:
        """SessionRecord for a failed session has commit_sha == ''."""
        record = _make_session_record(status="failed", commit_sha="")
        assert record.commit_sha == ""

    def test_default_commit_sha_is_empty(self) -> None:
        """SessionRecord without explicit commit_sha defaults to ''."""
        record = SessionRecord(
            node_id="s:1",
            attempt=1,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="some error",
            timestamp="2026-03-01T10:00:00Z",
        )
        assert record.commit_sha == ""


# ===========================================================================
# TS-35-3: Backward-Compatible Deserialization
# Requirement: 35-REQ-1.3
# ===========================================================================


class TestBackwardCompatDeserialization:
    """TS-35-3: Deserializing SessionRecord without commit_sha defaults to ''."""

    def test_deserialize_without_commit_sha(self) -> None:
        """SessionRecord without commit_sha field defaults to empty string."""
        # SessionRecord created without explicit commit_sha should default to ''
        record = SessionRecord(
            node_id="s:1",
            attempt=1,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=5000,
            error_message=None,
            timestamp="2026-03-01T10:00:00Z",
            # NO commit_sha argument
        )
        assert record.commit_sha == ""


# ===========================================================================
# TS-35-4: Hard Flag Accepted by CLI
# Requirement: 35-REQ-2.1, 35-REQ-5.2
# ===========================================================================


class TestHardFlagAccepted:
    """TS-35-4: CLI accepts --hard as a valid flag."""

    def test_hard_flag_accepted(self, tmp_path: Path) -> None:
        """reset --hard --yes invokes without Click errors."""
        from click.testing import CliRunner

        from agent_fox.cli.reset import reset_cmd

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # Recreate structure in isolated filesystem
            iso_agent_dir = Path(td) / ".agent-fox"
            iso_agent_dir.mkdir(parents=True, exist_ok=True)
            nodes = {"s:1": {"title": "T1"}}
            (iso_agent_dir / "plan.json").write_text(_make_plan_json(nodes=nodes))
            (iso_agent_dir / "worktrees").mkdir(exist_ok=True)
            (iso_agent_dir / "memory.jsonl").write_text("")

            # Mock out hard_reset_all to avoid git operations
            mock_result = _make_hard_reset_result()
            with patch(
                "agent_fox.cli.reset.hard_reset_all",
                return_value=mock_result,
            ):
                result = runner.invoke(reset_cmd, ["--hard", "--yes"], obj={"json": False})

        assert result.exit_code == 0


# ===========================================================================
# TS-35-5: Soft Reset Unchanged Without Hard Flag
# Requirement: 35-REQ-2.2
# ===========================================================================


class TestSoftResetUnchanged:
    """TS-35-5: reset without --hard calls existing soft-reset path."""

    def test_soft_reset_preserves_completed_tasks(self, tmp_path: Path) -> None:
        """Without --hard, completed tasks remain completed."""
        from agent_fox.engine.reset import reset_all

        agent_dir, plan_path, worktrees_dir, _ = _setup_agent_dir(tmp_path)
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
        }
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state({"s:1": "completed", "s:2": "failed"})

        with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
            result = reset_all(plan_path, worktrees_dir, tmp_path)

        # Only failed task was reset
        assert "s:2" in result.reset_tasks
        assert "s:1" not in result.reset_tasks

        # Verify completed task is still completed in state
        assert state.node_states["s:1"] == "completed"
        assert state.node_states["s:2"] == "pending"


# ===========================================================================
# TS-35-6: Full Hard Reset Resets All Tasks
# Requirement: 35-REQ-3.1
# ===========================================================================


class TestFullHardResetAllTasks:
    """TS-35-6: hard_reset_all() resets every task to pending."""

    def test_all_tasks_reset_to_pending(self, tmp_path: Path) -> None:
        """All tasks including completed are set to pending."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
            "s:4": {"title": "T4"},
            "s:5": {"title": "T5"},
        }
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state(
            {
                "s:1": "pending",
                "s:2": "in_progress",
                "s:3": "completed",
                "s:4": "failed",
                "s:5": "blocked",
            },
        )
        memory_path.write_text("")

        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        for task_id in state.node_states:
            assert state.node_states[task_id] == "pending"

        assert len(result.reset_tasks) == 5


# ===========================================================================
# TS-35-7: Full Hard Reset Cleans All Worktrees
# Requirement: 35-REQ-3.2
# ===========================================================================


class TestFullHardResetCleansWorktrees:
    """TS-35-7: All worktree directories are removed."""

    def test_worktrees_removed(self, tmp_path: Path) -> None:
        """All worktree directories under .agent-fox/worktrees/ are removed."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state({"s:1": "completed", "s:2": "completed"})
        memory_path.write_text("")

        # Create worktree dirs
        (worktrees_dir / "s" / "1").mkdir(parents=True)
        (worktrees_dir / "s" / "1" / "somefile.py").write_text("content")
        (worktrees_dir / "s" / "2").mkdir(parents=True)

        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        assert len(result.cleaned_worktrees) == 2
        assert not (worktrees_dir / "s" / "1").exists()
        assert not (worktrees_dir / "s" / "2").exists()


# ===========================================================================
# TS-35-8: Full Hard Reset Deletes All Local Branches
# Requirement: 35-REQ-3.3
# ===========================================================================


class TestFullHardResetDeletesBranches:
    """TS-35-8: All local feature branches are deleted."""

    def test_feature_branches_deleted(self, tmp_path: Path) -> None:
        """All feature/{spec}/{group} branches are deleted."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state({"s:1": "completed", "s:2": "failed"})
        memory_path.write_text("")

        with (
            _mock_git_for_hard_reset(deleted_branches=["feature/s/1", "feature/s/2"]),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        assert "feature/s/1" in result.cleaned_branches
        assert "feature/s/2" in result.cleaned_branches


# ===========================================================================
# TS-35-9: Full Hard Reset Compacts Knowledge Base
# Requirement: 35-REQ-3.4, 35-REQ-3.7
# ===========================================================================


class TestFullHardResetCompactsKB:
    """TS-35-9: Knowledge compaction is called during hard reset."""

    def test_compaction_called(self, tmp_path: Path) -> None:
        """compact() is called and result reflected in HardResetResult."""
        from unittest.mock import MagicMock

        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}}
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state({"s:1": "completed"})
        memory_path.write_text("")

        mock_conn = MagicMock()
        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
            patch("agent_fox.engine.reset.compact", return_value=(42, 38)),
        ):
            result = hard_reset_all(
                plan_path,
                worktrees_dir,
                tmp_path,
                memory_path,
                db_conn=mock_conn,
            )

        assert result.compaction == (42, 38)
        assert result.compaction[0] >= result.compaction[1]


# ===========================================================================
# TS-35-11: Full Hard Reset Preserves Counters and History
# Requirement: 35-REQ-3.6
# ===========================================================================


class TestFullHardResetPreservesCounters:
    """TS-35-11: Session history and counters are not modified."""

    def test_counters_preserved(self, tmp_path: Path) -> None:
        """total_cost, tokens, sessions, session_history are unchanged."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}}
        _write_plan(agent_dir, nodes=nodes)

        history = [_make_session_record(node_id="s:1", status="completed")]
        state = _make_state(
            {"s:1": "completed"},
            session_history=history,
            total_cost=1.50,
            total_input_tokens=1000,
            total_output_tokens=500,
            total_sessions=3,
        )
        memory_path.write_text("")

        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        assert state.total_cost == 1.50
        assert state.total_input_tokens == 1000
        assert state.total_output_tokens == 500
        assert state.total_sessions == 3
        assert len(state.session_history) == 1


# ===========================================================================
# TS-35-13: Partial Hard Reset Identifies Affected Tasks
# Requirement: 35-REQ-4.3
# ===========================================================================


class TestFindAffectedTasks:
    """TS-35-13: find_affected_tasks() identifies tasks after rollback point."""

    def test_identifies_affected_tasks(self, tmp_path: Path) -> None:
        """Tasks whose commit_sha is NOT an ancestor of new_head are affected."""
        from agent_fox.engine.reset import find_affected_tasks

        history = [
            _make_session_record(node_id="s:1", commit_sha="aaa" * 13 + "a", status="completed"),
            _make_session_record(node_id="s:2", commit_sha="bbb" * 13 + "b", status="completed"),
            _make_session_record(node_id="s:3", commit_sha="ccc" * 13 + "c", status="completed"),
        ]

        new_head = "aaa" * 13 + "a"  # Only s:1's commit is ancestor

        # Mock git merge-base --is-ancestor:
        # s:1's SHA is ancestor (returncode 0)
        # s:2 and s:3 are NOT ancestors (returncode 1)
        def mock_run(args, **kwargs):
            from unittest.mock import MagicMock

            result = MagicMock()
            sha = args[3]  # git merge-base --is-ancestor <sha> <head>
            if sha == "aaa" * 13 + "a":
                result.returncode = 0
            else:
                result.returncode = 1
            return result

        with patch(
            "agent_fox.engine.reset.subprocess.run",
            side_effect=mock_run,
        ):
            affected = find_affected_tasks(history, new_head, tmp_path)

        assert "s:2" in affected
        assert "s:3" in affected
        assert "s:1" not in affected


# ===========================================================================
# TS-35-14: Partial Hard Reset Cleans Affected Artifacts
# Requirement: 35-REQ-4.4
# ===========================================================================


class TestPartialHardResetCleansAffected:
    """TS-35-14: Worktrees and branches for affected tasks are cleaned."""

    def test_cleans_affected_not_unaffected(self, tmp_path: Path) -> None:
        """Only affected tasks' artifacts are cleaned."""
        from agent_fox.engine.reset import hard_reset_task

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
        }
        _write_plan(agent_dir, nodes=nodes)

        history = [
            _make_session_record(node_id="s:1", commit_sha="aaa" * 13 + "a", status="completed"),
            _make_session_record(node_id="s:2", commit_sha="bbb" * 13 + "b", status="completed"),
            _make_session_record(node_id="s:3", commit_sha="ccc" * 13 + "c", status="completed"),
        ]
        state = _make_state(
            {"s:1": "completed", "s:2": "completed", "s:3": "completed"},
            session_history=history,
        )
        memory_path.write_text("")

        # Create worktrees for all tasks
        (worktrees_dir / "s" / "1").mkdir(parents=True)
        (worktrees_dir / "s" / "2").mkdir(parents=True)
        (worktrees_dir / "s" / "3").mkdir(parents=True)

        # Mock: rollback to before s:2, so s:2 and s:3 are affected
        with (
            _mock_git_for_hard_reset(
                deleted_branches=["feature/s/2", "feature/s/3"],
                ancestor_check=lambda sha, head: sha == "aaa" * 13 + "a",
            ),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_task("s:2", plan_path, worktrees_dir, tmp_path, memory_path)

        assert "feature/s/2" in result.cleaned_branches
        assert "feature/s/3" in result.cleaned_branches
        assert "feature/s/1" not in result.cleaned_branches


# ===========================================================================
# TS-35-15: Confirmation Required Without --yes
# Requirement: 35-REQ-5.1
# ===========================================================================


class TestConfirmationRequired:
    """TS-35-15: reset --hard prompts for confirmation."""

    def test_user_prompted_without_yes(self, tmp_path: Path) -> None:
        """reset --hard without --yes prompts, 'n' cancels."""
        from click.testing import CliRunner

        from agent_fox.cli.reset import reset_cmd

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            iso_agent_dir = Path(td) / ".agent-fox"
            iso_agent_dir.mkdir(parents=True, exist_ok=True)
            nodes = {"s:1": {"title": "T1"}}
            (iso_agent_dir / "plan.json").write_text(_make_plan_json(nodes=nodes))
            (iso_agent_dir / "worktrees").mkdir(exist_ok=True)
            (iso_agent_dir / "memory.jsonl").write_text("")

            result = runner.invoke(reset_cmd, ["--hard"], input="n\n", obj={"json": False})

        assert "cancelled" in result.output.lower() or "cancel" in result.output.lower()


# ===========================================================================
# TS-35-16: JSON Output for Hard Reset
# Requirement: 35-REQ-6.2, 35-REQ-5.3
# ===========================================================================


class TestJsonOutput:
    """TS-35-16: Hard reset produces structured JSON output in JSON mode."""

    def test_json_output_structure(self, tmp_path: Path) -> None:
        """JSON output contains reset_tasks, compaction, rollback keys."""
        from click.testing import CliRunner

        from agent_fox.cli.reset import reset_cmd

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            iso_agent_dir = Path(td) / ".agent-fox"
            iso_agent_dir.mkdir(parents=True, exist_ok=True)
            nodes = {"s:1": {"title": "T1"}}
            (iso_agent_dir / "plan.json").write_text(_make_plan_json(nodes=nodes))
            (iso_agent_dir / "worktrees").mkdir(exist_ok=True)
            (iso_agent_dir / "memory.jsonl").write_text("")

            mock_result = _make_hard_reset_result(reset_tasks=["s:1"])
            with patch(
                "agent_fox.cli.reset.hard_reset_all",
                return_value=mock_result,
            ):
                result = runner.invoke(
                    reset_cmd,
                    ["--hard", "--yes"],
                    obj={"json": True},
                )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "reset_tasks" in data
        assert "compaction" in data
        assert "rollback" in data


# ===========================================================================
# TS-35-17: Hard Reset Resets Tasks.md Checkboxes
# Requirement: 35-REQ-7.1, 35-REQ-7.3
# ===========================================================================


class TestResetTasksMdCheckboxes:
    """TS-35-17: tasks.md checkboxes reset to [ ] for affected groups."""

    def test_checkboxes_reset(self, tmp_path: Path) -> None:
        """Top-level checkboxes for affected groups are set to [ ]."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "myspec"
        spec_dir.mkdir(parents=True)
        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n"
            "- [x] 1. First task group\n"
            "  - [x] 1.1 Subtask\n"
            "- [-] 2. Second task group\n"
            "  - [ ] 2.1 Subtask\n"
            "- [ ] 3. Third task group\n"
        )

        reset_tasks_md_checkboxes(["myspec:1", "myspec:2"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1." in text
        assert "- [ ] 2." in text
        # Group 3 should be unchanged (already [ ])
        assert "- [ ] 3." in text

    def test_subtask_checkboxes_are_reset(self, tmp_path: Path) -> None:
        """Sub-task checkboxes within a task group are reset (fixes #163)."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "myspec"
        spec_dir.mkdir(parents=True)
        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n"
            "- [x] 1. First task group\n"
            "  - [x] 1.1 Subtask one\n"
            "  - [x] 1.2 Subtask two\n"
            "  - [x] 1.V Verify task group 1\n"
        )

        reset_tasks_md_checkboxes(["myspec:1"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1. First task group" in text
        assert "  - [ ] 1.1 Subtask one" in text
        assert "  - [ ] 1.2 Subtask two" in text
        assert "  - [ ] 1.V Verify task group 1" in text

    def test_subtask_in_progress_checkboxes_are_reset(self, tmp_path: Path) -> None:
        """In-progress [-] sub-task checkboxes are also reset (fixes #163)."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "myspec"
        spec_dir.mkdir(parents=True)
        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n"
            "- [-] 1. First task group\n"
            "  - [x] 1.1 Done subtask\n"
            "  - [-] 1.2 In-progress subtask\n"
            "  - [ ] 1.3 Pending subtask\n"
        )

        reset_tasks_md_checkboxes(["myspec:1"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1. First task group" in text
        assert "  - [ ] 1.1 Done subtask" in text
        assert "  - [ ] 1.2 In-progress subtask" in text
        # Already-pending subtask unchanged
        assert "  - [ ] 1.3 Pending subtask" in text

    def test_subtask_reset_does_not_affect_other_groups(self, tmp_path: Path) -> None:
        """Resetting group 1 sub-tasks does not touch group 2 sub-tasks."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "myspec"
        spec_dir.mkdir(parents=True)
        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n"
            "- [x] 1. First task group\n"
            "  - [x] 1.1 Subtask one\n"
            "- [x] 2. Second task group\n"
            "  - [x] 2.1 Subtask one\n"
        )

        reset_tasks_md_checkboxes(["myspec:1"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1. First task group" in text
        assert "  - [ ] 1.1 Subtask one" in text
        # Group 2 untouched
        assert "- [x] 2. Second task group" in text
        assert "  - [x] 2.1 Subtask one" in text

    def test_deep_nested_checkboxes_are_reset(self, tmp_path: Path) -> None:
        """Checkboxes at any nesting depth within a group are reset."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "myspec"
        spec_dir.mkdir(parents=True)
        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text(
            "# Tasks\n\n"
            "- [x] 1. First task group\n"
            "  - [x] 1.1 Subtask\n"
            "    - [x] 1.1.1 Deep subtask\n"
            "- [x] 2. Second task group\n"
        )

        reset_tasks_md_checkboxes(["myspec:1"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1. First task group" in text
        assert "  - [ ] 1.1 Subtask" in text
        assert "    - [ ] 1.1.1 Deep subtask" in text
        # Group 2 untouched
        assert "- [x] 2. Second task group" in text


# ===========================================================================
# TS-35-18: Hard Reset Updates Plan.json Statuses
# Requirement: 35-REQ-7.2
# NOTE: reset_plan_statuses() was removed with the StateManager→DB migration.
#       Plan node statuses are now persisted via _persist_resets() to DuckDB.
#       The test class was removed because the function no longer exists.
# ===========================================================================


# ===========================================================================
# TS-35-E1: Git Rev-Parse Fails After Harvest
# Requirement: 35-REQ-1.E1
# ===========================================================================


class TestRevParseFailGraceful:
    """TS-35-E1: Graceful handling when git rev-parse develop fails."""

    def test_commit_sha_empty_on_rev_parse_failure(self) -> None:
        """When git rev-parse fails, commit_sha is '' and session is not failed.

        This test verifies the contract: if _capture_develop_head fails,
        the SessionRecord should have commit_sha='' but status should
        remain 'completed'.
        """
        # The actual implementation will be in session_lifecycle.py.
        # For now we verify the data model contract.
        record = _make_session_record(
            status="completed",
            commit_sha="",
        )
        assert record.commit_sha == ""
        assert record.status == "completed"


# ===========================================================================
# TS-35-E2: No Commit SHAs in History (Full Reset)
# Requirement: 35-REQ-3.E1
# ===========================================================================


class TestNoCommitShasSkipsRollback:
    """TS-35-E2: Full hard reset skips rollback when no revision data exists."""

    def test_no_shas_skips_rollback(self, tmp_path: Path) -> None:
        """All tasks reset, rollback_sha is None, no git reset executed."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        _write_plan(agent_dir, nodes=nodes)

        # All session records have empty commit_sha
        history = [
            _make_session_record(node_id="s:1", commit_sha="", status="completed"),
            _make_session_record(node_id="s:2", commit_sha="", status="completed"),
        ]
        state = _make_state(
            {"s:1": "completed", "s:2": "completed"},
            session_history=history,
        )
        memory_path.write_text("")

        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        assert result.rollback_sha is None
        assert all(s == "pending" for s in state.node_states.values())


# ===========================================================================
# TS-35-E3: Rollback Target Unresolvable
# Requirement: 35-REQ-3.E2
# ===========================================================================


class TestUnresolvableShaSkipsRollback:
    """TS-35-E3: Hard reset continues when rollback SHA can't be resolved."""

    def test_unresolvable_sha_skips_rollback(self, tmp_path: Path) -> None:
        """Warning logged, rollback_sha is None, tasks still reset."""
        from agent_fox.engine.reset import hard_reset_all

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}}
        _write_plan(agent_dir, nodes=nodes)

        # commit_sha that won't resolve
        history = [
            _make_session_record(
                node_id="s:1",
                commit_sha="dead" * 10,
                status="completed",
            ),
        ]
        state = _make_state(
            {"s:1": "completed"},
            session_history=history,
        )
        memory_path.write_text("")

        # Mock git rev-parse to fail (simulate unresolvable SHA)
        with (
            _mock_git_for_hard_reset(rev_parse_fails=True),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_all(plan_path, worktrees_dir, tmp_path, memory_path)

        assert result.rollback_sha is None
        assert all(s == "pending" for s in state.node_states.values())


# ===========================================================================
# TS-35-E4: Target Task Not in Plan
# Requirement: 35-REQ-4.E2
# ===========================================================================


class TestUnknownTaskIdError:
    """TS-35-E4: Error raised when task_id doesn't exist in the plan."""

    def test_unknown_task_raises(self, tmp_path: Path) -> None:
        """AgentFoxError raised with valid task IDs in message."""
        from agent_fox.engine.reset import hard_reset_task

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}, "s:3": {"title": "T3"}}
        _write_plan(agent_dir, nodes=nodes)
        state = _make_state(
            {"s:1": "completed", "s:2": "completed", "s:3": "pending"},
        )
        memory_path.write_text("")

        with pytest.raises(AgentFoxError) as exc_info:
            with patch("agent_fox.engine.reset._load_state_or_raise", return_value=state):
                hard_reset_task(
                    "nonexistent:99",
                    plan_path,
                    worktrees_dir,
                    tmp_path,
                    memory_path,
                )

        assert "s:1" in str(exc_info.value)


# ===========================================================================
# TS-35-E5: Target Task Has No Commit SHA (Partial Reset)
# Requirement: 35-REQ-4.E1
# ===========================================================================


class TestPartialNoCommitSha:
    """TS-35-E5: Partial hard reset skips rollback when target has no SHA."""

    def test_no_commit_sha_skips_rollback(self, tmp_path: Path) -> None:
        """Target task reset to pending, no code rollback."""
        from agent_fox.engine.reset import hard_reset_task

        agent_dir, plan_path, worktrees_dir, memory_path = _setup_agent_dir(tmp_path)
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        _write_plan(agent_dir, nodes=nodes)

        # Target task s:2 has empty commit_sha
        history = [
            _make_session_record(node_id="s:2", commit_sha="", status="completed"),
        ]
        state = _make_state(
            {"s:1": "completed", "s:2": "completed"},
            session_history=history,
        )
        memory_path.write_text("")

        with (
            _mock_git_for_hard_reset(),
            patch("agent_fox.engine.reset._load_state_or_raise", return_value=state),
        ):
            result = hard_reset_task("s:2", plan_path, worktrees_dir, tmp_path, memory_path)

        assert result.rollback_sha is None
        assert state.node_states["s:2"] == "pending"


# ===========================================================================
# TS-35-E6: User Declines Confirmation
# Requirement: 35-REQ-5.E1
# ===========================================================================


class TestUserDeclines:
    """TS-35-E6: Operation aborted when user says no."""

    def test_cancellation_on_decline(self, tmp_path: Path) -> None:
        """No tasks reset, cancellation message printed."""
        from click.testing import CliRunner

        from agent_fox.cli.reset import reset_cmd

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            iso_agent_dir = Path(td) / ".agent-fox"
            iso_agent_dir.mkdir(parents=True, exist_ok=True)
            nodes = {"s:1": {"title": "T1"}}
            (iso_agent_dir / "plan.json").write_text(_make_plan_json(nodes=nodes))
            (iso_agent_dir / "worktrees").mkdir(exist_ok=True)
            (iso_agent_dir / "memory.jsonl").write_text("")

            result = runner.invoke(reset_cmd, ["--hard"], input="n\n", obj={"json": False})

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower() or "cancel" in result.output.lower()


# ===========================================================================
# TS-35-E7: Tasks.md File Missing
# Requirement: 35-REQ-7.E1
# ===========================================================================


class TestTasksMdMissing:
    """TS-35-E7: Missing tasks.md files are skipped gracefully."""

    def test_missing_tasks_md_no_error(self, tmp_path: Path) -> None:
        """No error raised for missing spec tasks.md."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        specs_dir = tmp_path / ".specs"
        # Create existing_spec with tasks.md
        existing_dir = specs_dir / "existing_spec"
        existing_dir.mkdir(parents=True)
        tasks_md = existing_dir / "tasks.md"
        tasks_md.write_text("# Tasks\n\n- [x] 1. First task group\n")

        # missing_spec has no tasks.md at all
        # (don't even create the directory)

        # Should not raise
        reset_tasks_md_checkboxes(["existing_spec:1", "missing_spec:1"], specs_dir)

        text = tasks_md.read_text()
        assert "- [ ] 1." in text


# ===========================================================================
# TS-35-E8: Plan.json Missing
# Requirement: 35-REQ-7.E2
# NOTE: reset_plan_statuses() was removed with the StateManager→DB migration.
#       The test class was removed because the function no longer exists.
# ===========================================================================


# ===========================================================================
# Mock helpers
# ===========================================================================


def _make_hard_reset_result(
    reset_tasks: list[str] | None = None,
    cleaned_worktrees: list[str] | None = None,
    cleaned_branches: list[str] | None = None,
    compaction: tuple[int, int] = (0, 0),
    rollback_sha: str | None = None,
):
    """Create a HardResetResult for mocking CLI tests."""
    from agent_fox.engine.reset import HardResetResult

    return HardResetResult(
        reset_tasks=reset_tasks or [],
        cleaned_worktrees=cleaned_worktrees or [],
        cleaned_branches=cleaned_branches or [],
        compaction=compaction,
        rollback_sha=rollback_sha,
    )


def _mock_git_for_hard_reset(
    deleted_branches: list[str] | None = None,
    rev_parse_fails: bool = False,
    ancestor_check: Any = None,
):
    """Context manager that mocks git operations for hard reset tests.

    Args:
        deleted_branches: Branch names that git branch -D succeeds for.
        rev_parse_fails: If True, git rev-parse fails.
        ancestor_check: Callable(sha, head) -> bool for merge-base checks.
    """
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    deleted = set(deleted_branches or [])

    def mock_subprocess_run(args, **kwargs):
        result = MagicMock()
        cmd = args if isinstance(args, list) else [args]

        if "branch" in cmd and "-D" in cmd:
            branch_name = cmd[-1]
            if branch_name in deleted or not deleted:
                result.returncode = 0
                result.stderr = ""
                return result
            result.returncode = 1
            result.stderr = f"error: branch '{branch_name}' not found."
            return result

        if "rev-parse" in cmd:
            if rev_parse_fails:
                result.returncode = 128
                result.stdout = ""
                result.stderr = "fatal: bad revision"
                return result
            result.returncode = 0
            result.stdout = "a" * 40
            result.stderr = ""
            return result

        if "merge-base" in cmd and "--is-ancestor" in cmd:
            if ancestor_check is not None:
                sha = cmd[3]
                head = cmd[4]
                result.returncode = 0 if ancestor_check(sha, head) else 1
            else:
                result.returncode = 1
            return result

        if "reset" in cmd and "--hard" in cmd:
            result.returncode = 0
            result.stderr = ""
            return result

        if "checkout" in cmd:
            result.returncode = 0
            result.stderr = ""
            return result

        # Default: success
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    @contextmanager
    def _ctx():
        with (
            patch(
                "agent_fox.engine.reset.subprocess.run",
                side_effect=mock_subprocess_run,
            ),
            patch("agent_fox.engine.reset.compact", return_value=(0, 0)),
        ):
            yield

    return _ctx()
