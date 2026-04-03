"""Hunt category registry, scanner, and parallel dispatch.

Requirements: 61-REQ-3.1, 61-REQ-3.2, 61-REQ-3.3, 61-REQ-3.4, 61-REQ-3.E1
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_fox.nightshift.finding import Finding

logger = logging.getLogger(__name__)


@runtime_checkable
class HuntCategory(Protocol):
    """Interface for pluggable hunt categories.

    Requirements: 61-REQ-3.3
    """

    @property
    def name(self) -> str: ...

    @property
    def prompt_template(self) -> str: ...

    async def detect(
        self,
        project_root: Path,
        config: object,
    ) -> list[Finding]: ...


class HuntCategoryRegistry:
    """Registry of all available hunt categories.

    On instantiation, registers all eight built-in categories.

    Requirements: 61-REQ-3.1, 67-REQ-6.1
    """

    def __init__(self) -> None:
        self._categories: list[HuntCategory] = []
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the eight built-in hunt categories."""
        from agent_fox.nightshift.categories import (
            DeadCodeCategory,
            DependencyFreshnessCategory,
            DeprecatedAPICategory,
            DocumentationDriftCategory,
            LinterDebtCategory,
            QualityGateCategory,
            TestCoverageCategory,
            TodoFixmeCategory,
        )

        self._categories = [
            DependencyFreshnessCategory(),
            TodoFixmeCategory(),
            TestCoverageCategory(),
            DeprecatedAPICategory(),
            LinterDebtCategory(),
            DeadCodeCategory(),
            DocumentationDriftCategory(),
            QualityGateCategory(),
        ]

    def all(self) -> list[HuntCategory]:
        """Return all registered categories."""
        return list(self._categories)

    def enabled(self, config: object) -> list[HuntCategory]:
        """Return only categories enabled in configuration.

        Requirements: 61-REQ-3.2
        """
        categories_config = getattr(getattr(config, "night_shift", None), "categories", None)
        if categories_config is None:
            return list(self._categories)

        return [cat for cat in self._categories if getattr(categories_config, cat.name, True)]


class HuntScanner:
    """Coordinates parallel execution of hunt categories.

    Requirements: 61-REQ-3.4, 61-REQ-3.E1
    """

    def __init__(self, registry: HuntCategoryRegistry, config: object) -> None:
        self._registry = registry
        self._config = config

    async def run(self, project_root: Path) -> list[Finding]:
        """Execute all enabled categories in parallel, returning findings.

        Categories that fail are logged and skipped; remaining categories
        still produce their findings.

        Requirements: 61-REQ-3.4, 61-REQ-3.E1
        """
        enabled_cats = self._registry.enabled(self._config)
        if not enabled_cats:
            return []

        tasks = [self._run_category(cat, project_root) for cat in enabled_cats]
        results = await asyncio.gather(*tasks)

        all_findings: list[Finding] = []
        for findings in results:
            all_findings.extend(findings)
        return all_findings

    async def _run_category(self, category: HuntCategory, project_root: Path) -> list[Finding]:
        """Run a single category with error isolation.

        Requirements: 61-REQ-3.E1
        """
        try:
            return await category.detect(project_root, self._config)
        except Exception:
            logger.warning(
                "Hunt category '%s' failed",
                category.name,
                exc_info=True,
            )
            return []
