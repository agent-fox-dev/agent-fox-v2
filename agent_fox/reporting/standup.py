"""Standup report generator: agent activity, human commits, file overlaps.

Requirements: 07-REQ-2.1, 07-REQ-2.2, 07-REQ-2.3, 07-REQ-2.4, 07-REQ-2.5,
              40-REQ-14.2, 40-REQ-14.3
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.graph.persistence import load_plan
from agent_fox.graph.types import TaskGraph
from agent_fox.reporting import parse_audit_payload

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditStandupReport:
    """Standup report built from DuckDB audit_events table.

    Requirements: 40-REQ-14.2
    """

    total_sessions: int
    total_cost: float
    recent_events: list[dict]


def build_standup_from_audit(
    conn: duckdb.DuckDBPyConnection | None,
    *,
    lookback_hours: int = 24,
) -> AuditStandupReport | None:
    """Build a standup report by reading from the DuckDB audit_events table.

    Queries recent session events to produce a standup-style summary.
    Returns None when DuckDB is unavailable.

    Requirements: 40-REQ-14.2, 40-REQ-14.3
    """
    if conn is None:
        return None

    try:
        rows = conn.execute(
            """
            SELECT event_type, timestamp, node_id, archetype, payload
            FROM audit_events
            WHERE event_type IN ('session.complete', 'session.fail')
            ORDER BY timestamp DESC
            LIMIT 100
            """
        ).fetchall()
    except Exception:
        logger.warning("Failed to query audit_events for standup report", exc_info=True)
        return None

    total_sessions = len(rows)
    total_cost = 0.0
    recent_events: list[dict] = []

    for event_type, timestamp, node_id, archetype, payload_raw in rows:
        payload = parse_audit_payload(payload_raw)
        cost = payload.get("cost", 0.0)
        total_cost += float(cost)

        recent_events.append(
            {
                "event_type": event_type,
                "timestamp": str(timestamp),
                "node_id": node_id,
                "archetype": archetype,
                "cost": cost,
            }
        )

    return AuditStandupReport(
        total_sessions=total_sessions,
        total_cost=total_cost,
        recent_events=recent_events,
    )


# ---------------------------------------------------------------------------
# Git activity (merged from git_activity.py)
# ---------------------------------------------------------------------------

_git_activity_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HumanCommit:
    """A commit record (human or agent) within the reporting window."""

    sha: str
    author: str
    timestamp: str  # ISO 8601
    subject: str
    files_changed: list[str]


# Conventional-commit prefix pattern used by coding agents.
_CONVENTIONAL_PREFIX_RE = re.compile(
    r"^(feat|fix|refactor|test|chore|style|docs|ci|build|perf|revert)"
    r"(\([^)]+\))?!?:\s",
)

# Merge-commit pattern produced by git merge (used by agent workflows).
# Matches both "Merge branch '<name>'" and "Merge fix/issue-... into develop"
# (branch-path merges where the branch name contains a slash).
_MERGE_BRANCH_RE = re.compile(r"^Merge (branch\s+'|\S+/)")


def is_agent_commit(commit: HumanCommit, agent_author: str) -> bool:
    """Determine whether a commit was made by an agent.

    Checks two signals:
    1. Author name matches the configured agent identity.
    2. Commit subject uses a conventional-commit prefix or is a
       merge-branch commit — patterns agents follow but humans
       typically do not.
    """
    if commit.author == agent_author:
        return True
    if _CONVENTIONAL_PREFIX_RE.match(commit.subject):
        return True
    if _MERGE_BRANCH_RE.match(commit.subject):
        return True
    return False


def partition_commits(
    repo_path: Path,
    since: datetime,
    agent_author: str,
) -> tuple[list[HumanCommit], list[HumanCommit]]:
    """Query git log and partition commits into human and agent lists.

    Runs ``git log --since=<ISO>`` and classifies each commit using
    author identity and commit message patterns.

    Args:
        repo_path: Path to the git repository root.
        since: Start of reporting window.
        agent_author: Author name used by the agent.

    Returns:
        Tuple of (human_commits, agent_commits).
    """
    since_iso = since.isoformat()

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since_iso}",
                "--format=%H|%an|%aI|%s",
                "--name-only",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        _git_activity_logger.warning("git log failed: %s", exc)
        return [], []

    if result.returncode != 0:
        _git_activity_logger.warning("git log returned non-zero: %s", result.stderr.strip())
        return [], []

    all_commits = parse_git_log_output(result.stdout)

    human: list[HumanCommit] = []
    agent: list[HumanCommit] = []
    for c in all_commits:
        if is_agent_commit(c, agent_author):
            agent.append(c)
        else:
            human.append(c)
    return human, agent


def parse_git_log_output(output: str) -> list[HumanCommit]:
    """Parse structured git log output into HumanCommit records.

    Git outputs with ``--format="%H|%an|%aI|%s" --name-only``::

        <hash>|<author>|<ISO date>|<subject>
        <blank line>
        <file1>
        <file2>
        <hash>|<author>|<ISO date>|<subject>
        <blank line>
        <file1>
        ...

    Each commit has a header line followed by a blank separator, then
    file names. The next commit header follows immediately after files.

    Args:
        output: Raw stdout from git log command.

    Returns:
        List of parsed HumanCommit records.
    """
    commits: list[HumanCommit] = []
    if not output.strip():
        return commits

    lines = output.split("\n")

    # Collect commit blocks: each starts with a header (contains |),
    # followed by a blank line, then file names.
    headers: list[tuple[str, int]] = []  # (header, line_index)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and "|" in stripped:
            # Check if it looks like a commit header (40-char hex hash prefix)
            parts = stripped.split("|", 1)
            if len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
                headers.append((stripped, i))

    for idx, (header, start_line) in enumerate(headers):
        # Files are between this header and the next header
        if idx + 1 < len(headers):
            end_line = headers[idx + 1][1]
        else:
            end_line = len(lines)

        # Collect non-empty, non-header lines as file names
        files: list[str] = []
        for j in range(start_line + 1, end_line):
            stripped = lines[j].strip()
            if stripped:
                files.append(stripped)

        commit = parse_commit_header(header, files)
        if commit is not None:
            commits.append(commit)

    return commits


def parse_commit_header(
    header: str,
    files: list[str],
) -> HumanCommit | None:
    """Parse a single commit header line into a HumanCommit.

    Args:
        header: The header line in format "hash|author|date|subject".
        files: List of changed file paths.

    Returns:
        HumanCommit record or None if parsing fails.
    """
    parts = header.split("|", 3)
    if len(parts) < 4:
        _git_activity_logger.warning("Malformed git log header: %s", header)
        return None

    sha, author, timestamp, subject = parts
    return HumanCommit(
        sha=sha.strip(),
        author=author.strip(),
        timestamp=timestamp.strip(),
        subject=subject.strip(),
        files_changed=[f for f in files if f],
    )


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
    archetype: str = "coder"  # agent archetype working on this task


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
    plan_path: Path | None = None,
    repo_path: Path | None = None,
    hours: int = 24,
    agent_author: str = "agent-fox",
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> StandupReport:
    """Generate a standup report for the given time window.

    Prefers DuckDB audit_events for session activity when a DuckDB
    connection is available, falling back to state.jsonl when it is not.

    Args:
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.
        repo_path: Path to the git repository root.
        hours: Reporting window in hours (default 24).
        agent_author: Git author name used by agent-fox for filtering.
        db_conn: Optional DuckDB connection for reading audit events.
            When provided, session metrics are sourced from audit_events.
            Falls back to state.jsonl when None or on query failure.

    Returns:
        StandupReport covering the specified time window.

    Requirements: 40-REQ-14.2, 40-REQ-14.3
    """
    # Compute time window
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours)
    window_end = now

    # Resolve default paths if not provided
    if plan_path is None:
        from agent_fox.core.paths import PLAN_PATH

        plan_path = PLAN_PATH
    if repo_path is None:
        repo_path = Path.cwd()

    # Load plan (needed for queue summary)
    graph = load_plan(plan_path)

    # Load execution state
    state = StateManager(state_path).load()

    # Filter sessions within the time window
    windowed_sessions = _filter_sessions_by_window(
        state.session_history if state else [],
        window_start,
    )

    # Try DuckDB audit_events for session activity (40-REQ-14.2)
    audit_standup = build_standup_from_audit(db_conn, lookback_hours=hours)
    if audit_standup is not None and audit_standup.total_sessions > 0:
        logger.debug(
            "Standup report: using DuckDB audit_events (%d sessions)",
            audit_standup.total_sessions,
        )

    # Compute agent activity from windowed sessions (state.jsonl fallback)
    agent = _compute_agent_activity(windowed_sessions)

    # Compute per-task activity breakdowns (all sessions, not just windowed)
    all_sessions = state.session_history if state else []
    node_states: dict[str, str] = {}
    if state is not None:
        node_states = dict(state.node_states)
    node_archetypes = {nid: node.archetype for nid, node in graph.nodes.items()} if graph else None
    task_activities = _compute_task_activities(all_sessions, node_states, node_archetypes)

    # Partition git commits into human and agent
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

    # All-time total cost: prefer DuckDB audit data, fall back to state
    if audit_standup is not None and audit_standup.total_cost > 0:
        all_time_cost = audit_standup.total_cost
    else:
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
    node_archetypes: dict[str, str] | None = None,
) -> list[TaskActivity]:
    """Compute per-task activity breakdowns across all sessions.

    Includes every task from node_states (the full plan) so the standup
    report shows the complete picture.  Tasks that have never been
    executed appear with zero tokens/cost and their current status.

    Args:
        sessions: All session records from execution state.
        node_states: Mapping of node_id to current status from ExecutionState.

    Returns:
        List of TaskActivity entries, sorted by task_id.

    Requirements: 15-REQ-2.2, 15-REQ-2.3
    """
    groups: dict[str, list[SessionRecord]] = defaultdict(list)
    for session in sessions:
        groups[session.node_id].append(session)

    # Merge all task IDs: those with sessions + those only in node_states
    all_task_ids = sorted(set(groups.keys()) | set(node_states.keys()))

    activities: list[TaskActivity] = []
    for task_id in all_task_ids:
        task_sessions = groups.get(task_id, [])
        completed_count = sum(1 for s in task_sessions if s.status == "completed")
        total_input = sum(s.input_tokens for s in task_sessions)
        total_output = sum(s.output_tokens for s in task_sessions)
        total_cost = sum(s.cost for s in task_sessions)
        current_status = node_states.get(task_id, "pending")

        # Resolve archetype: prefer graph data, fall back to session records
        if node_archetypes and task_id in node_archetypes:
            archetype = node_archetypes[task_id]
        elif task_sessions and hasattr(task_sessions[0], "archetype"):
            archetype = task_sessions[0].archetype
        else:
            archetype = "coder"

        activities.append(
            TaskActivity(
                task_id=task_id,
                current_status=current_status,
                completed_sessions=completed_count,
                total_sessions=len(task_sessions),
                input_tokens=total_input,
                output_tokens=total_output,
                cost=total_cost,
                archetype=archetype,
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
