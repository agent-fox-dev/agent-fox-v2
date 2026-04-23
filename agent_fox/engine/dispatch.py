"""Dispatch strategies: serial and parallel task execution.

Extracted from engine.py to isolate dispatch mechanics from orchestration
control flow. Each dispatcher manages the loop of preparing, launching,
and processing sessions for ready tasks.

Requirements: 04-REQ-1.1, 04-REQ-1.2, 04-REQ-2.1
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agent_fox.engine.graph_sync import _is_auto_pre
from agent_fox.engine.session_lifecycle import _REVIEW_ARCHETYPES
from agent_fox.engine.state import SessionRecord

logger = logging.getLogger(__name__)


class SerialDispatcher:
    """Dispatches one ready task at a time with inter-session delay."""

    def __init__(self, orch: Any) -> None:
        self._orch = orch

    async def dispatch(
        self,
        ready: list[str],
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
        first_dispatch: bool,
    ) -> bool:
        """Dispatch one ready task serially. Returns updated first_dispatch."""
        orch = self._orch
        assert orch._graph_sync is not None  # noqa: S101

        for node_id in ready:
            if orch._signal.interrupted:
                break

            launch = await orch._prepare_launch(
                node_id,
                state,
                attempt_tracker,
                error_tracker,
            )
            if launch is None:
                continue

            (
                _,
                attempt,
                previous_error,
                node_archetype,
                node_instances,
                assessed_tier,
                node_mode,
            ) = launch

            if not first_dispatch:
                await orch._serial_runner.delay()
            first_dispatch = False

            orch._graph_sync.mark_in_progress(node_id)

            # Capture coverage baseline before coder sessions
            if node_archetype == "coder" and orch._result_handler is not None:
                orch._result_handler.capture_coverage_baseline(node_id, Path.cwd())

            timeout_override: int | None = None
            max_turns_override: int | None = None
            if orch._result_handler is not None:
                timeout_override = orch._result_handler._node_timeout.get(node_id)
                if node_id in orch._result_handler._node_max_turns:
                    max_turns_override = orch._result_handler._node_max_turns[node_id]

            record = await orch._serial_runner.execute(
                node_id,
                attempt,
                previous_error,
                archetype=node_archetype,
                mode=node_mode,
                instances=node_instances,
                assessed_tier=assessed_tier,
                run_id=orch._run_id,
                timeout_override=timeout_override,
                max_turns_override=max_turns_override,
            )

            assert orch._result_handler is not None  # noqa: S101
            orch._result_handler.process(
                record,
                attempt,
                state,
                attempt_tracker,
                error_tracker,
            )

            if record.status == "completed":
                await orch._run_sync_barrier_if_needed(state)

            break

        return first_dispatch


class ParallelDispatcher:
    """Dispatches ready tasks using a streaming pool of concurrent sessions."""

    def __init__(self, orch: Any) -> None:
        self._orch = orch

    async def dispatch(
        self,
        ready: list[str],
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Dispatch ready tasks using a streaming pool.

        Maintains a pool of up to ``max_parallelism`` concurrent asyncio
        tasks. When a task completes, ``ready_tasks()`` is re-evaluated
        and empty pool slots are filled with newly-unblocked work.
        """
        orch = self._orch
        assert orch._graph_sync is not None  # noqa: S101
        assert orch._parallel_runner is not None  # noqa: S101

        graph_sync = orch._graph_sync
        parallel_runner = orch._parallel_runner

        pool: set[asyncio.Task[SessionRecord]] = set()

        await self.fill_pool(pool, ready, state, attempt_tracker, error_tracker)

        if not pool:
            return

        parallel_runner.track_tasks(list(pool))

        while pool:
            if orch._signal.interrupted:
                break

            done, pool = await asyncio.wait(pool, return_when=asyncio.FIRST_COMPLETED)

            barrier_needed = self.process_completed(
                done,
                state,
                attempt_tracker,
                error_tracker,
            )

            if barrier_needed and pool:
                if orch._signal.interrupted:
                    break
                logger.info("Barrier triggered — draining %d in-flight tasks", len(pool))
                try:
                    drain_done, pool = await asyncio.wait(pool)
                except asyncio.CancelledError:
                    break
                self.process_completed(drain_done, state, attempt_tracker, error_tracker)

            if barrier_needed:
                await orch._run_sync_barrier_if_needed(state)

            if not orch._signal.interrupted:
                new_ready = graph_sync.ready_tasks()
                if not new_ready and len(pool) < parallel_runner.max_parallelism:
                    promoted = graph_sync.promote_deferred(
                        parallel_runner.max_parallelism - len(pool),
                    )
                    if promoted:
                        logger.info("Promoted %d deferred review node(s)", len(promoted))
                        new_ready = graph_sync.ready_tasks()
                await self.fill_pool(pool, new_ready, state, attempt_tracker, error_tracker)

            parallel_runner.track_tasks(list(pool))

    async def fill_pool(
        self,
        pool: set[asyncio.Task[SessionRecord]],
        candidates: list[str],
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Launch candidates into the parallel pool up to max_parallelism.

        Review archetype sessions (excluding auto_pre group-0 nodes) are
        capped at ``max(1, max_pool * max_review_fraction)`` concurrent
        slots to prevent slot starvation.
        """
        orch = self._orch
        assert orch._graph_sync is not None  # noqa: S101
        assert orch._parallel_runner is not None  # noqa: S101

        max_pool = orch._parallel_runner.max_parallelism
        max_review = max(1, int(max_pool * orch._config.max_review_fraction))

        review_in_pool = 0
        for t in pool:
            name = t.get_name()
            if name.startswith("parallel-"):
                pool_node_id = name[len("parallel-") :]
                if not _is_auto_pre(pool_node_id):
                    pool_archetype = orch._get_node_archetype(pool_node_id)
                    if pool_archetype in _REVIEW_ARCHETYPES:
                        review_in_pool += 1

        for node_id in candidates:
            if len(pool) >= max_pool:
                break
            if orch._signal.interrupted:
                break

            if orch._graph_sync.node_states.get(node_id) == "blocked":
                continue

            candidate_archetype = orch._get_node_archetype(node_id)
            if candidate_archetype in _REVIEW_ARCHETYPES and not _is_auto_pre(node_id) and review_in_pool >= max_review:
                continue

            launch = await orch._prepare_launch(
                node_id,
                state,
                attempt_tracker,
                error_tracker,
            )
            if launch is None:
                continue

            _, attempt, previous_error, archetype, instances, assessed_tier, node_mode = launch

            orch._graph_sync.mark_in_progress(node_id)

            # Capture coverage baseline before coder sessions
            if archetype == "coder" and orch._result_handler is not None:
                orch._result_handler.capture_coverage_baseline(node_id, Path.cwd())

            timeout_override_p: int | None = None
            max_turns_override_p: int | None = None
            if orch._result_handler is not None:
                timeout_override_p = orch._result_handler._node_timeout.get(node_id)
                if node_id in orch._result_handler._node_max_turns:
                    max_turns_override_p = orch._result_handler._node_max_turns[node_id]

            task = asyncio.create_task(
                orch._parallel_runner.execute_one(
                    node_id,
                    attempt,
                    previous_error,
                    archetype=archetype,
                    mode=node_mode,
                    instances=instances,
                    assessed_tier=assessed_tier,
                    run_id=orch._run_id,
                    timeout_override=timeout_override_p,
                    max_turns_override=max_turns_override_p,
                ),
                name=f"parallel-{node_id}",
            )
            pool.add(task)

            if archetype in _REVIEW_ARCHETYPES and not _is_auto_pre(node_id):
                review_in_pool += 1

    def process_completed(
        self,
        done: set[asyncio.Task[SessionRecord]],
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> bool:
        """Process completed parallel tasks. Returns True if a barrier is needed."""
        orch = self._orch
        assert orch._result_handler is not None  # noqa: S101

        barrier_needed = False
        for completed_task in done:
            try:
                record = completed_task.result()
            except Exception as exc:
                logger.error("Parallel task raised: %s", exc)
                continue

            orch._result_handler.process(
                record,
                attempt_tracker.get(record.node_id, 1),
                state,
                attempt_tracker,
                error_tracker,
            )

            if record.status == "completed":
                if orch._should_trigger_barrier(state):
                    barrier_needed = True

        return barrier_needed
