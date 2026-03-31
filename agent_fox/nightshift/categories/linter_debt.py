"""Linter debt hunt category.

Scans for linter warnings, style violations, and code quality
issues using static linting tools and AI analysis.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class LinterDebtCategory(BaseHuntCategory):
    """Detects accumulated linter debt and style violations."""

    _name = "linter_debt"
    _prompt_template = (
        "Analyze the codebase for linter warnings, unused imports, "
        "style violations, and code quality issues. Use ruff, mypy, "
        "or equivalent tool output to identify concrete issues. "
        "Group findings by rule category (unused imports, type errors, "
        "naming conventions, etc.) and prioritise by impact on "
        "maintainability.\n\n"
        "Static tool output:\n{static_output}"
    )
