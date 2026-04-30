"""Barrier entry operation tests: worktree verification and bidirectional develop sync.

Test Spec: TS-51-5 through TS-51-11
Requirements: 51-REQ-2.1, 51-REQ-2.2, 51-REQ-2.3, 51-REQ-2.E1,
              51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3, 51-REQ-3.E1,
              51-REQ-3.E2, 51-REQ-3.E3
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.engine.barrier import (
    _format_progress_line,
    run_sync_barrier_sequence,
    sync_develop_bidirectional,
    verify_worktrees,
)
from agent_fox.engine.state import ExecutionState


class TestVerifyWorktreesOrphansFound:
    """TS-51-5: Worktree verification finds orphans.

    Verify that orphaned worktree directories are detected and logged.

    Requirements: 51-REQ-2.1, 51-REQ-2.2
    """

    def test_finds_orphaned_worktree_dirs(self, tmp_path: Path) -> None:
        """Orphaned worktree subdirectories are detected."""
        wt_dir = tmp_path / ".agent-fox" / "worktrees"
        (wt_dir / "spec_a" / "1").mkdir(parents=True)
        (wt_dir / "spec_b" / "2").mkdir(parents=True)

        result = verify_worktrees(tmp_path)
        assert len(result) == 2
        names = {p.name for p in result}
        assert "spec_a" in names
        assert "spec_b" in names

    def test_logs_warning_for_orphans(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """WARNING log emitted listing orphaned paths."""
        wt_dir = tmp_path / ".agent-fox" / "worktrees"
        (wt_dir / "spec_a" / "1").mkdir(parents=True)
        (wt_dir / "spec_b" / "2").mkdir(parents=True)

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.barrier"):
            verify_worktrees(tmp_path)

        assert "spec_a" in caplog.text
        assert "spec_b" in caplog.text


class TestVerifyWorktreesNoOrphans:
    """TS-51-6: Worktree verification with no orphans.

    Requirements: 51-REQ-2.3
    """

    def test_returns_empty_list_when_no_orphans(self, tmp_path: Path) -> None:
        """Empty worktrees directory returns empty list."""
        wt_dir = tmp_path / ".agent-fox" / "worktrees"
        wt_dir.mkdir(parents=True)

        result = verify_worktrees(tmp_path)
        assert result == []

    def test_no_warning_when_no_orphans(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """No warnings logged when no orphans exist."""
        wt_dir = tmp_path / ".agent-fox" / "worktrees"
        wt_dir.mkdir(parents=True)

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.barrier"):
            verify_worktrees(tmp_path)

        assert caplog.text == ""


class TestVerifyWorktreesDirMissing:
    """TS-51-7: Worktree dir missing.

    Requirements: 51-REQ-2.E1
    """

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        """Missing .agent-fox/worktrees/ returns empty list, no exception."""
        result = verify_worktrees(tmp_path)
        assert result == []


class TestSyncDevelopBidirectionalSuccess:
    """TS-51-8: Bidirectional develop sync success.

    Requirements: 51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3
    """

    @pytest.mark.asyncio
    async def test_pull_then_push_with_lock(self, tmp_path: Path) -> None:
        """Pull sync runs first, then push, with MergeLock around both."""
        call_order: list[str] = []

        mock_lock_instance = AsyncMock()

        async def mock_aenter(self_: object) -> object:
            call_order.append("lock.__aenter__")
            return mock_lock_instance

        async def mock_aexit(self_: object, *args: object, **kwargs: object) -> bool:
            call_order.append("lock.__aexit__")
            return False

        mock_lock_instance.__aenter__ = mock_aenter
        mock_lock_instance.__aexit__ = mock_aexit

        async def mock_sync(repo_root: Path) -> None:
            call_order.append("sync")

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            if args[:2] == ["remote", "get-url"]:
                call_order.append("remote_check")
                return (0, "https://github.com/test/repo.git", "")
            if args[:2] == ["push", "origin"]:
                call_order.append("push")
                return (0, "", "")
            return (0, "", "")

        with (
            patch("agent_fox.engine.barrier.MergeLock", return_value=mock_lock_instance),
            patch(
                "agent_fox.engine.barrier._sync_develop_with_remote",
                side_effect=mock_sync,
            ),
            patch("agent_fox.engine.barrier.run_git", side_effect=mock_run_git),
        ):
            await sync_develop_bidirectional(tmp_path)

        # Verify lock context manager wraps operations
        assert call_order.index("lock.__aenter__") < call_order.index("sync")
        assert call_order.index("sync") < call_order.index("push")
        assert call_order.index("push") < call_order.index("lock.__aexit__")


class TestSyncDevelopPullFailSkipsPush:
    """TS-51-9: Pull sync failure skips push.

    Requirements: 51-REQ-3.E1
    """

    @pytest.mark.asyncio
    async def test_push_skipped_on_pull_failure(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """When pull sync fails, push is NOT attempted."""
        push_called = False

        mock_lock_instance = AsyncMock()
        mock_lock_instance.__aenter__ = AsyncMock(return_value=mock_lock_instance)
        mock_lock_instance.__aexit__ = AsyncMock(return_value=False)

        async def mock_sync(repo_root: Path) -> None:
            raise Exception("fetch failed")

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            nonlocal push_called
            if args[:2] == ["remote", "get-url"]:
                return (0, "https://github.com/test/repo.git", "")
            if args[:2] == ["push", "origin"]:
                push_called = True
                return (0, "", "")
            return (0, "", "")

        with (
            patch("agent_fox.engine.barrier.MergeLock", return_value=mock_lock_instance),
            patch(
                "agent_fox.engine.barrier._sync_develop_with_remote",
                side_effect=mock_sync,
            ),
            patch("agent_fox.engine.barrier.run_git", side_effect=mock_run_git),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.barrier"),
        ):
            await sync_develop_bidirectional(tmp_path)

        assert not push_called
        assert "WARNING" in caplog.text or len(caplog.records) > 0


class TestSyncDevelopPushFailNonBlocking:
    """TS-51-10: Push failure is non-blocking.

    Requirements: 51-REQ-3.E2
    """

    @pytest.mark.asyncio
    async def test_push_failure_does_not_raise(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Push failure logs warning but does not raise."""
        mock_lock_instance = AsyncMock()
        mock_lock_instance.__aenter__ = AsyncMock(return_value=mock_lock_instance)
        mock_lock_instance.__aexit__ = AsyncMock(return_value=False)

        async def mock_sync(repo_root: Path) -> None:
            pass  # success

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            if args[:2] == ["remote", "get-url"]:
                return (0, "https://github.com/test/repo.git", "")
            if args[:2] == ["push", "origin"]:
                raise Exception("push failed")
            return (0, "", "")

        with (
            patch("agent_fox.engine.barrier.MergeLock", return_value=mock_lock_instance),
            patch(
                "agent_fox.engine.barrier._sync_develop_with_remote",
                side_effect=mock_sync,
            ),
            patch("agent_fox.engine.barrier.run_git", side_effect=mock_run_git),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.barrier"),
        ):
            # Should not raise
            await sync_develop_bidirectional(tmp_path)

        assert len(caplog.records) > 0


