"""Fix report rendering.

Renders the fix summary report to the console using Rich.

Requirements: 08-REQ-6.1, 08-REQ-6.2
"""

from __future__ import annotations

from rich.console import Console

from agent_fox.fix.loop import FixResult  # noqa: F401


def render_fix_report(result: FixResult, console: Console) -> None:
    """Render the fix summary report to the console.

    Displays:
    - Passes completed (e.g., "3 of 3 passes")
    - Clusters resolved vs remaining
    - Total sessions consumed
    - Termination reason (human-readable)
    - If failures remain: list of remaining failure summaries
    """
    raise NotImplementedError
