"""Session runner tests.

Test Spec: TS-03-7 (success), TS-03-8 (SDK error), TS-03-9 (timeout),
           TS-03-E3 (is_error result),
           TS-18-8 (activity callback invoked),
           TS-18-9 (session works without callback),
           TS-18-E3 (callback exception does not crash session)
           AC-1, AC-2, AC-5 (tool telemetry recording — fixes #282)
Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.1, 03-REQ-6.2,
              03-REQ-6.E1, 18-REQ-2.1, 18-REQ-2.3, 18-REQ-2.E1,
              26-REQ-1.E1, 26-REQ-2.4
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.knowledge.sink import SinkDispatcher, ToolCall, ToolError
from agent_fox.session.backends.protocol import (
    AgentMessage,
    AssistantMessage,
    PermissionCallback,
    ResultMessage,
    ToolUseMessage,
)
from agent_fox.session.session import run_session
from agent_fox.ui.progress import ActivityCallback, ActivityEvent, abbreviate_arg
from agent_fox.workspace import WorkspaceInfo

# -- Mock backend for testing ---


class MockBackend:
    """A mock AgentBackend that yields pre-configured canonical messages."""

    def __init__(
        self,
        messages: list[AgentMessage] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._messages = messages or []
        self._error = error
        self.last_prompt: str | None = None
        self.last_system_prompt: str | None = None
        self.last_model: str | None = None
        self.last_cwd: str | None = None

    @property
    def name(self) -> str:
        return "mock"

    async def execute(
        self,
        prompt: str,
        *,
        system_prompt: str,
        model: str,
        cwd: str,
        permission_callback: PermissionCallback | None = None,
        activity_callback: ActivityCallback | None = None,
        node_id: str = "",
        archetype: str | None = None,
        tools: list | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        fallback_model: str | None = None,
        thinking: dict | None = None,
    ) -> AsyncIterator[AgentMessage]:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        self.last_model = model
        self.last_cwd = cwd

        if self._error is not None:
            raise self._error

        turn = 0
        for msg in self._messages:
            # Fire activity events from ToolUseMessages when a callback is registered.
            # This mirrors the behaviour of ClaudeBackend's notification hook so that
            # session-runner tests (which use MockBackend) remain valid.
            if activity_callback is not None and isinstance(msg, ToolUseMessage):
                turn += 1
                arg = ""
                for v in msg.tool_input.values():
                    if isinstance(v, str):
                        arg = abbreviate_arg(v)
                        break
                event = ActivityEvent(
                    node_id=node_id,
                    tool_name=msg.tool_name,
                    argument=arg,
                    turn=turn,
                    tokens=0,
                    archetype=archetype,
                )
                try:
                    activity_callback(event)
                except Exception:
                    pass
            yield msg

    async def close(self) -> None:
        pass


def _make_result(
    *,
    is_error: bool = False,
    input_tokens: int = 100,
    output_tokens: int = 200,
    duration_ms: int = 5000,
    error_message: str | None = None,
) -> ResultMessage:
    """Helper to create a canonical ResultMessage."""
    return ResultMessage(
        status="failed" if is_error else "completed",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        error_message=error_message,
        is_error=is_error,
    )


class TestSessionRunnerSuccess:
    """TS-03-7: Session runner returns completed outcome on success."""

    @pytest.mark.asyncio
    async def test_returns_completed_status(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session returns status 'completed'."""
        backend = MockBackend(
            [
                AssistantMessage(content="Working on it..."),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.status == "completed"

    @pytest.mark.asyncio
    async def test_captures_token_usage(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session captures input and output token counts."""
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(input_tokens=100, output_tokens=200),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(duration_ms=5000),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.duration_ms == 5000

    @pytest.mark.asyncio
    async def test_no_error_message_on_success(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Successful session has no error message."""
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.error_message is None

    @pytest.mark.asyncio
    async def test_outcome_has_correct_spec_and_group(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Outcome spec_name and task_group match the workspace."""
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(error=Exception("boom"))

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.status == "failed"

    @pytest.mark.asyncio
    async def test_sdk_error_captures_message(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """The SDK error message is captured in the outcome."""
        backend = MockBackend(error=Exception("boom"))

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(),
            ]
        )

        async def mock_with_timeout(coro, timeout_minutes):
            del timeout_minutes
            coro.close()
            raise TimeoutError()

        with patch(
            "agent_fox.session.session.with_timeout",
            side_effect=mock_with_timeout,
        ):
            outcome = await run_session(
                workspace_info,
                "03:1",
                "sys prompt",
                "task prompt",
                short_timeout_config,
                backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(
                    is_error=True,
                    error_message="something went wrong",
                    input_tokens=50,
                    output_tokens=100,
                    duration_ms=3000,
                ),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.status == "failed"

    @pytest.mark.asyncio
    async def test_is_error_captures_error_message(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Error details are captured from a ResultMessage with is_error."""
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(
                    is_error=True,
                    error_message="something went wrong",
                    input_tokens=50,
                    output_tokens=100,
                    duration_ms=3000,
                ),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.error_message is not None


class TestSessionRunnerResultHandling:
    """Regression tests for result parsing and timeout partial metrics."""

    @pytest.mark.asyncio
    async def test_canonical_result_tokens_are_captured(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Token counts from canonical ResultMessage are captured correctly."""
        backend = MockBackend(
            [
                _make_result(input_tokens=12, output_tokens=34, duration_ms=4321),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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


class TestSessionRunnerActivityCallback:
    """TS-18-8: Session runner activity callback invoked."""

    @pytest.mark.asyncio
    async def test_callback_invoked_for_tool_use(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """run_session invokes the activity callback for tool-use messages."""
        events: list[ActivityEvent] = []

        backend = MockBackend(
            [
                ToolUseMessage(
                    tool_name="Read",
                    tool_input={"file_path": "/some/path/config.py"},
                ),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        events: list[ActivityEvent] = []

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={"file_path": "/a.py"}),
                ToolUseMessage(tool_name="Edit", tool_input={"file_path": "/b.py"}),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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
        backend = MockBackend(
            [
                AssistantMessage(content="Working..."),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
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

        def raising_cb(event):
            raise ZeroDivisionError("boom")

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={"file_path": "/foo.py"}),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "03:1",
            "sys prompt",
            "task prompt",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            activity_callback=raising_cb,
        )

        assert outcome.status == "completed"


# ---------------------------------------------------------------------------
# AC-1, AC-2, AC-5: Tool telemetry recording (fixes #282)
# ---------------------------------------------------------------------------


class TestSessionRunnerRecordsToolCalls:
    """AC-1: record_tool_call is invoked for every ToolUseMessage.

    Each ToolUseMessage received from the backend must produce exactly one
    record_tool_call dispatch on the sink_dispatcher.
    """

    @pytest.mark.asyncio
    async def test_single_tool_call_recorded(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """A session with one ToolUseMessage records exactly one tool call."""
        recorded: list[ToolCall] = []

        sink = MagicMock()
        sink.record_tool_call.side_effect = lambda c: recorded.append(c)
        sink.record_tool_error = MagicMock()
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={"file_path": "/a.py"}),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-abc",
        )

        assert len(recorded) == 1
        assert recorded[0].tool_name == "Read"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_all_recorded(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """AC-1: N ToolUseMessages produce N tool_call records."""
        recorded: list[ToolCall] = []

        sink = MagicMock()
        sink.record_tool_call.side_effect = lambda c: recorded.append(c)
        sink.record_tool_error = MagicMock()
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={"file_path": "/a.py"}),
                ToolUseMessage(tool_name="Edit", tool_input={"file_path": "/b.py"}),
                ToolUseMessage(tool_name="Bash", tool_input={"command": "make test"}),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-abc",
        )

        assert len(recorded) == 3
        assert [r.tool_name for r in recorded] == ["Read", "Edit", "Bash"]

    @pytest.mark.asyncio
    async def test_tool_call_carries_node_id(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Recorded ToolCall has the correct node_id."""
        recorded: list[ToolCall] = []

        sink = MagicMock()
        sink.record_tool_call.side_effect = lambda c: recorded.append(c)
        sink.record_tool_error = MagicMock()
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={}),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "my-node:2",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-xyz",
        )

        assert len(recorded) == 1
        assert recorded[0].node_id == "my-node:2"
        assert recorded[0].session_id == "run-xyz"

    @pytest.mark.asyncio
    async def test_no_tool_calls_when_no_dispatcher(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """Session without sink_dispatcher completes without errors."""
        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={}),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
        )

        assert outcome.status == "completed"


class TestSessionRunnerRecordsToolErrors:
    """AC-2: record_tool_error is invoked when a session fails after tool use."""

    @pytest.mark.asyncio
    async def test_tool_error_recorded_on_is_error_result(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """AC-2: ResultMessage(is_error=True) after a tool use records a ToolError."""
        error_records: list[ToolError] = []

        sink = MagicMock()
        sink.record_tool_call = MagicMock()
        sink.record_tool_error.side_effect = lambda e: error_records.append(e)
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Bash", tool_input={"command": "make"}),
                _make_result(is_error=True, error_message="build failed"),
            ]
        )

        await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-err",
        )

        assert len(error_records) == 1
        assert error_records[0].tool_name == "Bash"

    @pytest.mark.asyncio
    async def test_no_tool_error_when_session_succeeds(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """No ToolError recorded when session ends successfully."""
        error_records: list[ToolError] = []

        sink = MagicMock()
        sink.record_tool_call = MagicMock()
        sink.record_tool_error.side_effect = lambda e: error_records.append(e)
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={}),
                _make_result(),
            ]
        )

        await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-ok",
        )

        assert len(error_records) == 0

    @pytest.mark.asyncio
    async def test_no_tool_error_without_tool_invocation(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """No ToolError recorded when session fails without any tool invocation."""
        error_records: list[ToolError] = []

        sink = MagicMock()
        sink.record_tool_call = MagicMock()
        sink.record_tool_error.side_effect = lambda e: error_records.append(e)
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                _make_result(is_error=True, error_message="init failure"),
            ]
        )

        await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-no-tool",
        )

        assert len(error_records) == 0


