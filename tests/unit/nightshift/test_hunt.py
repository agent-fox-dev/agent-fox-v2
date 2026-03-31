"""Unit tests for HuntCategory, HuntCategoryRegistry, and HuntScanner.

Test Spec: TS-61-7, TS-61-8, TS-61-11, TS-61-12, TS-61-E6
Requirements: 61-REQ-3.1, 61-REQ-3.2, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3,
              61-REQ-4.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-61-7: Seven built-in hunt categories registered
# Requirement: 61-REQ-3.1
# ---------------------------------------------------------------------------


class TestHuntCategoryRegistry:
    """Verify that all seven categories are registered."""

    def test_seven_categories_registered(self) -> None:
        """Registry contains exactly the 7 built-in categories."""
        from agent_fox.nightshift.hunt import HuntCategoryRegistry

        registry = HuntCategoryRegistry()
        names = {cat.name for cat in registry.all()}
        expected = {
            "dependency_freshness",
            "todo_fixme",
            "test_coverage",
            "deprecated_api",
            "linter_debt",
            "dead_code",
            "documentation_drift",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# TS-61-8: Only enabled categories execute
# Requirement: 61-REQ-3.2
# ---------------------------------------------------------------------------


class TestEnabledCategoriesOnly:
    """Verify that disabled categories are skipped during a scan."""

    @pytest.mark.asyncio
    async def test_disabled_category_skipped(self) -> None:
        """When todo_fixme is disabled, its detect() is NOT called."""
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        config = MagicMock()
        config.night_shift.categories.todo_fixme = False
        # Enable all others
        for name in [
            "dependency_freshness",
            "test_coverage",
            "deprecated_api",
            "linter_debt",
            "dead_code",
            "documentation_drift",
        ]:
            setattr(config.night_shift.categories, name, True)

        registry = HuntCategoryRegistry()
        # Replace all categories with mocks
        mock_cats = {}
        for cat in registry.all():
            mock = AsyncMock()
            mock.name = cat.name
            mock.detect = AsyncMock(return_value=[])
            mock_cats[cat.name] = mock

        registry._categories = list(mock_cats.values())

        scanner = HuntScanner(registry, config)
        await scanner.run(Path("/tmp/test"))

        assert not mock_cats["todo_fixme"].detect.called
        # At least one other category should have been called
        assert mock_cats["linter_debt"].detect.called


# ---------------------------------------------------------------------------
# TS-61-11: Static tooling runs before AI analysis
# Requirements: 61-REQ-4.1, 61-REQ-4.2
# ---------------------------------------------------------------------------


class TestTwoPhaseDetection:
    """Verify the two-phase detection order."""

    @pytest.mark.asyncio
    async def test_static_before_ai(self) -> None:
        """Static tool output is passed to the AI agent."""
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.categories import DependencyFreshnessCategory

        config = MagicMock()
        backend = AsyncMock()

        call_order: list[str] = []

        async def mock_static(self: object, project_root: object) -> str:
            call_order.append("static")
            return "static tool output"

        async def mock_ai(
            self: object, project_root: object, static_output: str
        ) -> list[object]:
            call_order.append("ai")
            assert "static tool output" in static_output
            return []

        with (
            patch.object(
                DependencyFreshnessCategory, "_run_static_tool", mock_static
            ),
            patch.object(
                DependencyFreshnessCategory, "_run_ai_analysis", mock_ai
            ),
        ):
            cat = DependencyFreshnessCategory(config=config, backend=backend)
            await cat.detect(Path("/tmp/test"), config)

        assert call_order == ["static", "ai"]


# ---------------------------------------------------------------------------
# TS-61-12: Category-specific prompt templates
# Requirement: 61-REQ-4.3
# ---------------------------------------------------------------------------


class TestCategoryPromptTemplates:
    """Verify that each category has a distinct prompt template."""

    def test_distinct_prompt_templates(self) -> None:
        """Each of the 7 categories has a unique, non-empty prompt template."""
        from agent_fox.nightshift.hunt import HuntCategoryRegistry

        registry = HuntCategoryRegistry()
        templates = {cat.name: cat.prompt_template for cat in registry.all()}
        assert len(templates) == 7
        # All templates are distinct
        assert len(set(templates.values())) == 7
        # All templates are non-empty
        for t in templates.values():
            assert len(t) > 0


# ---------------------------------------------------------------------------
# TS-61-E6: No static tooling available
# Requirement: 61-REQ-4.E1
# ---------------------------------------------------------------------------


class TestNoStaticTooling:
    """Verify AI-only analysis when no static tools are available."""

    @pytest.mark.asyncio
    async def test_ai_only_analysis(self) -> None:
        """Category proceeds with AI-only when static tool is None."""
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.categories import LinterDebtCategory

        config = MagicMock()
        backend = AsyncMock()

        cat = LinterDebtCategory(config=config, backend=backend, static_tool=None)

        with patch.object(
            LinterDebtCategory,
            "_run_ai_analysis",
            AsyncMock(return_value=[]),
        ):
            findings = await cat.detect(Path("/tmp/test"), config)

        assert isinstance(findings, list)
