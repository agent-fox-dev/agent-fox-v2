"""Parallel runner: concurrent session execution via asyncio.

Runs up to N tasks concurrently, serializes state writes under an asyncio
lock, and supports cancellation of in-flight tasks on SIGINT.

Requirements: 04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from agent_fox.engine.state import SessionRecord, invoke_runner

logger = logging.getLogger(__name__)

MAX_PARALLELISM = 8


def _failure_record(node_id: str, attempt: int, exc: BaseException) -> SessionRecord:
    """Build a SessionRecord for a failed task."""
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status="failed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=str(exc),
        timestamp=datetime.now(UTC).isoformat(),
    )


class ParallelRunner:
    """Runs up to N tasks concurrently via asyncio.

    Supports two execution models:

    - **Batch** (``execute_batch``): Launch all tasks at once, bounded by a
      semaphore. Waits for all to complete before returning.  Used by tests.
    - **Streaming pool** (``execute_one`` + external pool management): The
      orchestrator manages a pool of asyncio tasks, launching new ones as
      slots open after each completion.  Preferred at runtime.

    State writes via completion callbacks are serialized under an
    ``asyncio.Lock`` to prevent interleaved writes.
    """

    def __init__(
        self,
        session_runner_factory: Callable[..., Any],
        max_parallelism: int,
        inter_session_delay: float,
    ) -> None:
        """Initialise the parallel runner.

        Args:
            session_runner_factory: Factory that creates a session runner
                for a given node_id. The returned runner is either a
                callable ``(node_id, attempt, previous_error) -> SessionRecord``
                or an object with an ``execute()`` method.
            max_parallelism: Maximum number of concurrent sessions.
                Clamped to 8 if higher.
            inter_session_delay: Seconds to wait between sessions
                (applied per-task after completion, before callback).
        """
        if max_parallelism > MAX_PARALLELISM:
            logger.warning(
                "Parallelism %d exceeds maximum of %d; clamped to %d.",
                max_parallelism,
                MAX_PARALLELISM,
                MAX_PARALLELISM,
            )
        self._session_runner_factory = session_runner_factory
        self._max_parallelism = min(max_parallelism, MAX_PARALLELISM)
        self._inter_session_delay = inter_session_delay
        self._state_lock = asyncio.Lock()
        self._in_flight_tasks: list[asyncio.Task[SessionRecord]] = []

    @property
    def max_parallelism(self) -> int:
        """Return the effective maximum parallelism."""
        return self._max_parallelism

    async def execute_one(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
        *,
        archetype: str = "coder",
        mode: str | None = None,
        instances: int = 1,
        assessed_tier: Any | None = None,
        run_id: str = "",
        timeout_override: int | None = None,
        max_turns_override: int | None = None,
    ) -> SessionRecord:
        """Execute a single session and return the record.

        This is the building block for streaming pool dispatch.
        The orchestrator wraps this in an ``asyncio.Task`` and manages
        the pool externally.

        Args:
            node_id: The task graph node to execute.
            attempt: The attempt number (1-indexed).
            previous_error: Error message from prior attempt, if any.
            archetype: Archetype name from the plan node.
            mode: Optional mode variant for the archetype (97-REQ-5.3).
            instances: Instance count from the plan node.
            assessed_tier: Model tier from adaptive routing assessment.
            run_id: Audit run identifier for correlation.
            timeout_override: Per-node session timeout override in minutes.
            max_turns_override: Per-node max_turns override.

        Returns:
            A SessionRecord with outcome, cost, and timing.
        """
        try:
            return await self._execute_session(
                node_id,
                attempt,
                previous_error,
                archetype=archetype,
                mode=mode,
                instances=instances,
                assessed_tier=assessed_tier,
                run_id=run_id,
                timeout_override=timeout_override,
                max_turns_override=max_turns_override,
            )
        except Exception as exc:
            logger.error(
                "Task %s failed with exception: %s",
                node_id,
                exc,
            )
            return _failure_record(node_id, attempt, exc)

    def track_tasks(self, tasks: list[asyncio.Task[SessionRecord]]) -> None:
        """Update the set of in-flight tasks (for SIGINT cancellation)."""
        self._in_flight_tasks = list(tasks)

    async def execute_batch(
        self,
        tasks: list[tuple[str, int, str | None]],
        on_complete: Callable[[SessionRecord], Awaitable[None]],
    ) -> list[SessionRecord]:
        """Execute a batch of tasks concurrently.

        Creates one asyncio task per entry in *tasks*, bounded by a
        semaphore to ``_max_parallelism`` concurrent executions. After
        each session completes, the ``on_complete`` callback is invoked
        under ``_state_lock`` so the orchestrator can safely update
        execution state.

        Args:
            tasks: List of ``(node_id, attempt, previous_error)`` tuples.
            on_complete: Callback invoked (under lock) after each session
                completes. Used by the orchestrator to update state and
                propagate graph changes.

        Returns:
            List of SessionRecords for all completed tasks.
        """
        semaphore = asyncio.Semaphore(self._max_parallelism)

        async def _run_one(
            node_id: str,
            attempt: int,
            previous_error: str | None,
        ) -> SessionRecord:
            async with semaphore:
                try:
                    record = await self._execute_session(
                        node_id,
                        attempt,
                        previous_error,
                    )
                except Exception as exc:
                    logger.error(
                        "Task %s failed with exception: %s",
                        node_id,
                        exc,
                    )
                    record = _failure_record(node_id, attempt, exc)

            # Invoke callback under lock to serialise state writes
            async with self._state_lock:
                await on_complete(record)

            return record

        # Launch all tasks concurrently
        self._in_flight_tasks = [
            asyncio.create_task(
                _run_one(node_id, attempt, previous_error),
                name=f"parallel-{node_id}",
            )
            for node_id, attempt, previous_error in tasks
        ]

        # Gather results, collecting exceptions rather than raising
        results = await asyncio.gather(
            *self._in_flight_tasks,
            return_exceptions=True,
        )

        records: list[SessionRecord] = []
        for result in results:
            if isinstance(result, SessionRecord):
                records.append(result)
            elif isinstance(result, BaseException):
                logger.error("Task failed with exception: %s", result)

        self._in_flight_tasks.clear()
        return records

    async def cancel_all(self) -> list[SessionRecord]:
        """Cancel all in-flight tasks. Called on SIGINT.

        Cancels every asyncio task that is still running and waits for
        them to finish. Returns a list of SessionRecords for all tasks
        that had not already been processed by the dispatch loop — either
        a synthesised failure record for cancelled/errored tasks, or the
        actual record for tasks that happened to complete just before
        cancellation.  The caller should pass these to
        ``result_handler.process()`` so that every in-flight session gets
        a ``session_outcomes`` row even on an interrupted run.

        Requirements: 536-AC-1, 536-AC-2, 536-AC-3
        """
        for task in self._in_flight_tasks:
            if not task.done():
                task.cancel()

        unprocessed: list[SessionRecord] = []
        if self._in_flight_tasks:
            results = await asyncio.gather(
                *self._in_flight_tasks,
                return_exceptions=True,
            )
            for task, result in zip(self._in_flight_tasks, results):
                if isinstance(result, SessionRecord):
                    # Task completed normally just before cancellation took
                    # effect but was not yet processed by the dispatch loop.
                    unprocessed.append(result)
                elif isinstance(result, BaseException):
                    # Task was cancelled or raised an unexpected error.
                    task_name = task.get_name()
                    node_id = task_name[len("parallel-") :] if task_name.startswith("parallel-") else task_name
                    unprocessed.append(_failure_record(node_id, 1, result))
            self._in_flight_tasks.clear()

        return unprocessed

    async def _execute_session(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
        *,
        archetype: str = "coder",
        mode: str | None = None,
        instances: int = 1,
        assessed_tier: Any | None = None,
        run_id: str = "",
        timeout_override: int | None = None,
        max_turns_override: int | None = None,
    ) -> SessionRecord:
        """Execute a single session via the factory-created runner."""
        runner = self._session_runner_factory(
            node_id,
            archetype=archetype,
            mode=mode,
            instances=instances,
            assessed_tier=assessed_tier,
            run_id=run_id,
            timeout_override=timeout_override,
            max_turns_override=max_turns_override,
        )
        return await invoke_runner(runner, node_id, attempt, previous_error)