class TestSessionRunnerTelemetrySinkFailure:
    """AC-5: Sink failures in telemetry methods do not crash the session."""

    @pytest.mark.asyncio
    async def test_record_tool_call_failure_does_not_crash_session(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """AC-5: If record_tool_call raises, the session continues and completes."""
        sink = MagicMock()
        sink.record_tool_call.side_effect = RuntimeError("DB connection lost")
        sink.record_tool_error = MagicMock()
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Read", tool_input={}),
                _make_result(),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-fail",
        )

        # Session must complete successfully despite sink failure
        assert outcome.status == "completed"

    @pytest.mark.asyncio
    async def test_record_tool_error_failure_does_not_crash_session(
        self,
        workspace_info: WorkspaceInfo,
        default_config: AgentFoxConfig,
    ) -> None:
        """AC-5: If record_tool_error raises, the session returns a result without crashing."""
        sink = MagicMock()
        sink.record_tool_call = MagicMock()
        sink.record_tool_error.side_effect = RuntimeError("DB connection lost")
        sink.record_session_outcome = MagicMock()
        sink.emit_audit_event = MagicMock()
        sink.close = MagicMock()

        dispatcher = SinkDispatcher([sink])

        backend = MockBackend(
            [
                ToolUseMessage(tool_name="Bash", tool_input={"command": "make"}),
                _make_result(is_error=True, error_message="build failed"),
            ]
        )

        outcome = await run_session(
            workspace_info,
            "test:1",
            "sys",
            "task",
            default_config,
            backend=backend,  # type: ignore[arg-type]
            sink_dispatcher=dispatcher,
            run_id="run-err-sink-fail",
        )

        # Session must return a result without raising, even though the sink failed
        assert outcome is not None
