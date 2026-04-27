"""State management: loading, initialization, persistence, node status tracking.

Encapsulates all execution state operations previously spread across
module-level functions and Orchestrator methods in engine.py.

Requirements: 04-REQ-4.1, 04-REQ-7.E1, 105-REQ-2.1, 105-REQ-2.4,
              105-REQ-5.3
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.graph_sync import GraphSync, _is_auto_pre
from agent_fox.engine.session_lifecycle import _REVIEW_ARCHETYPES
from agent_fox.engine.state import (
    ExecutionState,
    RunStatus,
    SessionRecord,
    load_state_from_db,
)
from agent_fox.graph.types import NodeStatus, TaskGraph
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.ui.progress import TaskCallback, TaskEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure functions (no state required)
# ---------------------------------------------------------------------------


def build_edges_dict(graph: TaskGraph) -> dict[str, list[str]]:
    """Build adjacency list from a TaskGraph.

    Returns dict mapping each node to its dependencies (predecessors).
    """
    edges_dict: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges:
        if edge.target in edges_dict:
            edges_dict[edge.target].append(edge.source)
    return edges_dict


def seed_node_states(graph: TaskGraph) -> dict[str, str]:
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


def load_or_init_state(
    conn: Any,
    plan_hash: str,
    graph: TaskGraph,
) -> ExecutionState:
    """Load existing state from DB or initialize fresh state.

    If state exists and plan hash matches, reuse it (adding any new nodes).
    If state exists but plan hash differs, merge: carry forward
    ``completed``/``skipped`` statuses from the old state for nodes that
    still exist in the new plan, so that already-finished work is not
    re-executed. New nodes and previously failed/blocked nodes start fresh.
    If no prior state exists, seed entirely from the TaskGraph.

    Requirements: 105-REQ-5.3 (DB-only state loading, no JSONL)
    """
    existing = load_state_from_db(conn) if conn is not None else None

    if existing is not None:
        if existing.plan_hash != plan_hash:
            node_states = seed_node_states(graph)
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
                if k in graph.nodes and node_states.get(k) != "pending"
            }
            return existing

        for nid in graph.nodes:
            if nid not in existing.node_states:
                existing.node_states[nid] = "pending"
        return existing

    node_states = seed_node_states(graph)
    now = datetime.now(UTC).isoformat()
    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states,
        started_at=now,
        updated_at=now,
    )


def reset_in_progress_tasks(
    state: ExecutionState,
    conn: Any,
) -> None:
    """Reset in_progress tasks to pending on resume (04-REQ-7.E1).

    Requirements: 105-REQ-2.E1 (DB-based reset)
    """
    any_reset = False
    for node_id, status in state.node_states.items():
        if status == "in_progress":
            state.node_states[node_id] = "pending"
            any_reset = True
            logger.info(
                "Task %s was in_progress from prior run; resetting to pending.",
                node_id,
            )
    if any_reset and conn is not None:
        from agent_fox.engine.state import reset_in_progress_nodes

        reset_in_progress_nodes(conn)


def reset_blocked_tasks(
    state: ExecutionState,
    conn: Any,
) -> None:
    """Reset blocked tasks to pending on resume so they get fresh retries.

    Requirements: 105-REQ-5.3 (DB-only persistence)
    """
    reset_ids: list[str] = []
    for node_id, status in state.node_states.items():
        if status == "blocked":
            state.node_states[node_id] = "pending"
            state.blocked_reasons.pop(node_id, None)
            reset_ids.append(node_id)
            logger.info(
                "Task %s was blocked from prior run; resetting to pending.",
                node_id,
            )
    if reset_ids and conn is not None:
        from agent_fox.engine.state import persist_node_status

        for node_id in reset_ids:
            persist_node_status(conn, node_id, "pending")


def defer_ready_reviews(
    graph: TaskGraph,
    graph_sync: GraphSync,
    conn: Any = None,
) -> list[str]:
    """Mark non-auto_pre review nodes as deferred when deps are already completed.

    Returns list of node IDs that were deferred.
    """
    deferred: list[str] = []
    for nid, node in graph.nodes.items():
        if graph_sync.node_states.get(nid) != "pending":
            continue
        if _is_auto_pre(nid):
            continue
        if node.archetype not in _REVIEW_ARCHETYPES:
            continue
        preds = graph_sync.predecessors(nid)
        if preds and all(graph_sync.node_states.get(p) == "completed" for p in preds):
            graph_sync.node_states[nid] = "deferred"
            deferred.append(nid)
    if deferred and conn is not None:
        from agent_fox.engine.state import persist_node_status

        for nid in deferred:
            persist_node_status(conn, nid, "deferred")
    if deferred:
        logger.info(
            "Deferred %d review node(s) with already-completed deps: %s",
            len(deferred),
            ", ".join(deferred),
        )
    return deferred


def init_attempt_tracker(state: ExecutionState) -> dict[str, int]:
    """Initialize attempt counter from session history.

    Tasks whose current status is ``"pending"`` are excluded — they are
    either new or have been reset and should start fresh at attempt 0.
    """
    tracker: dict[str, int] = {}
    for record in state.session_history:
        if state.node_states.get(record.node_id) == "pending":
            continue
        current = tracker.get(record.node_id, 0)
        tracker[record.node_id] = max(current, record.attempt)
    return tracker


def init_error_tracker(state: ExecutionState) -> dict[str, str | None]:
    """Initialize error tracker from session history."""
    tracker: dict[str, str | None] = {}

    for record in state.session_history:
        if record.status == "failed" and record.error_message:
            tracker[record.node_id] = record.error_message

    history_by_node: dict[str, list[SessionRecord]] = defaultdict(list)
    for record in state.session_history:
        history_by_node[record.node_id].append(record)

    for node_id, status in state.node_states.items():
        if status == "pending" and node_id not in tracker:
            prior_attempts = history_by_node.get(node_id, [])
            if prior_attempts:
                last = prior_attempts[-1]
                if last.error_message:
                    tracker[node_id] = last.error_message

    return tracker


# ---------------------------------------------------------------------------
# StateManager — stateful collaborator
# ---------------------------------------------------------------------------


class StateManager:
    """Manages execution state: loading, initialization, persistence, node status tracking.

    Extracted from Orchestrator to isolate state concerns from orchestration
    control flow.
    """

    def __init__(
        self,
        knowledge_db_conn: Any | None,
        task_callback: TaskCallback | None,
        max_blocked_fraction: float | None,
    ) -> None:
        self._knowledge_db_conn = knowledge_db_conn
        self._task_callback = task_callback
        self._max_blocked_fraction = max_blocked_fraction

    def sync_plan_statuses(
        self,
        state: ExecutionState,
        graph: TaskGraph | None,
    ) -> None:
        """Write current node statuses back to DB.

        Updates each node's ``status`` field in the graph to match the
        execution state, then persists to DB.

        Requirements: 105-REQ-2.1, 105-REQ-2.4 (DB-only, no plan.json)
        """
        if graph is None or not state.node_states:
            return

        changed = False
        for nid, current_status in state.node_states.items():
            node = graph.nodes.get(nid)
            if node is not None and node.status.value != current_status:
                node.status = NodeStatus(current_status)
                changed = True

        if not changed:
            return

        if self._knowledge_db_conn is not None:
            try:
                from agent_fox.engine.state import persist_node_status as _persist

                for nid, current_status in state.node_states.items():
                    _persist(
                        self._knowledge_db_conn,
                        nid,
                        current_status,
                        blocked_reason=state.blocked_reasons.get(nid),
                    )
            except Exception:
                logger.debug("Failed to persist node statuses to DB", exc_info=True)

    def block_task(
        self,
        node_id: str,
        state: ExecutionState,
        reason: str,
        *,
        graph_sync: GraphSync | None = None,
        get_archetype_fn: Any = None,
        sink: Any | None = None,
        run_id: str = "",
    ) -> None:
        """Mark a task as blocked and cascade-block all dependents."""
        if graph_sync is not None:
            cascade_blocked = graph_sync.mark_blocked(node_id, reason)
            state.blocked_reasons[node_id] = reason
            if self._task_callback is not None:
                archetype = get_archetype_fn(node_id) if get_archetype_fn else "coder"
                self._task_callback(
                    TaskEvent(
                        node_id=node_id,
                        status="blocked",
                        duration_s=0,
                        error_message=reason,
                        archetype=archetype,
                    )
                )
            for blocked_id in cascade_blocked:
                cascade_reason = f"Blocked by upstream task {node_id}"
                state.blocked_reasons[blocked_id] = cascade_reason
                if self._task_callback is not None:
                    archetype = get_archetype_fn(blocked_id) if get_archetype_fn else "coder"
                    self._task_callback(
                        TaskEvent(
                            node_id=blocked_id,
                            status="blocked",
                            duration_s=0,
                            error_message=cascade_reason,
                            archetype=archetype,
                        )
                    )
                logger.info("Cascade-blocked %s due to %s", blocked_id, node_id)

    def check_block_budget(
        self,
        state: ExecutionState,
        *,
        sink: Any | None = None,
        run_id: str = "",
    ) -> bool:
        """Check if the blocked fraction exceeds the configured budget.

        Returns True if the run should stop due to excessive blocking.
        """
        from agent_fox.engine.barrier import _count_node_status

        max_fraction = self._max_blocked_fraction
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
                "Block budget exceeded: %.0f%% of tasks blocked (limit: %.0f%%). Stopping run.",
                fraction * 100,
                max_fraction * 100,
            )
            emit_audit_event(
                sink,
                run_id,
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
            return True

        return False
