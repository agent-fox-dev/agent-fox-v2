"""Phase 2 report rendering and combined report.

Requirements: 31-REQ-9.1, 31-REQ-9.2, 31-REQ-9.3, 31-REQ-9.E1
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

from agent_fox.fix.fix import FixResult, TerminationReason
from agent_fox.fix.improve import ImproveResult, ImproveTermination

# Human-readable labels for Phase 1 termination reasons.
_P1_REASON_LABELS: dict[TerminationReason, str] = {
    TerminationReason.ALL_FIXED: "All checks pass",
    TerminationReason.MAX_PASSES: "Max passes reached",
    TerminationReason.COST_LIMIT: "Cost limit reached",
    TerminationReason.INTERRUPTED: "Interrupted",
}

# Human-readable labels for Phase 2 termination reasons.
_P2_REASON_LABELS: dict[ImproveTermination, str] = {
    ImproveTermination.CONVERGED: "Converged (no further improvements)",
    ImproveTermination.PASS_LIMIT: "Pass limit reached",
    ImproveTermination.COST_LIMIT: "Cost limit reached",
    ImproveTermination.VERIFIER_FAIL: "Verifier rejected changes",
    ImproveTermination.INTERRUPTED: "Interrupted",
    ImproveTermination.ANALYZER_ERROR: "Analyzer error",
    ImproveTermination.CODER_ERROR: "Coder error",
}


def render_combined_report(
    fix_result: FixResult,
    improve_result: ImproveResult | None,
    total_cost: float,
    console: Console,
) -> None:
    """Render the combined Phase 1 + Phase 2 report.

    Phase 1 section: passes completed, clusters resolved/remaining,
    sessions consumed, termination reason.

    Phase 2 section (if present): passes completed (of max), improvements
    applied, improvements by tier, verifier verdicts, sessions consumed
    (by role), termination reason.

    Total cost line.

    Requirements: 31-REQ-9.1, 31-REQ-9.2, 31-REQ-9.E1
    """
    # -- Phase 1 --
    p1_label = _P1_REASON_LABELS.get(
        fix_result.termination_reason, str(fix_result.termination_reason)
    )
    _print = lambda msg: console.print(msg, highlight=False)  # noqa: E731

    _print("[bold]Phase 1: Repair[/bold]")
    _print(f"  Passes completed: {fix_result.passes_completed}")
    _print(f"  Clusters resolved: {fix_result.clusters_resolved}")
    _print(f"  Clusters remaining: {fix_result.clusters_remaining}")
    _print(f"  Sessions consumed: {fix_result.sessions_consumed}")
    _print(f"  Termination: {p1_label}")

    # -- Phase 2 (omit entirely when None) --
    if improve_result is not None:
        p2_label = _P2_REASON_LABELS.get(
            improve_result.termination_reason,
            str(improve_result.termination_reason),
        )
        console.print()
        _print("[bold]Phase 2: Improve[/bold]")
        _print(
            f"  Passes completed: {improve_result.passes_completed}"
            f" of {improve_result.max_passes}"
        )
        _print(
            f"  Improvements applied: "
            f"{improve_result.total_improvements}"
        )
        if improve_result.improvements_by_tier:
            for tier, count in improve_result.improvements_by_tier.items():
                _print(f"    {tier}: {count}")
        _print(
            f"  Verifier: {improve_result.verifier_pass_count} PASS, "
            f"{improve_result.verifier_fail_count} FAIL"
        )
        _print(f"  Sessions consumed: {improve_result.sessions_consumed}")
        _print(f"  Termination: {p2_label}")

    # -- Total cost --
    _print("")
    _print(f"Total cost: ${total_cost:.2f}")


def build_combined_json(
    fix_result: FixResult,
    improve_result: ImproveResult | None,
    total_cost: float,
) -> dict[str, Any]:
    """Build the JSONL-compatible dict for the combined report.

    Requirements: 31-REQ-9.3
    """
    summary: dict[str, Any] = {
        "phase1": {
            "passes_completed": fix_result.passes_completed,
            "clusters_resolved": fix_result.clusters_resolved,
            "clusters_remaining": fix_result.clusters_remaining,
            "sessions_consumed": fix_result.sessions_consumed,
            "termination_reason": str(fix_result.termination_reason),
        },
        "total_cost": total_cost,
    }

    if improve_result is not None:
        summary["phase2"] = {
            "passes_completed": improve_result.passes_completed,
            "max_passes": improve_result.max_passes,
            "total_improvements": improve_result.total_improvements,
            "improvements_by_tier": improve_result.improvements_by_tier,
            "verifier_pass_count": improve_result.verifier_pass_count,
            "verifier_fail_count": improve_result.verifier_fail_count,
            "sessions_consumed": improve_result.sessions_consumed,
            "termination_reason": str(improve_result.termination_reason),
        }

    return {
        "event": "complete",
        "summary": summary,
    }
