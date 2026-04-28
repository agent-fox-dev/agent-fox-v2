"""Orchestrator: deterministic execution engine. Zero LLM calls.

Loads the task graph, dispatches sessions in dependency order, manages
retries with error feedback, cascade-blocks failed tasks, persists state
after every session, and handles graceful interruption.

The Orchestrator delegates to three collaborators:
- StateManager  — state loading, initialization, persistence, node status
- DispatchManager — runners, dispatchers, launch preparation, preflight
- ConfigReloader — configuration hot-reload from disk

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
import atexit
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_fox.core.config import (
    AgentFoxConfig,
    ArchetypesConfig,
    OrchestratorConfig,
    PlanningConfig,
    RoutingConfig,
)
from agent_fox.core.errors import PlanError
from agent_fox.engine.assessment import AssessmentManager
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.barrier import _count_node_status, run_sync_barrier_sequence
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.config_reload import (  # noqa: F401 — ReloadResult, diff_configs re-exported
    ConfigReloader,
    ReloadResult,
    diff_configs,
)
from agent_fox.engine.dispatch import (
    DispatchManager,
    ParallelDispatcher,
    SerialDispatcher,
    SerialRunner,
)
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.hot_load import hot_load_into_graph, should_trigger_barrier
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, RunStatus
from agent_fox.engine.state_manager import (
    StateManager,
    build_edges_dict,
    defer_ready_reviews,
    init_attempt_tracker,
    init_error_tracker,
    load_or_init_state,
    reset_blocked_tasks,
    reset_in_progress_tasks,
    seed_node_states,
)
from agent_fox.graph.injection import ensure_graph_archetypes
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.types import TaskGraph
from agent_fox.knowledge.audit import (
    AuditEventType,
    AuditJsonlSink,
    AuditSeverity,
    enforce_audit_retention,
    generate_run_id,
)
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.ui.progress import TaskCallback

logger = logging.getLogger(__name__)

# Backward-compatibility re-exports so existing imports keep working.
_build_edges_dict_from_graph = build_edges_dict
_seed_node_states_from_graph = seed_node_states
_load_or_init_state = load_or_init_state
_reset_in_progress_tasks = reset_in_progress_tasks
_reset_blocked_tasks = reset_blocked_tasks
_defer_ready_reviews = defer_ready_reviews
_init_attempt_tracker = init_attempt_tracker
_init_error_tracker = init_error_tracker


class _SignalHandler:
    """SIGINT/SIGTERM handling for graceful shutdown (04-REQ-8.E1)."""

    def __init__(self) -> None:
        self.interrupted = False
        self._interrupt_count = 0
        self._prev_sigint: Any = None
        self._prev_sigterm: Any = None

    def install(self) -> None:
        def handler(signum: int, frame: Any) -> None:
            self._interrupt_count += 1
            if self._interrupt_count >= 2:
                logger.warning("Double interrupt received, exiting immediately.")
                raise SystemExit(1)
            self.interrupted = True
            sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
            logger.info("%s received, shutting down gracefully...", sig_name)

        try:
            self._prev_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, handler)
        except (OSError, ValueError):
            self._prev_sigint = None
        try:
            self._prev_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, handler)
        except (OSError, ValueError):
            self._prev_sigterm = None

    def restore(self) -> None:
        if self._prev_sigint is not None:
            try:
                signal.signal(signal.SIGINT, self._prev_sigint)
            except (OSError, ValueError):
                pass
        if self._prev_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, self._prev_sigterm)
            except (OSError, ValueError):
                pass


class Orchestrator:
    """Deterministic execution engine. Zero LLM calls.

    Delegates to StateManager, DispatchManager, and ConfigReloader.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        session_runner_factory: Callable[..., Any],
        *,
        agent_dir: Path | None = None,
        watch: bool = False,
        specs_dir: Path | None = None,
        task_callback: TaskCallback | None = None,
        routing_config: RoutingConfig | None = None,
        archetypes_config: ArchetypesConfig | None = None,
        planning_config: PlanningConfig | None = None,
        sink_dispatcher: SinkDispatcher | None = None,
        audit_dir: Path | None = None,
        audit_db_conn: Any | None = None,
        knowledge_db_conn: Any | None = None,
        config_path: Path | None = None,
        full_config: AgentFoxConfig | None = None,
        platform: Any | None = None,
    ) -> None:
        self._config = config
        self._watch = watch
        self._agent_dir = agent_dir or Path(".agent-fox")
        self._circuit = CircuitBreaker(config)
        self._graph_sync: GraphSync | None = None
        self._signal = _SignalHandler()
        self._is_parallel = config.parallel > 1
        self._specs_dir = specs_dir
        self._task_callback = task_callback
        self._graph: TaskGraph | None = None
        self._archetypes_config = archetypes_config
        self._planning_config = planning_config or PlanningConfig()
        self._sink = sink_dispatcher
        self._run_id: str = ""
        self._audit_dir = audit_dir
        self._audit_db_conn = audit_db_conn
        self._knowledge_db_conn = knowledge_db_conn
        self._platform = platform
        self._issue_summaries_posted: set[str] = set()
        self._atexit_handler: Callable[[], None] | None = None

        self._config_reloader = ConfigReloader(config_path, full_config)

        _rc = routing_config or RoutingConfig()
        self._routing_config = _rc
        self._routing = AssessmentManager(
            retries_before_escalation=self._resolve_retries_before_escalation(_rc),
            config=full_config or AgentFoxConfig(),
        )

        self._state_mgr = StateManager(
            knowledge_db_conn=knowledge_db_conn,
            task_callback=task_callback,
            max_blocked_fraction=config.max_blocked_fraction,
        )

        self._dispatch_mgr = DispatchManager(
            session_runner_factory=session_runner_factory,
            inter_session_delay=float(config.inter_session_delay),
            parallel=config.parallel,
            routing=self._routing,
            circuit=self._circuit,
            config=config,
            routing_config=_rc,
            specs_dir=specs_dir,
            full_config=lambda: self._full_config,
            knowledge_db_conn=knowledge_db_conn,
            sink=sink_dispatcher,
            task_callback=task_callback,
            planning_config=self._planning_config,
        )

        self._result_handler: SessionResultHandler | None = None
        self._serial_dispatcher = SerialDispatcher(self)
        self._parallel_dispatcher: ParallelDispatcher | None = None
        if self._is_parallel:
            self._parallel_dispatcher = ParallelDispatcher(self)

    @property
    def _serial_runner(self) -> SerialRunner:
        return self._dispatch_mgr.serial_runner

    @property
    def _parallel_runner(self):  # noqa: ANN202
        return self._dispatch_mgr.parallel_runner

    @property
    def _repo_root(self) -> Path:
        return self._agent_dir.parent

    @property
    def _config_path(self) -> Path | None:
        return self._config_reloader.config_path

    @_config_path.setter
    def _config_path(self, value: Path | None) -> None:
        self._config_reloader._config_path = value

    @property
    def _full_config(self) -> AgentFoxConfig | None:
        return self._config_reloader.full_config

    @_full_config.setter
    def _full_config(self, value: AgentFoxConfig | None) -> None:
        self._config_reloader._full_config = value

    @property
    def _config_hash(self) -> str:
        return self._config_reloader.config_hash

    @_config_hash.setter
    def _config_hash(self, value: str) -> None:
        self._config_reloader.config_hash = value

    def _resolve_retries_before_escalation(self, routing_config: RoutingConfig) -> int:
        routing_retries = routing_config.retries_before_escalation
        orch_retries = self._config.max_retries
        if routing_retries != 1:
            return routing_retries
        if orch_retries != 2:
            logger.warning(
                "orchestrator.max_retries is deprecated; use "
                "routing.retries_before_escalation instead. "
                "Using max_retries=%d as fallback.",
                orch_retries,
            )
            return min(orch_retries, 3)
        return routing_retries

    def _emit_audit(self, *args: Any, **kwargs: Any) -> None:
        emit_audit_event(self._sink, self._run_id, *args, **kwargs)

    def _emit_watch_poll(self, poll: int, *, new_tasks: bool) -> None:
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.WATCH_POLL,
            payload={"poll_number": poll, "new_tasks_found": new_tasks},
        )

    def _get_node(self, node_id: str) -> Any | None:
        return self._dispatch_mgr.get_node(node_id)

    def _get_node_archetype(self, node_id: str) -> str:
        return self._dispatch_mgr.get_node_archetype(node_id)

    def _get_node_instances(self, node_id: str) -> int:
        return self._dispatch_mgr.get_node_instances(node_id)

    def _get_node_mode(self, node_id: str) -> str | None:
        return self._dispatch_mgr.get_node_mode(node_id)

    def _get_predecessors(self, node_id: str) -> list[str]:
        if self._graph_sync is None:
            return []
        return self._graph_sync.predecessors(node_id)

    def _block_task(self, node_id: str, state: ExecutionState, reason: str) -> None:
        self._state_mgr.block_task(
            node_id,
            state,
            reason,
            graph_sync=self._graph_sync,
            get_archetype_fn=self._get_node_archetype,
        )

    def _check_block_budget(self, state: ExecutionState) -> bool:
        return self._state_mgr.check_block_budget(
            state,
            sink=self._sink,
            run_id=self._run_id,
        )

    def _sync_plan_statuses(self, state: ExecutionState) -> None:
        self._state_mgr.sync_plan_statuses(state, self._graph)

    @property
    def node_states(self) -> dict[str, str]:
        if self._graph_sync is not None:
            return self._graph_sync.node_states
        return {}

    def _load_graph(self) -> TaskGraph:
        if self._knowledge_db_conn is None:
            raise PlanError("No database connection available. Run `agent-fox plan` first.")
        graph = load_plan(self._knowledge_db_conn)
        if graph is None:
            raise PlanError("No plan found in database. Run `agent-fox plan` first to generate a plan.")
        return graph

    def _compute_plan_hash(self) -> str:
        if self._graph is not None:
            try:
                from agent_fox.graph.persistence import compute_plan_hash

                return compute_plan_hash(self._graph)
            except Exception:
                pass
        return ""

    def _should_trigger_barrier(self, state: ExecutionState) -> bool:
        return self._dispatch_mgr.should_trigger_barrier(state)

    # -- Init / Run / Watch / Shutdown --------------------------------------

    def _init_run(
        self,
    ) -> tuple[ExecutionState, dict[str, int], dict[str, str | None]] | ExecutionState:
        self._run_id = generate_run_id()
        logger.debug("Audit run ID: %s", self._run_id)

        if self._audit_dir is not None and self._sink is not None:
            try:
                self._sink.add(AuditJsonlSink(self._audit_dir, self._run_id))
            except Exception:
                logger.warning("Failed to register AuditJsonlSink", exc_info=True)

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

        if ensure_graph_archetypes(graph, self._archetypes_config, self._specs_dir):
            if self._knowledge_db_conn is not None:
                try:
                    save_plan(graph, self._knowledge_db_conn)
                    logger.info("Persisted plan with injected archetype nodes")
                except Exception:
                    logger.warning("Failed to persist plan after archetype injection", exc_info=True)

        if not graph.nodes and not self._watch:
            return ExecutionState(
                plan_hash=self._compute_plan_hash(),
                node_states={},
                run_status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            )

        self._graph = graph
        self._dispatch_mgr.set_graph(graph)

        plan_hash = self._compute_plan_hash()
        state = load_or_init_state(self._knowledge_db_conn, plan_hash, graph)
        is_fresh_start = state.total_sessions == 0 and not state.session_history
        reset_in_progress_tasks(state, self._knowledge_db_conn)
        if not is_fresh_start:
            reset_blocked_tasks(state, self._knowledge_db_conn)
        else:
            for node_id, node in graph.nodes.items():
                if node.status.value == "blocked":
                    state.node_states[node_id] = "blocked"

        if self._knowledge_db_conn is not None:
            try:
                from agent_fox.engine.state import cleanup_stale_runs as _cleanup

                cleaned = _cleanup(self._knowledge_db_conn, self._run_id)
                if cleaned:
                    logger.info("Marked %d stale running run(s) as stalled", cleaned)
            except Exception:
                logger.warning("Failed to clean up stale running runs", exc_info=True)

        if self._knowledge_db_conn is not None:
            try:
                from agent_fox.engine.state import create_run as _create_run

                _create_run(self._knowledge_db_conn, self._run_id, plan_hash)
            except Exception:
                logger.debug("Failed to create DB run record", exc_info=True)

            # Register atexit handler to transition run to 'stalled' on
            # unexpected process termination (118-REQ-6.2)
            try:
                from agent_fox.engine.state import run_cleanup_handler

                _db_conn = self._knowledge_db_conn
                _run_id = self._run_id

                def _atexit_cleanup() -> None:
                    run_cleanup_handler(_run_id, _db_conn)

                self._atexit_handler = _atexit_cleanup
                atexit.register(_atexit_cleanup)
            except Exception:
                logger.warning("Failed to register run cleanup handler", exc_info=True)

        edges_dict = build_edges_dict(graph)
        node_archetypes = {nid: n.archetype for nid, n in graph.nodes.items()}
        self._graph_sync = GraphSync(state.node_states, edges_dict, node_archetypes)
        self._dispatch_mgr.set_graph_sync(self._graph_sync)
        self._dispatch_mgr.set_run_id(self._run_id)
        self._dispatch_mgr.set_callbacks(self._block_task, self._check_block_budget)

        defer_ready_reviews(graph, self._graph_sync, self._knowledge_db_conn)
        self._result_handler = SessionResultHandler(
            graph_sync=self._graph_sync,
            routing_ladders=self._routing.ladders,
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
            max_timeout_retries=self._routing_config.max_timeout_retries,
            timeout_multiplier=self._routing_config.timeout_multiplier,
            timeout_ceiling_factor=self._routing_config.timeout_ceiling_factor,
            original_session_timeout=self._config.session_timeout,
        )

        return state, init_attempt_tracker(state), init_error_tracker(state)

    async def run(self) -> ExecutionState:
        """Execute the full orchestration loop."""
        run_start_time = datetime.now(UTC)
        self._watch_poll_count = 0
        result = self._init_run()
        if isinstance(result, ExecutionState):
            return result
        state, attempt_tracker, error_tracker = result

        self._signal.install()
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.RUN_START,
            payload={
                "plan_hash": self._compute_plan_hash(),
                "total_nodes": len(self._graph.nodes) if self._graph else 0,
                "parallel": self._is_parallel,
            },
        )

        first_dispatch = True
        try:
            while True:
                if self._signal.interrupted:
                    await self._shutdown(state, attempt_tracker, error_tracker)
                    return state
                if state.run_status == RunStatus.BLOCK_LIMIT:
                    return state

                stop_decision = self._circuit.should_stop(state)
                if not stop_decision.allowed:
                    if self._config.max_cost is not None and state.total_cost >= self._config.max_cost:
                        state.run_status = RunStatus.COST_LIMIT
                        limit_type, limit_value = "cost", float(self._config.max_cost)
                    else:
                        state.run_status = RunStatus.SESSION_LIMIT
                        limit_type, limit_value = "sessions", float(self._config.max_sessions or 0)
                    logger.info("Circuit breaker tripped: %s", stop_decision.reason)
                    emit_audit_event(
                        self._sink,
                        self._run_id,
                        AuditEventType.RUN_LIMIT_REACHED,
                        severity=AuditSeverity.WARNING,
                        payload={"limit_type": limit_type, "limit_value": limit_value},
                    )
                    return state

                assert self._graph_sync is not None  # noqa: S101
                ready = self._graph_sync.ready_tasks()

                if self._planning_config.file_conflict_detection and self._is_parallel and len(ready) > 1:
                    ready = self._dispatch_mgr.filter_file_conflicts(ready)

                if not ready:
                    pr = self._dispatch_mgr.parallel_runner
                    max_slots = pr.max_parallelism if pr else 1
                    promoted = self._graph_sync.promote_deferred(limit=max_slots)
                    if promoted:
                        logger.info("Promoted %d deferred review node(s)", len(promoted))
                        ready = self._graph_sync.ready_tasks()

                if not ready:
                    if self._graph_sync.is_stalled(ready=ready):
                        state.run_status = RunStatus.STALLED
                        logger.warning("Execution stalled. Summary: %s", self._graph_sync.summary())
                        return state
                    if await self._try_end_of_run_discovery(state):
                        continue
                    if self._watch:
                        if not self._config.hot_load:
                            logger.warning(
                                "Watch mode is active but hot_load is disabled "
                                "in configuration; terminating with COMPLETED "
                                "status instead of entering watch loop."
                            )
                        else:
                            watch_result = await self._watch_loop(state)
                            if watch_result is None:
                                continue
                            return watch_result
                    state.run_status = RunStatus.COMPLETED
                    return state

                if self._is_parallel and self._dispatch_mgr.parallel_runner is not None:
                    await self._parallel_dispatcher.dispatch(ready, state, attempt_tracker, error_tracker)
                else:
                    first_dispatch = await self._serial_dispatcher.dispatch(
                        ready,
                        state,
                        attempt_tracker,
                        error_tracker,
                        first_dispatch,
                    )
        finally:
            await self._finalize_run(state, run_start_time)

    async def _finalize_run(self, state: ExecutionState, run_start_time: datetime) -> None:
        self._signal.restore()
        self._sync_plan_statuses(state)

        try:
            from agent_fox.session.auditor_output import cleanup_completed_spec_audits

            if self._graph_sync is not None:
                completed = self._graph_sync.completed_spec_names()
                if completed:
                    cleanup_completed_spec_audits(Path.cwd(), completed)
        except Exception:
            logger.warning("Audit report cleanup failed", exc_info=True)

        if self._platform is not None and self._graph_sync is not None:
            await self._post_issue_summaries()

        # Unregister the atexit cleanup handler — the run is completing
        # normally so we don't want the handler to overwrite the terminal
        # status with 'stalled' (118-REQ-6.3).
        if self._atexit_handler is not None:
            try:
                atexit.unregister(self._atexit_handler)
            except Exception:
                pass
            self._atexit_handler = None

        if self._knowledge_db_conn is not None:
            try:
                from agent_fox.engine.state import complete_run as _complete_run

                run_status_val = state.run_status.value if hasattr(state.run_status, "value") else str(state.run_status)
                _complete_run(self._knowledge_db_conn, self._run_id, run_status_val)
            except Exception:
                logger.debug("Failed to complete run in DB", exc_info=True)

        run_duration_ms = int((datetime.now(UTC) - run_start_time).total_seconds() * 1000)
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.RUN_COMPLETE,
            payload={
                "total_sessions": len(state.session_history),
                "total_cost": state.total_cost,
                "duration_ms": run_duration_ms,
                "run_status": state.run_status.value if hasattr(state.run_status, "value") else str(state.run_status),
            },
        )

    async def _post_issue_summaries(self) -> None:
        try:
            from agent_fox.engine.issue_summary import post_issue_summaries as _post

            completed = self._graph_sync.completed_spec_names()
            newly_completed = completed - self._issue_summaries_posted
            if newly_completed:
                _eff = self._specs_dir
                if _eff is None and self._full_config is not None:
                    from agent_fox.core.config import resolve_spec_root as _rsr

                    _eff = _rsr(self._full_config, Path.cwd())
                posted = await _post(
                    self._platform,
                    _eff or Path(".specs"),
                    newly_completed,
                    self._issue_summaries_posted,
                    Path.cwd(),
                )
                self._issue_summaries_posted.update(posted)
        except Exception:
            logger.warning("Issue summary posting failed", exc_info=True)

    async def _watch_loop(self, state: ExecutionState) -> ExecutionState | None:
        while True:
            self._watch_poll_count += 1
            poll = self._watch_poll_count

            if self._signal.interrupted:
                self._emit_watch_poll(poll, new_tasks=False)
                state.run_status = RunStatus.INTERRUPTED
                return state

            interval = self._config.watch_interval
            logger.info("Watch poll %d: sleeping %ds", poll, interval)
            await asyncio.sleep(interval)

            if self._signal.interrupted:
                self._emit_watch_poll(poll, new_tasks=False)
                state.run_status = RunStatus.INTERRUPTED
                return state

            stop_decision = self._circuit.should_stop(state)
            if not stop_decision.allowed:
                cost_exceeded = self._config.max_cost is not None and state.total_cost >= self._config.max_cost
                state.run_status = RunStatus.COST_LIMIT if cost_exceeded else RunStatus.SESSION_LIMIT
                return state

            try:
                new_tasks = await self._try_end_of_run_discovery(state)
            except Exception:
                logger.exception("Watch poll %d: barrier error", poll)
                new_tasks = False

            self._emit_watch_poll(poll, new_tasks=new_tasks)
            if new_tasks:
                return None

    async def _run_sync_barrier_if_needed(self, state: ExecutionState) -> None:
        if self._config.sync_interval == 0:
            return
        completed_count = _count_node_status(state.node_states, "completed")
        if not should_trigger_barrier(completed_count, self._config.sync_interval):
            return
        await run_sync_barrier_sequence(
            state=state,
            sync_interval=self._config.sync_interval,
            repo_root=self._repo_root,
            emit_audit=self._emit_audit,
            specs_dir=self._specs_dir,
            hot_load_enabled=self._config.hot_load,
            hot_load_fn=self._hot_load_new_specs,
            sync_plan_fn=self._sync_plan_statuses,
            barrier_callback=None,
            knowledge_db_conn=self._knowledge_db_conn,
            reload_config_fn=self._reload_config,
        )

    async def _try_end_of_run_discovery(self, state: ExecutionState) -> bool:
        if not self._config.hot_load:
            return False
        logger.info("End-of-run discovery: checking for new specs")
        try:
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=self._config.sync_interval,
                repo_root=self._repo_root,
                emit_audit=self._emit_audit,
                specs_dir=self._specs_dir,
                hot_load_enabled=self._config.hot_load,
                hot_load_fn=self._hot_load_new_specs,
                sync_plan_fn=self._sync_plan_statuses,
                barrier_callback=None,
                knowledge_db_conn=self._knowledge_db_conn,
                reload_config_fn=self._reload_config,
            )
        except Exception:
            logger.error("End-of-run discovery barrier failed", exc_info=True)
            return False
        if self._graph_sync is None:
            return False
        ready = self._graph_sync.ready_tasks()
        if ready:
            logger.info("End-of-run discovery found %d new ready task(s)", len(ready))
            return True
        return False

    async def _hot_load_new_specs(self, state: ExecutionState) -> None:
        assert self._specs_dir is not None  # noqa: S101
        assert self._graph_sync is not None  # noqa: S101
        assert self._graph is not None  # noqa: S101

        self._graph, self._graph_sync = await hot_load_into_graph(
            specs_dir=self._specs_dir,
            graph=self._graph,
            graph_sync=self._graph_sync,
            state=state,
            repo_root=self._repo_root,
            knowledge_db_conn=self._knowledge_db_conn,
            archetypes_config=self._archetypes_config,
        )
        self._dispatch_mgr.set_graph(self._graph)
        self._dispatch_mgr.set_graph_sync(self._graph_sync)

    def _reload_config(self) -> None:
        result = self._config_reloader.reload(
            current_config=self._config,
            circuit=self._circuit,
            sink=self._sink,
            run_id=self._run_id,
        )
        if result is None:
            return
        self._config = result.config
        self._circuit = result.circuit
        self._archetypes_config = result.archetypes
        self._planning_config = result.planning

    async def _shutdown(
        self,
        state: ExecutionState,
        attempt_tracker: dict[str, int] | None = None,
        error_tracker: dict[str, str | None] | None = None,
    ) -> None:
        if self._dispatch_mgr.parallel_runner is not None:
            unprocessed = await self._dispatch_mgr.parallel_runner.cancel_all()
            if unprocessed and self._result_handler is not None:
                _at = attempt_tracker or {}
                _et = error_tracker or {}
                for record in unprocessed:
                    actual_attempt = _at.get(record.node_id, record.attempt)
                    if record.attempt != actual_attempt:
                        from dataclasses import replace as _dc_replace

                        record = _dc_replace(record, attempt=actual_attempt)
                    try:
                        self._result_handler.process(record, actual_attempt, state, _at, _et)
                    except Exception:
                        logger.debug(
                            "Failed to persist interrupted session record for %s",
                            record.node_id,
                            exc_info=True,
                        )

        state.run_status = RunStatus.INTERRUPTED
        summary = self._graph_sync.summary() if self._graph_sync else {}
        completed = summary.get("completed", 0)
        total = sum(summary.values()) if summary else 0
        remaining = total - completed
        logger.info(
            "Execution interrupted. %d/%d tasks completed, %d remaining. Resume with: agent-fox code",
            completed,
            total,
            remaining,
        )
