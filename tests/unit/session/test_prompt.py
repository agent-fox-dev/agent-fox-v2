"""Prompt builder tests.

Test Spec: TS-15-3 through TS-15-10, TS-15-E2 through TS-15-E6
Requirements: 15-REQ-2.1 through 15-REQ-5.E1

Tests updated after legacy template path removal (issue #342).
The prompt builder now uses 3-layer assembly exclusively.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.session.prompt import build_system_prompt, build_task_prompt

# ---------------------------------------------------------------------------
# TS-15-3: System prompt loads archetype profile
# Requirements: 15-REQ-2.1, 15-REQ-2.2
# ---------------------------------------------------------------------------


class TestSystemPromptCoderProfile:
    """TS-15-3: build_system_prompt with archetype='coder' loads coder profile."""

    def test_contains_coder_archetype_keyword(self) -> None:
        """Output contains recognizable text from coder profile."""
        result = build_system_prompt("context", archetype="coder")
        assert "Identity" in result

    def test_contains_git_workflow_section(self) -> None:
        """Output contains git workflow instructions (in coder profile)."""
        result = build_system_prompt("context", archetype="coder")
        assert "conventional commits" in result.lower()


# ---------------------------------------------------------------------------
# TS-15-5: Archetype defaults to coder
# Requirement: 15-REQ-2.4
# ---------------------------------------------------------------------------


class TestArchetypeDefaultsToCoder:
    """TS-15-5: Omitting archetype defaults to coder profile."""

    def test_default_archetype_is_coder(self) -> None:
        """Calling without archetype argument loads coder profile."""
        result = build_system_prompt("context")
        assert "Identity" in result


# ---------------------------------------------------------------------------
# TS-15-6: Context appended to system prompt
# Requirement: 15-REQ-2.5
# ---------------------------------------------------------------------------


class TestContextAppendedToSystemPrompt:
    """TS-15-6: The assembled context appears in the system prompt."""

    def test_context_present_in_output(self) -> None:
        """System prompt contains the exact context string."""
        result = build_system_prompt("unique_context_xyz")
        assert "unique_context_xyz" in result


# ---------------------------------------------------------------------------
# TS-15-8: Frontmatter stripped
# Requirement: 15-REQ-4.1
# ---------------------------------------------------------------------------


class TestFrontmatterStripped:
    """TS-15-8: YAML frontmatter is stripped from profiles."""

    def test_frontmatter_not_in_output(self) -> None:
        """Output does NOT contain YAML frontmatter delimiters at start."""
        result = build_system_prompt("ctx", archetype="coder")
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
# AC-2 (issue #534): build_task_prompt must not embed task group number
# in non-coder archetype prompts, regardless of the group_number passed.
# ---------------------------------------------------------------------------


class TestNonCoderTaskPromptOmitsGroupNumber:
    """AC-2 regression guard: verifier (and other non-coder archetypes)
    must never have a task group number in their task prompt, even if
    the node was formerly assigned a phantom group_number like 7."""

    def test_verifier_prompt_contains_spec_name_not_group_number(self) -> None:
        """build_task_prompt for verifier omits any task group reference."""
        result = build_task_prompt(
            task_group=7,  # phantom group that was the bug
            spec_name="08_parking_operator_adaptor",
            archetype="verifier",
        )
        assert "08_parking_operator_adaptor" in result, "Spec name must appear in prompt"
        assert "verifier" in result.lower(), "Archetype role must appear in prompt"
        # Must not instruct the agent to implement task group 7 (or any group)
        assert "task group" not in result.lower(), (
            f"Non-coder prompt must not reference 'task group': {result!r}"
        )
        assert "7" not in result, (
            f"Non-coder prompt must not embed phantom group number 7: {result!r}"
        )

    def test_reviewer_prompt_omits_group_number(self) -> None:
        """Non-coder prompt does not include the task group integer."""
        result = build_task_prompt(
            task_group=99,
            spec_name="my_spec",
            archetype="reviewer",
        )
        assert "my_spec" in result
        assert "99" not in result, (
            f"Non-coder prompt must not embed group number: {result!r}"
        )


# ---------------------------------------------------------------------------
# TS-15-E6: Profile without frontmatter unchanged
# Requirement: 15-REQ-4.2
# ---------------------------------------------------------------------------


class TestProfileWithoutFrontmatterUnchanged:
    """TS-15-E6: Profiles without frontmatter are returned unchanged."""

    def test_no_frontmatter_content_unchanged(self) -> None:
        """Content without frontmatter passes through _strip_frontmatter unchanged."""
        from agent_fox.session.profiles import _strip_frontmatter

        content = "## CODING AGENT\n\nContent here"
        result = _strip_frontmatter(content)
        assert result == content


# ---------------------------------------------------------------------------
# 3-layer assembly with project_dir
# ---------------------------------------------------------------------------


class TestThreeLayerAssemblyWithProjectDir:
    """Verify 3-layer assembly works correctly with project_dir."""

    def test_project_agent_profile_included(self, tmp_path: Path) -> None:
        """Agent profile content is included as Layer 1."""
        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "agent.md").write_text("PROJECT RULES")
        result = build_system_prompt("ctx", archetype="coder", project_dir=tmp_path)
        assert "PROJECT RULES" in result

    def test_mode_specific_profile(self, tmp_path: Path) -> None:
        """Mode-specific profile is loaded when mode is provided."""
        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "coder_fix.md").write_text("FIX MODE PROFILE")
        result = build_system_prompt("ctx", archetype="coder", mode="fix", project_dir=tmp_path)
        assert "FIX MODE PROFILE" in result
