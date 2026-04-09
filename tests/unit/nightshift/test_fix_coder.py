"""Unit tests for fix pipeline archetype usage (fix_coder).

Test Spec: TS-88-10, TS-88-11, TS-88-12
Requirements: 88-REQ-3.1, 88-REQ-3.2, 88-REQ-3.3
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.workspace import WorkspaceInfo

if TYPE_CHECKING:
    from agent_fox.nightshift.fix_types import TriageResult
    from agent_fox.nightshift.spec_builder import InMemorySpec


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


def _make_spec(task_prompt: str = "Fix the issue: test\n\nIssue #42\n\nSome body") -> InMemorySpec:
    """Return a minimal InMemorySpec-like object."""
    from agent_fox.nightshift.spec_builder import InMemorySpec

    return InMemorySpec(
        issue_number=42,
        title="test",
        task_prompt=task_prompt,
        system_context="Repository context here.",
        branch_name="fix/test",
    )


def _make_triage() -> TriageResult:
    """Return an empty TriageResult."""
    from agent_fox.nightshift.fix_types import TriageResult

    return TriageResult()


def _make_workspace() -> WorkspaceInfo:
    """Return a mock WorkspaceInfo."""
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test",
        spec_name="fix-issue-42",
        task_group=0,
    )


# ---------------------------------------------------------------------------
# TS-88-10: _build_coder_prompt uses fix_coder archetype
# Requirement: 88-REQ-3.1
# ---------------------------------------------------------------------------


class TestBuildCoderPromptArchetype:
    """Verify _build_coder_prompt passes archetype='fix_coder' to build_system_prompt."""

    def test_build_system_prompt_called_with_fix_coder(self) -> None:
        """build_system_prompt receives archetype='fix_coder'."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)
        spec = _make_spec()
        triage = _make_triage()

        with patch(
            "agent_fox.session.prompt.build_system_prompt",
            return_value="mocked-system-prompt",
        ) as mock_bsp:
            pipeline._build_coder_prompt(spec, triage)

        # Verify archetype keyword argument
        assert mock_bsp.called, "build_system_prompt was not called"
        call_kwargs = mock_bsp.call_args.kwargs
        assert call_kwargs.get("archetype") == "fix_coder", (
            f"Expected archetype='fix_coder', got {call_kwargs.get('archetype')!r}"
        )

    def test_build_system_prompt_not_called_with_coder(self) -> None:
        """build_system_prompt is NOT called with archetype='coder'."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)
        spec = _make_spec()
        triage = _make_triage()

        with patch(
            "agent_fox.session.prompt.build_system_prompt",
            return_value="mocked-system-prompt",
        ) as mock_bsp:
            pipeline._build_coder_prompt(spec, triage)

        call_kwargs = mock_bsp.call_args.kwargs
        assert call_kwargs.get("archetype") != "coder", (
            "build_system_prompt was called with archetype='coder' (expected 'fix_coder')"
        )


# ---------------------------------------------------------------------------
# TS-88-11: _build_coder_prompt does not append commit format
# Requirement: 88-REQ-3.3
# ---------------------------------------------------------------------------


class TestBuildCoderPromptNoCommitFormat:
    """Verify the task prompt is not modified with hardcoded commit format."""

    def test_task_prompt_unchanged_without_review_feedback(self) -> None:
        """Returned task prompt equals spec.task_prompt when review_feedback is None."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        original_task = "Fix the issue: test\n\nIssue #42\n\nSome body"
        spec = _make_spec(task_prompt=original_task)
        triage = _make_triage()

        with patch(
            "agent_fox.session.prompt.build_system_prompt",
            return_value="mocked-system-prompt",
        ):
            _, task_prompt = pipeline._build_coder_prompt(spec, triage, review_feedback=None)

        assert task_prompt == original_task, (
            f"task_prompt was modified; expected {original_task!r}, got {task_prompt!r}"
        )

    def test_task_prompt_has_no_hardcoded_nightshift_suffix(self) -> None:
        """task_prompt does not contain hardcoded commit format appended by the method."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)
        spec = _make_spec()
        triage = _make_triage()

        with patch(
            "agent_fox.session.prompt.build_system_prompt",
            return_value="mocked-system-prompt",
        ):
            _, task_prompt = pipeline._build_coder_prompt(spec, triage, review_feedback=None)

        # The method must not have appended a hardcoded commit format block
        assert "fix(#" not in task_prompt or task_prompt == spec.task_prompt, (
            "task_prompt contains 'fix(#' appended by _build_coder_prompt"
        )


# ---------------------------------------------------------------------------
# TS-88-12: _run_coder_session passes fix_coder archetype
# Requirement: 88-REQ-3.2
# ---------------------------------------------------------------------------


class TestRunCoderSessionArchetype:
    """Verify _run_coder_session calls _run_session with 'fix_coder'."""

    @pytest.mark.asyncio
    async def test_run_session_called_with_fix_coder(self) -> None:
        """_run_session is called with 'fix_coder' as the first argument."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 0
        mock_outcome.output_tokens = 0
        mock_outcome.cache_read_input_tokens = 0
        mock_outcome.cache_creation_input_tokens = 0

        spec = _make_spec()
        workspace = _make_workspace()

        with patch.object(
            pipeline,
            "_run_session",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_rs:
            await pipeline._run_coder_session(
                workspace,
                spec,
                "system-prompt",
                "task-prompt",
            )

        assert mock_rs.called, "_run_session was not called"
        first_arg = mock_rs.call_args[0][0]
        assert first_arg == "fix_coder", (
            f"Expected _run_session called with 'fix_coder', got {first_arg!r}"
        )

    @pytest.mark.asyncio
    async def test_run_session_not_called_with_coder(self) -> None:
        """_run_session is NOT called with 'coder' as the archetype."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        platform = MagicMock()
        pipeline = FixPipeline(config=config, platform=platform)

        mock_outcome = MagicMock()
        mock_outcome.input_tokens = 0
        mock_outcome.output_tokens = 0
        mock_outcome.cache_read_input_tokens = 0
        mock_outcome.cache_creation_input_tokens = 0

        spec = _make_spec()
        workspace = _make_workspace()

        with patch.object(
            pipeline,
            "_run_session",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_rs:
            await pipeline._run_coder_session(
                workspace,
                spec,
                "system-prompt",
                "task-prompt",
            )

        first_arg = mock_rs.call_args[0][0]
        assert first_arg != "coder", (
            "_run_session was called with 'coder' instead of 'fix_coder'"
        )
