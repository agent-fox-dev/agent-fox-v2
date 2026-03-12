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
from dataclasses import dataclass
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
from agent_fox.core.models import ModelTier
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.hot_load import hot_load_specs, should_trigger_barrier
from agent_fox.engine.parallel import ParallelRunner
from agent_fox.engine.state import (
    ExecutionState,
    RunStatus,
    SessionRecord,
    StateManager,
    invoke_runner,
)
from agent_fox.graph.types import Edge, Node, NodeStatus, TaskGraph
from agent_fox.hooks.hooks import run_sync_barrier_hooks
from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    default_severity_for,
    generate_run_id,
)
from agent_fox.knowledge.rendering import render_summary
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.session.archetypes import get_archetype
from agent_fox.ui.events import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


@dataclass
class _RoutingState:
    """Groups all adaptive routing state for the Orchestrator."""

    config: RoutingConfig
    pipeline: Any | None
    ladders: dict[str, Any]
    assessments: dict[str, Any]
    retries_before_escalation: int


# ---------------------------------------------------------------------------
# SerialRunner (merged from serial.py)
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


# ---------------------------------------------------------------------------
# CircuitBreaker (merged from circuit.py)
# ---------------------------------------------------------------------------


@dataclass
class LaunchDecision:
    """Result of a circuit breaker check."""

    allowed: bool
    reason: str | None = None  # None if allowed, explanation if denied


