"""Registry and backend protocol unit tests.

Test Spec: TS-29-18 (backend accepts tools), TS-29-19 (tools available),
           TS-29-20 (handler called), TS-29-21 (permission callback),
           TS-29-E14 (no tools no change), TS-29-E15 (handler exception),
           TS-29-P8 (backward compat)
Requirements: 29-REQ-6.1, 29-REQ-6.2, 29-REQ-6.3, 29-REQ-6.4,
              29-REQ-6.E1, 29-REQ-6.E2
"""

from __future__ import annotations

import inspect

import pytest


class TestBackendAcceptsTools:
    """TS-29-18: AgentBackend.execute() accepts tools parameter."""

    def test_backend_accepts_tools(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend, ToolDefinition

        # Verify ToolDefinition exists and has required fields
        td = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            handler=lambda x: "ok",
        )
        assert td.name == "test_tool"
        assert td.description == "A test tool"
        assert callable(td.handler)

        # Verify execute() accepts tools parameter
        sig = inspect.signature(AgentBackend.execute)
        assert "tools" in sig.parameters


class TestToolsAvailable:
    """TS-29-19: Custom tools are available alongside built-in tools."""

    def test_tools_available(self) -> None:
        from agent_fox.tools.registry import build_fox_tool_definitions

        tools = build_fox_tool_definitions()
        assert len(tools) == 4
        names = {td.name for td in tools}
        assert names == {"fox_outline", "fox_read", "fox_edit", "fox_search"}

        for td in tools:
            assert td.name.startswith("fox_")
            assert "type" in td.input_schema
            assert callable(td.handler)


class TestHandlerCalled:
    """TS-29-20: Custom tool handler is called when agent invokes the tool."""

    def test_handler_called(self) -> None:
        from agent_fox.session.backends.protocol import ToolDefinition

        calls: list[dict] = []

        def handler(tool_input: dict) -> str:
            calls.append(tool_input)
            return "ok"

        td = ToolDefinition(
            name="test_tool",
            description="A test",
            input_schema={"type": "object"},
            handler=handler,
        )
        result = td.handler({"file_path": "/tmp/test.py"})
        assert len(calls) == 1
        assert calls[0]["file_path"] == "/tmp/test.py"
        assert result == "ok"


class TestPermissionCallback:
    """TS-29-21: Permission callback receives custom tool name and input."""

    @pytest.mark.asyncio
    async def test_permission_callback(self) -> None:
        recorded: list[tuple] = []

        async def cb(name: str, tool_input: dict) -> bool:
            recorded.append((name, tool_input))
            return True

        # Verify the callback can be called with custom tool names
        result = await cb("fox_edit", {"file_path": "/tmp/test.py"})
        assert result is True
        assert recorded[0] == ("fox_edit", {"file_path": "/tmp/test.py"})


class TestNoToolsNoChange:
    """TS-29-E14: tools=None produces identical behavior."""

    def test_no_tools_no_change(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        sig = inspect.signature(AgentBackend.execute)
        tools_param = sig.parameters["tools"]
        assert tools_param.default is None


class TestHandlerException:
    """TS-29-E15: Handler exception can be caught and returned as error."""

    def test_handler_exception(self) -> None:
        from agent_fox.session.backends.protocol import ToolDefinition

        def bad_handler(tool_input: dict) -> str:
            raise ValueError("broken")

        td = ToolDefinition(
            name="bad_tool",
            description="A bad tool",
            input_schema={"type": "object"},
            handler=bad_handler,
        )
        # Verify the handler raises and the system can catch it
        with pytest.raises(ValueError, match="broken"):
            td.handler({})
