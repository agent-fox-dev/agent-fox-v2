"""Standup report generator: agent activity, human commits, file overlaps.

Requirements: 07-REQ-2.1, 07-REQ-2.2, 07-REQ-2.3, 07-REQ-2.4, 07-REQ-2.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
class QueueSummary:
    """Current task queue status."""

    ready: int
    pending: int
    blocked: int
    failed: int
    completed: int


@dataclass(frozen=True)
class StandupReport:
    """Complete standup report data model."""

    window_hours: int
    window_start: str  # ISO 8601
    window_end: str  # ISO 8601
    agent: AgentActivity
    human_commits: list[HumanCommit]
    file_overlaps: list[FileOverlap]
    cost_breakdown: list[CostBreakdown]
    queue: QueueSummary


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
    raise NotImplementedError


def _get_human_commits(
    repo_path: Path,
    since: datetime,
    agent_author: str,
) -> list[HumanCommit]:
    """Query git log for non-agent commits since the given timestamp.

    Uses ``git log --since=<ISO> --invert-grep --author=<agent_author>``
    to exclude agent commits.

    Args:
        repo_path: Path to the git repository root.
        since: Start of reporting window.
        agent_author: Author name to exclude.

    Returns:
        List of HumanCommit records.
    """
    raise NotImplementedError


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
    raise NotImplementedError
