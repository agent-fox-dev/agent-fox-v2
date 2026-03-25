"""Property tests for barrier entry operations.

Test Spec: TS-51-P1 (parallel drain empties pool),
           TS-51-P2 (worktree verification never raises),
           TS-51-P3 (develop sync never raises)
Requirements: 51-REQ-1.1, 51-REQ-1.2, 51-REQ-2.1, 51-REQ-2.E1,
              51-REQ-3.E1, 51-REQ-3.E2, 51-REQ-3.E3
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agent_fox.engine.barrier import sync_develop_bidirectional, verify_worktrees
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.engine.state import SessionRecord


def _make_record(node_id: str, status: str = "completed") -> SessionRecord:
    """Create a minimal SessionRecord."""
    return SessionRecord(
        node_id=node_id,
        attempt=1,
        status=status,
        input_tokens=100,
        output_tokens=200,
        cost=0.10,
        duration_ms=5000,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# TS-51-P1: Parallel drain empties pool
# ---------------------------------------------------------------------------


class TestParallelDrainEmptiesPool:
    """TS-51-P1: For any set of tasks, drain empties the pool.

    Property 1 from design.md.
    Validates: 51-REQ-1.1, 51-REQ-1.2
    """

    @given(
        task_count=st.integers(min_value=1, max_value=10),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_drain_empties_pool_and_processes_all(self, task_count: int) -> None:
        """For any 1-10 tasks, pool is empty after drain and all results processed."""

        async def mock_task(i: int) -> SessionRecord:
            await asyncio.sleep(0.001)
            status = "completed" if i % 2 == 0 else "failed"
            return _make_record(f"task_{i}", status)

        pool = {asyncio.create_task(mock_task(i)) for i in range(task_count)}

        # Drain
        done, remaining = await asyncio.wait(pool)
        results = [t.result() for t in done]

        assert len(remaining) == 0
        assert len(results) == task_count


# ---------------------------------------------------------------------------
# TS-51-P2: Worktree verification never raises
# ---------------------------------------------------------------------------


class TestWorktreeVerificationNeverRaises:
    """TS-51-P2: For any filesystem state, verify_worktrees completes.

    Property 2 from design.md.
    Validates: 51-REQ-2.1, 51-REQ-2.E1
    """

    @given(
        subdir_count=st.integers(min_value=0, max_value=5),
        dir_exists=st.booleans(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_verify_worktrees_never_raises(
        self, subdir_count: int, dir_exists: bool
    ) -> None:
        """verify_worktrees returns a list without raising for any state."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            if dir_exists:
                wt_dir = repo_root / ".agent-fox" / "worktrees"
                wt_dir.mkdir(parents=True)
                for i in range(subdir_count):
                    (wt_dir / f"spec_{i}" / "1").mkdir(parents=True)

            result = verify_worktrees(repo_root)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-51-P3: Develop sync never raises
# ---------------------------------------------------------------------------


class TestDevelopSyncNeverRaises:
    """TS-51-P3: For any git operation outcomes, sync completes.

    Property 3 from design.md.
    Validates: 51-REQ-3.E1, 51-REQ-3.E2, 51-REQ-3.E3
    """

    @given(
        remote_exists=st.booleans(),
        sync_succeeds=st.booleans(),
        push_succeeds=st.booleans(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_sync_never_raises(
        self,
        remote_exists: bool,
        sync_succeeds: bool,
        push_succeeds: bool,
    ) -> None:
        """sync_develop_bidirectional completes without exception."""
        mock_lock = AsyncMock()
        mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
        mock_lock.__aexit__ = AsyncMock(return_value=False)

        async def mock_sync(repo_root: Path) -> None:
            if not sync_succeeds:
                raise Exception("sync failed")

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            if args[:2] == ["remote", "get-url"]:
                if not remote_exists:
                    raise Exception("No such remote")
                return (0, "https://github.com/test/repo.git", "")
            if args[:2] == ["push", "origin"]:
                if not push_succeeds:
                    raise Exception("push failed")
                return (0, "", "")
            return (0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch(
                    "agent_fox.engine.barrier.MergeLock",
                    return_value=mock_lock,
                ),
                patch(
                    "agent_fox.engine.barrier._sync_develop_with_remote",
                    side_effect=mock_sync,
                ),
                patch(
                    "agent_fox.engine.barrier.run_git",
                    side_effect=mock_run_git,
                ),
            ):
                # Must not raise
                await sync_develop_bidirectional(Path(tmp))
