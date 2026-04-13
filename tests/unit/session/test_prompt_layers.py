"""Unit tests for 3-layer prompt assembly (spec 99).

Covers: TS-99-1, TS-99-E1
"""

from __future__ import annotations

from pathlib import Path


def test_3_layer_order(tmp_path: Path) -> None:
    """TS-99-1: Prompt layers appear in correct order.

    Layer 1: project context (CLAUDE.md)
    Layer 2: archetype profile
    Layer 3: task context

    Requirement: 99-REQ-1.1
    """
    from agent_fox.session.prompt import build_system_prompt

    # Layer 1: project context
    (tmp_path / "CLAUDE.md").write_text("PROJECT_CONTEXT_CONTENT")

    # Layer 2: custom profile
    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder.md").write_text("PROFILE_CONTENT_MARKER")

    # Layer 3: task context (passed as context string)
    task_context = "TASK_CONTEXT_MARKER"

    prompt = build_system_prompt(
        task_context,
        archetype="coder",
        project_dir=tmp_path,
    )

    idx_claude = prompt.index("PROJECT_CONTEXT_CONTENT")
    idx_profile = prompt.index("PROFILE_CONTENT_MARKER")
    idx_task = prompt.index("TASK_CONTEXT_MARKER")

    assert idx_claude < idx_profile < idx_task


def test_missing_claude_md(tmp_path: Path) -> None:
    """TS-99-E1: Prompt assembly works without CLAUDE.md.

    Requirement: 99-REQ-1.E1
    """
    from agent_fox.session.prompt import build_system_prompt

    # No CLAUDE.md in tmp_path — should not raise
    task_context = "TASK_CONTEXT_MARKER"

    prompt = build_system_prompt(
        task_context,
        archetype="coder",
        project_dir=tmp_path,
    )

    assert len(prompt) > 0
