"""Status report generator: task counts, token usage, cost, problem tasks.

Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3,
              40-REQ-14.1, 40-REQ-14.3
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from agent_fox.core.errors import AgentFoxError
from agent_fox.core.node_id import spec_name_of
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.graph.persistence import load_plan
from agent_fox.graph.types import TaskGraph
from agent_fox.knowledge.store import read_all_facts

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditStatusReport:
    """Status report built from DuckDB audit_events table.

    Requirements: 40-REQ-14.1
    """

    total_sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    cost_by_archetype: dict[str, float] = field(default_factory=dict)


def build_status_report_from_audit(
    conn: duckdb.DuckDBPyConnection | None,
) -> AuditStatusReport | None:
    """Build a status report by reading from the DuckDB audit_events table.

    Queries session.complete and session.fail events to compute session
    metrics. Returns None when DuckDB is unavailable.

    Requirements: 40-REQ-14.1, 40-REQ-14.3
    """
    if conn is None:
        return None

    try:
        rows = conn.execute(
            """
            SELECT payload
            FROM audit_events
            WHERE event_type IN ('session.complete', 'session.fail')
            ORDER BY timestamp
            """
        ).fetchall()
    except Exception:
        logger.warning("Failed to query audit_events for status report", exc_info=True)
        return None

    total_sessions = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    cost_by_archetype: dict[str, float] = defaultdict(float)

    for (payload_raw,) in rows:
        total_sessions += 1
        try:
            if isinstance(payload_raw, str):
                payload = json.loads(payload_raw)
            elif isinstance(payload_raw, dict):
                payload = payload_raw
            else:
                payload = {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        cost = payload.get("cost", 0.0)
        archetype = payload.get("archetype", "unknown")

        # Prefer separate token fields; fall back to legacy combined "tokens"
        if "input_tokens" in payload:
            total_input_tokens += int(payload.get("input_tokens", 0))
            total_output_tokens += int(payload.get("output_tokens", 0))
        else:
            # Legacy: combined "tokens" field — attribute to input as best effort
            total_input_tokens += int(payload.get("tokens", 0))

        total_cost += float(cost)
        cost_by_archetype[archetype] += float(cost)

    return AuditStatusReport(
        total_sessions=total_sessions,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost=total_cost,
        cost_by_archetype=dict(cost_by_archetype),
    )


@dataclass(frozen=True)
class TaskSummary:
    """Summary of a single blocked or failed task."""

    task_id: str
    title: str
    status: str
    reason: str  # failure message or blocking reason


@dataclass(frozen=True)
class StatusReport:
    """Complete status report data model."""

    counts: dict[str, int]  # status -> count
    total_tasks: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float  # USD
    problem_tasks: list[TaskSummary]
    per_spec: dict[str, dict[str, int]]  # spec_name -> {status -> count}
    memory_total: int = 0
    memory_by_category: dict[str, int] = field(default_factory=dict)
    cost_by_archetype: dict[str, float] = field(default_factory=dict)
    cost_by_spec: dict[str, float] = field(default_factory=dict)


def extract_spec_name(node_id: str) -> str:
    """Extract spec name from a node_id by stripping the last colon-separated segment.

    Requirements: 34-REQ-4.2, 34-REQ-4.E1

    .. deprecated:: Use ``agent_fox.core.node_id.spec_name_of`` instead.
    """
    return spec_name_of(node_id)


def _load_plan_or_raise(plan_path: Path) -> TaskGraph:
    """Load the task graph from plan.json, raising on failure.

    Args:
        plan_path: Path to .agent-fox/plan.json.

    Returns:
        The loaded TaskGraph.

    Raises:
        AgentFoxError: If the plan file cannot be read.
    """
    graph = load_plan(plan_path)
    if graph is None:
        raise AgentFoxError(
            "No plan file found. Run `agent-fox plan` first.",
            path=str(plan_path),
        )
    return graph


def _load_state(state_path: Path) -> ExecutionState | None:
    """Load execution state from state.jsonl.

    Args:
        state_path: Path to .agent-fox/state.jsonl.

    Returns:
        The loaded ExecutionState, or None if the file does not exist.
    """
    manager = StateManager(state_path)
    return manager.load()


def _get_failure_reasons(
    session_history: list[SessionRecord],
) -> dict[str, str]:
    """Extract the most recent failure reason for each task.

    Scans session history for failed sessions and keeps the last
    error_message per node_id.

    Args:
        session_history: List of session records.

    Returns:
        Dict mapping node_id to its most recent error message.
    """
    reasons: dict[str, str] = {}
    for record in session_history:
        if record.status == "failed" and record.error_message:
            reasons[record.node_id] = record.error_message
    return reasons


def _get_block_reason(
    task_id: str,
    graph: TaskGraph,
    node_states: dict[str, str],
) -> str:
    """Determine why a task is blocked based on its predecessors.

    Args:
        task_id: The blocked task's ID.
        graph: The task graph with edges.
        node_states: Current status of all nodes.

    Returns:
        A human-readable blocking reason string.
    """
    preds = graph.predecessors(task_id)
    blockers = [
        p
        for p in preds
        if node_states.get(p, "pending") not in ("completed", "skipped")
    ]
    if blockers:
        return f"Blocked by: {', '.join(blockers)}"
    return "Blocked (unknown reason)"


def _build_problem_tasks(
    graph: TaskGraph,
    node_states: dict[str, str],
    failure_reasons: dict[str, str],
    blocked_reasons: dict[str, str] | None = None,
) -> list[TaskSummary]:
    """Build a list of problem tasks (failed and blocked).

    Args:
        graph: The task graph with node metadata.
        node_states: Current status of all nodes.
        failure_reasons: Mapping of node_id to error message.
        blocked_reasons: Mapping of node_id to stored blocking reason
            from ExecutionState. Preferred over predecessor heuristic.

    Returns:
        List of TaskSummary for failed and blocked tasks.
    """
    problems: list[TaskSummary] = []
    for node_id, status in node_states.items():
        if status not in ("failed", "blocked"):
            continue
        node = graph.nodes.get(node_id)
        title = node.title if node else f"Task {node_id}"

        if status == "failed":
            reason = failure_reasons.get(node_id, "Unknown failure")
        elif blocked_reasons and node_id in blocked_reasons:
            reason = blocked_reasons[node_id]
        else:
            reason = _get_block_reason(node_id, graph, node_states)

        problems.append(
            TaskSummary(
                task_id=node_id,
                title=title,
                status=status,
                reason=reason,
            )
        )
    return problems


def _compute_per_spec(
    graph: TaskGraph,
    node_states: dict[str, str],
) -> dict[str, dict[str, int]]:
    """Compute task counts grouped by spec and status.

    Args:
        graph: The task graph with node metadata.
        node_states: Current status of all nodes.

    Returns:
        Dict mapping spec_name to {status -> count}.
    """
    per_spec: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for node_id, status in node_states.items():
        node = graph.nodes.get(node_id)
        spec_name = node.spec_name if node else spec_name_of(node_id)
        per_spec[spec_name][status] += 1
    # Convert defaultdicts to regular dicts for serialization
    return {k: dict(v) for k, v in per_spec.items()}


def generate_status(
    state_path: Path,
    plan_path: Path,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> StatusReport:
    """Generate a status report from execution state and plan.

    Prefers DuckDB audit_events for session metrics (tokens, cost) when
    a DuckDB connection is available, falling back to state.jsonl when it
    is not.

    Args:
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        db_conn: Optional DuckDB connection for audit events and fact loading.
            If None, session metrics come from state.jsonl and facts section
            will be empty.

    Returns:
        StatusReport with task counts, token usage, cost, and problem tasks.

    Raises:
        AgentFoxError: If neither state nor plan file can be read.

    Requirements: 40-REQ-14.1, 40-REQ-14.3
    """
    # Load the plan (required)
    graph = _load_plan_or_raise(plan_path)

    # Load execution state (optional - may not exist yet)
    state = _load_state(state_path)

    # Determine node statuses: seed from graph (honours tasks.md [x]
    # checkboxes), then overlay any state.jsonl overrides for nodes the
    # orchestrator has actually touched.
    node_states = {nid: node.status.value for nid, node in graph.nodes.items()}
    if state is not None:
        for nid, status in state.node_states.items():
            if nid in node_states:
                node_states[nid] = status

    # Filter to real task nodes (exclude injected archetype nodes)
    task_node_ids = {
        nid for nid, node in graph.nodes.items() if node.archetype == "coder"
    }

    # Count tasks by status (real tasks only)
    counts: dict[str, int] = defaultdict(int)
    for nid, status in node_states.items():
        if nid in task_node_ids:
            counts[status] += 1
    counts = dict(counts)

    total_tasks = len(task_node_ids)

    # Try DuckDB audit_events for session metrics first (40-REQ-14.1)
    audit_report = build_status_report_from_audit(db_conn)

    if audit_report is not None and audit_report.total_sessions > 0:
        # Prefer DuckDB audit data for session metrics
        input_tokens = audit_report.total_input_tokens
        output_tokens = audit_report.total_output_tokens
        estimated_cost = audit_report.total_cost
        cost_by_archetype = dict(audit_report.cost_by_archetype)
        logger.debug(
            "Status report: using DuckDB audit_events (%d sessions)",
            audit_report.total_sessions,
        )
    elif state is not None:
        # Fall back to state.jsonl (40-REQ-14.3)
        input_tokens = state.total_input_tokens
        output_tokens = state.total_output_tokens
        estimated_cost = state.total_cost
        cost_by_archetype_agg: dict[str, float] = defaultdict(float)
        for record in state.session_history:
            cost_by_archetype_agg[record.archetype] += record.cost
        cost_by_archetype = dict(cost_by_archetype_agg)
        logger.debug("Status report: falling back to state.jsonl")
    else:
        input_tokens = 0
        output_tokens = 0
        estimated_cost = 0.0
        cost_by_archetype = {}

    # Failure reasons always come from state.jsonl (audit doesn't replace this)
    if state is not None:
        failure_reasons = _get_failure_reasons(state.session_history)
    else:
        failure_reasons = {}

    # Build problem tasks list (real tasks only)
    task_node_states = {
        nid: s for nid, s in node_states.items() if nid in task_node_ids
    }
    blocked_reasons = state.blocked_reasons if state is not None else {}
    problem_tasks = _build_problem_tasks(
        graph,
        task_node_states,
        failure_reasons,
        blocked_reasons,
    )

    # Compute per-spec breakdown (real tasks only)
    per_spec = _compute_per_spec(graph, task_node_states)

    # Memory facts summary (auto-fallback: conn → read-only DB → JSONL)
    facts = read_all_facts(db_conn)
    memory_total = len(facts)
    memory_by_category = dict(Counter(f.category for f in facts))

    # Per-spec cost breakdown (still from state.jsonl as audit doesn't track per-spec)
    cost_by_spec_agg: dict[str, float] = defaultdict(float)
    if state is not None:
        for record in state.session_history:
            spec_name = spec_name_of(record.node_id)
            cost_by_spec_agg[spec_name] += record.cost

    return StatusReport(
        counts=counts,
        total_tasks=total_tasks,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimated_cost,
        problem_tasks=problem_tasks,
        per_spec=per_spec,
        memory_total=memory_total,
        memory_by_category=memory_by_category,
        cost_by_archetype=cost_by_archetype,
        cost_by_spec=dict(cost_by_spec_agg),
    )
