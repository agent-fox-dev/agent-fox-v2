"""Parallel runner tests: concurrent dispatch, dependency ordering, state safety.

Test Spec: TS-04-12 (concurrent dispatch), TS-04-13 (respects dependencies),
           TS-04-14 (serialized state writes), TS-04-E5 (parallelism clamped),
           TS-04-E6 (fewer tasks than parallelism)
Requirements: 04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3, 04-REQ-6.E1
"""

from __future__ import annotations

import asyncio
import time

import pytest

from agent_fox.engine.parallel import ParallelRunner
from agent_fox.engine.state import SessionRecord

# -- Mock session runner for parallel tests ----------------------------------


class MockParallelSessionRunner:
    """Records dispatch timestamps and supports configurable delays."""

    def __init__(self, delay: float = 0.1) -> None:
        self.dispatch_times: dict[str, float] = {}
        self.complete_times: dict[str, float] = {}
        self._delay = delay
        self._lock = asyncio.Lock()
        self._concurrent_count = 0
        self.max_concurrent = 0

    async def __call__(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None = None,
    ) -> SessionRecord:
        self.dispatch_times[node_id] = time.monotonic()

        async with self._lock:
            self._concurrent_count += 1
            self.max_concurrent = max(
                self.max_concurrent,
                self._concurrent_count,
            )

        await asyncio.sleep(self._delay)

        async with self._lock:
            self._concurrent_count -= 1

        self.complete_times[node_id] = time.monotonic()
        return SessionRecord(
            node_id=node_id,
            attempt=attempt,
            status="completed",
            input_tokens=100,
            output_tokens=200,
            cost=0.10,
            duration_ms=int(self._delay * 1000),
            error_message=None,
            timestamp="2026-03-01T10:00:00Z",
        )


# -- Tests -------------------------------------------------------------------


class TestConcurrentDispatch:
    """TS-04-12: Parallel execution dispatches concurrent tasks.

    Verify the parallel runner dispatches multiple independent tasks
    concurrently.
    """

    @pytest.mark.asyncio
    async def test_all_independent_tasks_completed(self) -> None:
        """All 4 independent tasks are dispatched and completed."""
        mock = MockParallelSessionRunner(delay=0.05)

        async def factory(node_id: str):
            return await mock(node_id, 1, None)

        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None), ("C", 1, None), ("D", 1, None)]

        async def on_complete(record: SessionRecord) -> None:
            pass  # No-op callback

        records = await runner.execute_batch(tasks, on_complete)

        assert len(records) == 4
        assert all(r.status == "completed" for r in records)

    @pytest.mark.asyncio
    async def test_tasks_run_concurrently(self) -> None:
        """At least 2 tasks have overlapping execution times."""
        mock = MockParallelSessionRunner(delay=0.1)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None), ("C", 1, None), ("D", 1, None)]

        async def on_complete(record: SessionRecord) -> None:
            pass

        start = time.monotonic()
        await runner.execute_batch(tasks, on_complete)
        elapsed = time.monotonic() - start

        # 4 tasks at 0.1s each, if sequential would be 0.4s+
        # Concurrent should be closer to 0.1s
        assert elapsed < 0.3
        assert mock.max_concurrent >= 2


class TestRespectsDepencies:
    """TS-04-13: Parallel execution respects dependencies.

    In parallel mode, tasks with unmet dependencies are not dispatched
    prematurely. The orchestrator (not the parallel runner directly)
    is responsible for this, but we verify the runner correctly handles
    batches of only ready tasks.
    """

    @pytest.mark.asyncio
    async def test_batch_executes_only_given_tasks(self) -> None:
        """The runner only dispatches tasks in the provided batch."""
        mock = MockParallelSessionRunner(delay=0.01)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        # Only A and B are ready (C and D have dependencies, handled by
        # the orchestrator)
        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None)]

        async def on_complete(record: SessionRecord) -> None:
            pass

        records = await runner.execute_batch(tasks, on_complete)

        assert len(records) == 2
        dispatched = {r.node_id for r in records}
        assert dispatched == {"A", "B"}
        assert "C" not in mock.dispatch_times
        assert "D" not in mock.dispatch_times


