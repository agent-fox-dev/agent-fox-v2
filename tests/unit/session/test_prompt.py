"""Prompt builder tests.

Test Spec: TS-15-3 through TS-15-10, TS-15-E2 through TS-15-E6
Requirements: 15-REQ-2.1 through 15-REQ-5.E1

Supersedes the original TS-03-6 tests. The prompt builder now loads
templates from agent_fox/_templates/prompts/ and supports a ``role``
parameter, so the old inline-f-string tests are replaced.

Uses lazy imports inside test methods for functions that do not exist yet
(``_strip_frontmatter``, ``_TEMPLATE_DIR``) so that the file collects
successfully and individual tests fail at runtime.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.errors import ConfigError
from agent_fox.session.prompt import build_system_prompt, build_task_prompt

# ---------------------------------------------------------------------------
# TS-15-3: System prompt loads coding template
# Requirements: 15-REQ-2.1, 15-REQ-2.2
# ---------------------------------------------------------------------------


class TestSystemPromptCodingTemplate:
    """TS-15-3: build_system_prompt with role='coding' loads coding.md."""

    def test_contains_coder_archetype_keyword(self) -> None:
        """Output contains recognizable text from coding.md."""
        result = build_system_prompt("context", 2, "my_spec", role="coding")
        assert "CODER ARCHETYPE" in result

    def test_contains_git_workflow_section(self) -> None:
        """Output contains git workflow instructions (inlined in coding.md)."""
        result = build_system_prompt("context", 2, "my_spec", role="coding")
        assert "GIT WORKFLOW" in result


# ---------------------------------------------------------------------------
# TS-15-4: System prompt loads coordinator template
# Requirement: 15-REQ-2.3
# ---------------------------------------------------------------------------


class TestSystemPromptCoordinatorTemplate:
    """TS-15-4: build_system_prompt with role='coordinator' loads coordinator.md."""

    def test_contains_coordinator_agent_keyword(self) -> None:
        """Output contains recognizable text from coordinator.md."""
        result = build_system_prompt("context", 1, "my_spec", role="coordinator")
        assert "COORDINATOR AGENT" in result


# ---------------------------------------------------------------------------
# TS-15-5: Role parameter defaults to coding
# Requirement: 15-REQ-2.4
# ---------------------------------------------------------------------------


class TestRoleDefaultsToCoding:
    """TS-15-5: Omitting role defaults to coding template."""

    def test_default_role_is_coding(self) -> None:
        """Calling without role argument loads coding template."""
        result = build_system_prompt("context", 2, "my_spec")
        assert "CODER ARCHETYPE" in result


# ---------------------------------------------------------------------------
# TS-15-6: Context appended to system prompt
# Requirement: 15-REQ-2.5
# ---------------------------------------------------------------------------


class TestContextAppendedToSystemPrompt:
    """TS-15-6: The assembled context appears in the system prompt."""

    def test_context_present_in_output(self) -> None:
        """System prompt contains the exact context string."""
        result = build_system_prompt("unique_context_xyz", 2, "my_spec")
        assert "unique_context_xyz" in result


# ---------------------------------------------------------------------------
# TS-15-7: Placeholder interpolation
# Requirement: 15-REQ-3.1
# ---------------------------------------------------------------------------


class TestPlaceholderInterpolation:
    """TS-15-7: {spec_name} and {task_group} placeholders are replaced."""

    def test_spec_name_interpolated(self) -> None:
        """Output contains the spec_name value."""
        result = build_system_prompt("ctx", 3, "05_my_feature")
        assert "05_my_feature" in result

    def test_task_group_interpolated(self) -> None:
        """Output contains the task_group value as a string."""
        result = build_system_prompt("ctx", 3, "05_my_feature")
        assert "3" in result


# ---------------------------------------------------------------------------
# TS-15-8: Frontmatter stripped
# Requirement: 15-REQ-4.1
# ---------------------------------------------------------------------------


class TestFrontmatterStripped:
    """TS-15-8: YAML frontmatter is stripped from templates."""

    def test_frontmatter_not_in_output(self) -> None:
        """Output does NOT contain YAML frontmatter delimiters."""
        result = build_system_prompt("ctx", 1, "spec", role="coding")
        # Coding.md has no frontmatter; verify none leaks from any template
        assert "inclusion: always" not in result
        # Also verify no frontmatter delimiter at the start
        assert not result.startswith("---")


# ---------------------------------------------------------------------------
# TS-15-9: Task prompt contains spec name
# Requirement: 15-REQ-5.1
# ---------------------------------------------------------------------------


class TestTaskPromptContainsSpecName:
    """TS-15-9: Task prompt includes the spec name and task group."""

    def test_spec_name_in_task_prompt(self) -> None:
        """Task prompt contains the spec name."""
        result = build_task_prompt(3, "05_my_feature")
        assert "05_my_feature" in result

    def test_task_group_in_task_prompt(self) -> None:
        """Task prompt contains the task group number."""
        result = build_task_prompt(3, "05_my_feature")
        assert "3" in result


# ---------------------------------------------------------------------------
# TS-15-10: Task prompt contains quality instructions
# Requirements: 15-REQ-5.2, 15-REQ-5.3
# ---------------------------------------------------------------------------


class TestTaskPromptQualityInstructions:
    """TS-15-10: Task prompt mentions checkbox, commit, and quality gates."""

    def test_mentions_checkbox_or_task_updates(self) -> None:
        """Task prompt mentions checkbox/task status updates."""
        result = build_task_prompt(2, "my_spec")
        lower = result.lower()
        assert "checkbox" in lower or "task" in lower

    def test_mentions_commit(self) -> None:
        """Task prompt mentions committing changes."""
        result = build_task_prompt(2, "my_spec")
        assert "commit" in result.lower()

    def test_mentions_tests_or_quality(self) -> None:
        """Task prompt mentions tests or quality gates."""
        result = build_task_prompt(2, "my_spec")
        lower = result.lower()
        assert "test" in lower or "quality" in lower


# ===================================================================
# Edge Case Tests
# ===================================================================


# ---------------------------------------------------------------------------
# TS-15-E2: Missing template file raises ConfigError
# Requirement: 15-REQ-2.E1
# ---------------------------------------------------------------------------


class TestMissingTemplateRaisesConfigError:
    """TS-15-E2: Prompt builder raises ConfigError for missing template."""

    def test_missing_template_raises_config_error(self, tmp_path: Path) -> None:
        """ConfigError raised when a template file does not exist."""
        # Lazy import to avoid collection failure before implementation
        from agent_fox.session import prompt as prompt_mod  # type: ignore[attr-error]

        # Point _TEMPLATE_DIR to an empty temp directory
        with patch.object(prompt_mod, "_TEMPLATE_DIR", tmp_path):
            with pytest.raises(ConfigError):
                build_system_prompt("ctx", 1, "spec", role="coding")


# ---------------------------------------------------------------------------
# TS-15-E3: Unknown role raises ValueError
# Requirement: 15-REQ-2.E2
# ---------------------------------------------------------------------------


class TestUnknownRoleRaisesValueError:
    """TS-15-E3: Prompt builder raises ValueError for unknown role."""

    def test_invalid_role_raises_value_error(self) -> None:
        """ValueError raised for an unrecognized role string."""
        with pytest.raises(ValueError):
            build_system_prompt("ctx", 1, "spec", role="invalid")


# ---------------------------------------------------------------------------
# TS-15-E4: Template with literal braces preserved
# Requirement: 15-REQ-3.E1
# ---------------------------------------------------------------------------


class TestLiteralBracesPreserved:
    """TS-15-E4: Literal braces in templates don't cause interpolation errors."""

    def test_coordinator_json_braces_preserved(self) -> None:
        """Coordinator template's JSON examples with literal braces are preserved."""
        result = build_system_prompt("ctx", 1, "spec", role="coordinator")
        # coordinator.md contains JSON output format with literal braces
        assert "inter_spec_edges" in result


