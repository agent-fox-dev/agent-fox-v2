"""Session result processing: retry decisions, escalation, blocking.

Extracted from engine.py to reduce the Orchestrator class size. Handles
the outcome of each completed session: marking success, deciding retries,
escalating model tiers, cascade-blocking on exhaustion, and emitting
audit events.

Requirements: 30-REQ-2.*, 30-REQ-7.3, 30-REQ-7.4, 26-REQ-9.3,
              40-REQ-9.4, 40-REQ-10.1, 18-REQ-5.4,
              58-REQ-1.*, 58-REQ-2.*
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_fox.core.config import ArchetypesConfig
from agent_fox.core.models import ModelTier
from agent_fox.core.node_id import parse_node_id
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.session.archetypes import get_archetype
from agent_fox.ui.progress import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Blocking logic (inlined from former engine/blocking.py)
# Requirements: 26-REQ-9.3, 30-REQ-2.3
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockDecision:
    """Result of evaluating whether a review session should block a task."""

    should_block: bool
    coder_node_id: str = ""
    reason: str = ""


def _format_block_reason(
    archetype: str,
    findings: list[Any],
    threshold: int,
    spec_name: str,
    task_group: str,
) -> str:
    """Format an enriched blocking reason string with finding IDs and descriptions.

    Includes the count of critical findings, up to 3 finding IDs as `F-<8hex>`
    short prefixes, truncated descriptions (max 60 chars each), and "and N more"
    when there are more than 3 critical findings.

    Requirements: 84-REQ-3.1, 84-REQ-3.E1
    """
    critical_findings = [f for f in findings if f.severity.lower() == "critical"]
    n = len(critical_findings)

    header = (
        f"{archetype.capitalize()} found {n} critical finding(s) (threshold: {threshold}) for {spec_name}:{task_group}"
    )

    if n == 0:
        return header

    shown = critical_findings[:3]
    parts = []
    for finding in shown:
        # Build F-<8hex> short ID from the UUID
        raw_id = finding.id.replace("-", "")[:8]
        short_id = f"F-{raw_id}"
        desc = finding.description[:60]
        if len(finding.description) > 60:
            desc += "…"
        parts.append(f"{short_id}: {desc}")

    detail = ", ".join(parts)
    if n > 3:
        detail += f", and {n - 3} more"

    return f"{header} — {detail}"


def evaluate_review_blocking(
    record: SessionRecord,
    archetypes_config: ArchetypesConfig | None,
    knowledge_db_conn: Any | None,
    *,
    sink: Any | None = None,
    run_id: str = "",
) -> BlockDecision:
    """Evaluate whether a skeptic/oracle session should block its downstream task.

    Queries persisted review findings from DuckDB, counts critical findings,
    applies the configured (or learned) block threshold.

    Critical findings with category='security' always trigger blocking,
    regardless of the numeric threshold, because security vulnerabilities
    must be remediated before downstream work can proceed.

    Returns a BlockDecision indicating whether blocking should occur and why.
    """
    archetype = record.archetype
    if archetype not in ("skeptic", "oracle"):
        return BlockDecision(should_block=False)

    if knowledge_db_conn is None:
        return BlockDecision(should_block=False)

    parsed = parse_node_id(record.node_id)
    spec_name = parsed.spec_name
    task_group = str(parsed.group_number) if parsed.group_number else "1"
    coder_node_id = f"{spec_name}:{task_group}"

    try:
        from agent_fox.knowledge.review_store import query_findings_by_session

        session_id = f"{record.node_id}:{record.attempt}"
        findings = query_findings_by_session(knowledge_db_conn, session_id)

        critical_count = sum(1 for f in findings if f.severity.lower() == "critical")

        if critical_count == 0:
            return BlockDecision(should_block=False)

        # Security bypass: critical findings with category='security' always block,
        # regardless of the numeric threshold.
        security_critical = [
            f for f in findings if f.severity.lower() == "critical" and getattr(f, "category", None) == "security"
        ]
        if security_critical:
            shown = security_critical[:3]
            detail = ", ".join(
                f"F-{f.id.replace('-', '')[:8]}: {f.description[:60]}" + ("…" if len(f.description) > 60 else "")
                for f in shown
            )
            reason = (
                f"[SECURITY] {archetype.capitalize()} found {len(security_critical)} critical "
                f"security finding(s) for {spec_name}:{task_group} — {detail}"
            )
            logger.warning("SECURITY blocking %s: %s", coder_node_id, reason)
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.SECURITY_FINDING_BLOCKED,
                node_id=record.node_id,
                session_id=session_id,
                archetype=archetype,
                payload={
                    "spec_name": spec_name,
                    "task_group": task_group,
                    "security_critical_count": len(security_critical),
                    "finding_ids": [str(f.id) for f in security_critical],
                },
            )
            return BlockDecision(
                should_block=True,
                coder_node_id=coder_node_id,
                reason=reason,
            )

        # Resolve threshold
        if archetype == "skeptic" and archetypes_config is not None:
            configured_threshold = archetypes_config.skeptic_config.block_threshold
        elif archetype == "oracle" and archetypes_config is not None:
            oracle_threshold = archetypes_config.oracle_settings.block_threshold
            if oracle_threshold is None:
                # Oracle is advisory-only when block_threshold is None
                return BlockDecision(should_block=False)
            configured_threshold = oracle_threshold
        else:
            # No config available, use conservative default
            configured_threshold = 3

        from agent_fox.session.convergence import resolve_block_threshold

        effective_threshold = resolve_block_threshold(
            configured_threshold,
            archetype,
            knowledge_db_conn,
            learn_thresholds=False,
        )

        blocked = critical_count > effective_threshold

        # Record the blocking decision for threshold learning
        try:
            from agent_fox.knowledge.blocking_history import (
                BlockingDecision as HistoryDecision,
            )
            from agent_fox.knowledge.blocking_history import (
                record_blocking_decision,
            )

            decision = HistoryDecision(
                spec_name=spec_name,
                archetype=archetype,
                critical_count=critical_count,
                threshold=effective_threshold,
                blocked=blocked,
                outcome="",  # outcome assessed later
            )
            record_blocking_decision(knowledge_db_conn, decision)
        except Exception:
            logger.debug(
                "Failed to record blocking decision for %s",
                record.node_id,
                exc_info=True,
            )

        if blocked:
            reason = _format_block_reason(
                archetype,
                findings,
                effective_threshold,
                spec_name,
                task_group,
            )
            logger.warning(
                "%s blocking %s: %s",
                archetype.capitalize(),
                coder_node_id,
                reason,
            )
            return BlockDecision(
                should_block=True,
                coder_node_id=coder_node_id,
                reason=reason,
            )

    except Exception:
        logger.warning(
            "Failed to evaluate %s blocking for %s",
            archetype,
            record.node_id,
            exc_info=True,
        )

    return BlockDecision(should_block=False)


class SessionResultHandler:
    """Processes session outcomes: success, retry, escalation, blocking.

    Extracted from Orchestrator to isolate the complex retry/escalation
    decision tree from the dispatch loop.
    """

    def __init__(
        self,
        *,
        graph_sync: GraphSync,
        state_manager: StateManager,
        routing_ladders: dict[str, Any],
        routing_assessments: dict[str, Any] | None = None,
        routing_pipeline: Any | None = None,
        retries_before_escalation: int,
        max_retries: int,
        task_callback: TaskCallback | None,
        sink: SinkDispatcher | None,
        run_id: str,
        graph: Any | None,
        archetypes_config: Any | None,
        knowledge_db_conn: Any | None,
        block_task_fn: Callable[[str, ExecutionState, str], None],
        check_block_budget_fn: Callable[[ExecutionState], bool],
        max_timeout_retries: int = 2,
        timeout_multiplier: float = 1.5,
        timeout_ceiling_factor: float = 2.0,
        original_session_timeout: int = 30,
    ) -> None:
        self._graph_sync = graph_sync
        self._state_manager = state_manager
        self._routing_ladders = routing_ladders
        self._routing_assessments: dict[str, Any] = routing_assessments or {}
        self._routing_pipeline = routing_pipeline
        self._retries_before_escalation = retries_before_escalation
        self._max_retries = max_retries
        self._task_callback = task_callback
        self._sink = sink
        self._run_id = run_id
        self._graph = graph
        self._archetypes_config = archetypes_config
        self._knowledge_db_conn = knowledge_db_conn
        self._block_task = block_task_fn
        self._check_block_budget = check_block_budget_fn

        # Timeout-aware escalation state (75-REQ-2.1)
        self._timeout_retries: dict[str, int] = {}
        self._node_max_turns: dict[str, int | None] = {}
        self._node_timeout: dict[str, int] = {}
        self._original_node_timeout: dict[str, int] = {}  # per-node original timeouts
        self._max_timeout_retries: int = max_timeout_retries
        self._timeout_multiplier: float = timeout_multiplier
        self._timeout_ceiling_factor: float = timeout_ceiling_factor
        self._original_session_timeout: int = original_session_timeout

    def _get_node_archetype(self, node_id: str) -> str:
        """Get the archetype name for a node from the task graph."""
        if self._graph is not None and node_id in self._graph.nodes:
            return self._graph.nodes[node_id].archetype
        return "coder"

    def _get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs for a given node."""
        return self._graph_sync.predecessors(node_id)

    def check_skeptic_blocking(
        self,
        record: SessionRecord,
        state: ExecutionState,
    ) -> bool:
        """Check if review findings should block downstream tasks."""
        decision = evaluate_review_blocking(
            record,
            self._archetypes_config,
            self._knowledge_db_conn,
            sink=self._sink,
            run_id=self._run_id,
        )
        if decision.should_block:
            self._block_task(decision.coder_node_id, state, decision.reason)
            return True
        return False

    def process(
        self,
        record: SessionRecord,
        attempt: int,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Process a completed session record and persist state."""
        self._state_manager.record_session(state, record)

        # Ensure timeout retry counter is initialised (even for non-timeout
        # events), so callers can use .get(node_id, -1) as a sentinel for
        # "never seen any event for this node" while still distinguishing
        # "zero timeout retries" from "counter not initialised".
        node_id = record.node_id
        if node_id not in self._timeout_retries:
            self._timeout_retries[node_id] = 0

        if record.status == "completed":
            self._handle_success(record, state, error_tracker)
        elif record.status == "timeout":
            # 75-REQ-1.1, 75-REQ-1.3: Route timeout to dedicated handler
            self._handle_timeout(record, attempt, state, attempt_tracker, error_tracker)
        else:
            # 75-REQ-1.2: Non-timeout failures use the escalation ladder
            self._handle_failure(record, attempt, state, attempt_tracker, error_tracker)

        self._state_manager.save(state)

    def _handle_success(
        self,
        record: SessionRecord,
        state: ExecutionState,
        error_tracker: dict[str, str | None],
    ) -> None:
        """Handle a successful session completion."""
        node_id = record.node_id
        prev_status = self._graph_sync.node_states.get(node_id, "in_progress")
        self._graph_sync.mark_completed(node_id)

        # 40-REQ-9.4: Emit task.status_change on completion
        emit_audit_event(
            self._sink,
            self._run_id,
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
                    archetype=self._get_node_archetype(node_id),
                )
            )

        # Skeptic/oracle blocking
        if self.check_skeptic_blocking(record, state):
            self._check_block_budget(state)

    def _get_original_node_timeout(self, node_id: str) -> int:
        """Return the original session timeout for a node before any extension.

        On first call for a node, captures the current value (from per-node
        override dict or the global original_session_timeout). Subsequent
        calls return the stored original so the ceiling stays fixed.

        Requirements: 75-REQ-3.3, 75-REQ-3.E1
        """
        if node_id not in self._original_node_timeout:
            self._original_node_timeout[node_id] = self._node_timeout.get(node_id, self._original_session_timeout)
        return self._original_node_timeout[node_id]

    def _extend_node_params(self, node_id: str) -> None:
        """Increase max_turns and session_timeout for the node by the multiplier.

        Applies ceiling clamping to session_timeout. Skips max_turns when it
        is None (unlimited). Changes are stored in per-node override dicts.

        Requirements: 75-REQ-3.1, 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.4,
                      75-REQ-3.5, 75-REQ-3.E1
        """
        multiplier = self._timeout_multiplier
        ceiling_factor = self._timeout_ceiling_factor

        # Get original timeout (stored on first extension for stable ceiling)
        original_timeout = self._get_original_node_timeout(node_id)

        # Extend session_timeout, clamped to ceiling (75-REQ-3.2, 75-REQ-3.3)
        current_timeout = self._node_timeout.get(node_id, original_timeout)
        ceiling_timeout = math.ceil(original_timeout * ceiling_factor)
        new_timeout = min(
            math.ceil(current_timeout * multiplier),
            ceiling_timeout,
        )
        self._node_timeout[node_id] = new_timeout

        # Extend max_turns if finite (75-REQ-3.1, 75-REQ-3.4)
        if node_id in self._node_max_turns:
            current_turns = self._node_max_turns[node_id]
            if current_turns is not None:
                self._node_max_turns[node_id] = math.ceil(current_turns * multiplier)

    def _handle_timeout(
        self,
        record: SessionRecord,
        attempt: int,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Handle a timeout failure: extend params and retry, or fall through.

        When timeout retries are available, increments the per-node timeout
        counter, extends session_timeout and max_turns, resets the node to
        pending, and emits a SESSION_TIMEOUT_RETRY audit event.

        When retries are exhausted, logs a warning and falls through to the
        normal escalation ladder via _handle_failure().

        Requirements: 75-REQ-1.1, 75-REQ-2.2, 75-REQ-2.3, 75-REQ-2.4,
                      75-REQ-5.1, 75-REQ-5.2, 75-REQ-5.3
        """
        node_id = record.node_id
        current_retries = self._timeout_retries.get(node_id, 0)

        if current_retries >= self._max_timeout_retries:
            # Exhausted timeout retries — fall through to escalation (75-REQ-2.4)
            logger.warning(
                "Timeout retries exhausted for %s (%d/%d), falling through to escalation ladder",
                node_id,
                current_retries,
                self._max_timeout_retries,
            )
            self._handle_failure(record, attempt, state, attempt_tracker, error_tracker)
            return

        # Capture original values before extending for audit payload (75-REQ-5.3)
        original_timeout = self._get_original_node_timeout(node_id)
        original_max_turns = self._node_max_turns.get(node_id)

        # Increment counter and extend parameters (75-REQ-2.2, 75-REQ-3.1, 75-REQ-3.2)
        self._timeout_retries[node_id] = current_retries + 1
        self._extend_node_params(node_id)

        extended_timeout = self._node_timeout[node_id]
        extended_max_turns = self._node_max_turns.get(node_id)

        # Reset to pending for retry at same tier (75-REQ-2.3)
        self._graph_sync.node_states[node_id] = "pending"

        # Emit SESSION_TIMEOUT_RETRY audit event (75-REQ-5.1, 75-REQ-5.3)
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.SESSION_TIMEOUT_RETRY,
            node_id=node_id,
            payload={
                "timeout_retry_count": current_retries + 1,
                "max_timeout_retries": self._max_timeout_retries,
                "original_max_turns": original_max_turns,
                "extended_max_turns": extended_max_turns,
                "original_timeout": original_timeout,
                "extended_timeout": extended_timeout,
            },
        )

    def _handle_failure(
        self,
        record: SessionRecord,
        attempt: int,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
        error_tracker: dict[str, str | None],
    ) -> None:
        """Handle a failed session: retry, escalate, or block."""
        node_id = record.node_id
        error_tracker[node_id] = record.error_message

        # Transport errors are retried without consuming an escalation attempt.
        # The ClaudeBackend already retried internally; this path is reached only
        # when all transport retries were exhausted.  Reset the node to pending
        # so the orchestrator re-dispatches it without touching the ladder.
        if getattr(record, "is_transport_error", False):
            logger.warning(
                "Transport error for %s (not consuming escalation retry): %s",
                node_id,
                record.error_message,
            )
            self._graph_sync.node_states[node_id] = "pending"
            return

        # 26-REQ-9.3: Retry-predecessor for archetypes with the flag
        node_archetype = self._get_node_archetype(node_id)
        archetype_entry = get_archetype(node_archetype)

        # 30-REQ-7.3: Use escalation ladder for retry/escalation decisions
        ladder = self._routing_ladders.get(node_id)

        if ladder is not None:
            ladder.record_failure()
            can_retry = ladder.should_retry()
            exhausted = ladder.is_exhausted
        else:
            # Fallback: no ladder (backward compat)
            max_attempts = self._max_retries + 1
            can_retry = attempt < max_attempts
            exhausted = attempt >= max_attempts

        # Retry-predecessor: reset predecessor instead of failed node
        if archetype_entry.retry_predecessor and can_retry:
            if self._try_retry_predecessor(node_id, record, attempt, state, error_tracker):
                return

        if exhausted:
            self._handle_exhausted(node_id, record, state, attempt_tracker)
        else:
            self._handle_retry(node_id, record, attempt, ladder)

    def _try_retry_predecessor(
        self,
        node_id: str,
        record: SessionRecord,
        attempt: int,
        state: ExecutionState,
        error_tracker: dict[str, str | None],
    ) -> bool:
        """Attempt retry-predecessor logic. Returns True if handled."""
        predecessors = self._get_predecessors(node_id)
        if not predecessors:
            return False

        pred_id = predecessors[0]

        # 58-REQ-1.1: Record failure on predecessor's escalation ladder
        from agent_fox.routing.escalation import EscalationLadder

        pred_ladder = self._routing_ladders.get(pred_id)
        if pred_ladder is None:
            # 58-REQ-1.E1: Create ladder defensively
            pred_archetype = self._get_node_archetype(pred_id)
            pred_entry = get_archetype(pred_archetype)
            pred_starting = ModelTier(pred_entry.default_model_tier)
            pred_ladder = EscalationLadder(
                starting_tier=pred_starting,
                tier_ceiling=ModelTier.ADVANCED,
                retries_before_escalation=self._retries_before_escalation,
            )
            self._routing_ladders[pred_id] = pred_ladder

        pred_ladder.record_failure()

        # 58-REQ-2.1: Block predecessor if ladder exhausted
        if pred_ladder.is_exhausted:
            self._block_task(
                pred_id,
                state,
                f"Predecessor {pred_id} exhausted all tiers after reviewer {node_id} failures",
            )
            self._check_block_budget(state)
            self._state_manager.save(state)
            return True

        logger.info(
            "Retry-predecessor: resetting %s to pending due to %s failure (attempt %d)",
            pred_id,
            node_id,
            attempt,
        )
        # 59-REQ-8.1: Emit disagreement event
        if self._task_callback is not None:
            self._task_callback(
                TaskEvent(
                    node_id=node_id,
                    status="disagreed",
                    duration_s=0,
                    archetype=self._get_node_archetype(node_id),
                    predecessor_node=pred_id,
                )
            )
        # 58-REQ-1.2: Reset predecessor to pending
        self._graph_sync.node_states[pred_id] = "pending"
        error_tracker[pred_id] = record.error_message
        self._graph_sync.node_states[node_id] = "pending"
        self._state_manager.save(state)
        return True

    def _handle_exhausted(
        self,
        node_id: str,
        record: SessionRecord,
        state: ExecutionState,
        attempt_tracker: dict[str, int],
    ) -> None:
        """Handle a node that has exhausted all retries."""
        # 18-REQ-5.4: Emit task failure event
        if self._task_callback is not None:
            duration_s = (record.duration_ms or 0) / 1000
            self._task_callback(
                TaskEvent(
                    node_id=node_id,
                    status="failed",
                    duration_s=duration_s,
                    error_message=record.error_message,
                    archetype=self._get_node_archetype(node_id),
                )
            )
        self._block_task(
            node_id,
            state,
            f"Retries exhausted for {node_id}: {record.error_message}",
        )
        self._check_block_budget(state)

    def _handle_retry(
        self,
        node_id: str,
        record: SessionRecord,
        attempt: int,
        ladder: Any | None,
    ) -> None:
        """Handle a retry (possibly with tier escalation)."""
        # 30-REQ-2.1/2.2: Retry at same tier or escalate
        if ladder is not None and ladder.escalation_count > 0:
            prev_tier = record.model or "unknown"
            logger.warning(
                "Escalating %s from %s to %s",
                node_id,
                prev_tier,
                ladder.current_tier,
            )
            # 40-REQ-10.1: Emit model.escalation audit event
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.MODEL_ESCALATION,
                node_id=node_id,
                payload={
                    "from_tier": prev_tier,
                    "to_tier": ladder.current_tier.value,
                    "reason": (f"retry limit at tier exhausted for {node_id}"),
                },
            )
        # 40-REQ-9.4: Emit session.retry on pending reset
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.SESSION_RETRY,
            node_id=node_id,
            payload={
                "attempt": attempt,
                "reason": record.error_message or "retrying after failure",
            },
        )
        # 59-REQ-8.2, 59-REQ-8.3: Emit retry task event with escalation info
        if self._task_callback is not None:
            escalated_from: str | None = None
            escalated_to: str | None = None
            if ladder is not None and ladder.escalation_count > 0:
                escalated_from = record.model or "unknown"
                escalated_to = ladder.current_tier.value
            self._task_callback(
                TaskEvent(
                    node_id=node_id,
                    status="retry",
                    duration_s=0,
                    archetype=self._get_node_archetype(node_id),
                    attempt=attempt + 1,
                    escalated_from=escalated_from,
                    escalated_to=escalated_to,
                )
            )
        self._graph_sync.node_states[node_id] = "pending"