class TestSerializedStateWrites:
    """TS-04-14: Parallel state writes are serialized.

    Verify that the on_complete callback is invoked under a lock so
    concurrent state writes do not interleave.
    """

    @pytest.mark.asyncio
    async def test_callbacks_invoked_for_each_task(self) -> None:
        """on_complete callback is called once per task."""
        mock = MockParallelSessionRunner(delay=0.05)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        completed_nodes: list[str] = []

        async def on_complete(record: SessionRecord) -> None:
            completed_nodes.append(record.node_id)

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None), ("C", 1, None), ("D", 1, None)]
        await runner.execute_batch(tasks, on_complete)

        assert set(completed_nodes) == {"A", "B", "C", "D"}

    @pytest.mark.asyncio
    async def test_callbacks_serialized_under_lock(self) -> None:
        """Callbacks are not called concurrently (lock serialization)."""
        mock = MockParallelSessionRunner(delay=0.05)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        concurrent_callbacks = 0
        max_concurrent_callbacks = 0

        async def on_complete(record: SessionRecord) -> None:
            nonlocal concurrent_callbacks, max_concurrent_callbacks
            # The runner's lock should ensure this is never >1
            concurrent_callbacks += 1
            max_concurrent_callbacks = max(
                max_concurrent_callbacks,
                concurrent_callbacks,
            )
            await asyncio.sleep(0.02)  # Simulate state write work
            concurrent_callbacks -= 1

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None), ("C", 1, None), ("D", 1, None)]
        await runner.execute_batch(tasks, on_complete)

        assert max_concurrent_callbacks == 1


class TestParallelismClamped:
    """TS-04-E5: Parallelism clamped to 8.

    Verify parallelism values above 8 are clamped.
    """

    def test_max_parallelism_capped_at_8(self) -> None:
        """ParallelRunner clamps max_parallelism to 8."""
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: MockParallelSessionRunner(),
            max_parallelism=16,
            inter_session_delay=0,
        )

        assert runner._max_parallelism == 8

    def test_max_parallelism_8_unchanged(self) -> None:
        """max_parallelism=8 is not changed."""
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: MockParallelSessionRunner(),
            max_parallelism=8,
            inter_session_delay=0,
        )

        assert runner._max_parallelism == 8

    def test_max_parallelism_under_8_unchanged(self) -> None:
        """max_parallelism < 8 is not clamped."""
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: MockParallelSessionRunner(),
            max_parallelism=4,
            inter_session_delay=0,
        )

        assert runner._max_parallelism == 4


class TestFewerTasksThanParallelism:
    """TS-04-E6: Fewer ready tasks than parallelism.

    Verify parallel runner does not block waiting for more tasks
    when fewer are available than the parallelism limit.
    """

    @pytest.mark.asyncio
    async def test_two_tasks_with_parallelism_four(self) -> None:
        """2 tasks with parallelism=4 complete without blocking."""
        mock = MockParallelSessionRunner(delay=0.01)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None), ("B", 1, None)]

        async def on_complete(record: SessionRecord) -> None:
            pass

        records = await runner.execute_batch(tasks, on_complete)

        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_single_task_with_high_parallelism(self) -> None:
        """1 task with parallelism=8 completes without blocking."""
        mock = MockParallelSessionRunner(delay=0.01)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=8,
            inter_session_delay=0,
        )

        tasks: list[tuple[str, int, str | None]] = [("A", 1, None)]

        async def on_complete(record: SessionRecord) -> None:
            pass

        records = await runner.execute_batch(tasks, on_complete)

        assert len(records) == 1
        assert records[0].node_id == "A"


class TestExecuteOne:
    """Tests for the execute_one method used by streaming pool dispatch."""

    @pytest.mark.asyncio
    async def test_execute_one_returns_record(self) -> None:
        """execute_one returns a SessionRecord on success."""
        mock = MockParallelSessionRunner(delay=0.01)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        record = await runner.execute_one("A", 1, None)

        assert record.node_id == "A"
        assert record.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_one_handles_exception(self) -> None:
        """execute_one returns a failed record on exception."""

        class FailingRunner:
            async def execute(
                self,
                node_id: str,
                attempt: int,
                previous_error: str | None = None,
            ) -> SessionRecord:
                raise RuntimeError("session crashed")

        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: FailingRunner(),
            max_parallelism=4,
            inter_session_delay=0,
        )

        record = await runner.execute_one("A", 1, None)

        assert record.node_id == "A"
        assert record.status == "failed"
        assert "session crashed" in (record.error_message or "")

    @pytest.mark.asyncio
    async def test_track_tasks_updates_in_flight(self) -> None:
        """track_tasks updates the in-flight task list for cancellation."""
        mock = MockParallelSessionRunner(delay=0.5)
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: mock,
            max_parallelism=4,
            inter_session_delay=0,
        )

        task = asyncio.create_task(runner.execute_one("A", 1, None))
        runner.track_tasks([task])

        assert len(runner._in_flight_tasks) == 1

        await runner.cancel_all()

        assert len(runner._in_flight_tasks) == 0

    @pytest.mark.asyncio
    async def test_max_parallelism_property(self) -> None:
        """max_parallelism property returns the effective value."""
        runner = ParallelRunner(
            session_runner_factory=lambda nid, **kw: MockParallelSessionRunner(),
            max_parallelism=3,
            inter_session_delay=0,
        )
        assert runner.max_parallelism == 3
