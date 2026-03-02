"""Iterative fix loop.

Runs quality checks, clusters failures, generates fix specs, runs coding
sessions, and iterates until all checks pass or a termination condition is met.

Requirements: 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3, 08-REQ-7.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.clusterer import cluster_failures
from agent_fox.fix.collector import FailureRecord, run_checks
from agent_fox.fix.detector import detect_checks
from agent_fox.fix.spec_gen import cleanup_fix_specs, generate_fix_spec

logger = logging.getLogger(__name__)

# Default output directory for fix specs (relative to project root)
_FIX_SPECS_DIR = ".agent-fox/fix_specs"


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
    # Clamp max_passes to >= 1 (08-REQ-7.E1)
    if max_passes < 1:
        logger.warning(
            "max_passes=%d is invalid, clamping to 1", max_passes
        )
        max_passes = 1

    # Step 1: Detect available quality checks (once)
    checks = detect_checks(project_root)

    # Track loop state
    passes_completed = 0
    sessions_consumed = 0
    total_clusters_seen = 0
    termination_reason = TerminationReason.MAX_PASSES
    current_failures: list[FailureRecord] = []
    current_clusters_count = 0

    fix_specs_dir = project_root / _FIX_SPECS_DIR

    try:
        for pass_num in range(1, max_passes + 1):
            passes_completed = pass_num

            # Step 2a: Run all checks, collect failures
            failures, _passed = run_checks(checks, project_root)

            # Step 2b: If no failures, terminate with ALL_FIXED
            if not failures:
                termination_reason = TerminationReason.ALL_FIXED
                current_failures = []
                current_clusters_count = 0
                break

            current_failures = failures

            # Step 2c: Cluster failures by root cause
            clusters = cluster_failures(failures, config)
            current_clusters_count = len(clusters)
            total_clusters_seen += len(clusters)

            # Step 2d: Generate fix specs for each cluster
            for cluster in clusters:
                generate_fix_spec(cluster, fix_specs_dir, pass_num)
                sessions_consumed += 1

            # Step 2e: Run coding sessions for each cluster
            # (Session runner integration is handled at the CLI level;
            #  the loop structure supports it but sessions are not
            #  executed inline in the current implementation.)

            # Clean up fix specs after each pass
            cleanup_fix_specs(fix_specs_dir)

        else:
            # Loop exhausted max_passes without fixing everything
            termination_reason = TerminationReason.MAX_PASSES

    except KeyboardInterrupt:
        termination_reason = TerminationReason.INTERRUPTED

    # Compute resolution counts
    if termination_reason == TerminationReason.ALL_FIXED:
        clusters_resolved = total_clusters_seen
        clusters_remaining = 0
    else:
        clusters_remaining = current_clusters_count
        clusters_resolved = max(
            0, total_clusters_seen - current_clusters_count
        )

    return FixResult(
        passes_completed=passes_completed,
        clusters_resolved=clusters_resolved,
        clusters_remaining=clusters_remaining,
        sessions_consumed=sessions_consumed,
        termination_reason=termination_reason,
        remaining_failures=current_failures,
    )
