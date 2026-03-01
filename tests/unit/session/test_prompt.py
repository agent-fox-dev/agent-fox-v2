"""Prompt builder tests.

Test Spec: TS-03-6 (system and task prompts)
Requirements: 03-REQ-5.1, 03-REQ-5.2
"""

from __future__ import annotations

from agent_fox.session.prompt import build_system_prompt, build_task_prompt


class TestPromptBuilder:
    """TS-03-6: Prompt builder produces system and task prompts."""

    def test_system_prompt_is_nonempty(self) -> None:
        """System prompt is non-empty."""
        sys_p = build_system_prompt("context text", 2, "my_spec")
        assert len(sys_p) > 0

    def test_system_prompt_mentions_task_group(self) -> None:
        """System prompt references the task group number."""
        sys_p = build_system_prompt("context text", 2, "my_spec")
        assert "2" in sys_p

    def test_system_prompt_mentions_spec_name(self) -> None:
        """System prompt references the spec name."""
        sys_p = build_system_prompt("context text", 2, "my_spec")
        assert "my_spec" in sys_p

    def test_system_prompt_includes_context(self) -> None:
        """System prompt includes the provided context."""
        sys_p = build_system_prompt("unique context text xyz", 2, "my_spec")
        assert "unique context text xyz" in sys_p

    def test_task_prompt_is_nonempty(self) -> None:
        """Task prompt is non-empty."""
        task_p = build_task_prompt(2, "my_spec")
        assert len(task_p) > 0

    def test_task_prompt_references_task_group(self) -> None:
        """Task prompt references the task group number."""
        task_p = build_task_prompt(2, "my_spec")
        assert "2" in task_p

    def test_task_prompt_references_spec(self) -> None:
        """Task prompt references the spec name."""
        task_p = build_task_prompt(2, "my_spec")
        assert "my_spec" in task_p
