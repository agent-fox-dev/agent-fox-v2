"""Dead code detection hunt category.

Identifies unreachable code, unused functions, classes, and
variables that can be safely removed.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class DeadCodeCategory(BaseHuntCategory):
    """Detects dead and unreachable code."""

    _name = "dead_code"
    _prompt_template = (
        "Analyze the codebase for dead code: unreachable branches, "
        "unused functions, unused classes, unused variables, and "
        "unused imports. Use static analysis output to identify "
        "candidates, then verify with AI analysis whether the code "
        "is truly unused or accessed via dynamic dispatch, plugins, "
        "or reflection.\n\n"
        "Static tool output:\n{static_output}"
    )
