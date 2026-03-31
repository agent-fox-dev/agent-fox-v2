"""TODO/FIXME resolution hunt category.

Scans for TODO, FIXME, HACK, and XXX comments that should be
addressed or converted to tracked issues.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class TodoFixmeCategory(BaseHuntCategory):
    """Detects TODO/FIXME comments for resolution."""

    _name = "todo_fixme"
    _prompt_template = (
        "Scan the codebase for TODO, FIXME, HACK, and XXX comments. "
        "For each one, assess whether it represents a real issue that "
        "should be tracked, a stale comment that can be removed, or a "
        "known limitation that should be documented. Group related "
        "TODOs by component or theme. Prioritise items that indicate "
        "bugs or security concerns.\n\n"
        "Static tool output:\n{static_output}"
    )
