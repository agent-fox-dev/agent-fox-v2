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
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_fox.core.config import (
    ArchetypesConfig,
    HookConfig,
    OrchestratorConfig,
    PlanningConfig,
    RoutingConfig,
)
from agent_fox.core.errors import PlanError
from agent_fox.engine.assessment import AssessmentManager
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.barrier import _count_node_status, run_sync_barrier_sequence
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.hot_load import (
    _build_nodes_and_edges,
    _validate_and_parse_specs,
    discover_new_specs_gated,
    should_trigger_barrier,
)
from agent_fox.engine.parallel import ParallelRunner
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import (
    ExecutionState,
    RunStatus,
    SessionRecord,
    StateManager,
    invoke_runner,
)
from agent_fox.graph.injection import ensure_graph_archetypes
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.types import NodeStatus, TaskGraph
from agent_fox.knowledge.audit import (
    AuditEventType,
    AuditJsonlSink,
    AuditSeverity,
    enforce_audit_retention,
    generate_run_id,
)
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.ui.progress import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


def _build_edges_dict_from_graph(graph: TaskGraph) -> dict[str, list[str]]:
    """Build adjacency list from a TaskGraph.

    Returns dict mapping each node to its dependencies (predecessors).
    """
    edges_dict: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges:
        if edge.target in edges_dict:
            edges_dict[edge.target].append(edge.source)
    return edges_dict


def _seed_node_states_from_graph(graph: TaskGraph) -> dict[str, str]:
    """Seed node states from a TaskGraph.

    Honours statuses already set by the graph builder (e.g. "completed"
    from tasks.md ``[x]`` markers) instead of resetting everything to
    "pending".
    """
    node_states: dict[str, str] = {}
    for nid, node in graph.nodes.items():
        status = node.status.value
        if status not in ("completed", "skipped"):
            status = "pending"
        node_states[nid] = status
    return node_states


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
        instances: int = 1,
        assessed_tier: Any | None = None,
        run_id: str = "",
    ) -> SessionRecord:
        """Execute a single session and return the outcome record."""
        runner = self._session_runner_factory(
            node_id,
            archetype=archetype,
            instances=instances,
            assessed_tier=assessed_tier,
            run_id=run_id,
        )
        return await invoke_runner(runner, node_id, attempt, previous_error)

    async def delay(self) -> None:
        """Wait for the configured inter-session delay."""
        if self._inter_session_delay > 0:
            await asyncio.sleep(self._inter_session_delay)