# ---------------------------------------------------------------------------
# TS-15-E5: Invalid task_group raises ValueError
# Requirement: 15-REQ-5.E1
# ---------------------------------------------------------------------------


class TestInvalidTaskGroupRaisesValueError:
    """TS-15-E5: Task prompt raises ValueError for task_group < 1."""

    def test_zero_task_group_raises(self) -> None:
        """ValueError raised when task_group is 0."""
        with pytest.raises(ValueError):
            build_task_prompt(0, "spec")

    def test_negative_task_group_raises(self) -> None:
        """ValueError raised when task_group is negative."""
        with pytest.raises(ValueError):
            build_task_prompt(-1, "spec")


# ---------------------------------------------------------------------------
# TS-15-E6: Template without frontmatter unchanged
# Requirement: 15-REQ-4.2
# ---------------------------------------------------------------------------


class TestTemplateWithoutFrontmatterUnchanged:
    """TS-15-E6: Templates without frontmatter are returned unchanged."""

    def test_no_frontmatter_content_unchanged(self) -> None:
        """Content without frontmatter passes through _strip_frontmatter unchanged."""
        # Lazy import: _strip_frontmatter doesn't exist yet
        from agent_fox.session.prompt import (  # type: ignore[attr-error]
            _strip_frontmatter,
        )

        content = "## CODING AGENT\n\nContent here"
        result = _strip_frontmatter(content)
        assert result == content
