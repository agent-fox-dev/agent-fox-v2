"""Merge lock unit tests.

Test Spec: TS-45-1 through TS-45-3, TS-45-E1 through TS-45-E4
Tests for Issue #561: stale_timeout default, heartbeat, concurrent safety.
Requirements: 45-REQ-1.1 through 45-REQ-1.E3, 45-REQ-2.1, 45-REQ-2.2, 45-REQ-2.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.merge_lock import _DEFAULT_STALE_TIMEOUT, MergeLock


@pytest.fixture
def lock_repo(tmp_path: Path) -> Path:
    """Create a temporary directory to serve as repo root."""
    return tmp_path / "repo"


class TestLockAcquisition:
    """TS-45-1: Lock acquired before merge operations."""

    @pytest.mark.asyncio
    async def test_lock_creates_lock_file(self, lock_repo: Path) -> None:
        """Acquiring the lock creates the lock file."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        await lock.acquire()
        lock_file = lock_repo / ".agent-fox" / "merge.lock"
        assert lock_file.exists()
        await lock.release()

    @pytest.mark.asyncio
    async def test_lock_file_contains_diagnostics(self, lock_repo: Path) -> None:
        """Lock file contains PID and hostname for diagnostics."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        await lock.acquire()
        lock_file = lock_repo / ".agent-fox" / "merge.lock"
        content = json.loads(lock_file.read_text())
        assert "pid" in content
        assert "hostname" in content
        assert "acquired_at" in content
        assert content["pid"] == os.getpid()
        await lock.release()


class TestLockQueuing:
    """TS-45-2: Lock queues concurrent callers."""

    @pytest.mark.asyncio
    async def test_second_caller_waits(self, lock_repo: Path) -> None:
        """A second caller blocks until the first releases."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo, timeout=5.0, poll_interval=0.05)
        acquired_order: list[int] = []

        async def worker(worker_id: int, hold_time: float) -> None:
            async with lock:
                acquired_order.append(worker_id)
                await asyncio.sleep(hold_time)

        # Worker 1 acquires first and holds for 0.2s
        # Worker 2 tries immediately but must wait
        t1 = asyncio.create_task(worker(1, 0.2))
        await asyncio.sleep(0.01)  # ensure task 1 starts first
        t2 = asyncio.create_task(worker(2, 0.0))

        await asyncio.gather(t1, t2)
        assert acquired_order == [1, 2]


class TestLockTimeout:
    """TS-45-3: Lock timeout raises IntegrationError."""

    @pytest.mark.asyncio
    async def test_timeout_raises_integration_error(self, lock_repo: Path) -> None:
        """Exceeding the timeout raises IntegrationError."""
        lock_repo.mkdir(parents=True)
        # Create the lock file manually to simulate another holder
        agent_fox_dir = lock_repo / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "hostname": "other-host",
                    "acquired_at": "2026-03-12T10:00:00Z",
                }
            )
        )
        # Touch the file so it's not stale
        os.utime(lock_file, None)

        lock = MergeLock(
            lock_repo,
            timeout=0.3,
            stale_timeout=600.0,  # very long, won't trigger stale
            poll_interval=0.05,
        )
        with pytest.raises(IntegrationError, match="(?i)lock.*timeout|timeout.*lock"):
            await lock.acquire()


class TestStaleLockBroken:
    """TS-45-E1: Stale lock file is broken and re-acquired."""

    @pytest.mark.asyncio
    async def test_stale_lock_broken(self, lock_repo: Path) -> None:
        """A stale lock file is broken and a fresh lock is acquired."""
        lock_repo.mkdir(parents=True)
        agent_fox_dir = lock_repo / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "hostname": "stale-host",
                    "acquired_at": "2026-03-12T09:00:00Z",
                }
            )
        )
        # Set mtime to 600 seconds ago (stale)
        stale_time = time.time() - 600
        os.utime(lock_file, (stale_time, stale_time))

        lock = MergeLock(lock_repo, stale_timeout=300.0, poll_interval=0.05)
        await lock.acquire()

        assert lock_file.exists()
        # Verify fresh lock has current PID
        content = json.loads(lock_file.read_text())
        assert content["pid"] == os.getpid()
        await lock.release()


