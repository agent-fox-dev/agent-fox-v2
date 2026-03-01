"""Status report generator: task counts, token usage, cost, problem tasks.

Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


def generate_status(
    state_path: Path,
    plan_path: Path,
) -> StatusReport:
    """Generate a status report from execution state and plan.

    Args:
        state_path: Path to .agent-fox/state.jsonl.
        plan_path: Path to .agent-fox/plan.json.

    Returns:
        StatusReport with task counts, token usage, cost, and problem tasks.

    Raises:
        AgentFoxError: If neither state nor plan file can be read.
    """
    raise NotImplementedError
