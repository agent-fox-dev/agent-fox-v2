"""Built-in hunt category definitions.

Each category is a thin data class specifying a name and prompt template.
All share the two-phase detection pattern from BaseHuntCategory.

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


class DeprecatedAPICategory(BaseHuntCategory):
    """Detects usage of deprecated APIs and patterns."""

    _name = "deprecated_api"
    _prompt_template = (
        "Scan the codebase for usage of deprecated APIs, functions, "
        "classes, and patterns. Check for Python deprecation warnings, "
        "library-specific deprecations, and outdated patterns. For each "
        "finding, identify the deprecated API, the recommended "
        "replacement, and the migration effort required.\n\n"
        "Static tool output:\n{static_output}"
    )


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
