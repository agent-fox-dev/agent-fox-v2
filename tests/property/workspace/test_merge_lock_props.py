"""Property tests for MergeLock.

Test Spec: TS-45-P1 through TS-45-P4
Requirements: 45-REQ-1.1, 45-REQ-1.4, 45-REQ-2.1, 45-REQ-2.2,
              45-REQ-1.E1, 45-REQ-6.1, 45-REQ-6.2
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.merge_lock import MergeLock

# ---------------------------------------------------------------------------
# TS-45-P1: Mutual Exclusion
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    """Property 1: At most one lock holder at any time."""

    @pytest.mark.asyncio
    @given(
        n_tasks=st.integers(min_value=2, max_value=6),
        hold_ms=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=10, deadline=30000)
    async def test_mutual_exclusion(self, n_tasks: int, hold_ms: int, tmp_path_factory: pytest.TempPathFactory) -> None:
        """A shared counter never exceeds 1 during any lock-held period."""
        repo_root = tmp_path_factory.mktemp("mutex")
        lock = MergeLock(repo_root, timeout=30.0, poll_interval=0.01)
        counter = 0
        max_concurrent = 0

        async def worker() -> None:
            nonlocal counter, max_concurrent
            async with lock:
                counter += 1
                if counter > max_concurrent:
                    max_concurrent = counter
                assert counter <= 1, f"Mutual exclusion violated: {counter}"
                await asyncio.sleep(hold_ms / 1000.0)
                counter -= 1

        await asyncio.gather(*[worker() for _ in range(n_tasks)])
        assert max_concurrent <= 1


# ---------------------------------------------------------------------------
# TS-45-P2: Lock Always Released
# ---------------------------------------------------------------------------


class TestLockAlwaysReleased:
    """Property 2: Lock released regardless of exception."""

    @pytest.mark.asyncio
    @given(
        exc_type=st.sampled_from([ValueError, RuntimeError, IntegrationError, None]),
    )
    @settings(max_examples=10, deadline=10000)
    async def test_lock_always_released(
        self,
        exc_type: type[Exception] | None,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """After async with block exits, lock file does not exist."""
        repo_root = tmp_path_factory.mktemp("release")
        lock = MergeLock(repo_root)
        lock_file = repo_root / ".agent-fox" / "merge.lock"

        try:
            async with lock:
                if exc_type is not None:
                    raise exc_type("test error")
        except Exception:
            pass

        assert not lock_file.exists()


# ---------------------------------------------------------------------------
# TS-45-P3: Stale Lock Recovery
# ---------------------------------------------------------------------------


class TestStaleLockRecovery:
    """Property 3: Stale locks are always recoverable."""

    @pytest.mark.asyncio
    @given(
        stale_factor=st.floats(min_value=1.0, max_value=5.0),
    )
    @settings(max_examples=5, deadline=10000)
    async def test_stale_lock_recovery(
        self,
        stale_factor: float,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """acquire() succeeds within expected time for stale locks."""
        repo_root = tmp_path_factory.mktemp("stale")
        stale_timeout = 0.1  # 100ms for fast tests
        poll_interval = 0.02

        # Create stale lock
        agent_fox_dir = repo_root / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"
        lock_content = json.dumps(
            {
                "pid": 999999,
                "hostname": "test",
                "acquired_at": "2026-01-01T00:00:00Z",
            }
        )
        lock_file.write_text(lock_content)
        stale_age = stale_timeout * stale_factor
        stale_time = time.time() - stale_age
        os.utime(lock_file, (stale_time, stale_time))

        lock = MergeLock(
            repo_root,
            timeout=5.0,
            stale_timeout=stale_timeout,
            poll_interval=poll_interval,
        )

        start = time.time()
        await lock.acquire()
        elapsed = time.time() - start

        # Should acquire quickly since lock is stale
        assert elapsed < stale_timeout + 2 * poll_interval + 0.5
        await lock.release()


# ---------------------------------------------------------------------------
# TS-45-P4: No Blind Strategy Options (static analysis)
# ---------------------------------------------------------------------------


class TestNoBlindStrategyOptions:
    """Property 4: Source code does not contain blind strategy options."""

    def test_no_x_theirs_in_harvest(self) -> None:
        """harvest.py does not use -X theirs."""
        import agent_fox.workspace.harvest as harvest_mod

        source = inspect.getsource(harvest_mod)
        assert '"-X", "theirs"' not in source
        assert "'-X', 'theirs'" not in source
        assert 'strategy_option="theirs"' not in source
        assert "strategy_option='theirs'" not in source

    def test_no_x_ours_in_workspace(self) -> None:
        """workspace submodules do not use -X ours."""
        import agent_fox.workspace.develop as develop_mod
        import agent_fox.workspace.git as git_mod

        for mod in (develop_mod, git_mod):
            source = inspect.getsource(mod)
            assert '"-X", "ours"' not in source
            assert "'-X', 'ours'" not in source
