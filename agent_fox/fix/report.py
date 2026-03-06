"""Fix report rendering.

Renders the fix summary report to the console as plain text.

Requirements: 08-REQ-6.1, 08-REQ-6.2
"""

from __future__ import annotations

from rich.console import Console

from agent_fox.fix.loop import FixResult, TerminationReason  # noqa: F401

# Human-readable labels for termination reasons.
_REASON_LABELS: dict[TerminationReason, tuple[str, str]] = {
    TerminationReason.ALL_FIXED: ("All checks pass", "green"),
    TerminationReason.MAX_PASSES: ("Max passes reached", "yellow"),
    TerminationReason.COST_LIMIT: ("Cost limit reached", "red"),
    TerminationReason.INTERRUPTED: ("Interrupted", "red"),
}


def render_fix_report(result: FixResult, console: Console) -> None:
    """Render the fix summary report to the console.

    Displays:
    - Passes completed (e.g., "3 of 3 passes")
    - Clusters resolved vs remaining
    - Total sessions consumed
    - Termination reason (human-readable)
    - If failures remain: list of remaining failure summaries
    """
    reason_label, reason_style = _REASON_LABELS.get(
        result.termination_reason,
        (str(result.termination_reason), "white"),
    )

    console.print(f"Passes completed: {result.passes_completed}")
    console.print(f"Clusters resolved: {result.clusters_resolved}")
    console.print(f"Clusters remaining: {result.clusters_remaining}")
    console.print(f"Sessions consumed: {result.sessions_consumed}")
    console.print(
        f"Termination reason: [{reason_style}]{reason_label}[/{reason_style}]"
    )

    # Remaining failures detail
    if result.remaining_failures:
        console.print()
        console.print("[bold]Remaining failures:[/bold]")
        for failure in result.remaining_failures:
            summary = failure.output[:200].strip()
            console.print(
                f"  - [bold]{failure.check.name}[/bold] "
                f"(exit {failure.exit_code}): {summary}"
            )
