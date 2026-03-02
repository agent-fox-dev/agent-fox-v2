"""Iterative fix loop.

Runs quality checks, clusters failures, generates fix specs, runs coding
sessions, and iterates until all checks pass or a termination condition is met.

Requirements: 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3, 08-REQ-7.E1
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.collector import FailureRecord


class TerminationReason(StrEnum):
    """Reason the fix loop terminated."""

    ALL_FIXED = "all_fixed"
    MAX_PASSES = "max_passes"
    COST_LIMIT = "cost_limit"
    INTERRUPTED = "interrupted"


@dataclass
class FixResult:
    """Result of the fix loop."""

    passes_completed: int
    clusters_resolved: int
    clusters_remaining: int
    sessions_consumed: int
    termination_reason: TerminationReason
    remaining_failures: list[FailureRecord]


async def run_fix_loop(
    project_root: Path,
    config: AgentFoxConfig,
    max_passes: int = 3,
) -> FixResult:
    """Run the iterative fix loop.

    Algorithm:
    1. Detect available quality checks (once, at start).
    2. For each pass (up to max_passes):
       a. Run all checks, collect failures.
       b. If no failures, terminate with ALL_FIXED.
       c. Cluster failures by root cause.
       d. Generate fix specs for each cluster.
       e. Run a coding session for each cluster.
       f. Track sessions consumed and cost.
    3. After last pass, run checks one final time to determine resolution.
    4. Produce FixResult.

    Termination conditions:
    - All checks pass -> ALL_FIXED
    - max_passes reached -> MAX_PASSES
    - Cost limit reached -> COST_LIMIT
    - KeyboardInterrupt -> INTERRUPTED
    """
    raise NotImplementedError
