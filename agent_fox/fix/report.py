"""Fix report rendering.

Renders the fix summary report to the console using Rich.

Requirements: 08-REQ-6.1, 08-REQ-6.2
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

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

    # Summary table
    table = Table(title="Fix Summary", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Passes completed", str(result.passes_completed))
    table.add_row("Clusters resolved", str(result.clusters_resolved))
    table.add_row("Clusters remaining", str(result.clusters_remaining))
    table.add_row("Sessions consumed", str(result.sessions_consumed))
    table.add_row(
        "Termination reason",
        f"[{reason_style}]{reason_label}[/{reason_style}]",
    )

    console.print(table)

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
