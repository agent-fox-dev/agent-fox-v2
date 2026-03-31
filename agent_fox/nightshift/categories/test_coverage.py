"""Test coverage gaps hunt category.

Identifies modules, functions, and branches lacking adequate
test coverage.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class TestCoverageCategory(BaseHuntCategory):
    """Detects test coverage gaps in the codebase."""

    _name = "test_coverage"
    _prompt_template = (
        "Analyze the codebase for test coverage gaps. Identify "
        "modules, classes, and functions that lack unit tests or "
        "have insufficient branch coverage. Focus on critical paths, "
        "error handling, and edge cases. Consider both line coverage "
        "and meaningful assertion coverage.\n\n"
        "Static tool output:\n{static_output}"
    )
