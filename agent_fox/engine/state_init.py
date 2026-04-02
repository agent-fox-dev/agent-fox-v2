"""State initialization: graph-to-state seeding and resumption helpers.

Pure functions that build initial execution state from a TaskGraph,
merge state across plan changes, and initialize attempt/error trackers
from session history.

Requirements: 04-REQ-7.E1
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from agent_fox.engine.state import ExecutionState, StateManager
from agent_fox.graph.types import TaskGraph

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
                k: v
                for k, v in existing.blocked_reasons.items()
                if k in graph.nodes and node_states.get(k) != "pending"
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
