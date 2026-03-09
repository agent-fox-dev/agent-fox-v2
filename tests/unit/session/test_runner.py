"""Session runner tests.

Test Spec: TS-03-7 (success), TS-03-8 (SDK error), TS-03-9 (timeout),
           TS-03-E3 (is_error result),
           TS-18-8 (activity callback invoked),
           TS-18-9 (session works without callback),
           TS-18-E3 (callback exception does not crash session)
Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.1, 03-REQ-6.2,
              03-REQ-6.E1, 18-REQ-2.1, 18-REQ-2.3, 18-REQ-2.E1
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.session.session import run_session
from agent_fox.workspace.workspace import WorkspaceInfo

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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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

        async def mock_with_timeout(coro, timeout_minutes):
            del timeout_minutes
            coro.close()
            raise TimeoutError()

        with (
            patch(
                "agent_fox.session.session._query_messages",
                side_effect=mock_query_hangs,
            ),
            patch(
                "agent_fox.session.session.with_timeout",
                side_effect=mock_with_timeout,
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
            "agent_fox.session.session._query_messages",
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
            "agent_fox.session.session._query_messages",
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


class TestSessionRunnerResultHandling:
    """Regression tests for result parsing and timeout partial metrics."""

    @pytest.mark.asyncio
    async def test_dict_usage_tokens_are_captured(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Dict-shaped usage from current SDK versions is parsed correctly."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=4321,
            usage={  # type: ignore[arg-type]
                "input_tokens": 12,
                "output_tokens": 34,
            },
        )

        async def mock_query(*args, **kwargs):
            yield result_msg

        with patch(
            "agent_fox.session.session._query_messages",
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
        assert outcome.input_tokens == 12
        assert outcome.output_tokens == 34
        assert outcome.duration_ms == 4321

    @pytest.mark.asyncio
    async def test_missing_result_message_returns_failed(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """A stream with no ResultMessage is treated as a failed session."""

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()

        with patch(
            "agent_fox.session.session._query_messages",
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
        assert outcome.error_message is not None
        assert "without a result message" in outcome.error_message.lower()

    @pytest.mark.asyncio
    async def test_timeout_preserves_partial_metrics(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Timeout outcome includes partial metrics already observed."""

        async def mock_execute_query(*, state, **kwargs):
            state.input_tokens = 55
            state.output_tokens = 89
            state.duration_ms = 1300
            raise TimeoutError()

        with patch(
            "agent_fox.session.session._execute_query",
            side_effect=mock_execute_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
            )

        assert outcome.status == "timeout"
        assert outcome.input_tokens == 55
        assert outcome.output_tokens == 89
        assert outcome.duration_ms == 1300


# -- Mock tool-use message for activity callback tests ---


@dataclass
class MockToolUseMessage:
    """Mock for SDK tool-use message."""

    type: str = "tool_use"
    tool_name: str = "Read"
    tool_input: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.tool_input is None:
            self.tool_input = {"file_path": "/some/path/config.py"}


class TestSessionRunnerActivityCallback:
    """TS-18-8: Session runner activity callback invoked."""

    @pytest.mark.asyncio
    async def test_callback_invoked_for_tool_use(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """run_session invokes the activity callback for tool-use messages."""
        from agent_fox.ui.events import ActivityEvent

        events: list[ActivityEvent] = []

        tool_msg = MockToolUseMessage(
            tool_name="Read",
            tool_input={"file_path": "/some/path/config.py"},
        )
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield tool_msg
            yield result_msg

        with patch(
            "agent_fox.session.session._query_messages",
            side_effect=mock_query,
        ):
            await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
                activity_callback=lambda e: events.append(e),
            )

        assert len(events) >= 1
        assert isinstance(events[0], ActivityEvent)


class TestSessionRunnerActivityTurnAndTokens:
    """Activity events include turn count and cumulative tokens."""

    @pytest.mark.asyncio
    async def test_turn_and_tokens_populated(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Activity events carry incrementing turn and cumulative token counts."""
        from agent_fox.ui.events import ActivityEvent

        events: list[ActivityEvent] = []

        tool_msg1 = MockToolUseMessage(
            tool_name="Read",
            tool_input={"file_path": "/a.py"},
        )
        tool_msg2 = MockToolUseMessage(
            tool_name="Edit",
            tool_input={"file_path": "/b.py"},
        )
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield tool_msg1
            yield tool_msg2
            yield result_msg

        with patch(
            "agent_fox.session.session._query_messages",
            side_effect=mock_query,
        ):
            await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
                activity_callback=lambda e: events.append(e),
            )

        assert len(events) == 2
        assert events[0].turn == 1
        assert events[1].turn == 2
        # Tokens should be int (cumulative), not None
        assert isinstance(events[0].tokens, int)
        assert isinstance(events[1].tokens, int)


class TestSessionRunnerNoCallback:
    """TS-18-9: Session runner works without callback."""

    @pytest.mark.asyncio
    async def test_no_callback_works(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """run_session without activity_callback behaves identically."""
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        async def mock_query(*args, **kwargs):
            yield MockAssistantMessage()
            yield result_msg

        with patch(
            "agent_fox.session.session._query_messages",
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


class TestSessionRunnerCallbackException:
    """TS-18-E3: Activity callback exception does not crash session."""

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Exceptions in activity_callback are caught."""
        tool_msg = MockToolUseMessage()
        result_msg = MockResultMessage(
            is_error=False,
            duration_ms=5000,
            usage=MockUsage(input_tokens=100, output_tokens=200),
        )

        def raising_cb(event):
            raise ZeroDivisionError("boom")

        async def mock_query(*args, **kwargs):
            yield tool_msg
            yield result_msg

        with patch(
            "agent_fox.session.session._query_messages",
            side_effect=mock_query,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                default_config,
                activity_callback=raising_cb,
            )

        assert outcome.status == "completed"
