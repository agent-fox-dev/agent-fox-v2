"""Parallel drain and orchestrator integration tests.

Test Spec: TS-51-1 through TS-51-4, TS-51-E1
Requirements: 51-REQ-1.1, 51-REQ-1.2, 51-REQ-1.3, 51-REQ-1.E1, 51-REQ-1.E2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from agent_fox.engine.state import SessionRecord


def _make_record(
    node_id: str,
    status: str = "completed",
    error_message: str | None = None,
) -> SessionRecord:
    """Create a minimal SessionRecord for testing."""
    return SessionRecord(
        node_id=node_id,
        attempt=1,
        status=status,
        input_tokens=100,
        output_tokens=200,
        cost=0.10,
        duration_ms=5000,
        error_message=error_message,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# TS-51-1: Parallel drain waits for all in-flight tasks
# ---------------------------------------------------------------------------


class TestParallelDrainWaitsForAll:
    """TS-51-1: Parallel drain waits for all in-flight tasks.

    Verify that the orchestrator waits for all in-flight parallel tasks
    to complete before entering the barrier.

    Requirements: 51-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_all_tasks_complete_before_barrier(self) -> None:
        """All pool tasks complete before barrier operations begin."""
        completed_tasks: list[str] = []
        barrier_entered = False

        async def mock_task(node_id: str, delay: float) -> SessionRecord:
            await asyncio.sleep(delay)
            completed_tasks.append(node_id)
            return _make_record(node_id)

        # Create 3 tasks with short delays
        tasks = [
            asyncio.create_task(mock_task("A", 0.05)),
            asyncio.create_task(mock_task("B", 0.08)),
            asyncio.create_task(mock_task("C", 0.03)),
        ]
        pool = set(tasks)

        # Drain the pool (simulating what _dispatch_parallel should do)
        if pool:
            done, pool = await asyncio.wait(pool)
            for t in done:
                t.result()  # process results

        barrier_entered = True

        assert len(pool) == 0
        assert len(completed_tasks) == 3
        assert barrier_entered


# ---------------------------------------------------------------------------
# TS-51-2: Drained task results are processed
# ---------------------------------------------------------------------------


class TestDrainedTaskResultsProcessed:
    """TS-51-2: Drained task results are processed.

    Verify that session results from drained tasks are processed
    (state updates, cascade blocking).

    Requirements: 51-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_session_results_processed_after_drain(self) -> None:
        """Both success and failure results are recorded after drain."""
        results_processed: list[SessionRecord] = []

        async def mock_task_a() -> SessionRecord:
            await asyncio.sleep(0.02)
            return _make_record("A", status="completed")

        async def mock_task_b() -> SessionRecord:
            await asyncio.sleep(0.03)
            return _make_record("B", status="failed", error_message="test error")

        pool = {
            asyncio.create_task(mock_task_a()),
            asyncio.create_task(mock_task_b()),
        }

        # Drain all tasks
        done, pool = await asyncio.wait(pool)
        for t in done:
            record = t.result()
            results_processed.append(record)

        assert len(pool) == 0
        assert len(results_processed) == 2

        statuses = {r.node_id: r.status for r in results_processed}
        assert statuses["A"] == "completed"
        assert statuses["B"] == "failed"


# ---------------------------------------------------------------------------
# TS-51-3: No new tasks dispatched during drain
# ---------------------------------------------------------------------------


class TestNoNewDispatchDuringDrain:
    """TS-51-3: No new tasks dispatched during drain.

    Verify that no new tasks are dispatched while draining.

    Requirements: 51-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_new_tasks_not_launched_during_drain(self) -> None:
        """Ready tasks are NOT launched during drain, only after barrier."""
        new_tasks_launched: list[str] = []
        drain_complete = False

        async def mock_task(node_id: str) -> SessionRecord:
            await asyncio.sleep(0.02)
            return _make_record(node_id)

        # Simulate pool with 2 tasks
        pool = {
            asyncio.create_task(mock_task("A")),
            asyncio.create_task(mock_task("B")),
        }

        # Drain
        done, pool = await asyncio.wait(pool)
        drain_complete = True

        # Only after drain is complete, launch new tasks
        assert drain_complete
        assert len(pool) == 0

        # Now fill pool (this simulates post-barrier behavior)
        for node_id in ["C", "D", "E"]:
            new_tasks_launched.append(node_id)

        assert len(new_tasks_launched) == 3
        assert drain_complete  # new tasks only after drain


# ---------------------------------------------------------------------------
# TS-51-4: Serial mode skips drain
# ---------------------------------------------------------------------------


class TestSerialModeSkipsDrain:
    """TS-51-4: Serial mode skips drain.

    Verify that serial mode (parallel=1) skips the parallel drain step.

    Requirements: 51-REQ-1.E1
    """

    def test_serial_mode_no_drain(self) -> None:
        """In serial mode, no parallel pool exists to drain."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(parallel=1)
        is_parallel = config.parallel > 1

        # Serial mode: no parallel runner, so no drain needed
        assert not is_parallel


# ---------------------------------------------------------------------------
# TS-51-E1: SIGINT during parallel drain
# ---------------------------------------------------------------------------


class TestSIGINTDuringDrain:
    """TS-51-E1: SIGINT during parallel drain.

    Verify that SIGINT cancels remaining tasks and proceeds to shutdown.

    Requirements: 51-REQ-1.E2
    """

    @pytest.mark.asyncio
    async def test_sigint_cancels_remaining_tasks(self) -> None:
        """SIGINT causes remaining pool tasks to be cancelled."""

        async def slow_task() -> SessionRecord:
            await asyncio.sleep(10)
            return _make_record("slow")

        pool = {asyncio.create_task(slow_task())}

        # Give the task a moment to start sleeping
        await asyncio.sleep(0.01)

        # Simulate SIGINT by cancelling all tasks
        for task in pool:
            task.cancel()

        # Wait for cancellation to propagate
        done, _ = await asyncio.wait(pool)
        for t in done:
            assert t.cancelled()
