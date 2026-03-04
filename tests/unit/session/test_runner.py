"""Session runner tests.

Test Spec: TS-03-7 (success), TS-03-8 (SDK error), TS-03-9 (timeout),
           TS-03-E3 (is_error result)
Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.1, 03-REQ-6.2,
              03-REQ-6.E1
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.session.runner import run_session
from agent_fox.workspace.worktree import WorkspaceInfo

# -- Mock message types matching claude-code-sdk structure ---


@dataclass
class MockUsage:
    """Mock for SDK Usage object."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class MockResultMessage:
    """Mock for SDK ResultMessage."""

    type: str = "result"
    is_error: bool = False
    duration_ms: int = 5000
    usage: MockUsage | None = None
    result: str = ""

    def __post_init__(self) -> None:
        if self.usage is None:
            self.usage = MockUsage()


@dataclass
class MockAssistantMessage:
    """Mock for SDK AssistantMessage."""

    type: str = "assistant"
    content: str = "Working on the task..."


class TestSessionRunnerSuccess:
    """TS-03-7: Session runner returns completed outcome on success."""

    @pytest.mark.asyncio
    async def test_returns_completed_status(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session returns status 'completed'."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.status == "completed"

    @pytest.mark.asyncio
    async def test_captures_token_usage(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session captures input and output token counts."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.input_tokens == 100
        assert outcome.output_tokens == 200

    @pytest.mark.asyncio
    async def test_captures_duration(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session captures duration in milliseconds."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.duration_ms == 5000

    @pytest.mark.asyncio
    async def test_no_error_message_on_success(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session has no error message."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.error_message is None

    @pytest.mark.asyncio
    async def test_outcome_has_correct_spec_and_group(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Outcome spec_name and task_group match the workspace."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.spec_name == workspace_info.spec_name
        assert outcome.task_group == str(workspace_info.task_group)


class TestSessionRunnerSDKError:
    """TS-03-8: Session runner returns failed outcome on SDK error."""

    @pytest.mark.asyncio
    async def test_sdk_error_returns_failed_status(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """An SDK ProcessError results in a failed outcome."""
        with patch(
            "agent_fox.session.runner.query",
            side_effect=Exception("boom"),
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.status == "failed"

    @pytest.mark.asyncio
    async def test_sdk_error_captures_message(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """The SDK error message is captured in the outcome."""
        with patch(
            "agent_fox.session.runner.query",
            side_effect=Exception("boom"),
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.error_message is not None
        assert "boom" in outcome.error_message


class TestSessionRunnerTimeout:
    """TS-03-9: Session runner returns timeout outcome."""

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_status(
        self,
        workspace_info: WorkspaceInfo,
        short_timeout_config: AgentFoxConfig,
    ) -> None:
        """A timed-out session returns status 'timeout'."""

        async def mock_query_hangs(*args, **kwargs):
            yield MockAssistantMessage()
            # Hang indefinitely
            await asyncio.sleep(3600)
            yield MockResultMessage()  # Never reached

        with (
            patch(
                "agent_fox.session.runner.query",
                side_effect=mock_query_hangs,
            ),
            patch(
                "agent_fox.session.runner.with_timeout",
                side_effect=asyncio.TimeoutError,
            ),
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                short_timeout_config,
            )

        assert outcome.status == "timeout"


class TestSessionRunnerIsError:
    """TS-03-E3: ResultMessage with is_error produces failed outcome."""

    @pytest.mark.asyncio
    async def test_is_error_returns_failed_status(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """A ResultMessage with is_error=True produces a failed outcome."""
        result_msg = MockResultMessage(
            is_error=True,
            result="something went wrong",
            duration_ms=3000,
            usage=MockUsage(input_tokens=50, output_tokens=100),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.status == "failed"

    @pytest.mark.asyncio
    async def test_is_error_captures_error_message(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Error details are captured from a ResultMessage with is_error."""
        result_msg = MockResultMessage(
            is_error=True,
            result="something went wrong",
            duration_ms=3000,
            usage=MockUsage(input_tokens=50, output_tokens=100),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.runner.query",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.error_message is not None
