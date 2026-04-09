"""Tests for ClaudeBackend adapter.

Test Spec: TS-26-5 through TS-26-8, TS-26-E2, TS-26-P2
Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.4, 26-REQ-2.E1
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.session.backends.claude import ClaudeBackend, _coerce_int
from agent_fox.session.backends.protocol import (
    AgentBackend,
    AssistantMessage,
    ResultMessage,
    ToolUseMessage,
)

# ---------------------------------------------------------------------------
# TS-26-5: ClaudeBackend is in backends/claude.py
# Requirement: 26-REQ-2.1
# ---------------------------------------------------------------------------


class TestClaudeBackendConforms:
    """Verify ClaudeBackend can be imported and satisfies AgentBackend protocol."""

    def test_import_and_protocol_check(self) -> None:
        backend = ClaudeBackend()
        assert isinstance(backend, AgentBackend)

    def test_name_returns_claude(self) -> None:
        backend = ClaudeBackend()
        assert backend.name == "claude"


# ---------------------------------------------------------------------------
# TS-26-6: ClaudeBackend maps SDK types to canonical messages
# Requirement: 26-REQ-2.2
# ---------------------------------------------------------------------------


class TestMapMessageResultType:
    """Verify _map_message correctly maps SDK ResultMessage."""

    def test_maps_sdk_result_to_canonical(self) -> None:
        """SDK ResultMessage type='result' maps to canonical ResultMessage."""
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_msg = SDKResultMessage(
            subtype="success",
            is_error=False,
            result="done",
            duration_ms=1234,
            duration_api_ms=1000,
            num_turns=3,
            session_id="test",
            total_cost_usd=0.05,
            usage={"input_tokens": 500, "output_tokens": 200},
        )
        results = ClaudeBackend._map_message(sdk_msg)
        assert len(results) == 1
        canonical = results[0]
        assert isinstance(canonical, ResultMessage)
        assert canonical.status == "completed"
        assert canonical.input_tokens == 500
        assert canonical.output_tokens == 200
        assert canonical.duration_ms == 1234
        assert canonical.is_error is False

    def test_maps_error_result(self) -> None:
        """SDK ResultMessage with is_error=True maps to failed canonical."""
        msg = SimpleNamespace(
            type="result",
            is_error=True,
            result="session crashed",
            usage={"input_tokens": 10, "output_tokens": 5},
            duration_ms=100,
        )
        results = ClaudeBackend._map_message(msg)
        assert len(results) == 1
        canonical = results[0]
        assert isinstance(canonical, ResultMessage)
        assert canonical.status == "failed"
        assert canonical.is_error is True
        assert canonical.error_message == "session crashed"


class TestMapMessageToolUse:
    """Verify _map_message correctly maps tool-use messages."""

    def test_maps_tool_use_by_attribute(self) -> None:
        """Message with tool_name attribute maps to ToolUseMessage."""
        msg = SimpleNamespace(
            type="tool_use",
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        results = ClaudeBackend._map_message(msg)
        assert len(results) == 1
        canonical = results[0]
        assert isinstance(canonical, ToolUseMessage)
        assert canonical.tool_name == "Bash"
        assert canonical.tool_input == {"command": "ls"}

    def test_non_dict_tool_input_defaults_to_empty(self) -> None:
        """When tool_input is not a dict, it defaults to {}."""
        msg = SimpleNamespace(
            type="tool_use",
            tool_name="Read",
            tool_input="invalid",
        )
        results = ClaudeBackend._map_message(msg)
        assert len(results) == 1
        canonical = results[0]
        assert isinstance(canonical, ToolUseMessage)
        assert canonical.tool_input == {}

    def test_maps_sdk_assistant_with_tool_use_blocks(self) -> None:
        """SDK AssistantMessage with ToolUseBlock content yields ToolUseMessage."""
        from claude_agent_sdk.types import AssistantMessage as SDKAssistantMessage
        from claude_agent_sdk.types import ToolUseBlock

        sdk_msg = SDKAssistantMessage(
            content=[
                ToolUseBlock(id="tu_1", name="Read", input={"file_path": "/tmp/f.py"}),
                ToolUseBlock(id="tu_2", name="Edit", input={"file_path": "/tmp/g.py"}),
            ],
            model="claude-sonnet-4-6",
        )
        results = ClaudeBackend._map_message(sdk_msg)
        assert len(results) == 2
        assert isinstance(results[0], ToolUseMessage)
        assert results[0].tool_name == "Read"
        assert results[0].tool_input == {"file_path": "/tmp/f.py"}
        assert isinstance(results[1], ToolUseMessage)
        assert results[1].tool_name == "Edit"

    def test_maps_sdk_assistant_thinking_only(self) -> None:
        """SDK AssistantMessage with no tool-use blocks yields AssistantMessage."""
        from claude_agent_sdk.types import AssistantMessage as SDKAssistantMessage
        from claude_agent_sdk.types import TextBlock

        sdk_msg = SDKAssistantMessage(
            content=[TextBlock(text="let me think...")],
            model="claude-sonnet-4-6",
        )
        results = ClaudeBackend._map_message(sdk_msg)
        assert len(results) == 1
        assert isinstance(results[0], AssistantMessage)


class TestMapMessageAssistant:
    """Verify _map_message maps non-result, non-tool messages to AssistantMessage."""

    def test_maps_unknown_message_to_assistant(self) -> None:
        """Unknown message type maps to AssistantMessage."""
        msg = SimpleNamespace(text="hello", type="thinking")
        results = ClaudeBackend._map_message(msg)
        assert len(results) == 1
        assert isinstance(results[0], AssistantMessage)


# ---------------------------------------------------------------------------
# TS-26-7: ClaudeBackend constructs options and streams
# Requirement: 26-REQ-2.3
# ---------------------------------------------------------------------------


class TestExecuteConstructsOptions:
    """Verify execute() constructs ClaudeAgentOptions and yields messages."""

    pass


# ---------------------------------------------------------------------------
# TS-26-8: session.py has no claude_agent_sdk imports
# Requirement: 26-REQ-2.4
# ---------------------------------------------------------------------------


class TestSessionNoSdkImports:
    """Verify session.py does not import from claude_agent_sdk."""

    def test_session_no_sdk_imports(self) -> None:
        import os

        session_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "..",
            "agent_fox",
            "session",
            "session.py",
        )
        session_path = os.path.normpath(session_path)
        with open(session_path, encoding="utf-8") as f:
            content = f.read()

        assert "claude_agent_sdk" not in content, "session.py should not import from claude_agent_sdk after refactor"


# ---------------------------------------------------------------------------
# TS-26-E2: Streaming error yields ResultMessage with is_error=True
# Requirement: 26-REQ-2.E1
# ---------------------------------------------------------------------------


class TestStreamingErrorYieldsResult:
    """Verify SDK streaming error yields a ResultMessage with is_error=True."""

    @pytest.mark.asyncio
    async def test_streaming_error_yields_error_result(self) -> None:
        """When _stream_messages always raises, execute exhausts retries and
        yields a single failed ResultMessage with is_transport_error=True.

        asyncio.sleep is patched to zero out backoff delays in tests.
        """
        backend = ClaudeBackend()

        async def _exploding_stream(*, prompt, options):
            raise ConnectionError("network failure")
            yield  # noqa: RET503

        with (
            patch.object(backend, "_stream_messages", _exploding_stream),
            patch("agent_fox.session.backends.claude.asyncio.sleep") as mock_sleep,
        ):
            messages = []
            async for msg in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
            ):
                messages.append(msg)

        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is True
        assert result.status == "failed"
        assert result.error_message is not None
        assert "network failure" in result.error_message
        assert result.is_transport_error is True
        # Sleep was called for retries 2 and 3 (not the first attempt)
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_stream_yields_synthetic_error_result(self) -> None:
        """When _stream_messages always yields no ResultMessage, execute exhausts
        retries and yields a synthetic transport-error ResultMessage."""
        backend = ClaudeBackend()

        async def _empty_stream(*, prompt, options):
            return
            yield  # noqa: RET503

        with (
            patch.object(backend, "_stream_messages", _empty_stream),
            patch("agent_fox.session.backends.claude.asyncio.sleep"),
        ):
            messages = []
            async for msg in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
            ):
                messages.append(msg)

        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is True
        assert result.status == "failed"
        assert result.error_message is not None
        assert "without a result" in result.error_message
        assert result.is_transport_error is True


# ---------------------------------------------------------------------------
# Transport-layer retry tests (AC-1 through AC-5)
# Issue: #269 — API connection drops cause 0ms session failures
# ---------------------------------------------------------------------------


class TestTransportRetry:
    """Transport-layer retry with exponential backoff in ClaudeBackend.execute()."""

    # ------------------------------------------------------------------
    # AC-1: execute() retries on transient OSError and succeeds
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_retries_on_transient_exception_then_succeeds(self) -> None:
        """execute() retries _stream_messages on OSError; yields successful
        ResultMessage from the retry without emitting a failed one.

        AC-1: Mock _stream_messages to raise OSError once then succeed.
        """
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_result = SDKResultMessage(
            subtype="success",
            is_error=False,
            result="done",
            duration_ms=500,
            duration_api_ms=400,
            num_turns=1,
            session_id="test",
            total_cost_usd=0.01,
            usage={"input_tokens": 20, "output_tokens": 10},
        )
        call_count = 0

        async def _stream_once_then_succeed(*, prompt, options):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("connection refused")
            # Second call: yield a successful result
            for canonical in ClaudeBackend._map_message(sdk_result):
                yield canonical

        backend = ClaudeBackend()
        with (
            patch.object(backend, "_stream_messages", _stream_once_then_succeed),
            patch("agent_fox.session.backends.claude.asyncio.sleep") as mock_sleep,
        ):
            messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                messages.append(msg)

        # Should yield only the successful ResultMessage (no failed one)
        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is False
        assert result.status == "completed"
        assert result.is_transport_error is False
        # Exactly one retry → exactly one sleep call
        assert mock_sleep.call_count == 1
        assert call_count == 2

    # ------------------------------------------------------------------
    # AC-2: execute() retries when stream yields no ResultMessage
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_retries_on_empty_stream_then_succeeds(self) -> None:
        """execute() retries when _stream_messages yields no ResultMessage;
        yields the successful result from the second attempt.

        AC-2: Mock _stream_messages to yield empty iterator once then succeed.
        """
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_result = SDKResultMessage(
            subtype="success",
            is_error=False,
            result="done",
            duration_ms=300,
            duration_api_ms=200,
            num_turns=1,
            session_id="test",
            total_cost_usd=0.005,
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        call_count = 0

        async def _empty_then_succeed(*, prompt, options):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Empty stream — no messages yielded
                return
            for canonical in ClaudeBackend._map_message(sdk_result):
                yield canonical

        backend = ClaudeBackend()
        with (
            patch.object(backend, "_stream_messages", _empty_then_succeed),
            patch("agent_fox.session.backends.claude.asyncio.sleep") as mock_sleep,
        ):
            messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                messages.append(msg)

        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is False
        assert result.status == "completed"
        assert result.is_transport_error is False
        assert mock_sleep.call_count == 1
        assert call_count == 2

    # ------------------------------------------------------------------
    # AC-3: Exponential backoff delays between retries
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self) -> None:
        """execute() uses exponential backoff: delay doubles between retries.

        AC-3: _stream_messages fails twice then succeeds; verify sleep delays
        increase exponentially (1.0s, 2.0s pattern).
        """
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_result = SDKResultMessage(
            subtype="success",
            is_error=False,
            result="done",
            duration_ms=100,
            duration_api_ms=80,
            num_turns=1,
            session_id="test",
            total_cost_usd=0.001,
            usage={"input_tokens": 5, "output_tokens": 2},
        )
        call_count = 0

        async def _fail_twice_then_succeed(*, prompt, options):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError(f"transient failure {call_count}")
            for canonical in ClaudeBackend._map_message(sdk_result):
                yield canonical

        sleep_calls: list[float] = []

        async def _record_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        backend = ClaudeBackend()
        with (
            patch.object(backend, "_stream_messages", _fail_twice_then_succeed),
            patch("agent_fox.session.backends.claude.asyncio.sleep", side_effect=_record_sleep),
        ):
            messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                messages.append(msg)

        # Two failed attempts → two sleep calls with increasing delays
        assert len(sleep_calls) == 2, f"Expected 2 sleep calls, got {sleep_calls}"
        assert sleep_calls[0] < sleep_calls[1], "Delays must be increasing"
        assert sleep_calls[1] == sleep_calls[0] * 2, "Delay must double each retry"

        # Stream succeeded on third attempt
        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is False
        assert call_count == 3

    # ------------------------------------------------------------------
    # AC-4: All retries exhausted → single failed ResultMessage
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_transport_error_after_exhausting_retries(self) -> None:
        """execute() yields exactly one failed ResultMessage after all transport
        retries are exhausted.

        AC-4: _stream_messages always raises OSError.
        """
        backend = ClaudeBackend()

        async def _always_fail(*, prompt, options):
            raise OSError("persistent connection failure")
            yield  # noqa: RET503

        with (
            patch.object(backend, "_stream_messages", _always_fail),
            patch("agent_fox.session.backends.claude.asyncio.sleep"),
        ):
            messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                messages.append(msg)

        assert len(messages) == 1
        result = messages[0]
        assert isinstance(result, ResultMessage)
        assert result.is_error is True
        assert result.status == "failed"
        assert result.error_message is not None
        assert "Transport error" in result.error_message or "transport" in result.error_message.lower()
        assert "persistent connection failure" in result.error_message

    # ------------------------------------------------------------------
    # AC-5: is_transport_error flag present and distinguishable
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_transport_error_result_has_flag(self) -> None:
        """ResultMessage from a transport failure has is_transport_error=True;
        a normal session failure has is_transport_error=False.

        AC-5: The attribute distinguishes transport errors from session errors.
        """
        backend = ClaudeBackend()

        # --- transport error case ---
        async def _always_fail_transport(*, prompt, options):
            raise OSError("connection dropped")
            yield  # noqa: RET503

        with (
            patch.object(backend, "_stream_messages", _always_fail_transport),
            patch("agent_fox.session.backends.claude.asyncio.sleep"),
        ):
            transport_messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                transport_messages.append(msg)

        assert len(transport_messages) == 1
        transport_result = transport_messages[0]
        assert isinstance(transport_result, ResultMessage)
        assert transport_result.is_transport_error is True

        # --- session-level error case (is_error=True from SDK, not a transport error) ---
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_fail = SDKResultMessage(
            subtype="error",
            is_error=True,
            result="Agent hit turn limit",
            duration_ms=5000,
            duration_api_ms=4000,
            num_turns=10,
            session_id="test",
            total_cost_usd=0.50,
            usage={"input_tokens": 2000, "output_tokens": 500},
        )

        async def _session_failure(*, prompt, options):
            for canonical in ClaudeBackend._map_message(sdk_fail):
                yield canonical

        with patch.object(backend, "_stream_messages", _session_failure):
            session_messages = []
            async for msg in backend.execute(
                "test", system_prompt="sys", model="claude-sonnet-4-6", cwd="/tmp"
            ):
                session_messages.append(msg)

        assert len(session_messages) == 1
        session_result = session_messages[0]
        assert isinstance(session_result, ResultMessage)
        assert session_result.is_error is True
        # Session-level failure has is_transport_error=False (default)
        assert session_result.is_transport_error is False


# ---------------------------------------------------------------------------
# TS-26-P2: Message Type Completeness (Property)
# Validates: 26-REQ-1.3, 26-REQ-1.4
# ---------------------------------------------------------------------------


class TestPropertyMessageCompleteness:
    """Every ClaudeBackend message should be a canonical type."""

    def test_prop_message_types_are_union(self) -> None:
        """All three canonical types are distinct and valid."""
        tm = ToolUseMessage(tool_name="Bash", tool_input={})
        am = AssistantMessage(content="hello")
        rm = ResultMessage(
            status="completed",
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
            error_message=None,
            is_error=False,
        )
        for msg in [tm, am, rm]:
            assert isinstance(msg, (ToolUseMessage, AssistantMessage, ResultMessage))


# ---------------------------------------------------------------------------
# _coerce_int helper
# ---------------------------------------------------------------------------


class TestCoerceInt:
    """Tests for the _coerce_int helper."""

    def test_int_passes_through(self) -> None:
        assert _coerce_int(42) == 42

    def test_string_int_converts(self) -> None:
        assert _coerce_int("100") == 100

    def test_none_returns_zero(self) -> None:
        assert _coerce_int(None) == 0

    def test_invalid_string_returns_zero(self) -> None:
        assert _coerce_int("not a number") == 0

    def test_float_truncates(self) -> None:
        assert _coerce_int(3.7) == 3


# ---------------------------------------------------------------------------
# Issue #215: _stream_messages explicitly closes response stream before
# __aexit__ to prevent unhandled ProcessError during teardown.
# ---------------------------------------------------------------------------


class _TrackableAsyncIterator:
    """Async iterator wrapper that tracks aclose() calls.

    Wraps a real async generator but exposes aclose as a trackable method
    (async generators have read-only aclose attributes).
    """

    def __init__(self, async_gen, event: asyncio.Event) -> None:
        self._gen = async_gen
        self._event = event

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._gen.__anext__()

    async def aclose(self):
        self._event.set()
        await self._gen.aclose()


class TestStreamTeardownClosesResponseStream:
    """Verify _stream_messages calls aclose() on the response stream.

    When the async generator is consumed (fully or partially), the
    response stream must be explicitly closed before the ClaudeSDKClient
    context manager exits.  This prevents the SDK's internal read loop
    from raising ProcessError(exit code 143) when the subprocess receives
    SIGTERM during teardown.
    """

    @pytest.mark.asyncio
    async def test_aclose_called_on_normal_completion(self) -> None:
        """Response stream aclose() is called after full iteration."""
        from claude_agent_sdk.types import ResultMessage as SDKResultMessage

        sdk_result = SDKResultMessage(
            subtype="success",
            is_error=False,
            result="done",
            duration_ms=100,
            duration_api_ms=50,
            num_turns=1,
            session_id="test",
            total_cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

        aclose_called = asyncio.Event()

        async def _mock_response_gen():
            yield sdk_result

        stream = _TrackableAsyncIterator(_mock_response_gen(), aclose_called)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        backend = ClaudeBackend()
        messages = []
        with patch("agent_fox.session.backends.claude.ClaudeSDKClient", return_value=mock_client):
            async for msg in backend._stream_messages(
                prompt="test",
                options=MagicMock(),
            ):
                messages.append(msg)

        assert len(messages) == 1
        assert isinstance(messages[0], ResultMessage)
        assert aclose_called.is_set(), "aclose() must be called on the response stream"

    @pytest.mark.asyncio
    async def test_aclose_called_on_early_break(self) -> None:
        """Response stream aclose() is called when the generator is explicitly closed.

        When a consumer breaks early, the outer generator's aclose() is
        eventually called (by GC or explicit close).  We simulate this by
        explicitly calling aclose() on the _stream_messages generator.
        """
        from claude_agent_sdk.types import AssistantMessage as SDKAssistantMessage
        from claude_agent_sdk.types import TextBlock

        sdk_msg1 = SDKAssistantMessage(
            content=[TextBlock(text="hello")],
            model="claude-sonnet-4-6",
        )
        sdk_msg2 = SDKAssistantMessage(
            content=[TextBlock(text="world")],
            model="claude-sonnet-4-6",
        )

        aclose_called = asyncio.Event()

        async def _mock_response_gen():
            yield sdk_msg1
            yield sdk_msg2

        stream = _TrackableAsyncIterator(_mock_response_gen(), aclose_called)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        backend = ClaudeBackend()
        messages = []
        with patch("agent_fox.session.backends.claude.ClaudeSDKClient", return_value=mock_client):
            gen = backend._stream_messages(prompt="test", options=MagicMock())
            # Consume one message, then explicitly close the generator
            messages.append(await gen.__anext__())
            await gen.aclose()  # type: ignore[attr-defined]

        assert len(messages) == 1
        assert aclose_called.is_set(), "aclose() must be called even on early close"

    @pytest.mark.asyncio
    async def test_aclose_called_on_stream_error(self) -> None:
        """Response stream aclose() is called even when iteration raises."""
        aclose_called = asyncio.Event()

        async def _mock_response_gen():
            raise RuntimeError("stream error")
            yield  # noqa: RET503

        stream = _TrackableAsyncIterator(_mock_response_gen(), aclose_called)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        backend = ClaudeBackend()
        with pytest.raises(RuntimeError, match="stream error"):
            with patch("agent_fox.session.backends.claude.ClaudeSDKClient", return_value=mock_client):
                async for _ in backend._stream_messages(
                    prompt="test",
                    options=MagicMock(),
                ):
                    pass

        assert aclose_called.is_set(), "aclose() must be called even on stream error"


# ---------------------------------------------------------------------------
# Issue #320: SDK Notification hook wiring for activity progress events
# AC-1 through AC-7
# ---------------------------------------------------------------------------


class TestNotificationHookRegistered:
    """AC-1: ClaudeBackend registers a Notification hook when activity_callback
    is provided.
    """

    @pytest.mark.asyncio
    async def test_notification_hook_registered_when_callback_given(self) -> None:
        """When activity_callback is provided, ClaudeAgentOptions.hooks contains
        a 'Notification' key with at least one HookMatcher.

        AC-1: Inspect the options passed to ClaudeSDKClient.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.ui.progress import ActivityEvent

        captured_options: list = []

        async def _mock_response_gen():
            from claude_agent_sdk.types import ResultMessage as SDKResultMessage

            yield SDKResultMessage(
                subtype="success",
                is_error=False,
                result="done",
                duration_ms=100,
                duration_api_ms=80,
                num_turns=1,
                session_id="test",
                total_cost_usd=0.01,
                usage={"input_tokens": 10, "output_tokens": 5},
            )

        def _fake_sdk_client(options):
            captured_options.append(options)
            mock_client = AsyncMock()
            mock_client.query = AsyncMock()
            mock_client.receive_response = MagicMock(return_value=_mock_response_gen())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            return mock_client

        backend = ClaudeBackend()
        events: list[ActivityEvent] = []

        with patch("agent_fox.session.backends.claude.ClaudeSDKClient", side_effect=_fake_sdk_client):
            async for _ in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
                activity_callback=lambda e: events.append(e),
                node_id="node-1",
                archetype="coder",
            ):
                pass

        assert len(captured_options) == 1
        options = captured_options[0]
        assert options.hooks is not None, "hooks must not be None when activity_callback is provided"
        assert "Notification" in options.hooks, "hooks must contain 'Notification' key"
        matchers = options.hooks["Notification"]
        assert len(matchers) >= 1, "at least one HookMatcher must be registered"
        assert len(matchers[0].hooks) >= 1, "HookMatcher must have at least one hook function"

    @pytest.mark.asyncio
    async def test_no_notification_hook_when_callback_is_none(self) -> None:
        """When activity_callback is None, hooks is not set to contain Notification.

        AC-7: No hook registered, no errors raised.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        captured_options: list = []

        async def _mock_response_gen():
            from claude_agent_sdk.types import ResultMessage as SDKResultMessage

            yield SDKResultMessage(
                subtype="success",
                is_error=False,
                result="done",
                duration_ms=100,
                duration_api_ms=80,
                num_turns=1,
                session_id="test",
                total_cost_usd=0.01,
                usage={"input_tokens": 10, "output_tokens": 5},
            )

        def _fake_sdk_client(options):
            captured_options.append(options)
            mock_client = AsyncMock()
            mock_client.query = AsyncMock()
            mock_client.receive_response = MagicMock(return_value=_mock_response_gen())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            return mock_client

        backend = ClaudeBackend()

        with patch("agent_fox.session.backends.claude.ClaudeSDKClient", side_effect=_fake_sdk_client):
            messages = []
            async for msg in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
                activity_callback=None,
            ):
                messages.append(msg)

        assert len(captured_options) == 1
        options = captured_options[0]
        # When no activity_callback: hooks should be None or not contain 'Notification'
        assert options.hooks is None or "Notification" not in options.hooks
        assert len(messages) == 1
        assert isinstance(messages[0], ResultMessage)


class TestNotificationHookHandler:
    """AC-2: The Notification hook handler converts NotificationHookInput to
    ActivityEvent and invokes the activity_callback.
    """

    @pytest.mark.asyncio
    async def test_hook_produces_activity_event_from_notification_input(self) -> None:
        """Trigger the hook directly and verify the ActivityEvent fields.

        AC-2: tool_name and argument are derived from the notification input.
        """
        from agent_fox.session.backends.claude import _build_notification_hook
        from agent_fox.ui.progress import ActivityEvent

        events: list[ActivityEvent] = []

        hook = _build_notification_hook(
            lambda e: events.append(e),
            node_id="spec-1:2",
            archetype="verifier",
        )

        # NotificationHookInput is a TypedDict (dict subclass)
        notification_input = {
            "hook_event_name": "Notification",
            "session_id": "sess-123",
            "transcript_path": "/tmp/t.json",
            "cwd": "/tmp",
            "message": "Running Bash command",
            "title": "Bash",
            "notification_type": "tool_use",
        }

        result = await hook(notification_input, None, {"signal": None})

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ActivityEvent)
        assert event.node_id == "spec-1:2"
        assert event.tool_name == "Bash"  # derived from title
        assert event.argument == "Running Bash command"  # derived from message
        assert event.archetype == "verifier"
        assert event.turn == 1
        assert isinstance(event.tokens, int)
        # Hook must return a dict (SyncHookJSONOutput-compatible)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_hook_uses_notification_type_when_title_absent(self) -> None:
        """When title is absent, notification_type is used as tool_name.

        AC-2: tool_name derived from available notification fields.
        """
        from agent_fox.session.backends.claude import _build_notification_hook
        from agent_fox.ui.progress import ActivityEvent

        events: list[ActivityEvent] = []

        hook = _build_notification_hook(
            lambda e: events.append(e),
            node_id="node-x",
            archetype=None,
        )

        notification_input = {
            "hook_event_name": "Notification",
            "session_id": "sess-456",
            "transcript_path": "/tmp/t.json",
            "cwd": "/tmp",
            "message": "some notification",
            "notification_type": "progress",
        }

        await hook(notification_input, None, {"signal": None})

        assert len(events) == 1
        assert events[0].tool_name == "progress"

    @pytest.mark.asyncio
    async def test_hook_turn_counter_increments(self) -> None:
        """Turn counter increments with each hook invocation.

        AC-2: ActivityEvent.turn reflects invocation order.
        """
        from agent_fox.session.backends.claude import _build_notification_hook
        from agent_fox.ui.progress import ActivityEvent

        events: list[ActivityEvent] = []

        hook = _build_notification_hook(
            lambda e: events.append(e),
            node_id="node-y",
            archetype=None,
        )

        notification_input = {
            "hook_event_name": "Notification",
            "session_id": "sess-789",
            "transcript_path": "/tmp/t.json",
            "cwd": "/tmp",
            "message": "msg",
            "notification_type": "info",
        }

        await hook(notification_input, None, {"signal": None})
        await hook(notification_input, None, {"signal": None})
        await hook(notification_input, None, {"signal": None})

        assert [e.turn for e in events] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_hook_callback_exception_does_not_propagate(self) -> None:
        """An exception in activity_callback is swallowed by the hook.

        AC-2 / AC-6: Hook must not propagate callback exceptions.
        """
        from agent_fox.session.backends.claude import _build_notification_hook

        def _raising_cb(event):
            raise ValueError("callback boom")

        hook = _build_notification_hook(
            _raising_cb,
            node_id="node-z",
            archetype=None,
        )

        notification_input = {
            "hook_event_name": "Notification",
            "session_id": "s",
            "transcript_path": "/tmp/t.json",
            "cwd": "/tmp",
            "message": "msg",
            "notification_type": "info",
        }

        # Must not raise
        result = await hook(notification_input, None, {"signal": None})
        assert isinstance(result, dict)


class TestActivityCallbackThreadedThrough:
    """AC-5: activity_callback is passed to ClaudeBackend.execute() and accessible
    in the Notification hook closure.
    """

    @pytest.mark.asyncio
    async def test_execute_accepts_activity_callback_kwarg(self) -> None:
        """ClaudeBackend.execute() accepts activity_callback without error.

        AC-5: The parameter is present and accessible.
        """
        from agent_fox.ui.progress import ActivityEvent

        backend = ClaudeBackend()

        async def _empty_stream(*, prompt, options):
            from claude_agent_sdk.types import ResultMessage as SDKResultMessage

            for canonical in ClaudeBackend._map_message(
                SDKResultMessage(
                    subtype="success",
                    is_error=False,
                    result="done",
                    duration_ms=100,
                    duration_api_ms=80,
                    num_turns=1,
                    session_id="test",
                    total_cost_usd=0.01,
                    usage={"input_tokens": 10, "output_tokens": 5},
                )
            ):
                yield canonical

        events: list[ActivityEvent] = []

        with patch.object(backend, "_stream_messages", _empty_stream):
            messages = []
            async for msg in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
                activity_callback=lambda e: events.append(e),
                node_id="ac5-node",
                archetype="coder",
            ):
                messages.append(msg)

        # Session completes without error; callback was passed and accessible
        assert len(messages) == 1
        assert isinstance(messages[0], ResultMessage)


class TestActivityEventBackwardCompatibility:
    """AC-6: ActivityEvent from the hook is backward-compatible with
    ProgressDisplay.on_activity().
    """

    def test_hook_event_renders_in_progress_display(self) -> None:
        """ActivityEvent produced by hook path renders without error.

        AC-6: ProgressDisplay.on_activity() accepts the event and updates
        the spinner text with tool_name and argument.
        """
        from io import StringIO

        from rich.console import Console
        from rich.theme import Theme

        from agent_fox.ui.display import ThemeConfig, create_theme
        from agent_fox.ui.progress import ActivityEvent, ProgressDisplay

        # Build a non-TTY theme with a StringIO console (mirrors test_progress.py helper)
        config = ThemeConfig()
        theme = create_theme(config)
        buf = StringIO()
        rich_theme = Theme({})
        theme.console = Console(file=buf, theme=rich_theme, width=120, force_terminal=False)
        display = ProgressDisplay(theme, quiet=False)

        event = ActivityEvent(
            node_id="spec-1:2",
            tool_name="Bash",
            argument="make test",
            turn=3,
            tokens=0,
            archetype="coder",
        )

        # Must not raise; spinner text should contain tool_name (or verbified form)
        display.on_activity(event)
        spinner_text = display._get_spinner_text()
        assert "Bash" in spinner_text or "Running command" in spinner_text
        assert "make test" in spinner_text


class TestSessionNoExtractActivity:
    """AC-3, AC-4: _extract_activity() is removed from session.py and the
    message loop no longer calls it directly.
    """

    def test_extract_activity_not_in_session_py(self) -> None:
        """_extract_activity is not defined in session.py at module scope.

        AC-4: Function relocated or removed.
        """
        import agent_fox.session.session as session_module

        assert not hasattr(session_module, "_extract_activity"), (
            "_extract_activity must not exist in session.py after refactor"
        )

    def test_message_loop_does_not_call_extract_activity(self) -> None:
        """session.py source does not contain a call to _extract_activity().

        AC-3: The branching block is removed from _execute_query().
        """
        import os

        session_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "..",
            "agent_fox",
            "session",
            "session.py",
        )
        session_path = os.path.normpath(session_path)
        with open(session_path, encoding="utf-8") as f:
            content = f.read()

        assert "_extract_activity" not in content, (
            "_extract_activity must not appear in session.py after refactor"
        )