class CircuitBreaker:
    """Pre-launch checks: cost ceiling, session limit, retry counter.

    The circuit breaker is consulted before every session launch. It
    checks three conditions (in order):

    1. **Cost ceiling:** cumulative cost >= config.max_cost
    2. **Session limit:** total sessions >= config.max_sessions
    3. **Retry limit:** attempt number > config.max_retries + 1

    If any check fails, the launch is denied with an explanatory reason.
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    def _check_global_limits(
        self,
        state: ExecutionState,
    ) -> LaunchDecision | None:
        """Check cost ceiling and session limit.

        Returns a denied LaunchDecision if a limit is hit, or None if
        both checks pass.
        """
        if (
            self._config.max_cost is not None
            and state.total_cost >= self._config.max_cost
        ):
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Cost limit reached: cumulative cost "
                    f"${state.total_cost:.2f} >= "
                    f"max_cost ${self._config.max_cost:.2f}"
                ),
            )

        if (
            self._config.max_sessions is not None
            and state.total_sessions >= self._config.max_sessions
        ):
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Session limit reached: {state.total_sessions} "
                    f"sessions >= max_sessions {self._config.max_sessions}"
                ),
            )

        return None

    def check_launch(
        self,
        node_id: str,
        attempt: int,
        state: ExecutionState,
    ) -> LaunchDecision:
        """Determine whether a session launch is permitted.

        Checks (in order):
        1. Cost ceiling: state.total_cost >= config.max_cost
        2. Session limit: state.total_sessions >= config.max_sessions
        3. Retry limit: attempt > config.max_retries + 1

        Args:
            node_id: The task to check.
            attempt: The proposed attempt number (1-indexed).
            state: Current execution state.

        Returns:
            LaunchDecision with allowed=True or allowed=False with reason.
        """
        denied = self._check_global_limits(state)
        if denied is not None:
            return denied

        # Retry limit check
        max_attempts = self._config.max_retries + 1
        if attempt > max_attempts:
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Retry limit exceeded for {node_id}: "
                    f"attempt {attempt} > max_retries + 1 "
                    f"({max_attempts})"
                ),
            )

        return LaunchDecision(allowed=True)

    def should_stop(self, state: ExecutionState) -> LaunchDecision:
        """Check whether the orchestrator should stop launching entirely.

        This is called before picking the next batch of ready tasks.
        Checks cost ceiling and session limit only (not per-task retry).

        Args:
            state: Current execution state.

        Returns:
            LaunchDecision with allowed=True or allowed=False with reason.
        """
        return self._check_global_limits(state) or LaunchDecision(allowed=True)


# ---------------------------------------------------------------------------
# Orchestrator (from orchestrator.py)
# ---------------------------------------------------------------------------


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


def _ensure_archetype_nodes(
    plan_data: dict,
    archetypes_config: ArchetypesConfig | None,
) -> bool:
    """Inject missing archetype nodes into plan_data based on config.

    Examines each spec in the plan and adds auto_pre/auto_post nodes
    if they're enabled in config but absent from the plan. This ensures
    archetypes activate at runtime even with a stale cached plan.

    Returns True if any nodes were injected (plan needs re-persisting).
    """
    if archetypes_config is None:
        return False

    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    nodes = plan_data.get("nodes", {})
    edges = plan_data.get("edges", [])
    order = plan_data.get("order", [])
    injected = False

    # Group existing coder nodes by spec
    spec_groups: dict[str, list[int]] = {}
    for nid, node in nodes.items():
        spec = node.get("spec_name", "")
        group = node.get("group_number", 0)
        arch = node.get("archetype", "coder")
        if arch == "coder":
            spec_groups.setdefault(spec, []).append(group)

    for spec, groups in spec_groups.items():
        sorted_groups = sorted(groups)
        first_group = sorted_groups[0]
        last_group = sorted_groups[-1]

        # auto_pre injection (e.g., Skeptic/Oracle at group 0)
        # 32-REQ-3.E1: When a legacy plan has {spec}:0 and we need to add
        # another auto_pre, add the new one with a suffixed ID to avoid
        # conflicting with the existing node.
        enabled_auto_pre: list[tuple[str, Any]] = [
            (arch_name, entry)
            for arch_name, entry in ARCHETYPE_REGISTRY.items()
            if entry.injection == "auto_pre"
            and getattr(archetypes_config, arch_name, False)
        ]

        # Find existing auto_pre archetypes for this spec (group_number == 0)
        existing_archetypes: set[str] = set()
        for nid, n in nodes.items():
            if n.get("spec_name") == spec and n.get("group_number") == 0:
                existing_archetypes.add(n.get("archetype", ""))

        needed = [
            (arch_name, entry) for arch_name, entry in enabled_auto_pre
            if arch_name not in existing_archetypes
        ]

        for arch_name, entry in needed:
            # Use suffixed ID to avoid conflict with existing :0 node
            node_id = f"{spec}:0:{arch_name}"
            if node_id in nodes:
                continue  # already present

            instances_cfg = getattr(archetypes_config, "instances", None)
            instances = getattr(instances_cfg, arch_name, 1) if instances_cfg else 1

            nodes[node_id] = {
                "id": node_id,
                "spec_name": spec,
                "group_number": 0,
                "title": f"{arch_name.capitalize()} Review",
                "optional": False,
                "status": "pending",
                "subtask_count": 0,
                "body": "",
                "archetype": arch_name,
                "instances": instances if isinstance(instances, int) else 1,
            }
            first_id = f"{spec}:{first_group}"
            if first_id in nodes:
                edges.append({
                    "source": node_id, "target": first_id, "kind": "intra_spec",
                })
            order.insert(0, node_id)
            injected = True
            logger.info("Injected %s node '%s' at runtime", arch_name, node_id)

        # auto_post injection (e.g., Verifier after last group)
        offset = 1
        for arch_name, entry in ARCHETYPE_REGISTRY.items():
            if entry.injection != "auto_post":
                continue
            if not getattr(archetypes_config, arch_name, False):
                continue

            post_group = last_group + offset
            node_id = f"{spec}:{post_group}"
            if node_id in nodes:
                offset += 1
                continue  # already present

            instances_cfg = getattr(archetypes_config, "instances", None)
            instances = getattr(instances_cfg, arch_name, 1) if instances_cfg else 1

            nodes[node_id] = {
                "id": node_id,
                "spec_name": spec,
                "group_number": post_group,
                "title": f"{arch_name.capitalize()} Check",
                "optional": False,
                "status": "pending",
                "subtask_count": 0,
                "body": "",
                "archetype": arch_name,
                "instances": instances if isinstance(instances, int) else 1,
            }
            last_id = f"{spec}:{last_group}"
            if last_id in nodes:
                edges.append({
                    "source": last_id, "target": node_id, "kind": "intra_spec",
                })
            order.append(node_id)
            offset += 1
            injected = True
            logger.info("Injected %s node '%s' at runtime", arch_name, node_id)

    return injected


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


def _seed_node_states(nodes: dict) -> dict[str, str]:
    """Seed node states from plan.json node data.

    Honours statuses already set by the graph builder (e.g. "completed"
    from tasks.md ``[x]`` markers) instead of resetting everything to
    "pending".
    """
    node_states: dict[str, str] = {}
    for nid, node_data in nodes.items():
        status = "pending"
        if isinstance(node_data, dict):
            plan_status = node_data.get("status", "pending")
            if plan_status in ("completed", "skipped"):
                status = plan_status
        node_states[nid] = status
    return node_states


def _load_or_init_state(
    state_manager: StateManager,
    plan_hash: str,
    nodes: dict,
) -> ExecutionState:
    """Load existing state or initialize fresh state.

    If state exists and plan hash matches, reuse it (adding any new nodes).
    If state exists but plan hash differs, merge: carry forward
    ``completed``/``skipped`` statuses from the old state for nodes that
    still exist in the new plan, so that already-finished work is not
    re-executed. New nodes and previously failed/blocked nodes start fresh.
    If no prior state exists, seed entirely from plan.json.
    """
    existing = state_manager.load()

    if existing is not None:
        if existing.plan_hash != plan_hash:
            # Plan structure changed (e.g. new spec added).  Merge old
            # completed/skipped statuses into the new plan rather than
            # discarding them — tasks.md checkboxes may be stale.
            node_states = _seed_node_states(nodes)
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
                k: v
                for k, v in existing.blocked_reasons.items()
                if k in nodes
            }
            return existing

        # Hash matches — reuse existing state, add any new nodes.
        for nid in nodes:
            if nid not in existing.node_states:
                existing.node_states[nid] = "pending"
        return existing

    # No prior state — seed from plan.json.
    node_states = _seed_node_states(nodes)
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
        self._plan_nodes: dict = {}
        self._edges_list: list[dict] = []
        self._plan_data: dict = {}  # Full plan data for plan.json updates
        self._archetypes_config = archetypes_config
        self._planning_config = planning_config or PlanningConfig()
        self._sink = sink_dispatcher
        self._run_id: str = ""  # populated in run()

        # 30-REQ-7: Adaptive routing state
        _rc = routing_config or RoutingConfig()
        self._routing = _RoutingState(
            config=_rc,
            pipeline=assessment_pipeline,
            ladders={},
            assessments={},
            retries_before_escalation=self._resolve_retries_before_escalation(_rc),
        )

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
        self, routing_config: RoutingConfig,
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

    def _emit_audit(
        self,
        event_type: AuditEventType,
        *,
        node_id: str = "",
        session_id: str = "",
        severity: AuditSeverity | None = None,
        payload: dict | None = None,
    ) -> None:
        """Emit an audit event to the sink dispatcher (best-effort).

        Requirements: 40-REQ-9.1, 40-REQ-9.2, 40-REQ-9.3, 40-REQ-9.4,
                      40-REQ-9.5, 40-REQ-10.1, 40-REQ-10.2
        """
        if self._sink is None or not self._run_id:
            return
        try:
            event = AuditEvent(
                run_id=self._run_id,
                event_type=event_type,
                severity=severity or default_severity_for(event_type),
                node_id=node_id,
                session_id=session_id,
                payload=payload or {},
            )
            self._sink.emit_audit_event(event)
        except Exception:
            logger.debug(
                "Failed to emit orchestrator audit event %s",
                event_type,
                exc_info=True,
            )

    async def _assess_node(self, node_id: str) -> None:
        """Run complexity assessment for a node and create an escalation ladder.

        The assessment pipeline is called before the first dispatch of a node.
        On any failure, falls back to the archetype default tier (30-REQ-7.E1).

        When no assessment pipeline is configured, no ladder is created and
        the orchestrator falls back to legacy retry behaviour for backward
        compatibility.

        Requirements: 30-REQ-7.1, 30-REQ-7.E1
        """
        if node_id in self._routing.ladders:
            return  # Already assessed

        # Without an assessment pipeline, skip adaptive routing entirely
        # and rely on the legacy retry path in _process_session_result.
        if self._routing.pipeline is None:
            return

        from agent_fox.routing.escalation import EscalationLadder

        archetype = self._get_node_archetype(node_id)

        # Determine tier ceiling for this archetype
        try:
            entry = get_archetype(archetype)
            try:
                tier_ceiling = ModelTier(entry.default_model_tier)
            except ValueError:
                tier_ceiling = ModelTier.ADVANCED
        except Exception:
            tier_ceiling = ModelTier.ADVANCED

        # 30-REQ-7.1: Run assessment before session creation
        predicted_tier = tier_ceiling  # fallback
        try:
            # Parse node_id to get spec_name and task_group
            parts = node_id.rsplit(":", 1)
            spec_name = parts[0]
            task_group = int(parts[1]) if len(parts) > 1 else 1
            spec_dir = Path(".specs") / spec_name

            assessment = await self._routing.pipeline.assess(
                node_id=node_id,
                spec_name=spec_name,
                task_group=task_group,
                spec_dir=spec_dir,
                archetype=archetype,
                tier_ceiling=tier_ceiling,
            )
            predicted_tier = assessment.predicted_tier
            self._routing.assessments[node_id] = assessment

            logger.info(
                "Adaptive routing for %s: predicted_tier=%s confidence=%.2f "
                "method=%s ceiling=%s",
                node_id,
                predicted_tier,
                assessment.confidence,
                assessment.assessment_method,
                tier_ceiling,
            )
            # 40-REQ-10.2: Emit model.assessment audit event
            self._emit_audit(
                AuditEventType.MODEL_ASSESSMENT,
                node_id=node_id,
                payload={
                    "predicted_tier": predicted_tier.value,
                    "confidence": assessment.confidence,
                    "method": assessment.assessment_method,
                },
            )
        except Exception:
            # 30-REQ-7.E1: Fall back to archetype default tier
            logger.error(
                "Assessment pipeline failed for %s, falling back to "
                "archetype default tier %s",
                node_id,
                tier_ceiling,
                exc_info=True,
            )
            predicted_tier = tier_ceiling

        # Create escalation ladder
        ladder = EscalationLadder(
            starting_tier=predicted_tier,
            tier_ceiling=tier_ceiling,
            retries_before_escalation=self._routing.retries_before_escalation,
        )
        self._routing.ladders[node_id] = ladder

    def _record_node_outcome(
        self,
        node_id: str,
        state: ExecutionState,
        final_status: str,
    ) -> None:
        """Record execution outcome for a completed/failed node.

        Aggregates costs and tokens from all session records for this node
        and persists the outcome via the assessment pipeline.

        Requirements: 30-REQ-7.4, 30-REQ-3.1
        """
        if self._routing.pipeline is None:
            return
        assessment = self._routing.assessments.get(node_id)
        if assessment is None:
            return

        ladder = self._routing.ladders.get(node_id)

        # Aggregate metrics from all session records for this node
        node_records = [r for r in state.session_history if r.node_id == node_id]
        total_tokens = sum(r.input_tokens + r.output_tokens for r in node_records)
        total_cost = sum(r.cost for r in node_records)
        total_duration = sum(r.duration_ms for r in node_records)
        files_touched = set()
        for r in node_records:
            files_touched.update(r.files_touched)

        try:
            self._routing.pipeline.record_outcome(
                assessment=assessment,
                actual_tier=(
                    ladder.current_tier if ladder else assessment.predicted_tier
                ),
                total_tokens=total_tokens,
                total_cost=total_cost,
                duration_ms=total_duration,
                attempt_count=ladder.attempt_count if ladder else len(node_records),
                escalation_count=ladder.escalation_count if ladder else 0,
                outcome=final_status,
                files_touched_count=len(files_touched),
            )
        except Exception:
            logger.warning(
                "Failed to record outcome for %s",
                node_id,
                exc_info=True,
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
        # 40-REQ-2.1: Generate unique run ID at start of execute()
        self._run_id = generate_run_id()
        run_start_time = datetime.now(UTC)
        logger.debug("Audit run ID: %s", self._run_id)

        plan_data = _load_plan_data(self._plan_path)

        # Runtime archetype injection: ensure config-enabled archetypes
        # have nodes in the plan even if the plan was built before they
        # were enabled.
        if _ensure_archetype_nodes(plan_data, self._archetypes_config):
            try:
                self._plan_path.write_text(
                    json.dumps(plan_data, indent=2) + "\n",
                    encoding="utf-8",
                )
                logger.info("Persisted plan with injected archetype nodes")
            except OSError:
                logger.warning(
                    "Failed to persist plan after archetype injection",
                    exc_info=True,
                )

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

        # 40-REQ-9.1: Emit run.start audit event
        self._emit_audit(
            AuditEventType.RUN_START,
            payload={
                "plan_hash": plan_hash,
                "total_nodes": len(nodes),
                "parallel": self._is_parallel,
            },
        )

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
                    self._emit_audit(
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
                ready = self._graph_sync.ready_tasks(
                    duration_hints=duration_hints
                )

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
                render_summary()
            except Exception:
                logger.warning("Final memory summary render failed", exc_info=True)
            # 40-REQ-9.2: Emit run.complete at end of execute()
            run_duration_ms = int(
                (datetime.now(UTC) - run_start_time).total_seconds() * 1000
            )
            self._emit_audit(
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
                node_data = self._plan_nodes.get(node_id, {})
                spec_name = node_data.get("spec_name", "")
                archetype = node_data.get("archetype", "coder")
                tier = node_data.get("tier", "STANDARD")

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
                node_data = self._plan_nodes.get(node_id, {})
                spec_name = node_data.get("spec_name", "")
                task_group = node_data.get("task_group", 1)

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

            # 30-REQ-7.1: Run assessment before first dispatch
            await self._assess_node(node_id)

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

            node_archetype = self._get_node_archetype(node_id)
            node_instances = self._get_node_instances(node_id)

            # 30-REQ-7.2: Pass assessed tier from escalation ladder
            ladder = self._routing.ladders.get(node_id)
            assessed_tier = ladder.current_tier if ladder else None

            record = await self._serial_runner.execute(
                node_id,
                attempt,
                previous_error,
                archetype=node_archetype,
                instances=node_instances,
                assessed_tier=assessed_tier,
                run_id=self._run_id,
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
                # 30-REQ-7.4: Record outcome on success
                self._record_node_outcome(node_id, state, "completed")
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

                # 30-REQ-7.1: Assess before first dispatch
                await self._assess_node(node_id)

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
                node_archetype = self._get_node_archetype(node_id)
                node_instances = self._get_node_instances(node_id)

                # 30-REQ-7.2: Pass assessed tier from escalation ladder
                ladder = self._routing.ladders.get(node_id)
                assessed_tier = ladder.current_tier if ladder else None

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
                    # 30-REQ-7.4: Record outcome on success
                    self._record_node_outcome(record.node_id, state, "completed")
                    self._run_sync_barrier_if_needed(state)

            # Re-evaluate ready tasks and fill empty pool slots
            if not self._signal.interrupted:
                new_ready = graph_sync.ready_tasks(
                    duration_hints=self._compute_duration_hints()
                )
                await _fill_pool(new_ready)

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
            prev_status = self._graph_sync.node_states.get(node_id, "in_progress")
            self._graph_sync.mark_completed(node_id)
            # 40-REQ-9.4: Emit task.status_change on completion
            self._emit_audit(
                AuditEventType.TASK_STATUS_CHANGE,
                node_id=node_id,
                payload={
                    "from_status": prev_status,
                    "to_status": "completed",
                    "reason": "session completed successfully",
                },
            )
            error_tracker.pop(node_id, None)
            # 18-REQ-5.4: Emit task completion event
            if self._task_callback is not None:
                duration_s = (record.duration_ms or 0) / 1000
                self._task_callback(
                    TaskEvent(
                        node_id=node_id,
                        status="completed",
                        duration_s=duration_s,
                    )
                )
        else:
            error_tracker[node_id] = record.error_message

            # 26-REQ-9.3: Retry-predecessor for archetypes with the flag
            node_archetype = self._get_node_archetype(node_id)
            archetype_entry = get_archetype(node_archetype)

            # 30-REQ-7.3: Use escalation ladder for retry/escalation decisions
            ladder = self._routing.ladders.get(node_id)

            if ladder is not None:
                # Record failure on the escalation ladder
                ladder.record_failure()

                if archetype_entry.retry_predecessor and ladder.should_retry():
                    # Find predecessor and reset it instead of the failed node
                    predecessors = self._get_predecessors(node_id)
                    if predecessors:
                        pred_id = predecessors[0]
                        logger.info(
                            "Retry-predecessor: resetting %s to pending due to "
                            "%s failure (attempt %d)",
                            pred_id,
                            node_id,
                            attempt,
                        )
                        self._graph_sync.node_states[pred_id] = "pending"
                        error_tracker[pred_id] = record.error_message
                        self._graph_sync.node_states[node_id] = "pending"
                        self._state_manager.save(state)
                        return

                if ladder.is_exhausted:
                    # 30-REQ-2.3: All retries and escalation exhausted
                    # 30-REQ-7.4: Record outcome on final failure
                    self._record_node_outcome(node_id, state, "failed")

                    if self._task_callback is not None:
                        duration_s = (record.duration_ms or 0) / 1000
                        self._task_callback(
                            TaskEvent(
                                node_id=node_id,
                                status="failed",
                                duration_s=duration_s,
                                error_message=record.error_message,
                            )
                        )
                    self._block_task(
                        node_id,
                        state,
                        f"Retries exhausted for {node_id}: {record.error_message}",
                    )
                else:
                    # 30-REQ-2.1/2.2: Retry at same tier or escalate
                    if ladder.escalation_count > 0:
                        prev_tier = record.model or "unknown"
                        logger.warning(
                            "Escalating %s from %s to %s",
                            node_id,
                            prev_tier,
                            ladder.current_tier,
                        )
                        # 40-REQ-10.1: Emit model.escalation audit event
                        self._emit_audit(
                            AuditEventType.MODEL_ESCALATION,
                            node_id=node_id,
                            payload={
                                "from_tier": prev_tier,
                                "to_tier": ladder.current_tier.value,
                                "reason": (
                                    f"retry limit at tier exhausted "
                                    f"for {node_id}"
                                ),
                            },
                        )
                    # 40-REQ-9.4: Emit session.retry on pending reset
                    self._emit_audit(
                        AuditEventType.SESSION_RETRY,
                        node_id=node_id,
                        payload={
                            "attempt": attempt,
                            "reason": record.error_message or "retrying after failure",
                        },
                    )
                    self._graph_sync.node_states[node_id] = "pending"
            else:
                # Fallback: no ladder (backward compat) — use original retry logic
                if (
                    archetype_entry.retry_predecessor
                    and attempt < self._config.max_retries + 1
                ):
                    predecessors = self._get_predecessors(node_id)
                    if predecessors:
                        pred_id = predecessors[0]
                        logger.info(
                            "Retry-predecessor: resetting %s to pending due to "
                            "%s failure (attempt %d)",
                            pred_id,
                            node_id,
                            attempt,
                        )
                        self._graph_sync.node_states[pred_id] = "pending"
                        error_tracker[pred_id] = record.error_message
                        self._graph_sync.node_states[node_id] = "pending"
                        self._state_manager.save(state)
                        return

                if attempt >= self._config.max_retries + 1:
                    # 18-REQ-5.4: Emit task failure event
                    if self._task_callback is not None:
                        duration_s = (record.duration_ms or 0) / 1000
                        self._task_callback(
                            TaskEvent(
                                node_id=node_id,
                                status="failed",
                                duration_s=duration_s,
                                error_message=record.error_message,
                            )
                        )
                    self._block_task(
                        node_id,
                        state,
                        f"Retries exhausted for {node_id}: {record.error_message}",
                    )
                else:
                    # 40-REQ-9.4: Emit session.retry on pending reset (fallback path)
                    self._emit_audit(
                        AuditEventType.SESSION_RETRY,
                        node_id=node_id,
                        payload={
                            "attempt": attempt,
                            "reason": record.error_message or "retrying after failure",
                        },
                    )
                    self._graph_sync.node_states[node_id] = "pending"

        self._state_manager.save(state)

    def _get_node_archetype(self, node_id: str) -> str:
        """Get the archetype name for a node from plan data."""
        node_data = self._plan_nodes.get(node_id, {})
        if isinstance(node_data, dict):
            return node_data.get("archetype", "coder")
        return "coder"

    def _get_node_instances(self, node_id: str) -> int:
        """Get the instance count for a node from plan data."""
        node_data = self._plan_nodes.get(node_id, {})
        if isinstance(node_data, dict):
            return node_data.get("instances", 1)
        return 1

    def _get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs for a given node."""
        if self._graph_sync is None:
            return []
        return self._graph_sync.predecessors(node_id)

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

        # 40-REQ-9.5: Emit sync.barrier audit event
        completed_nodes = [
            nid for nid, s in state.node_states.items() if s == "completed"
        ]
        pending_nodes = [
            nid for nid, s in state.node_states.items()
            if s in ("pending", "in_progress")
        ]
        self._emit_audit(
            AuditEventType.SYNC_BARRIER,
            payload={
                "completed_nodes": completed_nodes,
                "pending_nodes": pending_nodes,
            },
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

        # 12-REQ-4.1, 12-REQ-4.2: Run barrier callback (knowledge ingestion)
        if self._barrier_callback is not None:
            try:
                self._barrier_callback()
            except Exception:
                logger.warning("Barrier callback failed", exc_info=True)

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
                    "archetype": node.archetype,
                    "instances": node.instances,
                }
                state.node_states[nid] = "pending"

        # 32-REQ-4.1: Inject archetype nodes for hot-loaded specs
        plan_data = {
            "nodes": self._plan_nodes,
            "edges": self._edges_list,
            "order": [],
        }
        _ensure_archetype_nodes(plan_data, self._archetypes_config)
        # Sync any newly injected archetype nodes into state
        for nid in self._plan_nodes:
            if nid not in state.node_states:
                state.node_states[nid] = "pending"

        # Rebuild edges and GraphSync with new nodes/edges
        self._edges_list = [
            {"source": e.source, "target": e.target, "kind": e.kind}
            for e in updated_graph.edges
        ]
        # Include any edges added by archetype injection
        existing_edge_set = {
            (e["source"], e["target"]) for e in self._edges_list
        }
        for e in plan_data.get("edges", []):
            key = (e["source"], e["target"])
            if key not in existing_edge_set:
                self._edges_list.append(e)
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
            state.blocked_reasons[node_id] = reason
            # 18-REQ-5.4: Emit blocked event
            if self._task_callback is not None:
                self._task_callback(
                    TaskEvent(
                        node_id=node_id,
                        status="blocked",
                        duration_s=0,
                        error_message=reason,
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
                        )
                    )
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
