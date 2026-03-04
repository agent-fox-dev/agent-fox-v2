"""Standup report generator: agent activity, human commits, file overlaps.

Requirements: 07-REQ-2.1, 07-REQ-2.2, 07-REQ-2.3, 07-REQ-2.4, 07-REQ-2.5
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.graph.persistence import load_plan
from agent_fox.graph.types import TaskGraph

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentActivity:
    """Agent work within the reporting window."""

    tasks_completed: int
    sessions_run: int
    input_tokens: int
    output_tokens: int
    cost: float  # USD
    completed_task_ids: list[str]


@dataclass(frozen=True)
class HumanCommit:
    """A non-agent commit within the reporting window."""

    sha: str
    author: str
    timestamp: str  # ISO 8601
    subject: str
    files_changed: list[str]


@dataclass(frozen=True)
class FileOverlap:
    """A file modified by both agent and human in the window."""

    path: str
    agent_task_ids: list[str]  # which agent tasks touched it
    human_commits: list[str]  # which human commit SHAs touched it


@dataclass(frozen=True)
class CostBreakdown:
    """Cost breakdown by model tier."""

    tier: str
    sessions: int
    input_tokens: int
    output_tokens: int
    cost: float


@dataclass(frozen=True)
class TaskActivity:
    """Per-task session summary within the reporting window.

    Requirements: 15-REQ-2.3
    """

    task_id: str  # internal format "spec:group"
    current_status: str  # from ExecutionState node_states
    completed_sessions: int  # sessions with status "completed"
    total_sessions: int  # all sessions for this task in window
    input_tokens: int
    output_tokens: int
    cost: float


@dataclass(frozen=True)
class QueueSummary:
    """Current task queue status."""

    ready: int
    pending: int
    blocked: int
    failed: int
    completed: int
    total: int = 0  # NEW: sum of all tasks
    in_progress: int = 0  # NEW: tasks currently executing
    ready_task_ids: list[str] = field(default_factory=list)  # NEW: IDs of ready tasks


@dataclass(frozen=True)
class StandupReport:
    """Complete standup report data model."""

    window_hours: int
    window_start: str  # ISO 8601
    window_end: str  # ISO 8601
    agent: AgentActivity
    human_commits: list[HumanCommit]
    agent_commits: list[HumanCommit]
    file_overlaps: list[FileOverlap]
    cost_breakdown: list[CostBreakdown]
    queue: QueueSummary
    task_activities: list[TaskActivity] = field(
        default_factory=list,
    )  # per-task breakdown
    total_cost: float = 0.0  # all-time total from ExecutionState


def generate_standup(
    state_path: Path,
    plan_path: Path,
    repo_path: Path,
    hours: int = 24,
    agent_author: str = "agent-fox",
) -> StandupReport:
    """Generate a standup report for the given time window.

    Args:
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        repo_path: Path to the git repository root.
        hours: Reporting window in hours (default 24).
        agent_author: Git author name used by agent-fox for filtering.

    Returns:
        StandupReport covering the specified time window.
    """
    # Compute time window
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours)
    window_end = now

    # Load plan (needed for queue summary)
    graph = load_plan(plan_path)

    # Load execution state
    state = StateManager(state_path).load()

    # Filter sessions within the time window
    windowed_sessions = _filter_sessions_by_window(
        state.session_history if state else [],
        window_start,
    )

    # Compute agent activity from windowed sessions
    agent = _compute_agent_activity(windowed_sessions)

    # Compute per-task activity breakdowns
    node_states: dict[str, str] = {}
    if state is not None:
        node_states = dict(state.node_states)
    task_activities = _compute_task_activities(windowed_sessions, node_states)

    # Partition git commits into human and agent
    from agent_fox.reporting.git_activity import partition_commits

    human_commits, agent_commits = partition_commits(
        repo_path,
        window_start,
        agent_author,
    )

    # Build agent file map from session records' files_touched
    agent_files = _build_agent_file_map(windowed_sessions)
    file_overlaps = _detect_overlaps(agent_files, human_commits)

    # Build cost breakdown by model tier
    cost_breakdown = _build_cost_breakdown(windowed_sessions)

    # Build queue summary from current task statuses
    queue = _build_queue_summary(graph, state)

    # All-time total cost from execution state
    all_time_cost = state.total_cost if state is not None else 0.0

    return StandupReport(
        window_hours=hours,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        agent=agent,
        human_commits=human_commits,
        agent_commits=agent_commits,
        file_overlaps=file_overlaps,
        cost_breakdown=cost_breakdown,
        queue=queue,
        task_activities=task_activities,
        total_cost=all_time_cost,
    )


def _filter_sessions_by_window(
    sessions: list[SessionRecord],
    window_start: datetime,
) -> list[SessionRecord]:
    """Filter session records to those within the reporting window.

    Args:
        sessions: All session records.
        window_start: Start of the reporting window.

    Returns:
        Sessions with timestamps at or after window_start.
    """
    result: list[SessionRecord] = []
    for session in sessions:
        try:
            ts = datetime.fromisoformat(session.timestamp)
            # Ensure timezone-aware comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts >= window_start:
                result.append(session)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid timestamp in session record: %s",
                session.timestamp,
            )
    return result


def _compute_agent_activity(
    sessions: list[SessionRecord],
) -> AgentActivity:
    """Compute agent activity metrics from windowed sessions.

    Args:
        sessions: Session records within the reporting window.

    Returns:
        AgentActivity summarizing agent work.
    """
    completed_ids: list[str] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for session in sessions:
        total_input += session.input_tokens
        total_output += session.output_tokens
        total_cost += session.cost
        if session.status == "completed":
            if session.node_id not in completed_ids:
                completed_ids.append(session.node_id)

    return AgentActivity(
        tasks_completed=len(completed_ids),
        sessions_run=len(sessions),
        input_tokens=total_input,
        output_tokens=total_output,
        cost=total_cost,
        completed_task_ids=completed_ids,
    )


def _compute_task_activities(
    sessions: list[SessionRecord],
    node_states: dict[str, str],
) -> list[TaskActivity]:
    """Compute per-task activity breakdowns from windowed sessions.

    Groups sessions by node_id and for each group counts completed vs
    total sessions, sums tokens and cost, and looks up the current status
    from the execution state node_states.

    Args:
        sessions: Session records within the reporting window.
        node_states: Mapping of node_id to current status from ExecutionState.

    Returns:
        List of TaskActivity entries, sorted by task_id.

    Requirements: 15-REQ-2.2, 15-REQ-2.3
    """
    groups: dict[str, list[SessionRecord]] = defaultdict(list)
    for session in sessions:
        groups[session.node_id].append(session)

    activities: list[TaskActivity] = []
    for task_id in sorted(groups):
        task_sessions = groups[task_id]
        completed_count = sum(1 for s in task_sessions if s.status == "completed")
        total_input = sum(s.input_tokens for s in task_sessions)
        total_output = sum(s.output_tokens for s in task_sessions)
        total_cost = sum(s.cost for s in task_sessions)
        current_status = node_states.get(task_id, "pending")

        activities.append(
            TaskActivity(
                task_id=task_id,
                current_status=current_status,
                completed_sessions=completed_count,
                total_sessions=len(task_sessions),
                input_tokens=total_input,
                output_tokens=total_output,
                cost=total_cost,
            )
        )

    return activities


def _detect_overlaps(
    agent_files: dict[str, list[str]],  # path -> list of task_ids
    human_commits: list[HumanCommit],
) -> list[FileOverlap]:
    """Detect files modified by both agent and human.

    Args:
        agent_files: Mapping of file path to agent task IDs that touched it.
        human_commits: Human commits with their changed files.

    Returns:
        List of FileOverlap records for files touched by both.
    """
    if not agent_files or not human_commits:
        return []

    # Build a map of human file -> list of commit SHAs
    human_file_commits: dict[str, list[str]] = defaultdict(list)
    for commit in human_commits:
        for fpath in commit.files_changed:
            human_file_commits[fpath].append(commit.sha)

    # Find intersection
    overlaps: list[FileOverlap] = []
    for fpath, task_ids in agent_files.items():
        if fpath in human_file_commits:
            overlaps.append(
                FileOverlap(
                    path=fpath,
                    agent_task_ids=list(task_ids),
                    human_commits=list(human_file_commits[fpath]),
                )
            )

    return overlaps


def _build_agent_file_map(
    sessions: list[SessionRecord],
) -> dict[str, list[str]]:
    """Build a mapping of file path to agent task IDs from session records.

    Aggregates ``files_touched`` across all windowed sessions, mapping
    each file path to the list of task IDs (node_ids) that touched it.

    Args:
        sessions: Session records within the reporting window.

    Returns:
        Dict mapping file path to list of task IDs that touched it.
    """
    file_map: dict[str, list[str]] = defaultdict(list)
    for session in sessions:
        for fpath in session.files_touched:
            if session.node_id not in file_map[fpath]:
                file_map[fpath].append(session.node_id)
    return dict(file_map)


def _build_cost_breakdown(
    sessions: list[SessionRecord],
) -> list[CostBreakdown]:
    """Build cost breakdown by model tier from windowed sessions.

    Groups sessions by their ``model`` field. Sessions without a model
    value are grouped under "default".

    Args:
        sessions: Session records within the reporting window.

    Returns:
        List of CostBreakdown entries, one per model tier, sorted by tier.
    """
    if not sessions:
        return []

    groups: dict[str, list[SessionRecord]] = defaultdict(list)
    for session in sessions:
        tier = session.model or "default"
        groups[tier].append(session)

    breakdowns: list[CostBreakdown] = []
    for tier in sorted(groups):
        tier_sessions = groups[tier]
        breakdowns.append(
            CostBreakdown(
                tier=tier,
                sessions=len(tier_sessions),
                input_tokens=sum(s.input_tokens for s in tier_sessions),
                output_tokens=sum(s.output_tokens for s in tier_sessions),
                cost=sum(s.cost for s in tier_sessions),
            ),
        )

    return breakdowns


def _build_queue_summary(
    graph: TaskGraph | None,
    state: ExecutionState | None,
) -> QueueSummary:
    """Build queue summary from current task statuses.

    A task is 'ready' if its status is 'pending' and all of its
    predecessors are completed. A task is 'pending' (not ready) if
    its status is 'pending' but it has incomplete predecessors.

    Args:
        graph: The task graph (may be None if plan not found).
        state: Current execution state (may be None).

    Returns:
        QueueSummary with counts by status.
    """
    if graph is None:
        return QueueSummary(
            ready=0,
            pending=0,
            blocked=0,
            failed=0,
            completed=0,
            total=0,
            in_progress=0,
            ready_task_ids=[],
        )

    # Get node statuses from state, defaulting to pending
    node_states: dict[str, str] = {}
    if state is not None:
        node_states = dict(state.node_states)

    # Fill in any nodes from the plan that aren't in the state
    for nid in graph.nodes:
        if nid not in node_states:
            node_states[nid] = "pending"

    ready = 0
    pending = 0
    blocked = 0
    failed = 0
    completed = 0
    in_progress = 0
    ready_task_ids: list[str] = []

    for nid, status in node_states.items():
        if status == "completed":
            completed += 1
        elif status == "failed":
            failed += 1
        elif status == "blocked":
            blocked += 1
        elif status == "pending":
            # Check if ready (all predecessors completed)
            preds = graph.predecessors(nid)
            if all(node_states.get(p, "pending") == "completed" for p in preds):
                ready += 1
                ready_task_ids.append(nid)
            else:
                pending += 1
        elif status == "skipped":
            pass  # Skipped tasks not counted in queue
        elif status == "in_progress":
            in_progress += 1

    total = ready + pending + in_progress + blocked + failed + completed

    return QueueSummary(
        ready=ready,
        pending=pending,
        blocked=blocked,
        failed=failed,
        completed=completed,
        total=total,
        in_progress=in_progress,
        ready_task_ids=ready_task_ids,
    )
