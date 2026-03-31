"""Deprecated API usage hunt category.

Scans for usage of deprecated APIs, functions, and patterns
that should be migrated to modern alternatives.

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from __future__ import annotations

from agent_fox.nightshift.categories.base import BaseHuntCategory


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
