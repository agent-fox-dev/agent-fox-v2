"""Orchestrator: deterministic execution engine. Zero LLM calls.

Loads the task graph, dispatches sessions in dependency order, manages
retries with error feedback, cascade-blocks failed tasks, persists state
after every session, and handles graceful interruption.

Requirements: 04-REQ-1.1 through 04-REQ-1.4, 04-REQ-1.E1, 04-REQ-1.E2,
              04-REQ-2.1 through 04-REQ-2.3, 04-REQ-2.E1,
              04-REQ-5.1, 04-REQ-5.2, 04-REQ-5.3,
              04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3,
              04-REQ-7.1, 04-REQ-7.2, 04-REQ-7.E1,
              04-REQ-8.1, 04-REQ-8.2, 04-REQ-8.3, 04-REQ-8.E1,
              04-REQ-9.1, 04-REQ-9.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_fox.core.config import HookConfig, OrchestratorConfig
from agent_fox.core.errors import PlanError
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.hot_load import hot_load_specs, should_trigger_barrier
from agent_fox.engine.parallel import ParallelRunner
from agent_fox.engine.serial import SerialRunner
from agent_fox.engine.state import (
    ExecutionState,
    RunStatus,
    SessionRecord,
    StateManager,
)
from agent_fox.engine.sync import GraphSync
from agent_fox.graph.types import Edge, Node, NodeStatus, TaskGraph
from agent_fox.hooks.runner import run_sync_barrier_hooks
from agent_fox.memory.render import render_summary

logger = logging.getLogger(__name__)


def _load_plan_data(plan_path: Path) -> dict:
    """Load plan.json and return the raw plan dict.

    Raises:
        PlanError: if plan.json is missing or corrupted
    """
    if not plan_path.exists():
        raise PlanError(
            f"Plan file not found: {plan_path}. "
            f"Run `agent-fox plan` first to generate a plan.",
            path=str(plan_path),
        )

    try:
        raw = plan_path.read_text(encoding="utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        raise PlanError(
            f"Corrupted plan file {plan_path}: {exc}. "
            f"Run `agent-fox plan` to regenerate.",
            path=str(plan_path),
        ) from exc


def _build_edges_dict(
    nodes: dict,
    edges_list: list[dict],
) -> dict[str, list[str]]:
    """Build adjacency list from plan edges.

    Returns dict mapping each node to its dependencies (predecessors).
    """
    edges_dict: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in edges_list:
        source = edge["source"]
        target = edge["target"]
        if target in edges_dict:
            edges_dict[target].append(source)
    return edges_dict


def _load_or_init_state(
    state_manager: StateManager,
    plan_hash: str,
    nodes: dict,
) -> ExecutionState:
    """Load existing state or initialize fresh state.

    If state exists but plan hash differs, warn and start fresh.
    """
    existing = state_manager.load()

    if existing is not None:
        if existing.plan_hash != plan_hash:
            logger.warning(
                "Plan has changed since last run (plan hash mismatch). Starting fresh.",
            )
        else:
            for nid in nodes:
                if nid not in existing.node_states:
                    existing.node_states[nid] = "pending"
            return existing

    now = datetime.now(UTC).isoformat()
    return ExecutionState(
        plan_hash=plan_hash,
        node_states={nid: "pending" for nid in nodes},
        started_at=now,
        updated_at=now,
    )


def _reset_in_progress_tasks(
    state: ExecutionState,
    state_manager: StateManager,
) -> None:
    """Reset in_progress tasks to pending on resume (04-REQ-7.E1)."""
    any_reset = False
    for node_id, status in state.node_states.items():
        if status == "in_progress":
            state.node_states[node_id] = "pending"
            any_reset = True
            logger.info(
                "Task %s was in_progress from prior run; resetting to pending.",
                node_id,
            )
    if any_reset:
        state_manager.save(state)


def _init_attempt_tracker(state: ExecutionState) -> dict[str, int]:
    """Initialize attempt counter from session history."""
    tracker: dict[str, int] = {}
    for record in state.session_history:
        current = tracker.get(record.node_id, 0)
        tracker[record.node_id] = max(current, record.attempt)
    return tracker


def _init_error_tracker(state: ExecutionState) -> dict[str, str | None]:
    """Initialize error tracker from session history."""
    tracker: dict[str, str | None] = {}

    for record in state.session_history:
        if record.status == "failed" and record.error_message:
            tracker[record.node_id] = record.error_message

    for node_id, status in state.node_states.items():
        if status == "pending" and node_id not in tracker:
            prior_attempts = [r for r in state.session_history if r.node_id == node_id]
            if prior_attempts:
                last = prior_attempts[-1]
                if last.error_message:
                    tracker[node_id] = last.error_message

    return tracker


class _SignalHandler:
    """Manages SIGINT handling for graceful orchestrator shutdown.

    Double-SIGINT exits immediately (04-REQ-8.E1).
    """

    def __init__(self) -> None:
        self.interrupted = False
        self._interrupt_count = 0
        self._prev_handler: Any = None

    def install(self) -> None:
        """Register SIGINT handler."""

        def handler(signum: int, frame: Any) -> None:
            self._interrupt_count += 1
            if self._interrupt_count >= 2:
                logger.warning("Double SIGINT received, exiting immediately.")
                raise SystemExit(1)
            self.interrupted = True
            logger.info("SIGINT received, shutting down gracefully...")

        try:
            self._prev_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, handler)
        except (OSError, ValueError):
            self._prev_handler = None

    def restore(self) -> None:
        """Restore the previous SIGINT handler."""
        if self._prev_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._prev_handler)
            except (OSError, ValueError):
                pass


class Orchestrator:
    """Deterministic execution engine. Zero LLM calls.

    Reads the task graph from plan.json, dispatches sessions in dependency
    order (serial or parallel), manages retries with error feedback,
    cascade-blocks failed tasks, persists state, and handles graceful
    interruption via SIGINT.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        plan_path: Path,
        state_path: Path,
        session_runner_factory: Callable[..., Any],
        *,
        hook_config: HookConfig | None = None,
        specs_dir: Path | None = None,
        no_hooks: bool = False,
    ) -> None:
        self._config = config
        self._plan_path = plan_path
        self._state_manager = StateManager(state_path)
        self._circuit = CircuitBreaker(config)
        self._graph_sync: GraphSync | None = None
        self._signal = _SignalHandler()
        self._is_parallel = config.parallel > 1
        self._hook_config = hook_config
        self._specs_dir = specs_dir
        self._no_hooks = no_hooks
        self._plan_nodes: dict = {}
        self._edges_list: list[dict] = []
        self._plan_data: dict = {}  # Full plan data for plan.json updates
        self._serial_runner = SerialRunner(
            session_runner_factory=session_runner_factory,
            inter_session_delay=float(config.inter_session_delay),
        )
        self._parallel_runner: ParallelRunner | None = None
        if self._is_parallel:
            self._parallel_runner = ParallelRunner(
                session_runner_factory=session_runner_factory,
                max_parallelism=config.parallel,
                inter_session_delay=float(config.inter_session_delay),
            )

    async def run(self) -> ExecutionState:
        """Execute the full orchestration loop.

        1. Load plan from plan.json
        2. Load or initialize execution state
        3. Register SIGINT handler
        4. Loop: pick ready tasks, dispatch, update state
        5. Update plan.json with final node statuses
        6. Return final execution state

        Raises:
            PlanError: if plan.json is missing or corrupted
        """
        plan_data = _load_plan_data(self._plan_path)
        nodes = plan_data.get("nodes", {})
        edges_list = plan_data.get("edges", [])

        # 04-REQ-1.E2: Empty plan
        if not nodes:
            return ExecutionState(
                plan_hash=self._compute_plan_hash(),
                node_states={},
                run_status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            )

        # Store plan data for sync barrier hot-loading
        self._plan_nodes = nodes
        self._edges_list = edges_list
        self._plan_data = plan_data

        edges_dict = _build_edges_dict(nodes, edges_list)
        plan_hash = self._compute_plan_hash()
        state = _load_or_init_state(self._state_manager, plan_hash, nodes)
        _reset_in_progress_tasks(state, self._state_manager)

        self._graph_sync = GraphSync(state.node_states, edges_dict)

        attempt_tracker = _init_attempt_tracker(state)
        error_tracker = _init_error_tracker(state)

        self._signal.install()

        first_dispatch = True
        try:
            while True:
                if self._signal.interrupted:
                    await self._shutdown(state)
                    return state

                # Check circuit breaker: cost/session limits (04-REQ-5.*)
                stop_decision = self._circuit.should_stop(state)
                if not stop_decision.allowed:
                    if (
                        self._config.max_cost is not None
                        and state.total_cost >= self._config.max_cost
                    ):
                        state.run_status = RunStatus.COST_LIMIT
                    else:
                        state.run_status = RunStatus.SESSION_LIMIT
                    logger.info(
                        "Circuit breaker tripped: %s",
                        stop_decision.reason,
                    )
                    self._state_manager.save(state)
                    return state

                ready = self._graph_sync.ready_tasks()

                if not ready:
                    if self._graph_sync.is_stalled():
                        state.run_status = RunStatus.STALLED
                        logger.warning(
                            "Execution stalled. Summary: %s",
                            self._graph_sync.summary(),
                        )
                        self._state_manager.save(state)
                        return state

                    state.run_status = RunStatus.COMPLETED
                    self._state_manager.save(state)
                    return state

                if self._is_parallel and self._parallel_runner is not None:
                    await self._dispatch_parallel(
                        ready,
                        state,
                        attempt_tracker,
                        error_tracker,
                        first_dispatch,
                    )
                    first_dispatch = False
                else:
                    first_dispatch = await self._dispatch_serial(
                        ready,
                        state,
                        attempt_tracker,
                        error_tracker,
                        first_dispatch,
                    )

        finally:
            self._signal.restore()
            # Update plan.json with current node statuses so the file
            # reflects actual progress, not just the original pending state.
            self._sync_plan_statuses(state)

    def _compute_plan_hash(self) -> str:
        """Compute plan hash, returning empty string if file doesn't exist."""
        if self._plan_path.exists():
            return StateManager.compute_plan_hash(self._plan_path)
        return ""

    def _check_launch(
        self,
        node_id: str,
        attempt: int,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
    ) -> str:
        """Check whether *node_id* may be launched.

        Returns ``"allowed"``, ``"blocked"``, or ``"limited"``.
        """
        decision = self._circuit.check_launch(node_id, attempt, state)
        if decision.allowed:
            return "allowed"

        if (
            self._config.max_retries is not None
            and attempt > self._config.max_retries + 1
        ):
            attempt_tracker[node_id] = attempt
            self._block_task(
                node_id,
                state,
                f"Retry limit exceeded for {node_id}",
            )
            self._state_manager.save(state)
            return "blocked"
        return "limited"

    async def _dispatch_serial(
        self,
        ready: list[str],
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
        first_dispatch: bool,
    ) -> bool:
        """Dispatch one ready task serially. Returns updated first_dispatch."""
        assert self._graph_sync is not None  # noqa: S101

        for node_id in ready:
            if self._signal.interrupted:
                break

            attempt = attempt_tracker.get(node_id, 0) + 1
            verdict = self._check_launch(node_id, attempt, state, attempt_tracker)
            if verdict == "blocked":
                continue
            if verdict == "limited":
                break

            attempt_tracker[node_id] = attempt

            if not first_dispatch:
                await self._serial_runner.delay()
            first_dispatch = False

            self._graph_sync.mark_in_progress(node_id)
            # Persist in_progress state so agent-fox status can show it
            self._state_manager.save(state)

            previous_error = error_tracker.get(node_id)

            record = await self._serial_runner.execute(
                node_id,
                attempt,
                previous_error,
            )

            self._process_session_result(
                record,
                attempt,
                state,
                attempt_tracker,
                error_tracker,
            )

            # 06-REQ-6.1: Check sync barrier after task completion
            if record.status == "completed":
                self._run_sync_barrier_if_needed(state)

            # Re-evaluate ready tasks after each completion
            break

        return first_dispatch

    async def _dispatch_parallel(
        self,
        ready: list[str],
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
        first_dispatch: bool,
    ) -> None:
        """Dispatch ready tasks using a streaming pool.

        Maintains a pool of up to ``max_parallelism`` concurrent asyncio
        tasks.  When a task completes, ``ready_tasks()`` is re-evaluated
        and empty pool slots are filled with newly-unblocked work.

        Only tasks that are *actually running* are marked ``in_progress``
        — queued tasks remain ``pending`` until a pool slot opens.

        This replaces the former batch-and-wait model which over-committed
        all ready tasks as ``in_progress`` and delayed newly-unblocked
        tasks until the entire batch completed.
        """
        assert self._graph_sync is not None  # noqa: S101
        assert self._parallel_runner is not None  # noqa: S101

        # Local refs so the nested closure satisfies mypy narrowing.
        graph_sync = self._graph_sync
        parallel_runner = self._parallel_runner

        pool: set[asyncio.Task[SessionRecord]] = set()
        max_pool = parallel_runner.max_parallelism

        def _fill_pool(candidates: list[str]) -> None:
            """Launch candidates into the pool up to max_parallelism."""
            for node_id in candidates:
                if len(pool) >= max_pool:
                    break
                if self._signal.interrupted:
                    break

                attempt = attempt_tracker.get(node_id, 0) + 1
                verdict = self._check_launch(
                    node_id,
                    attempt,
                    state,
                    attempt_tracker,
                )
                if verdict != "allowed":
                    continue

                attempt_tracker[node_id] = attempt
                graph_sync.mark_in_progress(node_id)
                previous_error = error_tracker.get(node_id)

                task = asyncio.create_task(
                    parallel_runner.execute_one(
                        node_id,
                        attempt,
                        previous_error,
                    ),
                    name=f"parallel-{node_id}",
                )
                pool.add(task)

        _fill_pool(ready)

        if not pool:
            return

        # Persist in_progress state so agent-fox status can show it
        parallel_runner.track_tasks(list(pool))
        self._state_manager.save(state)

        while pool:
            if self._signal.interrupted:
                break

            # Wait for any task to complete
            done, pool = await asyncio.wait(
                pool,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for completed_task in done:
                try:
                    record = completed_task.result()
                except Exception as exc:
                    logger.error("Parallel task raised: %s", exc)
                    continue

                self._process_session_result(
                    record,
                    attempt_tracker.get(record.node_id, 1),
                    state,
                    attempt_tracker,
                    error_tracker,
                )

                # 06-REQ-6.1: Check sync barrier after task completion
                if record.status == "completed":
                    self._run_sync_barrier_if_needed(state)

            # Re-evaluate ready tasks and fill empty pool slots
            if not self._signal.interrupted:
                new_ready = graph_sync.ready_tasks()
                _fill_pool(new_ready)

            parallel_runner.track_tasks(list(pool))
            self._state_manager.save(state)

    def _process_session_result(
        self,
        record: SessionRecord,
        attempt: int,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Process a completed session record and persist state."""
        assert self._graph_sync is not None  # noqa: S101

        node_id = record.node_id
        self._state_manager.record_session(state, record)

        if record.status == "completed":
            self._graph_sync.mark_completed(node_id)
            state.node_states[node_id] = "completed"
            error_tracker.pop(node_id, None)
        else:
            error_tracker[node_id] = record.error_message
            if attempt >= self._config.max_retries + 1:
                self._block_task(
                    node_id,
                    state,
                    f"Retries exhausted for {node_id}: {record.error_message}",
                )
            else:
                self._graph_sync.node_states[node_id] = "pending"
                state.node_states[node_id] = "pending"

        self._state_manager.save(state)

    def _run_sync_barrier_if_needed(self, state: ExecutionState) -> None:
        """Check and run sync barrier actions if triggered.

        After each task completion, checks whether the completed count
        crosses a sync_interval boundary. On trigger: runs sync barrier
        hooks, hot-loads new specs, and regenerates the memory summary.

        Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3
        """
        if self._config.sync_interval == 0:
            return

        completed_count = sum(1 for s in state.node_states.values() if s == "completed")

        if not should_trigger_barrier(completed_count, self._config.sync_interval):
            return

        barrier_number = completed_count // self._config.sync_interval
        logger.info(
            "Sync barrier %d triggered at %d completed tasks",
            barrier_number,
            completed_count,
        )

        # 06-REQ-6.1: Run sync barrier hooks
        if self._hook_config is not None:
            run_sync_barrier_hooks(
                barrier_number=barrier_number,
                config=self._hook_config,
                no_hooks=self._no_hooks,
            )

        # 06-REQ-6.3: Hot-load new specs
        if self._specs_dir is not None and self._config.hot_load:
            try:
                self._hot_load_new_specs(state)
                # Persist immediately so a crash doesn't lose new specs
                self._sync_plan_statuses(state)
            except Exception:
                logger.warning("Hot-loading specs failed at barrier", exc_info=True)

        # 06-REQ-6.2 / 05-REQ-6.3: Regenerate memory summary
        try:
            render_summary()
        except Exception:
            logger.warning("Memory summary regeneration failed", exc_info=True)

    def _hot_load_new_specs(self, state: ExecutionState) -> None:
        """Discover and incorporate new specs into the running graph."""
        assert self._specs_dir is not None  # noqa: S101
        assert self._graph_sync is not None  # noqa: S101

        graph = self._build_task_graph(state)
        updated_graph, new_spec_names = hot_load_specs(graph, self._specs_dir)

        if not new_spec_names:
            return

        logger.info(
            "Hot-loaded %d new spec(s): %s",
            len(new_spec_names),
            ", ".join(new_spec_names),
        )

        # Add new nodes to plan data and state
        for nid, node in updated_graph.nodes.items():
            if nid not in self._plan_nodes:
                self._plan_nodes[nid] = {
                    "id": nid,
                    "spec_name": node.spec_name,
                    "group_number": node.group_number,
                    "title": node.title,
                    "optional": node.optional,
                    "status": "pending",
                    "subtask_count": node.subtask_count,
                    "body": node.body,
                }
                state.node_states[nid] = "pending"

        # Rebuild edges and GraphSync with new nodes/edges
        self._edges_list = [
            {"source": e.source, "target": e.target, "kind": e.kind}
            for e in updated_graph.edges
        ]
        edges_dict = _build_edges_dict(self._plan_nodes, self._edges_list)
        self._graph_sync = GraphSync(state.node_states, edges_dict)

    def _build_task_graph(self, state: ExecutionState) -> TaskGraph:
        """Build a TaskGraph from current plan data and execution state."""
        graph_nodes = {}
        for nid, data in self._plan_nodes.items():
            graph_nodes[nid] = Node(
                id=nid,
                spec_name=data["spec_name"],
                group_number=data["group_number"],
                title=data.get("title", ""),
                optional=data.get("optional", False),
                status=NodeStatus(state.node_states.get(nid, "pending")),
                subtask_count=data.get("subtask_count", 0),
                body=data.get("body", ""),
            )
        graph_edges = [
            Edge(
                source=e["source"],
                target=e["target"],
                kind=e.get("kind", "intra_spec"),
            )
            for e in self._edges_list
        ]
        return TaskGraph(nodes=graph_nodes, edges=graph_edges, order=[])

    def _block_task(
        self,
        node_id: str,
        state: ExecutionState,
        reason: str,
    ) -> None:
        """Mark a task as blocked and cascade-block all dependents."""
        if self._graph_sync is not None:
            cascade_blocked = self._graph_sync.mark_blocked(node_id, reason)
            state.node_states[node_id] = "blocked"
            for blocked_id in cascade_blocked:
                state.node_states[blocked_id] = "blocked"
                logger.info("Cascade-blocked %s due to %s", blocked_id, node_id)

    def _sync_plan_statuses(self, state: ExecutionState) -> None:
        """Write current node statuses back into plan.json.

        Updates each node's ``status`` field in the plan data to match
        the execution state, then overwrites plan.json. This keeps the
        plan file in sync with reality so ``agent-fox status`` and
        direct inspection of plan.json show accurate progress.
        """
        if not self._plan_data or not state.node_states:
            return

        nodes = self._plan_data.get("nodes", {})
        changed = False
        for nid, current_status in state.node_states.items():
            if nid in nodes and nodes[nid].get("status") != current_status:
                nodes[nid]["status"] = current_status
                changed = True

        if not changed:
            return

        try:
            self._plan_path.write_text(
                json.dumps(self._plan_data, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.info("Updated plan.json with current node statuses")
        except OSError:
            logger.warning("Failed to update plan.json", exc_info=True)

    async def _shutdown(self, state: ExecutionState) -> None:
        """Save state, cancel in-flight tasks, log resume instructions."""
        if self._parallel_runner is not None:
            await self._parallel_runner.cancel_all()

        state.run_status = RunStatus.INTERRUPTED
        self._state_manager.save(state)

        summary = self._graph_sync.summary() if self._graph_sync else {}
        completed = summary.get("completed", 0)
        total = sum(summary.values()) if summary else 0
        remaining = total - completed

        logger.info(
            "Execution interrupted. %d/%d tasks completed, "
            "%d remaining. Resume with: agent-fox code",
            completed,
            total,
            remaining,
        )
