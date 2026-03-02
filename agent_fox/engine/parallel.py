"""Parallel runner: concurrent session execution via asyncio.

Runs up to N tasks concurrently, serializes state writes under an asyncio
lock, and supports cancellation of in-flight tasks on SIGINT.

Requirements: 04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_fox.engine.state import SessionRecord

logger = logging.getLogger(__name__)

MAX_PARALLELISM = 8


class ParallelRunner:
    """Runs up to N tasks concurrently via asyncio.

    Uses an asyncio.Semaphore to limit the number of concurrent sessions
    to the configured ``max_parallelism`` (capped at 8). State writes
    via the ``on_complete`` callback are serialized under an asyncio.Lock
    to prevent interleaved writes.
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
                record = await self._execute_session(
                    node_id,
                    attempt,
                    previous_error,
                )

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

    async def cancel_all(self) -> None:
        """Cancel all in-flight tasks. Called on SIGINT.

        Cancels every asyncio task that is still running and waits for
        them to finish (suppressing CancelledError).
        """
        for task in self._in_flight_tasks:
            if not task.done():
                task.cancel()

        if self._in_flight_tasks:
            await asyncio.gather(
                *self._in_flight_tasks,
                return_exceptions=True,
            )
            self._in_flight_tasks.clear()

    async def _execute_session(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
    ) -> SessionRecord:
        """Execute a single session via the factory-created runner.

        Supports both callable runners and runners with an ``execute()``
        method, mirroring the SerialRunner's dual-support pattern.
        """
        runner = self._session_runner_factory(node_id)

        # Support both callable runners and runners with execute() method
        if hasattr(runner, "execute") and callable(runner.execute):
            result = await runner.execute(node_id, attempt, previous_error)
        else:
            result = await runner(node_id, attempt, previous_error)

        # If the result is already a SessionRecord, return it directly
        if isinstance(result, SessionRecord):
            return result

        # Otherwise, convert from MockSessionOutcome or similar
        return SessionRecord(
            node_id=result.node_id,
            attempt=attempt,
            status=result.status,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
            timestamp=getattr(result, "timestamp", ""),
        )
