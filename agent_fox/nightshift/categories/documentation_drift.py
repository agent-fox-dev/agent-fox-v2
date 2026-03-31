"""Documentation drift hunt category.

Detects discrepancies between code and its documentation,
including outdated docstrings, stale README sections, and
missing API docs.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class DocumentationDriftCategory(BaseHuntCategory):
    """Detects documentation that has drifted from the code."""

    _name = "documentation_drift"
    _prompt_template = (
        "Compare the codebase documentation against the actual code. "
        "Check for outdated docstrings, stale README sections, "
        "inaccurate API documentation, missing parameter descriptions, "
        "and configuration docs that no longer match the code. Focus "
        "on user-facing documentation that could mislead developers.\n\n"
        "Static tool output:\n{static_output}"
    )
