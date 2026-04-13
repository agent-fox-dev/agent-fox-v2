"""Unit tests for fix branch push to upstream feature.

Test Spec: TS-93-1 through TS-93-9 (excluding TS-93-4 which is integration type),
           TS-93-E1 through TS-93-E4
Requirements: 93-REQ-1.1, 93-REQ-1.2, 93-REQ-1.E1,
              93-REQ-2.1, 93-REQ-2.2, 93-REQ-2.E1,
              93-REQ-3.1, 93-REQ-3.2, 93-REQ-3.3, 93-REQ-3.4,
              93-REQ-3.E1, 93-REQ-3.E2, 93-REQ-4.1

Note: TS-93-4 is an integration-type test and lives in
      tests/integration/nightshift/test_fix_branch_push_smoke.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from agent_fox.platform.github import IssueResult
from agent_fox.workspace import WorkspaceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_workspace(branch: str = "fix/1-test-issue") -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch=branch,
        spec_name="fix-issue-1",
        task_group=0,
    )


def _make_issue(number: int = 1, title: str = "test issue") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


def _make_config(*, push_fix_branch: bool = False, merge_strategy: str = "direct") -> MagicMock:
    config = MagicMock()
    config.night_shift.push_fix_branch = push_fix_branch
    config.night_shift.merge_strategy = merge_strategy
    config.orchestrator.retries_before_escalation = 1
    config.orchestrator.max_retries = 1
    return config


# ---------------------------------------------------------------------------
# TS-93-1: Config field defaults to false
# Requirement: 93-REQ-1.2
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    """Verify push_fix_branch defaults to False when absent."""

    def test_config_defaults_false(self) -> None:
        """NightShiftConfig() with no args must have push_fix_branch == False."""
        from agent_fox.nightshift.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.push_fix_branch is False


# ---------------------------------------------------------------------------
# TS-93-2: Config field reads true from dict
# Requirement: 93-REQ-1.1
# ---------------------------------------------------------------------------


class TestConfigReadsTrue:
    """Verify push_fix_branch is correctly read as True."""

    def test_config_reads_true(self) -> None:
        """NightShiftConfig(push_fix_branch=True) must have push_fix_branch == True."""
        from agent_fox.nightshift.config import NightShiftConfig

        config = NightShiftConfig(push_fix_branch=True)
        assert config.push_fix_branch is True


# ---------------------------------------------------------------------------
# TS-93-3: Branch name includes issue number
# Requirements: 93-REQ-2.1, 93-REQ-2.2
# ---------------------------------------------------------------------------


class TestBranchNameIncludesIssueNumber:
    """Verify sanitise_branch_name includes the issue number."""

    def test_branch_name_includes_issue_number(self) -> None:
        """sanitise_branch_name with issue_number=42 returns fix/42-unused-imports-in-utils."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name("Unused imports in utils", 42)
        assert result == "fix/42-unused-imports-in-utils"
        assert "42" in result

    def test_branch_name_starts_with_fix_prefix(self) -> None:
        """Branch name must always start with fix/."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name("Some issue title", 10)
        assert result.startswith("fix/")

    def test_branch_name_issue_number_before_slug(self) -> None:
        """Issue number appears immediately after fix/ prefix."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name("Fix broken tests", 99)
        # Should be fix/99-fix-broken-tests
        assert result.startswith("fix/99-")


# ---------------------------------------------------------------------------
# TS-93-5: Push NOT called when disabled
# Requirement: 93-REQ-3.3
# ---------------------------------------------------------------------------