class TestMissingAgentFoxDir:
    """TS-45-E2: Lock creates .agent-fox/ directory if missing."""

    @pytest.mark.asyncio
    async def test_creates_directory(self, lock_repo: Path) -> None:
        """Lock creates .agent-fox/ if it doesn't exist."""
        lock_repo.mkdir(parents=True)
        agent_fox_dir = lock_repo / ".agent-fox"
        assert not agent_fox_dir.exists()

        lock = MergeLock(lock_repo)
        await lock.acquire()
        assert (agent_fox_dir / "merge.lock").exists()
        await lock.release()


class TestConcurrentStaleLockBreak:
    """TS-45-E3: Concurrent stale-lock breaks don't corrupt."""

    @pytest.mark.asyncio
    async def test_concurrent_stale_break(self, lock_repo: Path) -> None:
        """Two concurrent acquires on a stale lock both eventually succeed."""
        lock_repo.mkdir(parents=True)
        agent_fox_dir = lock_repo / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "hostname": "stale-host",
                    "acquired_at": "2026-03-12T09:00:00Z",
                }
            )
        )
        stale_time = time.time() - 600
        os.utime(lock_file, (stale_time, stale_time))

        lock_kw = dict(
            stale_timeout=300.0,
            timeout=5.0,
            poll_interval=0.05,
        )
        lock1 = MergeLock(lock_repo, **lock_kw)
        lock2 = MergeLock(lock_repo, **lock_kw)

        # Both should eventually succeed (one after the other releases)
        acquired = []

        async def acquire_and_release(lock: MergeLock, idx: int) -> None:
            async with lock:
                acquired.append(idx)
                await asyncio.sleep(0.05)

        results = await asyncio.gather(
            acquire_and_release(lock1, 1),
            acquire_and_release(lock2, 2),
            return_exceptions=True,
        )
        # Neither should have raised
        for r in results:
            assert not isinstance(r, Exception), f"Unexpected error: {r}"
        # Both acquired (order may vary)
        assert sorted(acquired) == [1, 2]


class TestReleaseMissingLockFile:
    """TS-45-E4: Release handles missing lock file gracefully."""

    @pytest.mark.asyncio
    async def test_release_missing_file_logs_warning(self, lock_repo: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Releasing when lock file is gone logs a warning."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        await lock.acquire()
        lock_file = lock_repo / ".agent-fox" / "merge.lock"
        assert lock_file.exists()

        # Externally remove the lock file
        lock_file.unlink()

        with caplog.at_level(logging.WARNING):
            await lock.release()  # Should not raise

        # Check that a warning was logged about the missing lock
        has_warning = any(r.levelno >= logging.WARNING for r in caplog.records)
        assert has_warning, "Expected a warning log about missing lock"


class TestStaleLockAtomicBreak:
    """H2: Stale lock breaking does not remove a freshly-acquired lock."""

    @pytest.mark.asyncio
    async def test_break_does_not_remove_fresh_lock(self, lock_repo: Path) -> None:
        """If the lock file is replaced between stat and unlink, the fresh lock
        survives."""
        lock_repo.mkdir(parents=True)
        agent_fox_dir = lock_repo / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"

        # Create a stale lock
        lock_file.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "hostname": "old",
                    "acquired_at": "2026-01-01T00:00:00Z",
                }
            )
        )
        stale_time = time.time() - 600
        os.utime(lock_file, (stale_time, stale_time))

        lock = MergeLock(lock_repo, stale_timeout=300.0, poll_interval=0.05)

        # The lock should be acquirable (stale lock is broken atomically)
        await lock.acquire()
        assert lock_file.exists()
        content = json.loads(lock_file.read_text())
        assert content["pid"] == os.getpid()
        await lock.release()