class TestSyncDevelopNoOrigin:
    """TS-51-11: No origin remote skips sync.

    Requirements: 51-REQ-3.E3
    """

    @pytest.mark.asyncio
    async def test_skips_sync_when_no_origin(self, tmp_path: Path) -> None:
        """No fetch or push when origin remote doesn't exist."""
        sync_called = False
        push_called = False

        mock_lock_instance = AsyncMock()
        mock_lock_instance.__aenter__ = AsyncMock(return_value=mock_lock_instance)
        mock_lock_instance.__aexit__ = AsyncMock(return_value=False)

        async def mock_sync(repo_root: Path) -> None:
            nonlocal sync_called
            sync_called = True

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            nonlocal push_called
            if args[:2] == ["remote", "get-url"]:
                raise Exception("No such remote 'origin'")
            if args[:2] == ["push", "origin"]:
                push_called = True
                return (0, "", "")
            return (0, "", "")

        with (
            patch("agent_fox.engine.barrier.MergeLock", return_value=mock_lock_instance),
            patch(
                "agent_fox.engine.barrier._sync_develop_with_remote",
                side_effect=mock_sync,
            ),
            patch("agent_fox.engine.barrier.run_git", side_effect=mock_run_git),
        ):
            await sync_develop_bidirectional(tmp_path)

        assert not sync_called
        assert not push_called


# ---------------------------------------------------------------------------
# Knowledge compaction during sync barrier (fixes #211)
# ---------------------------------------------------------------------------


def _make_barrier_state() -> ExecutionState:
    """Create a minimal ExecutionState for barrier tests."""
    return ExecutionState(
        plan_hash="test",
        node_states={"spec:1": "completed"},
        session_history=[],
        total_cost=0.0,
        total_sessions=1,
        started_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:01Z",
    )


class TestCompactionCalledDuringBarrier:
    """Spec 114 removed compaction from sync barrier.

    NOTE: Knowledge compaction, consolidation, and rendering were removed
    from run_sync_barrier_sequence by spec 114 (knowledge decoupling).
    These tests now verify the barrier completes without those steps.
    """

    @pytest.mark.asyncio
    async def test_barrier_completes_with_db_conn(self, tmp_path: Path) -> None:
        """Barrier completes with knowledge_db_conn (no compaction)."""
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            await run_sync_barrier_sequence(
                state=_make_barrier_state(),
                sync_interval=5,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=MagicMock(),
            )

    @pytest.mark.asyncio
    async def test_barrier_completes_without_db_conn(self, tmp_path: Path) -> None:
        """Barrier completes when knowledge_db_conn is None."""
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            await run_sync_barrier_sequence(
                state=_make_barrier_state(),
                sync_interval=5,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=None,
            )

    @pytest.mark.asyncio
    async def test_barrier_completes_without_knowledge_steps(self, tmp_path: Path) -> None:
        """Barrier completes without compaction, rendering, or other knowledge steps."""
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            # Must not raise
            await run_sync_barrier_sequence(
                state=_make_barrier_state(),
                sync_interval=5,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
            )


