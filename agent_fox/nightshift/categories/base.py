"""Base class for two-phase hunt categories.

Provides the static-tool-then-AI detection pattern used by all
built-in categories.

Requirements: 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.nightshift.finding import Finding

logger = logging.getLogger(__name__)


class BaseHuntCategory:
    """Base class implementing the two-phase detection pattern.

    Subclasses override `_run_static_tool` and `_run_ai_analysis`
    to provide category-specific detection logic.

    When no static tool is available (static_tool=None), the category
    proceeds with AI-only analysis.

    Requirements: 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.E1
    """

    _name: str = ""
    _prompt_template: str = ""

    def __init__(
        self,
        config: object | None = None,
        backend: object | None = None,
        *,
        static_tool: object | None = ...,
    ) -> None:
        self._config = config
        self._backend = backend
        # Use sentinel to distinguish "not passed" from "passed as None"
        if static_tool is ...:
            self._static_tool: object | None = "default"
        else:
            self._static_tool = static_tool

    @property
    def name(self) -> str:
        """Category name identifier."""
        return self._name

    @property
    def prompt_template(self) -> str:
        """Category-specific prompt template for AI analysis."""
        return self._prompt_template

    async def detect(
        self,
        project_root: Path,
        config: object,
    ) -> list[Finding]:
        """Execute two-phase detection: static tool then AI analysis.

        If no static tool is available, proceeds with AI-only analysis.

        Requirements: 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.E1
        """
        static_output = ""
        if self._static_tool is not None:
            try:
                static_output = await self._run_static_tool(project_root)
            except Exception:
                logger.warning(
                    "Static tool failed for category '%s', proceeding with AI-only analysis",
                    self._name,
                    exc_info=True,
                )
                static_output = ""

        return await self._run_ai_analysis(project_root, static_output)

    async def _run_static_tool(self, project_root: Path) -> str:
        """Run static tooling and return output as a string.

        Override in subclasses.
        """
        return ""

    async def _run_ai_analysis(self, project_root: Path, static_output: str) -> list[Finding]:
        """Run AI analysis with optional static tool context.

        Override in subclasses.
        """
        return []
