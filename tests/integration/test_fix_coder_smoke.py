"""Integration smoke test: fix pipeline coder session uses fix_coding.md.

Test Spec: TS-88-SMOKE-1
Requirements: 88-REQ-1.1, 88-REQ-3.1, 88-REQ-3.2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.workspace import WorkspaceInfo


def _make_workspace() -> WorkspaceInfo:
    """Return a mock WorkspaceInfo."""
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test",
        spec_name="fix-issue-42",
        task_group=0,
    )


def _make_config() -> MagicMock:
    """Return a minimal mock AgentFoxConfig."""
    config = MagicMock()
    config.archetypes.overrides.get.return_value = None
    config.archetypes.max_turns.get.return_value = None
    config.archetypes.thinking.get.return_value = None
    config.archetypes.models.get.return_value = None
    config.archetypes.allowlists.get.return_value = None
    config.security = None
    return config


# ---------------------------------------------------------------------------
# TS-88-SMOKE-1: Fix pipeline coder session uses fix_coding.md
# Execution Path 1 from design.md
# Requirements: 88-REQ-1.1, 88-REQ-3.1, 88-REQ-3.2
# ---------------------------------------------------------------------------


class TestFixPipelineUsesFix_CodingMd:
    """Smoke test: real prompt build uses fix_coding.md content."""

    def test_system_prompt_uses_fix_coding_template(self) -> None:
        """System prompt built by _build_coder_prompt uses fix_coding.md.

        Uses real build_system_prompt, get_archetype, and _load_template.
        Does NOT mock build_system_prompt or template loading.
        """
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.fix_types import TriageResult
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        spec = InMemorySpec(
            issue_number=42,
            title="Fix unused imports",
            task_prompt="Fix the issue: Fix unused imports\n\nIssue #42\n\nBody.",
            system_context="Repository context.",
            branch_name="fix/fix-unused-imports",
        )
        triage = TriageResult()

        # Build system prompt with real template loading (no mocking)
        system_prompt, task_prompt = pipeline._build_coder_prompt(spec, triage)

        # The system prompt must NOT contain spec-driven workflow text
        assert "task group" not in system_prompt.lower(), (
            "System prompt contains 'task group' — it likely came from coding.md, not fix_coding.md"
        )

        # The system prompt must NOT contain .specs/ references
        assert ".specs/" not in system_prompt, "System prompt contains '.specs/' — template isolation failed"

        # The system prompt must reference nightshift (from commit format instruction)
        assert "nightshift" in system_prompt.lower(), (
            "System prompt does not contain 'nightshift' — fix_coding.md template not used"
        )

        # The task prompt must contain the issue context from spec
        assert "42" in task_prompt, "task_prompt does not contain issue number '42'"

    @pytest.mark.asyncio
    async def test_run_coder_session_uses_fix_coder_archetype(self) -> None:
        """_run_coder_session calls _run_session with 'fix_coder'.

        Uses real _build_coder_prompt, mocks only _run_session to avoid
        actual execution.
        """
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.fix_types import TriageResult
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        spec = InMemorySpec(
            issue_number=42,
            title="Fix unused imports",
            task_prompt="Fix the issue: Fix unused imports\n\nIssue #42\n\nBody.",
            system_context="Repository context.",
            branch_name="fix/fix-unused-imports",
        )
        triage = TriageResult()
        workspace = _make_workspace()

        # Build real system prompt and task prompt
        system_prompt, task_prompt = pipeline._build_coder_prompt(spec, triage)

        # Mock only _run_session to avoid actual subprocess execution
        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 0
        mock_outcome.output_tokens = 0
        mock_outcome.cache_read_input_tokens = 0
        mock_outcome.cache_creation_input_tokens = 0

        with patch.object(
            pipeline,
            "_run_session",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_rs:
            await pipeline._run_coder_session(
                workspace,
                spec,
                system_prompt,
                task_prompt,
            )

        assert mock_rs.called, "_run_session was not called"
        first_arg = mock_rs.call_args[0][0]
        assert first_arg == "fix_coder", f"_run_session called with {first_arg!r}, expected 'fix_coder'"

    def test_system_prompt_does_not_contain_task_group_instructions(self) -> None:
        """System prompt does not contain spec-driven task group instructions."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.fix_types import TriageResult
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        spec = InMemorySpec(
            issue_number=99,
            title="Another issue",
            task_prompt="Fix the issue: Another issue\n\nIssue #99\n\nDetails.",
            system_context="Repo context.",
            branch_name="fix/another-issue",
        )
        triage = TriageResult()

        system_prompt, _ = pipeline._build_coder_prompt(spec, triage)

        # coding.md-specific phrases must NOT appear
        assert "Choose exactly one task group" not in system_prompt, (
            "System prompt contains coding.md task group instruction"
        )
        assert "tasks.md" not in system_prompt, "System prompt contains 'tasks.md' reference"
