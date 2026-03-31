"""Dependency freshness hunt category.

Scans for outdated or vulnerable dependencies using static
dependency checkers and AI analysis.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


class DependencyFreshnessCategory(BaseHuntCategory):
    """Detects outdated or vulnerable dependencies."""

    _name = "dependency_freshness"
    _prompt_template = (
        "Analyze the project's dependency files (requirements.txt, "
        "pyproject.toml, package.json, etc.) for outdated packages, "
        "known vulnerabilities, and version pinning issues. "
        "Consider both direct and transitive dependencies. "
        "Report each finding with the package name, current version, "
        "latest version, and any known CVEs.\n\n"
        "Static tool output:\n{static_output}"
    )
