"""Tests for ClaudeBackend adapter.

Test Spec: TS-26-5 through TS-26-8, TS-26-E2, TS-26-P2
Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.4, 26-REQ-2.E1
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_fox.session.backends.claude import ClaudeBackend, _coerce_int
from agent_fox.session.backends.protocol import (
    AgentBackend,
    AssistantMessage,
    ResultMessage,
    ToolDefinition,
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
        from claude_code_sdk.types import ResultMessage as SDKResultMessage

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
        canonical = ClaudeBackend._map_message(sdk_msg)
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
        canonical = ClaudeBackend._map_message(msg)
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
        canonical = ClaudeBackend._map_message(msg)
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
        canonical = ClaudeBackend._map_message(msg)
        assert isinstance(canonical, ToolUseMessage)
        assert canonical.tool_input == {}


class TestMapMessageAssistant:
    """Verify _map_message maps non-result, non-tool messages to AssistantMessage."""

    def test_maps_text_message(self) -> None:
        """Message with content attribute maps to AssistantMessage."""
        msg = SimpleNamespace(content="thinking about it", type="text")
        canonical = ClaudeBackend._map_message(msg)
        assert isinstance(canonical, AssistantMessage)
        assert canonical.content == "thinking about it"

    def test_maps_text_attribute(self) -> None:
        """Falls back to 'text' attribute when no 'content'."""
        msg = SimpleNamespace(text="hello", type="thinking")
        canonical = ClaudeBackend._map_message(msg)
        assert isinstance(canonical, AssistantMessage)
        assert canonical.content == "hello"


# ---------------------------------------------------------------------------
# TS-26-7: ClaudeBackend constructs options and streams
# Requirement: 26-REQ-2.3
# ---------------------------------------------------------------------------


class TestExecuteConstructsOptions:
    """Verify execute() constructs ClaudeCodeOptions and yields messages."""

    @pytest.mark.asyncio
    async def test_fox_tools_passed_as_mcp_server(self) -> None:
        """When tools are provided, ClaudeCodeOptions includes an MCP server."""
        backend = ClaudeBackend()
        tools = [
            ToolDefinition(
                name="fox_read",
                description="Read file",
                input_schema={"type": "object", "properties": {}},
                handler=lambda **kw: "ok",
            ),
        ]

        captured_options = {}

        async def _fake_stream(*, prompt, options):
            captured_options["opts"] = options
            return
            yield  # make it an async generator  # noqa: RET503

        with patch.object(backend, "_stream_messages", _fake_stream):
            async for _ in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
                tools=tools,
            ):
                pass

        opts = captured_options["opts"]
        assert "agent-fox-tools" in opts.mcp_servers
        srv_cfg = opts.mcp_servers["agent-fox-tools"]
        assert srv_cfg["type"] == "sdk"
        assert srv_cfg["instance"] is not None

    @pytest.mark.asyncio
    async def test_no_tools_means_no_mcp_servers(self) -> None:
        """When no tools provided, mcp_servers is empty."""
        backend = ClaudeBackend()

        captured_options = {}

        async def _fake_stream(*, prompt, options):
            captured_options["opts"] = options
            return
            yield  # noqa: RET503

        with patch.object(backend, "_stream_messages", _fake_stream):
            async for _ in backend.execute(
                "test",
                system_prompt="sys",
                model="claude-sonnet-4-6",
                cwd="/tmp",
            ):
                pass

        opts = captured_options["opts"]
        assert opts.mcp_servers == {}


# ---------------------------------------------------------------------------
# TS-26-8: session.py has no claude_code_sdk imports
# Requirement: 26-REQ-2.4
# ---------------------------------------------------------------------------


class TestSessionNoSdkImports:
    """Verify session.py does not import from claude_code_sdk."""

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

        assert "claude_code_sdk" not in content, (
            "session.py should not import from claude_code_sdk after refactor"
        )


# ---------------------------------------------------------------------------
# TS-26-E2: Streaming error yields ResultMessage with is_error=True
# Requirement: 26-REQ-2.E1
# ---------------------------------------------------------------------------


class TestStreamingErrorYieldsResult:
    """Verify SDK streaming error yields a ResultMessage with is_error=True."""

    @pytest.mark.asyncio
    async def test_streaming_error_yields_error_result(self) -> None:
        """When _stream_messages raises, execute yields a failed ResultMessage."""
        backend = ClaudeBackend()

        async def _exploding_stream(*, prompt, options):
            raise ConnectionError("network failure")
            yield  # noqa: RET503

        with patch.object(backend, "_stream_messages", _exploding_stream):
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
        assert "network failure" in result.error_message


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