class TestPushNotCalledWhenDisabled:
    """Verify push_to_remote is not called for fix branch when disabled."""

    @pytest.mark.asyncio
    async def test_push_not_called_when_disabled(self) -> None:
        """With push_fix_branch=False, _push_fix_branch_upstream must NOT be called."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config(push_fix_branch=False)
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]
        pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
        pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock(criteria=[], summary="ok")
        )

        push_upstream = AsyncMock(return_value=True)
        pipeline._push_fix_branch_upstream = push_upstream  # type: ignore[method-assign]

        await pipeline.process_issue(_make_issue(), issue_body="fix this")

        push_upstream.assert_not_called()


# ---------------------------------------------------------------------------
# TS-93-6: Force-push flag is set
# Requirement: 93-REQ-3.2
# ---------------------------------------------------------------------------


class TestForcePushFlag:
    """Verify push_to_remote is called with force=True."""

    @pytest.mark.asyncio
    async def test_force_push_flag(self) -> None:
        """_push_fix_branch_upstream must call push_to_remote with force=True."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = _make_config(push_fix_branch=True)
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        spec = InMemorySpec(
            issue_number=1,
            title="test issue",
            task_prompt="Fix this",
            system_context="context",
            branch_name="fix/1-test-issue",
        )
        workspace = _mock_workspace("fix/1-test-issue")

        with patch("agent_fox.workspace.git.push_to_remote", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = True
            await pipeline._push_fix_branch_upstream(spec, workspace)

        mock_push.assert_awaited_once()
        assert mock_push.call_args.kwargs.get("force") is True or (
            len(mock_push.call_args.args) > 2 and mock_push.call_args.args[2] is True
        ), "push_to_remote must be called with force=True"


# ---------------------------------------------------------------------------
# TS-93-7: Push failure does not block harvest
# Requirements: 93-REQ-3.E1, 93-REQ-3.E2
# ---------------------------------------------------------------------------


class TestPushFailureContinues:
    """Verify harvest still runs when push fails."""

    @pytest.mark.asyncio
    async def test_push_failure_continues(self, caplog: pytest.LogCaptureFixture) -> None:
        """When push raises an exception, harvest still runs and warning is logged."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config(push_fix_branch=True)
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        mock_harvest = AsyncMock(return_value="merged")

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = mock_harvest  # type: ignore[method-assign]
        pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
        pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock(criteria=[], summary="ok")
        )

        with patch(
            "agent_fox.workspace.git.push_to_remote",
            new_callable=AsyncMock,
            side_effect=Exception("network error"),
        ):
            with caplog.at_level(logging.WARNING):
                await pipeline.process_issue(_make_issue(), issue_body="fix this")

        # Harvest must still be called despite push failure
        mock_harvest.assert_awaited_once()
        # Warning must mention the failure reason
        assert "network error" in caplog.text


# ---------------------------------------------------------------------------
# TS-93-8: Independence from merge_strategy
# Requirement: 93-REQ-4.1
# ---------------------------------------------------------------------------


class TestIndependenceFromMergeStrategy:
    """Verify push_fix_branch works regardless of merge_strategy."""

    @pytest.mark.asyncio
    async def test_independence_from_merge_strategy(self) -> None:
        """push_to_remote called with force=True for both 'direct' and 'pr' strategies."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        for strategy in ("direct", "pr"):
            config = _make_config(push_fix_branch=True, merge_strategy=strategy)
            mock_platform = AsyncMock()
            mock_platform.add_issue_comment = AsyncMock()
            mock_platform.close_issue = AsyncMock()
            mock_platform.remove_label = AsyncMock()

            push_upstream = AsyncMock(return_value=True)

            pipeline = FixPipeline(config=config, platform=mock_platform)
            pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
            pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
            pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]
            pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
            pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
                return_value=MagicMock(criteria=[], summary="ok")
            )
            pipeline._push_fix_branch_upstream = push_upstream  # type: ignore[method-assign]

            await pipeline.process_issue(_make_issue(), issue_body="fix this")

            push_upstream.assert_awaited_once()
            assert push_upstream.await_count == 1, f"push not called for strategy={strategy}"
            push_upstream.reset_mock()


# ---------------------------------------------------------------------------
# TS-93-9: Remote branch not deleted after merge
# Requirement: 93-REQ-3.4
# ---------------------------------------------------------------------------