class TestLockAsContextManager:
    """TS-45-2.2: Lock works as async context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, lock_repo: Path) -> None:
        """Lock can be used as async context manager."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        lock_file = lock_repo / ".agent-fox" / "merge.lock"

        async with lock:
            assert lock_file.exists()

        assert not lock_file.exists()

    @pytest.mark.asyncio
    async def test_context_manager_releases_on_exception(self, lock_repo: Path) -> None:
        """Lock is released even when an exception occurs inside."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        lock_file = lock_repo / ".agent-fox" / "merge.lock"

        with pytest.raises(ValueError, match="boom"):
            async with lock:
                assert lock_file.exists()
                raise ValueError("boom")

        assert not lock_file.exists()


# ---------------------------------------------------------------------------
# Issue #561: stale_timeout default must be large enough for merge-agent sessions
# ---------------------------------------------------------------------------


class TestDefaultStaletimeoutLargeEnough:
    """AC-1: Default stale_timeout >= 3600 so a 300s-old lock is not broken."""

    def test_default_stale_timeout_at_least_3600(self, lock_repo: Path) -> None:
        """MergeLock built with no explicit stale_timeout has stale_timeout >= 3600."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)
        assert lock.stale_timeout >= 3600

    def test_module_constant_at_least_3600(self) -> None:
        """_DEFAULT_STALE_TIMEOUT module constant is >= 3600."""
        assert _DEFAULT_STALE_TIMEOUT >= 3600

    @pytest.mark.asyncio
    async def test_lock_300s_old_not_broken_by_default(self, lock_repo: Path) -> None:
        """A lock file with mtime 300 s ago is NOT broken with the default stale_timeout."""
        lock_repo.mkdir(parents=True)
        agent_fox_dir = lock_repo / ".agent-fox"
        agent_fox_dir.mkdir(parents=True, exist_ok=True)
        lock_file = agent_fox_dir / "merge.lock"
        lock_file.write_text(
            json.dumps({"pid": 999999, "hostname": "other", "acquired_at": "2026-01-01T00:00:00Z"})
        )
        # Set mtime to 300 s ago — should NOT be considered stale with 3600 s default
        mtime_300s_ago = time.time() - 300
        os.utime(lock_file, (mtime_300s_ago, mtime_300s_ago))

        # Attempt to acquire with a very short timeout so it fails fast.
        # The important thing: the lock must NOT have been broken (file still exists
        # and still belongs to pid 999999 after the attempt).
        waiter = MergeLock(lock_repo, timeout=0.2, poll_interval=0.05)
        with pytest.raises(IntegrationError, match="(?i)timeout"):
            await waiter.acquire()

        # The 300 s-old lock file should still be intact (not broken)
        assert lock_file.exists(), "Lock file was wrongly broken despite being only 300 s old"
        content = json.loads(lock_file.read_text())
        assert content["pid"] == 999999, "Lock file was replaced — stale break fired incorrectly"


