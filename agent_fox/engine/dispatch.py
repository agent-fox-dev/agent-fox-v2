"""Dispatch strategies: serial and parallel task execution.

Extracted from engine.py to isolate dispatch mechanics from orchestration
control flow. Each dispatcher manages the loop of preparing, launching,
and processing sessions for ready tasks.

DispatchManager is the top-level collaborator that owns runners,
dispatchers, and launch preparation.

Requirements: 04-REQ-1.1, 04-REQ-1.2, 04-REQ-2.1
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.graph_sync import _is_auto_pre
from agent_fox.engine.session_lifecycle import _REVIEW_ARCHETYPES
from agent_fox.engine.state import SessionRecord
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.ui.progress import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SerialRunner — executes one session at a time
# ---------------------------------------------------------------------------


class SerialRunner:
    """Runs tasks one at a time with inter-session delay."""

    def __init__(
        self,
        session_runner_factory: Callable[..., Any],
        inter_session_delay: float,
    ) -> None:
        self._session_runner_factory = session_runner_factory
        self._inter_session_delay = inter_session_delay

    async def execute(
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
        """Execute a single session and return the outcome record."""
        from agent_fox.engine.state import invoke_runner

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

    async def delay(self) -> None:
        """Wait for the configured inter-session delay."""
        if self._inter_session_delay > 0:
            await asyncio.sleep(self._inter_session_delay)


# ---------------------------------------------------------------------------
# SerialDispatcher / ParallelDispatcher — dispatch strategies
# ---------------------------------------------------------------------------


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
        if orch._graph_sync is None:
            raise RuntimeError("Orchestrator._graph_sync must be initialized before dispatch")

        for node_id in ready:
            if orch._signal.interrupted:
                break

            launch = orch._dispatch_mgr.prepare_launch(
                node_id,
                state,
                attempt_tracker,
                error_tracker,
            )
            if asyncio.iscoroutine(launch):
                launch = await launch
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
                await orch._dispatch_mgr.serial_runner.delay()
            first_dispatch = False

            orch._graph_sync.mark_in_progress(node_id)

            if node_archetype == "coder" and orch._result_handler is not None:
                orch._result_handler.capture_coverage_baseline(node_id, Path.cwd())

            timeout_override: int | None = None
            max_turns_override: int | None = None
            if orch._result_handler is not None:
                timeout_override = orch._result_handler._node_timeout.get(node_id)
                if node_id in orch._result_handler._node_max_turns:
                    max_turns_override = orch._result_handler._node_max_turns[node_id]

            record = await orch._dispatch_mgr.serial_runner.execute(
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

            if orch._result_handler is None:
                raise RuntimeError("Orchestrator._result_handler must be initialized before dispatch")
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
        """Dispatch ready tasks using a streaming pool."""
        orch = self._orch
        if orch._graph_sync is None:
            raise RuntimeError("Orchestrator._graph_sync must be initialized before dispatch")
        if orch._dispatch_mgr.parallel_runner is None:
            raise RuntimeError("Orchestrator._parallel_runner must be initialized before dispatch")

        graph_sync = orch._graph_sync
        parallel_runner = orch._dispatch_mgr.parallel_runner

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
        """Launch candidates into the parallel pool up to max_parallelism."""
        orch = self._orch
        if orch._graph_sync is None:
            raise RuntimeError("Orchestrator._graph_sync must be initialized before dispatch")
        if orch._dispatch_mgr.parallel_runner is None:
            raise RuntimeError("Orchestrator._parallel_runner must be initialized before dispatch")

        max_pool = orch._dispatch_mgr.parallel_runner.max_parallelism
        max_review = max(1, int(max_pool * orch._config.max_review_fraction))

        review_in_pool = 0
        for t in pool:
            name = t.get_name()
            if name.startswith("parallel-"):
                pool_node_id = name[len("parallel-"):]
                if not _is_auto_pre(pool_node_id):
                    pool_archetype = orch._dispatch_mgr.get_node_archetype(pool_node_id)
                    if pool_archetype in _REVIEW_ARCHETYPES:
                        review_in_pool += 1

        for node_id in candidates:
            if len(pool) >= max_pool:
                break
            if orch._signal.interrupted:
                break

            if orch._graph_sync.node_states.get(node_id) == "blocked":
                continue

            candidate_archetype = orch._dispatch_mgr.get_node_archetype(node_id)
            if candidate_archetype in _REVIEW_ARCHETYPES and not _is_auto_pre(node_id) and review_in_pool >= max_review:
                continue

            launch = orch._dispatch_mgr.prepare_launch(
                node_id,
                state,
                attempt_tracker,
                error_tracker,
            )
            if asyncio.iscoroutine(launch):
                launch = await launch
            if launch is None:
                continue

            _, attempt, previous_error, archetype, instances, assessed_tier, node_mode = launch

            orch._graph_sync.mark_in_progress(node_id)

            if archetype == "coder" and orch._result_handler is not None:
                orch._result_handler.capture_coverage_baseline(node_id, Path.cwd())

            timeout_override_p: int | None = None
            max_turns_override_p: int | None = None
            if orch._result_handler is not None:
                timeout_override_p = orch._result_handler._node_timeout.get(node_id)
                if node_id in orch._result_handler._node_max_turns:
                    max_turns_override_p = orch._result_handler._node_max_turns[node_id]

            task = asyncio.create_task(
                orch._dispatch_mgr.parallel_runner.execute_one(
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
        if orch._result_handler is None:
            raise RuntimeError("Orchestrator._result_handler must be initialized before dispatch")

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
                if orch._dispatch_mgr.should_trigger_barrier(state):
                    barrier_needed = True

        return barrier_needed


# ---------------------------------------------------------------------------
# DispatchManager — top-level dispatch collaborator
# ---------------------------------------------------------------------------


class DispatchManager:
    """Owns runners, dispatchers, and launch preparation logic.

    Extracted from Orchestrator to isolate dispatch concerns from the
    main orchestration loop.
    """

    def __init__(
        self,
        *,
        session_runner_factory: Callable[..., Any],
        inter_session_delay: float,
        parallel: int,
        graph: Any | None = None,
        routing: Any | None = None,
        circuit: Any | None = None,
        config: Any | None = None,
        routing_config: Any | None = None,
        specs_dir: Path | None = None,
        full_config: Any | None = None,
        knowledge_db_conn: Any | None = None,
        sink: Any | None = None,
        task_callback: TaskCallback | None = None,
        planning_config: Any | None = None,
    ) -> None:
        from agent_fox.engine.parallel import ParallelRunner

        self._graph = graph
        self._routing = routing
        self._circuit = circuit
        self._config = config
        self._routing_config = routing_config
        self._specs_dir = specs_dir
        self._full_config_ref = full_config
        self._knowledge_db_conn = knowledge_db_conn
        self._sink = sink
        self._run_id = ""
        self._task_callback = task_callback
        self._planning_config = planning_config

        self.serial_runner = SerialRunner(
            session_runner_factory=session_runner_factory,
            inter_session_delay=inter_session_delay,
        )
        self.parallel_runner: ParallelRunner | None = None
        if parallel > 1:
            self.parallel_runner = ParallelRunner(
                session_runner_factory=session_runner_factory,
                max_parallelism=parallel,
                inter_session_delay=inter_session_delay,
            )

    def get_node(self, node_id: str) -> Any | None:
        """Look up a TaskNode by ID, returning None if graph is unset."""
        if self._graph is not None:
            return self._graph.nodes.get(node_id)
        return None

    def get_node_archetype(self, node_id: str) -> str:
        """Get the archetype name for a node from the task graph."""
        node = self.get_node(node_id)
        return node.archetype if node else "coder"

    def get_node_instances(self, node_id: str) -> int:
        """Get the instance count for a node from the task graph."""
        node = self.get_node(node_id)
        return node.instances if node else 1

    def get_node_mode(self, node_id: str) -> str | None:
        """Get the mode for a node from the task graph (97-REQ-5.3)."""
        node = self.get_node(node_id)
        return node.mode if node else None

    async def prepare_launch(
        self,
        node_id: str,
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> tuple[str, int, str | None, str, int, Any | None, str | None] | None:
        """Assess a node and check whether it may launch.

        Returns a tuple of (verdict, attempt, previous_error, archetype,
        instances, assessed_tier, mode) if the node is allowed to launch,
        or None if it was blocked/limited.
        """
        archetype = self.get_node_archetype(node_id)
        mode = self.get_node_mode(node_id)
        await self._routing.assess_node(
            node_id,
            archetype,
            mode=mode,
        )

        attempt = attempt_tracker.get(node_id, 0) + 1
        verdict = self._check_launch(
            node_id,
            attempt,
            state,
            attempt_tracker,
            error_tracker,
        )
        if verdict != "allowed":
            return None

        if archetype == "coder" and attempt == 1:
            skip = self._run_preflight(node_id)
            if skip:
                return None

        attempt_tracker[node_id] = attempt
        previous_error = error_tracker.get(node_id)
        instances = self.get_node_instances(node_id)

        ladder = self._routing.ladders.get(node_id)
        assessed_tier = ladder.current_tier if ladder else None

        return (verdict, attempt, previous_error, archetype, instances, assessed_tier, mode)

    def _check_launch(
        self,
        node_id: str,
        attempt: int,
        state: Any,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None] | None = None,
    ) -> str:
        """Check whether *node_id* may be launched.

        Returns ``"allowed"``, ``"blocked"``, or ``"limited"``.
        """
        decision = self._circuit.check_launch(node_id, attempt, state)
        if decision.allowed:
            return "allowed"

        if self._config.max_retries is not None and attempt > self._config.max_retries + 1:
            attempt_tracker[node_id] = attempt
            last_error = error_tracker.get(node_id) if error_tracker else None
            reason = f"Retry limit exceeded for {node_id}"
            if last_error:
                reason = f"{reason}: {last_error}"
            self._block_task_fn(
                node_id,
                state,
                reason,
            )
            self._check_block_budget_fn(state)
            return "blocked"
        return "limited"

    def _run_preflight(self, node_id: str) -> bool:
        """Run pre-flight check and skip the session if work is done."""
        from agent_fox.core.config import resolve_spec_root
        from agent_fox.core.node_id import parse_node_id
        from agent_fox.engine.preflight import PreflightVerdict, run_preflight

        parsed = parse_node_id(node_id)
        specs_dir = self._specs_dir
        if specs_dir is None and self._full_config_ref is not None:
            fc = self._full_config_ref() if callable(self._full_config_ref) else self._full_config_ref
            if fc is not None:
                specs_dir = resolve_spec_root(fc, Path.cwd())
        if specs_dir is None:
            return False

        verdict = run_preflight(
            spec_name=parsed.spec_name,
            group_number=parsed.group_number,
            conn=self._knowledge_db_conn,
            specs_dir=specs_dir,
            cwd=Path.cwd(),
        )
        if verdict != PreflightVerdict.SKIP:
            return False

        if self._graph_sync is not None:
            prev_status = self._graph_sync.node_states.get(node_id, "pending")
            self._graph_sync.mark_completed(node_id)
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.PREFLIGHT_SKIP,
                node_id=node_id,
                payload={
                    "from_status": prev_status,
                    "reason": "checkboxes done, no active findings, tests pass",
                },
            )
            if self._knowledge_db_conn is not None:
                try:
                    from agent_fox.engine.state import persist_node_status

                    persist_node_status(self._knowledge_db_conn, node_id, "completed")
                except Exception:
                    logger.debug("Failed to persist preflight skip status", exc_info=True)

            if self._task_callback is not None:
                self._task_callback(
                    TaskEvent(
                        node_id=node_id,
                        status="completed",
                        duration_s=0.0,
                        archetype="coder",
                    )
                )

        logger.info("Preflight skip: %s", node_id)
        return True

    def filter_file_conflicts(self, ready: list[str]) -> list[str]:
        """Filter conflicting tasks from the ready set.

        Requirements: 39-REQ-9.3
        """
        try:
            from agent_fox.graph.file_impacts import (
                FileImpact,
                filter_conflicts_from_dispatch,
            )

            impacts: list[FileImpact] = []
            for node_id in ready:
                node = self.get_node(node_id)
                spec_name = node.spec_name if node else ""
                task_group = node.group_number if node else 1

                if self._specs_dir is not None:
                    spec_dir = self._specs_dir / spec_name
                    if spec_dir.is_dir():
                        from agent_fox.graph.file_impacts import extract_file_impacts

                        predicted = extract_file_impacts(spec_dir, task_group)
                        impacts.append(FileImpact(node_id, predicted))
                    else:
                        impacts.append(FileImpact(node_id, set()))
                else:
                    impacts.append(FileImpact(node_id, set()))

            filtered = filter_conflicts_from_dispatch(ready, impacts)
            if len(filtered) < len(ready):
                deferred = set(ready) - set(filtered)
                logger.info(
                    "File conflict detection deferred %d tasks: %s",
                    len(deferred),
                    deferred,
                )
            return filtered
        except Exception:
            logger.warning(
                "File conflict detection failed, dispatching all ready tasks",
                exc_info=True,
            )
            return ready

    def should_trigger_barrier(self, state: Any) -> bool:
        """Check whether a sync barrier should fire (no side effects)."""
        from agent_fox.engine.barrier import _count_node_status
        from agent_fox.engine.hot_load import should_trigger_barrier

        if self._config.sync_interval == 0:
            return False
        completed_count = _count_node_status(state.node_states, "completed")
        return should_trigger_barrier(completed_count, self._config.sync_interval)

    def set_graph(self, graph: Any) -> None:
        """Update the task graph reference (after hot-loading)."""
        self._graph = graph

    def set_graph_sync(self, graph_sync: Any) -> None:
        """Update the graph_sync reference."""
        self._graph_sync = graph_sync

    def set_run_id(self, run_id: str) -> None:
        """Update the run ID."""
        self._run_id = run_id

    def set_callbacks(
        self,
        block_task_fn: Callable[..., None],
        check_block_budget_fn: Callable[..., bool],
    ) -> None:
        """Set callback functions for blocking tasks."""
        self._block_task_fn = block_task_fn
        self._check_block_budget_fn = check_block_budget_fn

    def set_sink(self, sink: Any) -> None:
        """Update the sink dispatcher reference."""
        self._sink = sink