class TestNoRemoteBranchDelete:
    """Verify no remote branch deletion after merge."""

    @pytest.mark.asyncio
    async def test_no_remote_branch_delete(self) -> None:
        """After harvest, no git push --delete or :{branch} call is made."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config(push_fix_branch=True)
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()
        mock_platform.close_issue = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]
        pipeline._coder_review_loop = AsyncMock(return_value=True)  # type: ignore[method-assign]
        pipeline._run_triage = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock(criteria=[], summary="ok")
        )
        pipeline._push_fix_branch_upstream = AsyncMock(return_value=True)  # type: ignore[method-assign]

        run_git_calls: list[list[str]] = []

        async def capturing_run_git(args: list[str], **kwargs: object) -> tuple[int, str, str]:
            run_git_calls.append(args)
            return (0, "", "")

        with patch("agent_fox.workspace.git.run_git", capturing_run_git):
            await pipeline.process_issue(_make_issue(), issue_body="fix this")

        for call_args in run_git_calls:
            assert "--delete" not in call_args, f"Unexpected git push --delete in call: {call_args}"
            assert not (call_args and call_args[-1].startswith(":")), (
                f"Unexpected :<branch> delete pattern in call: {call_args}"
            )


# ---------------------------------------------------------------------------
# TS-93-E1: Non-boolean push_fix_branch rejected
# Requirement: 93-REQ-1.E1
# ---------------------------------------------------------------------------


class TestNonBooleanRejected:
    """Verify invalid boolean values raise ValidationError."""

    def test_config_rejects_non_bool_string(self) -> None:
        """NightShiftConfig(push_fix_branch='banana') must raise ValidationError."""
        from agent_fox.nightshift.config import NightShiftConfig

        with pytest.raises(ValidationError):
            NightShiftConfig(push_fix_branch="banana")  # type: ignore[arg-type]

    def test_config_rejects_non_bool_int(self) -> None:
        """NightShiftConfig(push_fix_branch=42) must raise ValidationError."""
        from agent_fox.nightshift.config import NightShiftConfig

        with pytest.raises(ValidationError):
            NightShiftConfig(push_fix_branch=42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-93-E2: Empty title produces valid branch name
# Requirement: 93-REQ-2.E1
# ---------------------------------------------------------------------------


class TestEmptyTitleBranchName:
    """Verify empty title produces fix/{N} branch name."""

    def test_empty_title_branch_name(self) -> None:
        """sanitise_branch_name('', 99) must return 'fix/99'."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name("", 99)
        assert result == "fix/99"


# ---------------------------------------------------------------------------
# TS-93-E3: Special-chars-only title produces valid branch name
# Requirement: 93-REQ-2.E1
# ---------------------------------------------------------------------------


class TestSpecialCharsTitleBranchName:
    """Verify special-chars-only title produces fix/{N} branch name."""

    def test_special_chars_title_branch_name(self) -> None:
        """sanitise_branch_name('!!@@##$$', 7) must return 'fix/7'."""
        from agent_fox.nightshift.spec_builder import sanitise_branch_name

        result = sanitise_branch_name("!!@@##$$", 7)
        assert result == "fix/7"


# ---------------------------------------------------------------------------
# TS-93-E4: Push failure logs reason
# Requirement: 93-REQ-3.E2
# ---------------------------------------------------------------------------


class TestPushFailureLogsReason:
    """Verify push failure logs the branch name and failure reason."""

    @pytest.mark.asyncio
    async def test_push_failure_logs_reason(self, caplog: pytest.LogCaptureFixture) -> None:
        """When push returns False, warning log must mention branch name and failure."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.spec_builder import InMemorySpec

        config = _make_config(push_fix_branch=True)
        mock_platform = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        spec = InMemorySpec(
            issue_number=1,
            title="test issue",
            task_prompt="Fix this",
            system_context="context",
            branch_name="fix/1-test-issue",
        )
        workspace = _mock_workspace("fix/1-test-issue")

        with patch("agent_fox.workspace.git.push_to_remote", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = False
            with caplog.at_level(logging.WARNING):
                result = await pipeline._push_fix_branch_upstream(spec, workspace)

        assert result is False
        assert "fix/1-test-issue" in caplog.text
        # At least one WARNING record
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warning_records, "Expected at least one WARNING log entry"
