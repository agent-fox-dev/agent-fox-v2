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
from collections.abc import Callable
from typing import Any

from agent_fox.core.models import ModelTier
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    default_severity_for,
)
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.session.archetypes import get_archetype
from agent_fox.ui.events import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


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
        routing_assessments: dict[str, Any],
        routing_pipeline: Any | None,
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
    ) -> None:
        self._graph_sync = graph_sync
        self._state_manager = state_manager
        self._routing_ladders = routing_ladders
        self._routing_assessments = routing_assessments
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

    def _emit_audit(
        self,
        event_type: AuditEventType,
        *,
        node_id: str = "",
        session_id: str = "",
        severity: AuditSeverity | None = None,
        payload: dict | None = None,
    ) -> None:
        """Emit an audit event to the sink dispatcher (best-effort)."""
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
                "Failed to emit audit event %s",
                event_type,
                exc_info=True,
            )

    def _get_node_archetype(self, node_id: str) -> str:
        """Get the archetype name for a node from the task graph."""
        if self._graph is not None and node_id in self._graph.nodes:
            return self._graph.nodes[node_id].archetype
        return "coder"

    def _get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs for a given node."""
        return self._graph_sync.predecessors(node_id)

    def record_node_outcome(
        self,
        node_id: str,
        state: ExecutionState,
        final_status: str,
    ) -> None:
        """Record execution outcome for a completed/failed node.

        Requirements: 30-REQ-7.4, 30-REQ-3.1
        """
        if self._routing_pipeline is None:
            return
        assessment = self._routing_assessments.get(node_id)
        if assessment is None:
            return

        ladder = self._routing_ladders.get(node_id)

        node_records = [r for r in state.session_history if r.node_id == node_id]
        total_tokens = sum(r.input_tokens + r.output_tokens for r in node_records)
        total_cost = sum(r.cost for r in node_records)
        total_duration = sum(r.duration_ms for r in node_records)
        files_touched = set()
        for r in node_records:
            files_touched.update(r.files_touched)

        try:
            self._routing_pipeline.record_outcome(
                assessment=assessment,
                actual_tier=(
                    ladder.current_tier if ladder else assessment.predicted_tier
                ),
                total_tokens=total_tokens,
                total_cost=total_cost,
                duration_ms=total_duration,
                attempt_count=(ladder.attempt_count if ladder else len(node_records)),
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

    def check_skeptic_blocking(
        self,
        record: SessionRecord,
        state: ExecutionState,
    ) -> bool:
        """Check if review findings should block downstream tasks."""
        from agent_fox.engine.blocking import evaluate_review_blocking

        decision = evaluate_review_blocking(
            record,
            self._archetypes_config,
            self._knowledge_db_conn,
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

        if record.status == "completed":
            self._handle_success(record, state, error_tracker)
        else:
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

        # Skeptic/oracle blocking
        if self.check_skeptic_blocking(record, state):
            self._check_block_budget(state)

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
            if self._try_retry_predecessor(
                node_id, record, attempt, state, error_tracker
            ):
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
            self.record_node_outcome(pred_id, state, "failed")
            self._block_task(
                pred_id,
                state,
                f"Predecessor {pred_id} exhausted all tiers after "
                f"reviewer {node_id} failures",
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
        # 30-REQ-2.3, 30-REQ-7.4: All retries exhausted
        self.record_node_outcome(node_id, state, "failed")

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
            self._emit_audit(
                AuditEventType.MODEL_ESCALATION,
                node_id=node_id,
                payload={
                    "from_tier": prev_tier,
                    "to_tier": ladder.current_tier.value,
                    "reason": (f"retry limit at tier exhausted for {node_id}"),
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