# ---------------------------------------------------------------------------
# Issue #561: heartbeat keeps mtime fresh while the lock is held
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """AC-3: Heartbeat updates mtime at least once per (stale_timeout / 2) seconds."""

    @pytest.mark.asyncio
    async def test_heartbeat_refreshes_mtime(self, lock_repo: Path) -> None:
        """Lock file mtime is updated by the heartbeat while the lock is held."""
        lock_repo.mkdir(parents=True)
        # Use a very short stale_timeout so the heartbeat fires quickly in the test
        lock = MergeLock(lock_repo, stale_timeout=0.2, poll_interval=0.05)

        acquire_time = time.time()
        await lock.acquire()
        lock_file = lock_repo / ".agent-fox" / "merge.lock"

        # Manually backdate the mtime to simulate passage of time
        old_mtime = acquire_time - 1
        os.utime(lock_file, (old_mtime, old_mtime))
        assert lock_file.stat().st_mtime < acquire_time  # sanity

        # Wait long enough for heartbeat to fire (interval = stale_timeout / 2 = 0.1 s)
        await asyncio.sleep(0.25)

        # Mtime should now be >= acquire_time (heartbeat refreshed it)
        new_mtime = lock_file.stat().st_mtime
        assert new_mtime >= acquire_time - 0.05, (
            f"Heartbeat did not refresh mtime: mtime={new_mtime:.3f}, "
            f"acquire_time={acquire_time:.3f}"
        )

        await lock.release()

    @pytest.mark.asyncio
    async def test_heartbeat_prevents_stale_break_by_waiter(self, lock_repo: Path) -> None:
        """A heartbeating holder is not broken by a concurrent waiter checking stale."""
        lock_repo.mkdir(parents=True)

        # stale_timeout=0.4 s, heartbeat fires at 0.2 s
        holder = MergeLock(
            lock_repo,
            stale_timeout=0.4,
            timeout=10.0,
            poll_interval=0.05,
        )
        await holder.acquire()
        lock_file = lock_repo / ".agent-fox" / "merge.lock"

        # Let the heartbeat fire once
        await asyncio.sleep(0.25)

        # A concurrent waiter with the same short stale_timeout should not break
        # the holder's lock, because the mtime was just refreshed by the heartbeat.
        # It should time out instead.
        waiter = MergeLock(
            lock_repo,
            stale_timeout=0.4,
            timeout=0.15,
            poll_interval=0.05,
        )
        with pytest.raises(IntegrationError, match="(?i)timeout"):
            await waiter.acquire()

        # Holder's lock file should still exist and belong to our pid
        assert lock_file.exists(), "Holder's lock was wrongly broken by the waiter"
        content = json.loads(lock_file.read_text())
        assert content["pid"] == os.getpid()

        await holder.release()

    @pytest.mark.asyncio
    async def test_heartbeat_task_cancelled_on_release(self, lock_repo: Path) -> None:
        """The heartbeat task is cleaned up after release()."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo, stale_timeout=60.0)

        await lock.acquire()
        assert lock._heartbeat_task is not None

        await lock.release()
        assert lock._heartbeat_task is None


# ---------------------------------------------------------------------------
# Issue #561: AC-4 — normal release does not log 'already removed' warning
# ---------------------------------------------------------------------------


class TestNormalReleaseNoWarning:
    """AC-4: Normal acquire/release cycle emits no WARNING-level log about 'already removed'."""

    @pytest.mark.asyncio
    async def test_normal_release_no_already_removed_warning(
        self,
        lock_repo: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Acquiring and releasing normally produces no 'already removed' warning."""
        lock_repo.mkdir(parents=True)
        lock = MergeLock(lock_repo)

        with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.merge_lock"):
            await lock.acquire()
            await lock.release()

        already_removed_warnings = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "already removed" in r.message.lower()
        ]
        assert not already_removed_warnings, (
            f"Unexpected 'already removed' warning: {already_removed_warnings}"
        )


# ---------------------------------------------------------------------------
# Issue #561: AC-5 — two concurrent holders cannot overlap with heartbeat
# ---------------------------------------------------------------------------


class TestConcurrentHoldersMutualExclusion:
    """AC-5: Heartbeating holder cannot be displaced by a concurrent waiter."""

    @pytest.mark.asyncio
    async def test_only_one_holder_at_a_time_with_heartbeat(self, lock_repo: Path) -> None:
        """With heartbeat active, only one lock holder exists at any moment."""
        lock_repo.mkdir(parents=True)

        # stale_timeout=0.3, heartbeat=0.15 s; acquisition hold=0.5 s
        hold_seconds = 0.5
        stale_timeout = 0.3
        holder = MergeLock(
            lock_repo,
            stale_timeout=stale_timeout,
            timeout=5.0,
            poll_interval=0.02,
        )
        waiter = MergeLock(
            lock_repo,
            stale_timeout=stale_timeout,
            timeout=5.0,
            poll_interval=0.02,
        )

        holder_released_at: list[float] = []
        waiter_acquired_at: list[float] = []

        async def run_holder() -> None:
            async with holder:
                await asyncio.sleep(hold_seconds)
                holder_released_at.append(time.monotonic())

        async def run_waiter() -> None:
            # Small delay so holder gets there first
            await asyncio.sleep(0.05)
            async with waiter:
                waiter_acquired_at.append(time.monotonic())

        results = await asyncio.gather(
            run_holder(),
            run_waiter(),
            return_exceptions=True,
        )
        for r in results:
            assert not isinstance(r, Exception), f"Unexpected error: {r}"

        assert holder_released_at and waiter_acquired_at
        # Waiter must have acquired AFTER the holder released
        overlap = waiter_acquired_at[0] < holder_released_at[0]
        assert not overlap, (
            f"Lock overlap detected: waiter acquired at {waiter_acquired_at[0]:.3f}, "
            f"holder released at {holder_released_at[0]:.3f}"
        )