def _load_or_init_state(
    state_manager: StateManager,
    plan_hash: str,
    graph: TaskGraph,
) -> ExecutionState:
    """Load existing state or initialize fresh state.

    If state exists and plan hash matches, reuse it (adding any new nodes).
    If state exists but plan hash differs, merge: carry forward
    ``completed``/``skipped`` statuses from the old state for nodes that
    still exist in the new plan, so that already-finished work is not
    re-executed. New nodes and previously failed/blocked nodes start fresh.
    If no prior state exists, seed entirely from the TaskGraph.
    """
    existing = state_manager.load()

    if existing is not None:
        if existing.plan_hash != plan_hash:
            # Plan structure changed (e.g. new spec added).  Merge old
            # completed/skipped statuses into the new plan rather than
            # discarding them — tasks.md checkboxes may be stale.
            node_states = _seed_node_states_from_graph(graph)
            carried = 0
            for nid in node_states:
                old_status = existing.node_states.get(nid)
                if old_status in ("completed", "skipped"):
                    node_states[nid] = old_status
                    carried += 1

            logger.warning(
                "Plan has changed since last run (plan hash mismatch). "
                "Merged state: %d nodes carried forward, %d new/reset.",
                carried,
                len(node_states) - carried,
            )

            existing.plan_hash = plan_hash
            existing.node_states = node_states
            existing.updated_at = datetime.now(UTC).isoformat()
            existing.blocked_reasons = {
                k: v for k, v in existing.blocked_reasons.items() if k in graph.nodes
            }
            return existing

        # Hash matches — reuse existing state, add any new nodes.
        for nid in graph.nodes:
            if nid not in existing.node_states:
                existing.node_states[nid] = "pending"
        return existing

    # No prior state — seed from the TaskGraph.
    node_states = _seed_node_states_from_graph(graph)
    now = datetime.now(UTC).isoformat()
    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states,
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
        task_callback: TaskCallback | None = None,
        barrier_callback: Callable[[], None] | None = None,
        routing_config: RoutingConfig | None = None,
        assessment_pipeline: Any | None = None,
        archetypes_config: ArchetypesConfig | None = None,
        planning_config: PlanningConfig | None = None,
        sink_dispatcher: SinkDispatcher | None = None,
        audit_dir: Path | None = None,
        audit_db_conn: Any | None = None,
        knowledge_db_conn: Any | None = None,
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
        self._task_callback = task_callback
        self._barrier_callback = barrier_callback
        self._graph: TaskGraph | None = None
        self._archetypes_config = archetypes_config
        self._planning_config = planning_config or PlanningConfig()
        self._sink = sink_dispatcher
        self._run_id: str = ""  # populated in run()
        self._audit_dir = audit_dir
        self._audit_db_conn = audit_db_conn
        self._knowledge_db_conn = knowledge_db_conn

        # 30-REQ-7: Adaptive routing state
        _rc = routing_config or RoutingConfig()
        self._routing = AssessmentManager(
            routing_config=_rc,
            pipeline=assessment_pipeline,
            retries_before_escalation=self._resolve_retries_before_escalation(_rc),
        )

        self._result_handler: SessionResultHandler | None = None

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

    def _resolve_retries_before_escalation(
        self,
        routing_config: RoutingConfig,
    ) -> int:
        """Resolve retries_before_escalation with max_retries deprecation.

        If routing.retries_before_escalation is at its default (1) and
        orchestrator.max_retries is set, use max_retries as a fallback
        with a deprecation warning. Otherwise, routing config takes precedence.

        Requirements: 30-REQ-5.1
        """
        routing_retries = routing_config.retries_before_escalation
        orch_retries = self._config.max_retries

        # If routing config is explicitly set (non-default), it takes precedence
        if routing_retries != 1:
            return routing_retries

        # If orchestrator.max_retries is set and differs from default,
        # use it as fallback with deprecation warning
        if orch_retries != 2:  # 2 is OrchestratorConfig.max_retries default
            logger.warning(
                "orchestrator.max_retries is deprecated; use "
                "routing.retries_before_escalation instead. "
                "Using max_retries=%d as fallback.",
                orch_retries,
            )
            return min(orch_retries, 3)  # Clamp to valid range

        return routing_retries

    def _emit_audit(self, *args: Any, **kwargs: Any) -> None:
        """Thin delegate used as a callback for assess_node / barrier."""
        emit_audit_event(self._sink, self._run_id, *args, **kwargs)

    async def _prepare_launch(
        self,
        node_id: str,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> tuple[str, int, str | None, str, int, Any | None] | None:
        """Assess a node and check whether it may launch.

        Returns a tuple of (verdict, attempt, previous_error, archetype,
        instances, assessed_tier) if the node is allowed to launch, or
        None if it was blocked/limited.  The caller must still check
        ``verdict`` — ``"blocked"`` and ``"limited"`` are returned via
        the tuple so the caller can distinguish them.

        On ``"allowed"``, ``attempt_tracker`` is updated and the launch
        parameters are ready to use.
        """
        # 30-REQ-7.1: Run assessment before first dispatch
        archetype = self._get_node_archetype(node_id)
        await self._routing.assess_node(
            node_id,
            archetype,
            emit_audit=self._emit_audit,
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

        attempt_tracker[node_id] = attempt
        previous_error = error_tracker.get(node_id)
        instances = self._get_node_instances(node_id)

        # 30-REQ-7.2: Pass assessed tier from escalation ladder
        ladder = self._routing.ladders.get(node_id)
        assessed_tier = ladder.current_tier if ladder else None

        return (verdict, attempt, previous_error, archetype, instances, assessed_tier)

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
        # 40-REQ-2.1: Generate unique run ID at start of execute()
        self._run_id = generate_run_id()
        run_start_time = datetime.now(UTC)
        logger.debug("Audit run ID: %s", self._run_id)

        # 40-REQ-6.1, 40-REQ-6.2: Register AuditJsonlSink now that run_id is known
        if self._audit_dir is not None and self._sink is not None:
            try:
                jsonl_sink = AuditJsonlSink(self._audit_dir, self._run_id)
                self._sink.add(jsonl_sink)
            except Exception:
                logger.warning("Failed to register AuditJsonlSink", exc_info=True)

        # 40-REQ-12.2: Enforce audit retention before emitting run.start
        if self._audit_dir is not None and self._audit_db_conn is not None:
            try:
                enforce_audit_retention(
                    self._audit_dir,
                    self._audit_db_conn,
                    max_runs=self._config.audit_retention_runs,
                )
            except Exception:
                logger.warning("Failed to enforce audit retention", exc_info=True)

        graph = self._load_graph()

        # Runtime archetype injection: ensure config-enabled archetypes
        # have nodes in the plan even if the plan was built before they
        # were enabled.
        if ensure_graph_archetypes(graph, self._archetypes_config, self._specs_dir):
            try:
                save_plan(graph, self._plan_path)
                logger.info("Persisted plan with injected archetype nodes")
            except OSError:
                logger.warning(
                    "Failed to persist plan after archetype injection",
                    exc_info=True,
                )

        # 04-REQ-1.E2: Empty plan
        if not graph.nodes:
            return ExecutionState(
                plan_hash=self._compute_plan_hash(),
                node_states={},
                run_status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            )

        self._graph = graph

        edges_dict = _build_edges_dict_from_graph(graph)
        plan_hash = self._compute_plan_hash()
        state = _load_or_init_state(self._state_manager, plan_hash, graph)
        _reset_in_progress_tasks(state, self._state_manager)

        self._graph_sync = GraphSync(state.node_states, edges_dict)
        self._result_handler = SessionResultHandler(
            graph_sync=self._graph_sync,
            state_manager=self._state_manager,
            routing_ladders=self._routing.ladders,
            routing_assessments=self._routing.assessments,
            routing_pipeline=self._routing.pipeline,
            retries_before_escalation=self._routing.retries_before_escalation,
            max_retries=self._config.max_retries,
            task_callback=self._task_callback,
            sink=self._sink,
            run_id=self._run_id,
            graph=self._graph,
            archetypes_config=self._archetypes_config,
            knowledge_db_conn=self._knowledge_db_conn,
            block_task_fn=self._block_task,
            check_block_budget_fn=self._check_block_budget,
        )

        attempt_tracker = _init_attempt_tracker(state)
        error_tracker = _init_error_tracker(state)

        self._signal.install()

        # 40-REQ-9.1: Emit run.start audit event
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.RUN_START,
            payload={
                "plan_hash": plan_hash,
                "total_nodes": len(graph.nodes),
                "parallel": self._is_parallel,
            },
        )

        first_dispatch = True
        try:
            while True:
                if self._signal.interrupted:
                    await self._shutdown(state)
                    return state

                # Check block budget: stop if too many tasks are blocked
                if state.run_status == RunStatus.BLOCK_LIMIT:
                    return state

                # Check circuit breaker: cost/session limits (04-REQ-5.*)
                stop_decision = self._circuit.should_stop(state)
                if not stop_decision.allowed:
                    if (
                        self._config.max_cost is not None
                        and state.total_cost >= self._config.max_cost
                    ):
                        state.run_status = RunStatus.COST_LIMIT
                        limit_type = "cost"
                        limit_value: float = float(self._config.max_cost)
                    else:
                        state.run_status = RunStatus.SESSION_LIMIT
                        limit_type = "sessions"
                        limit_value = float(self._config.max_sessions or 0)
                    logger.info(
                        "Circuit breaker tripped: %s",
                        stop_decision.reason,
                    )
                    # 40-REQ-9.3: Emit run.limit_reached with severity warning
                    emit_audit_event(
                        self._sink,
                        self._run_id,
                        AuditEventType.RUN_LIMIT_REACHED,
                        severity=AuditSeverity.WARNING,
                        payload={
                            "limit_type": limit_type,
                            "limit_value": limit_value,
                        },
                    )
                    self._state_manager.save(state)
                    return state

                # 39-REQ-1.1: Sort ready tasks by predicted duration
                duration_hints = self._compute_duration_hints()
                ready = self._graph_sync.ready_tasks(duration_hints=duration_hints)

                # 39-REQ-9.3: Filter conflicting tasks when enabled
                if (
                    self._planning_config.file_conflict_detection
                    and self._is_parallel
                    and len(ready) > 1
                ):
                    ready = self._filter_file_conflicts(ready)

                if not ready:
                    if self._graph_sync.is_stalled():
                        state.run_status = RunStatus.STALLED
                        logger.warning(
                            "Execution stalled. Summary: %s",
                            self._graph_sync.summary(),
                        )
                        self._state_manager.save(state)
                        return state

                    if await self._try_end_of_run_discovery(state):
                        continue  # New specs found — re-enter the main loop

                    state.run_status = RunStatus.COMPLETED
                    self._state_manager.save(state)
                    return state

                if self._is_parallel and self._parallel_runner is not None:
                    await self._dispatch_parallel(
                        ready,
                        state,
                        attempt_tracker,
                        error_tracker,
                    )
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
            # Render memory summary so docs/memory.md reflects all
            # extracted facts, not just those captured at sync barriers.
            try:
                from agent_fox.knowledge.rendering import render_summary

                render_summary(conn=self._knowledge_db_conn)
            except Exception:
                logger.warning("Final memory summary render failed", exc_info=True)
            # 40-REQ-9.2: Emit run.complete at end of execute()
            run_duration_ms = int(
                (datetime.now(UTC) - run_start_time).total_seconds() * 1000
            )
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.RUN_COMPLETE,
                payload={
                    "total_sessions": len(state.session_history),
                    "total_cost": state.total_cost,
                    "duration_ms": run_duration_ms,
                    "run_status": state.run_status.value
                    if hasattr(state.run_status, "value")
                    else str(state.run_status),
                },
            )

    def _compute_duration_hints(self) -> dict[str, int] | None:
        """Compute duration hints for ready task ordering.

        When duration ordering is enabled and an assessment pipeline with
        a DB connection is available, queries historical/regression/preset
        duration hints for all pending nodes.

        Returns:
            Mapping of node_id to predicted duration in ms, or None
            if duration ordering is disabled.

        Requirements: 39-REQ-1.1, 39-REQ-2.2
        """
        if not self._planning_config.duration_ordering:
            return None

        pipeline = self._routing.pipeline
        if pipeline is None:
            return None

        db = getattr(pipeline, "_db", None)
        if db is None:
            return None

        try:
            from agent_fox.routing.duration import get_duration_hint

            duration_model = getattr(pipeline, "duration_model", None)
            hints: dict[str, int] = {}

            for node_id in self.node_states:
                # Extract spec_name and archetype from plan node data
                node = self._graph.nodes.get(node_id) if self._graph else None
                spec_name = node.spec_name if node else ""
                archetype = node.archetype if node else "coder"
                tier = "STANDARD"

                hint = get_duration_hint(
                    db,
                    node_id,
                    spec_name,
                    archetype,
                    tier,
                    min_outcomes=self._planning_config.min_outcomes_for_historical,
                    model=duration_model,
                )
                hints[node_id] = hint.predicted_ms

            return hints
        except Exception:
            logger.warning(
                "Failed to compute duration hints, using default ordering",
                exc_info=True,
            )
            return None

    def _filter_file_conflicts(self, ready: list[str]) -> list[str]:
        """Filter conflicting tasks from the ready set.

        When file_conflict_detection is enabled, extracts predicted file
        impacts for each ready task and serializes conflicting pairs.

        Args:
            ready: List of ready task node IDs.

        Returns:
            Filtered list with conflicting tasks serialized.

        Requirements: 39-REQ-9.3
        """
        try:
            from agent_fox.graph.file_impacts import (
                FileImpact,
                filter_conflicts_from_dispatch,
            )

            impacts: list[FileImpact] = []
            for node_id in ready:
                node = self._graph.nodes.get(node_id) if self._graph else None
                spec_name = node.spec_name if node else ""
                task_group = node.group_number if node else 1

                # Try to extract file impacts from spec dir
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

    @property
    def node_states(self) -> dict[str, str]:
        """Return node states from graph sync, or empty dict."""
        if self._graph_sync is not None:
            return self._graph_sync.node_states
        return {}

    def _load_graph(self) -> TaskGraph:
        """Load plan.json as a typed TaskGraph.

        Raises:
            PlanError: if plan.json is missing or corrupted
        """
        graph = load_plan(self._plan_path)
        if graph is None:
            if not self._plan_path.exists():
                raise PlanError(
                    f"Plan file not found: {self._plan_path}. "
                    f"Run `agent-fox plan` first to generate a plan.",
                    path=str(self._plan_path),
                )
            raise PlanError(
                f"Corrupted plan file {self._plan_path}. "
                f"Run `agent-fox plan` to regenerate.",
                path=str(self._plan_path),
            )
        return graph

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
        error_tracker: dict[str, str | None] | None = None,
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
            last_error = error_tracker.get(node_id) if error_tracker else None
            reason = f"Retry limit exceeded for {node_id}"
            if last_error:
                reason = f"{reason}: {last_error}"
            self._block_task(
                node_id,
                state,
                reason,
            )
            self._check_block_budget(state)
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

            launch = await self._prepare_launch(
                node_id,
                state,
                attempt_tracker,
                error_tracker,
            )
            if launch is None:
                # _check_launch returned blocked or limited; the serial
                # path can't distinguish, so just skip to re-evaluate.
                continue

            (
                _,
                attempt,
                previous_error,
                node_archetype,
                node_instances,
                assessed_tier,
            ) = launch

            if not first_dispatch:
                await self._serial_runner.delay()
            first_dispatch = False

            self._graph_sync.mark_in_progress(node_id)
            # Persist in_progress state so agent-fox status can show it
            self._state_manager.save(state)

            record = await self._serial_runner.execute(
                node_id,
                attempt,
                previous_error,
                archetype=node_archetype,
                instances=node_instances,
                assessed_tier=assessed_tier,
                run_id=self._run_id,
            )

            self._result_handler.process(
                record,
                attempt,
                state,
                attempt_tracker,
                error_tracker,
            )

            # 06-REQ-6.1: Check sync barrier after task completion
            if record.status == "completed":
                # 30-REQ-7.4: Record outcome on success
                self._result_handler.record_node_outcome(node_id, state, "completed")
                await self._run_sync_barrier_if_needed(state)

            # Re-evaluate ready tasks after each completion
            break

        return first_dispatch

    async def _dispatch_parallel(
        self,
        ready: list[str],
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
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

        async def _fill_pool(candidates: list[str]) -> None:
            """Launch candidates into the pool up to max_parallelism."""
            for node_id in candidates:
                if len(pool) >= max_pool:
                    break
                if self._signal.interrupted:
                    break

                launch = await self._prepare_launch(
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
                ) = launch
                graph_sync.mark_in_progress(node_id)

                task = asyncio.create_task(
                    parallel_runner.execute_one(
                        node_id,
                        attempt,
                        previous_error,
                        archetype=node_archetype,
                        instances=node_instances,
                        assessed_tier=assessed_tier,
                        run_id=self._run_id,
                    ),
                    name=f"parallel-{node_id}",
                )
                pool.add(task)

        await _fill_pool(ready)

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

            barrier_needed = False
            for completed_task in done:
                try:
                    record = completed_task.result()
                except Exception as exc:
                    logger.error("Parallel task raised: %s", exc)
                    continue

                self._result_handler.process(
                    record,
                    attempt_tracker.get(record.node_id, 1),
                    state,
                    attempt_tracker,
                    error_tracker,
                )

                # 06-REQ-6.1: Check sync barrier after task completion
                if record.status == "completed":
                    # 30-REQ-7.4: Record outcome on success
                    self._result_handler.record_node_outcome(
                        record.node_id, state, "completed"
                    )
                    if self._should_trigger_barrier(state):
                        barrier_needed = True

            # 51-REQ-1.1, 51-REQ-1.2, 51-REQ-1.3: Drain remaining pool
            # before entering the barrier sequence.
            if barrier_needed and pool:
                if self._signal.interrupted:
                    break
                logger.info(
                    "Barrier triggered — draining %d in-flight tasks",
                    len(pool),
                )
                try:
                    drain_done, pool = await asyncio.wait(pool)
                except asyncio.CancelledError:
                    # 51-REQ-1.E2: SIGINT during drain
                    break
                for drain_task in drain_done:
                    try:
                        drain_record = drain_task.result()
                    except Exception as exc:
                        logger.error("Drained task raised: %s", exc)
                        continue
                    self._result_handler.process(
                        drain_record,
                        attempt_tracker.get(drain_record.node_id, 1),
                        state,
                        attempt_tracker,
                        error_tracker,
                    )
                    if drain_record.status == "completed":
                        self._result_handler.record_node_outcome(
                            drain_record.node_id, state, "completed"
                        )

            # Run the barrier after draining
            if barrier_needed:
                await self._run_sync_barrier_if_needed(state)

            # Re-evaluate ready tasks and fill empty pool slots
            if not self._signal.interrupted:
                new_ready = graph_sync.ready_tasks(
                    duration_hints=self._compute_duration_hints()
                )
                await _fill_pool(new_ready)

            parallel_runner.track_tasks(list(pool))
            self._state_manager.save(state)

    def _get_node_archetype(self, node_id: str) -> str:
        """Get the archetype name for a node from the task graph."""
        if self._graph is not None and node_id in self._graph.nodes:
            return self._graph.nodes[node_id].archetype
        return "coder"

    def _get_node_instances(self, node_id: str) -> int:
        """Get the instance count for a node from the task graph."""
        if self._graph is not None and node_id in self._graph.nodes:
            return self._graph.nodes[node_id].instances
        return 1

    def _get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs for a given node."""
        if self._graph_sync is None:
            return []
        return self._graph_sync.predecessors(node_id)

    def _should_trigger_barrier(self, state: ExecutionState) -> bool:
        """Check whether a sync barrier should fire (no side effects).

        Used by _dispatch_parallel to decide whether to drain the pool
        before calling _run_sync_barrier_if_needed.
        """
        if self._config.sync_interval == 0:
            return False
        completed_count = _count_node_status(state.node_states, "completed")
        return should_trigger_barrier(completed_count, self._config.sync_interval)

    async def _run_sync_barrier_if_needed(self, state: ExecutionState) -> None:
        """Check and run sync barrier actions if triggered.

        Delegates to ``run_sync_barrier_sequence`` in barrier.py for the
        actual work. See that function for details.

        Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3,
                      51-REQ-2.*, 51-REQ-3.*
        """
        if self._config.sync_interval == 0:
            return

        completed_count = _count_node_status(state.node_states, "completed")

        if not should_trigger_barrier(completed_count, self._config.sync_interval):
            return

        await run_sync_barrier_sequence(
            state=state,
            sync_interval=self._config.sync_interval,
            repo_root=self._plan_path.parent,
            emit_audit=self._emit_audit,
            hook_config=self._hook_config,
            no_hooks=self._no_hooks,
            specs_dir=self._specs_dir,
            hot_load_enabled=self._config.hot_load,
            hot_load_fn=self._hot_load_new_specs,
            sync_plan_fn=self._sync_plan_statuses,
            barrier_callback=self._barrier_callback,
            knowledge_db_conn=self._knowledge_db_conn,
        )

    async def _try_end_of_run_discovery(self, state: ExecutionState) -> bool:
        """Run a sync barrier at end-of-run to check for new specs.

        Returns True if new ready tasks were discovered (caller should
        continue the main loop). Returns False if no new work was found
        or if the barrier failed (caller should terminate).

        Requirements: 60-REQ-1.1, 60-REQ-1.E1, 60-REQ-1.E2,
                      60-REQ-3.1, 60-REQ-3.2, 60-REQ-3.3
        """
        if not self._config.hot_load:
            return False

        logger.info("End-of-run discovery: checking for new specs")

        try:
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=self._config.sync_interval,
                repo_root=self._plan_path.parent,
                emit_audit=self._emit_audit,
                hook_config=self._hook_config,
                no_hooks=self._no_hooks,
                specs_dir=self._specs_dir,
                hot_load_enabled=self._config.hot_load,
                hot_load_fn=self._hot_load_new_specs,
                sync_plan_fn=self._sync_plan_statuses,
                barrier_callback=self._barrier_callback,
                knowledge_db_conn=self._knowledge_db_conn,
            )
        except Exception:
            logger.error("End-of-run discovery barrier failed", exc_info=True)
            return False

        assert self._graph_sync is not None  # noqa: S101
        ready = self._graph_sync.ready_tasks()
        if ready:
            logger.info("End-of-run discovery found %d new ready task(s)", len(ready))
            return True

        return False

    async def _hot_load_new_specs(self, state: ExecutionState) -> None:
        """Discover and incorporate new specs into the running graph.

        Uses gated discovery (51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1) to
        filter specs through git-tracked, completeness, and lint gates,
        then builds nodes/edges directly from the accepted specs.
        """
        assert self._specs_dir is not None  # noqa: S101
        assert self._graph_sync is not None  # noqa: S101
        assert self._graph is not None  # noqa: S101

        # Sync current execution state into graph node statuses
        for nid, node in self._graph.nodes.items():
            node.status = NodeStatus(state.node_states.get(nid, "pending"))

        # 51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1: Gated discovery — single pass
        repo_root = self._plan_path.parent
        known_specs = {n.spec_name for n in self._graph.nodes.values()}
        gated_specs = await discover_new_specs_gated(
            self._specs_dir, known_specs, repo_root
        )

        if not gated_specs:
            return

        # Validate, parse tasks/deps, and build nodes/edges directly
        all_spec_names = known_specs | {s.name for s in gated_specs}
        valid_specs, spec_task_groups, spec_deps = _validate_and_parse_specs(
            gated_specs, all_spec_names
        )

        if not valid_specs:
            return

        new_nodes, new_edges, added_spec_names = _build_nodes_and_edges(
            valid_specs,
            spec_task_groups,
            spec_deps,
            self._graph.nodes,
            self._graph.edges,
        )

        if not added_spec_names:
            return

        logger.info(
            "Hot-loaded %d new spec(s): %s",
            len(added_spec_names),
            ", ".join(added_spec_names),
        )

        # Merge new nodes into our graph and state
        for nid, node in new_nodes.items():
            if nid not in self._graph.nodes:
                self._graph.nodes[nid] = node
                state.node_states[nid] = "pending"

        # Merge new edges
        existing_edge_set = {(e.source, e.target) for e in self._graph.edges}
        for edge in new_edges:
            if (edge.source, edge.target) not in existing_edge_set:
                self._graph.edges.append(edge)

        # 32-REQ-4.1: Inject archetype nodes for hot-loaded specs
        ensure_graph_archetypes(self._graph, self._archetypes_config, self._specs_dir)
        # Sync any newly injected archetype nodes into state
        for nid in self._graph.nodes:
            if nid not in state.node_states:
                state.node_states[nid] = "pending"

        # Rebuild GraphSync with updated graph
        edges_dict = _build_edges_dict_from_graph(self._graph)
        self._graph_sync = GraphSync(state.node_states, edges_dict)

    def _block_task(
        self,
        node_id: str,
        state: ExecutionState,
        reason: str,
    ) -> None:
        """Mark a task as blocked and cascade-block all dependents."""
        if self._graph_sync is not None:
            cascade_blocked = self._graph_sync.mark_blocked(node_id, reason)
            state.blocked_reasons[node_id] = reason
            # 18-REQ-5.4: Emit blocked event
            if self._task_callback is not None:
                self._task_callback(
                    TaskEvent(
                        node_id=node_id,
                        status="blocked",
                        duration_s=0,
                        error_message=reason,
                        archetype=self._get_node_archetype(node_id),
                    )
                )
            for blocked_id in cascade_blocked:
                cascade_reason = f"Blocked by upstream task {node_id}"
                state.blocked_reasons[blocked_id] = cascade_reason
                if self._task_callback is not None:
                    self._task_callback(
                        TaskEvent(
                            node_id=blocked_id,
                            status="blocked",
                            duration_s=0,
                            error_message=cascade_reason,
                            archetype=self._get_node_archetype(blocked_id),
                        )
                    )
                logger.info("Cascade-blocked %s due to %s", blocked_id, node_id)

    def _check_block_budget(self, state: ExecutionState) -> bool:
        """Check if the blocked fraction exceeds the configured budget.

        Returns True if the run should stop due to excessive blocking.
        """
        max_fraction = self._config.max_blocked_fraction
        if max_fraction is None:
            return False

        total = len(state.node_states)
        if total == 0:
            return False

        blocked_count = _count_node_status(state.node_states, "blocked")
        fraction = blocked_count / total

        if fraction >= max_fraction:
            state.run_status = RunStatus.BLOCK_LIMIT
            logger.warning(
                "Block budget exceeded: %.0f%% of tasks blocked "
                "(limit: %.0f%%). Stopping run.",
                fraction * 100,
                max_fraction * 100,
            )
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.RUN_LIMIT_REACHED,
                severity=AuditSeverity.WARNING,
                payload={
                    "limit_type": "block_budget",
                    "blocked_count": blocked_count,
                    "total_nodes": total,
                    "blocked_fraction": round(fraction, 3),
                    "max_blocked_fraction": max_fraction,
                },
            )
            self._state_manager.save(state)
            return True

        return False

    def _sync_plan_statuses(self, state: ExecutionState) -> None:
        """Write current node statuses back into plan.json.

        Updates each node's ``status`` field in the graph to match
        the execution state, then persists via save_plan. This keeps
        the plan file in sync with reality so ``agent-fox status`` and
        direct inspection of plan.json show accurate progress.
        """
        if self._graph is None or not state.node_states:
            return

        changed = False
        for nid, current_status in state.node_states.items():
            node = self._graph.nodes.get(nid)
            if node is not None and node.status.value != current_status:
                node.status = NodeStatus(current_status)
                changed = True

        if not changed:
            return

        try:
            save_plan(self._graph, self._plan_path)
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