# ---------------------------------------------------------------------------
# Progress line during sync barrier (issue #588)
# ---------------------------------------------------------------------------


class TestFormatProgressLine:
    """Unit tests for _format_progress_line()."""

    def test_single_status(self) -> None:
        """Only the present status appears in the output."""
        node_states = {"s:1": "completed", "s:2": "completed"}
        line = _format_progress_line(node_states)
        assert "completed: 2" in line
        assert "pending" not in line

    def test_multiple_statuses(self) -> None:
        """All present statuses appear, absent ones are omitted."""
        node_states = {
            "s:1": "completed",
            "s:2": "completed",
            "s:3": "pending",
            "s:4": "blocked",
        }
        line = _format_progress_line(node_states)
        assert "completed: 2" in line
        assert "pending: 1" in line
        assert "blocked: 1" in line
        assert "failed" not in line

    def test_empty_states_returns_no_tasks(self) -> None:
        """Empty node_states returns 'no tasks'."""
        assert _format_progress_line({}) == "no tasks"

    def test_output_is_single_line(self) -> None:
        """No embedded newlines in the formatted line."""
        node_states = {"s:1": "completed", "s:2": "in_progress", "s:3": "failed"}
        line = _format_progress_line(node_states)
        assert "\n" not in line


class TestBarrierProgressPrint:
    """Tests for the progress line printed by run_sync_barrier_sequence (issue #588)."""

    def _barrier_kwargs(self, state: ExecutionState, tmp_path: Path) -> dict:
        return {
            "state": state,
            "sync_interval": 5,
            "repo_root": tmp_path,
            "emit_audit": MagicMock(),
            "specs_dir": None,
            "hot_load_enabled": False,
            "hot_load_fn": AsyncMock(),
            "sync_plan_fn": MagicMock(),
            "barrier_callback": None,
        }

    @pytest.mark.asyncio
    async def test_progress_line_printed_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """AC-1: A progress line is printed to stdout when the barrier fires."""
        state = ExecutionState(
            plan_hash="test",
            node_states={
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "pending",
                "s:4": "blocked",
            },
            session_history=[],
            total_cost=0.0,
            total_sessions=2,
            started_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:01Z",
        )
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            await run_sync_barrier_sequence(**self._barrier_kwargs(state, tmp_path))

        captured = capsys.readouterr().out
        assert "completed" in captured
        assert "2" in captured  # completed count

    @pytest.mark.asyncio
    async def test_progress_line_is_single_line(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """AC-2: The printed output is exactly one line."""
        state = ExecutionState(
            plan_hash="test",
            node_states={"s:1": "completed", "s:2": "pending"},
            session_history=[],
            total_cost=0.0,
            total_sessions=1,
            started_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:01Z",
        )
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            await run_sync_barrier_sequence(**self._barrier_kwargs(state, tmp_path))

        captured = capsys.readouterr().out
        lines = [ln for ln in captured.split("\n") if ln.strip()]
        assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_progress_line_contains_all_present_statuses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC-3: Counts for all present statuses appear in the output."""
        state = ExecutionState(
            plan_hash="test",
            node_states={
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "pending",
                "s:4": "blocked",
            },
            session_history=[],
            total_cost=0.0,
            total_sessions=2,
            started_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:01Z",
        )
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                new_callable=AsyncMock,
            ),
        ):
            await run_sync_barrier_sequence(**self._barrier_kwargs(state, tmp_path))

        captured = capsys.readouterr().out
        assert "completed: 2" in captured
        assert "pending: 1" in captured
        assert "blocked: 1" in captured

    @pytest.mark.asyncio
    async def test_broken_pipe_does_not_abort_barrier(self, tmp_path: Path) -> None:
        """AC-5: OSError from print is suppressed; sync_develop_bidirectional still called."""
        sync_called = False

        async def _mock_sync(repo_root: Path) -> None:
            nonlocal sync_called
            sync_called = True

        state = _make_barrier_state()
        with (
            patch("agent_fox.engine.barrier.verify_worktrees", return_value=[]),
            patch(
                "agent_fox.engine.barrier.sync_develop_bidirectional",
                side_effect=_mock_sync,
            ),
            patch("builtins.print", side_effect=OSError("broken pipe")),
        ):
            # Must not raise despite print failing
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=5,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
            )

        assert sync_called, "sync_develop_bidirectional must still be called after print failure"
