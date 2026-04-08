"""Tests for af-spec skill guidance injection in spec generator.

Verifies that _generate_spec_package uses the af-spec skill template
to provide document-specific instructions to the AI, including wiring
verification rules in tasks.md generation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.nightshift.spec_gen import _load_spec_skill_guidance


class TestLoadSpecSkillGuidance:
    """Verify _load_spec_skill_guidance extracts per-document sections."""

    def test_loads_all_four_documents(self) -> None:
        """Guidance is loaded for requirements, design, test_spec, and tasks."""
        # Clear cache to force reload
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        guidance = _load_spec_skill_guidance()
        assert "requirements.md" in guidance
        assert "design.md" in guidance
        assert "test_spec.md" in guidance
        assert "tasks.md" in guidance

    def test_tasks_guidance_includes_wiring_verification(self) -> None:
        """The tasks.md guidance includes the wiring verification section."""
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        guidance = _load_spec_skill_guidance()
        tasks_guidance = guidance.get("tasks.md", "")
        assert "Wiring Verification" in tasks_guidance
        assert "Cross-spec entry point verification" in tasks_guidance

    def test_tasks_guidance_includes_errata_rule(self) -> None:
        """The tasks.md guidance includes the errata-cannot-satisfy rule."""
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        guidance = _load_spec_skill_guidance()
        tasks_guidance = guidance.get("tasks.md", "")
        assert "errata" in tasks_guidance.lower() or "deferral" in tasks_guidance.lower()

    def test_requirements_guidance_includes_ears(self) -> None:
        """The requirements.md guidance references EARS syntax."""
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        guidance = _load_spec_skill_guidance()
        req_guidance = guidance.get("requirements.md", "")
        assert "EARS" in req_guidance

    def test_design_guidance_includes_execution_paths(self) -> None:
        """The design.md guidance references execution paths."""
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        guidance = _load_spec_skill_guidance()
        design_guidance = guidance.get("design.md", "")
        assert "Execution Path" in design_guidance

    def test_returns_empty_dict_when_file_missing(self) -> None:
        """Returns empty dict when af-spec skill file is not found."""
        import agent_fox.nightshift.spec_gen as mod

        mod._SKILL_GUIDANCE_CACHE = None

        with patch("agent_fox.nightshift.spec_gen.Path.read_text", side_effect=OSError):
            guidance = _load_spec_skill_guidance()

        assert guidance == {}
        # Reset cache for other tests
        mod._SKILL_GUIDANCE_CACHE = None


class TestGuidanceInjectedIntoPrompt:
    """Verify _generate_spec_package injects guidance into system prompts."""

    @pytest.mark.asyncio
    async def test_system_prompt_includes_guidance_for_tasks(self) -> None:
        """When generating tasks.md, system prompt includes wiring verification."""
        from agent_fox.nightshift.spec_gen import SpecGenerator

        config = MagicMock()
        config.max_budget_usd = 100.0
        config.spec_gen_model_tier = "ADVANCED"

        gen = SpecGenerator(
            platform=MagicMock(),
            config=config,
            repo_root=Path("/tmp/test"),
        )

        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated content")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        from agent_fox.platform.github import IssueResult

        issue = IssueResult(
            number=99,
            title="Test issue",
            html_url="https://github.com/test/repo/issues/99",
        )

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await gen._generate_spec_package(issue, [], MagicMock())

        # Find the call that generated tasks.md (last of the 4 doc calls)
        assert mock_ai.call_count == 4
        tasks_call = mock_ai.call_args_list[3]
        system_prompt = tasks_call.kwargs.get("system", "") or tasks_call.args[0] if tasks_call.args else ""
        # The system kwarg should contain wiring verification guidance
        if isinstance(system_prompt, str):
            assert "Wiring Verification" in system_prompt
