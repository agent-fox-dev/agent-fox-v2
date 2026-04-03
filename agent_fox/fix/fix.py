"""Iterative fix loop.

Runs quality checks, clusters failures, generates fix specs, runs coding
sessions, and iterates until all checks pass or a termination condition is met.

Requirements: 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3, 08-REQ-7.E1
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import FailureRecord, detect_checks, run_checks
from agent_fox.fix.clusterer import cluster_failures
from agent_fox.fix.events import CheckCallback, FixProgressCallback, FixProgressEvent
from agent_fox.fix.spec_gen import FixSpec, cleanup_fix_specs, generate_fix_spec

# A session runner callable: takes a FixSpec and returns cost consumed.
FixSessionRunner = Callable[[FixSpec], Awaitable[float]]

logger = logging.getLogger(__name__)

# Default output directory for fix specs (relative to project root)
_FIX_SPECS_DIR = ".agent-fox/fix_specs"


class TerminationReason(StrEnum):
    """Reason the fix loop terminated."""

    ALL_FIXED = "all_fixed"
    MAX_PASSES = "max_passes"
    COST_LIMIT = "cost_limit"
    INTERRUPTED = "interrupted"


# Canonical human-readable labels with Rich color styles.
TERMINATION_LABELS: dict[TerminationReason, tuple[str, str]] = {
    TerminationReason.ALL_FIXED: ("All checks pass", "green"),
    TerminationReason.MAX_PASSES: ("Max passes reached", "yellow"),
    TerminationReason.COST_LIMIT: ("Cost limit reached", "red"),
    TerminationReason.INTERRUPTED: ("Interrupted", "red"),
}


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
    session_runner: FixSessionRunner | None = None,
    progress_callback: FixProgressCallback | None = None,
    check_callback: CheckCallback | None = None,
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

    Optional callbacks (76-REQ-6.1, 76-REQ-6.E1):
    - progress_callback: called with a FixProgressEvent at key loop milestones.
    - check_callback: forwarded to run_checks for per-check start/done events.
    When either callback is None, the loop behaves identically to the
    pre-76 implementation (fully backward compatible).
    """

    def _emit(stage: str, detail: str = "", *, pass_num: int) -> None:
        """Helper: invoke progress_callback if set."""
        if progress_callback is not None:
            progress_callback(
                FixProgressEvent(
                    phase="repair",
                    pass_number=pass_num,
                    max_passes=max_passes,
                    stage=stage,
                    detail=detail,
                )
            )

    # Clamp max_passes to >= 1 (08-REQ-7.E1)
    if max_passes < 1:
        logger.warning("max_passes=%d is invalid, clamping to 1", max_passes)
        max_passes = 1

    # Step 1: Detect available quality checks (once)
    checks = detect_checks(project_root)

    # Track loop state
    passes_completed = 0
    sessions_consumed = 0
    total_cost = 0.0
    total_clusters_seen = 0
    termination_reason = TerminationReason.MAX_PASSES
    current_failures: list[FailureRecord] = []
    current_clusters_count = 0

    # 08-REQ-5.2: cost limit from orchestrator config
    cost_limit = config.orchestrator.max_cost

    fix_specs_dir = project_root / _FIX_SPECS_DIR

    try:
        for pass_num in range(1, max_passes + 1):
            passes_completed = pass_num

            # Emit pass-start milestone (76-REQ-4.1)
            _emit("checks_start", pass_num=pass_num)

            # Step 2a: Run all checks, collect failures
            failures, _passed = run_checks(checks, project_root, check_callback=check_callback)

            # Step 2b: If no failures, terminate with ALL_FIXED
            if not failures:
                termination_reason = TerminationReason.ALL_FIXED
                current_failures = []
                current_clusters_count = 0
                # Emit all-passed milestone (76-REQ-4.2)
                _emit("all_passed", pass_num=pass_num)
                break

            current_failures = failures

            # Step 2c: Cluster failures by root cause
            clusters = cluster_failures(failures, config)
            current_clusters_count = len(clusters)
            total_clusters_seen += len(clusters)

            # Emit clusters-found milestone (76-REQ-4.3)
            _emit("clusters_found", detail=str(len(clusters)), pass_num=pass_num)

            # Step 2d: Generate fix specs for each cluster
            # Step 2e: Run coding sessions for each fix spec
            cost_limit_hit = False
            for cluster in clusters:
                # 08-REQ-5.2: check cost limit before launching session
                if cost_limit is not None and total_cost >= cost_limit:
                    logger.warning(
                        "Cost limit reached ($%.2f >= $%.2f), stopping",
                        total_cost,
                        cost_limit,
                    )
                    cost_limit_hit = True
                    break

                fix_spec = generate_fix_spec(cluster, fix_specs_dir, pass_num)

                if session_runner is not None:
                    # Emit session-start milestone (76-REQ-4.4)
                    _emit("session_start", detail=cluster.label, pass_num=pass_num)
                    try:
                        session_cost = await session_runner(fix_spec)
                        total_cost += session_cost
                        _emit("session_done", pass_num=pass_num)
                    except Exception:
                        logger.warning(
                            "Fix session failed for '%s'",
                            cluster.label,
                            exc_info=True,
                        )
                        # Emit session-error milestone (76-REQ-4.E2)
                        _emit("session_error", detail=cluster.label, pass_num=pass_num)
                sessions_consumed += 1

            # Clean up fix specs after each pass
            cleanup_fix_specs(fix_specs_dir)

            if cost_limit_hit:
                termination_reason = TerminationReason.COST_LIMIT
                # Emit cost-limit milestone (76-REQ-4.E1)
                _emit("cost_limit", pass_num=pass_num)
                break

        else:
            # Loop exhausted max_passes: run a final check to verify
            # the outcome of the last pass (08-REQ-5.1).
            final_failures, _passed = run_checks(checks, project_root, check_callback=check_callback)
            if not final_failures:
                termination_reason = TerminationReason.ALL_FIXED
                current_failures = []
                current_clusters_count = 0
                _emit("all_passed", pass_num=max_passes)
            else:
                termination_reason = TerminationReason.MAX_PASSES
                current_failures = final_failures

    except KeyboardInterrupt:
        termination_reason = TerminationReason.INTERRUPTED

    # Compute resolution counts
    if termination_reason == TerminationReason.ALL_FIXED:
        clusters_resolved = total_clusters_seen
        clusters_remaining = 0
    else:
        clusters_remaining = current_clusters_count
        clusters_resolved = max(0, total_clusters_seen - current_clusters_count)

    return FixResult(
        passes_completed=passes_completed,
        clusters_resolved=clusters_resolved,
        clusters_remaining=clusters_remaining,
        sessions_consumed=sessions_consumed,
        termination_reason=termination_reason,
        remaining_failures=current_failures,
    )
