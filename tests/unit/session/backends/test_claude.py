"""Tests for ClaudeBackend adapter.

Test Spec: TS-26-5 through TS-26-8, TS-26-E2, TS-26-P2
Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.4, 26-REQ-2.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-26-5: ClaudeBackend is in backends/claude.py
# Requirement: 26-REQ-2.1
# ---------------------------------------------------------------------------


class TestClaudeBackendConforms:
    """Verify ClaudeBackend can be imported and satisfies AgentBackend protocol."""

    def test_import_and_protocol_check(self) -> None:
        from agent_fox.session.backends.claude import ClaudeBackend
        from agent_fox.session.backends.protocol import AgentBackend

        backend = ClaudeBackend()
        assert isinstance(backend, AgentBackend)

    def test_name_returns_claude(self) -> None:
        from agent_fox.session.backends.claude import ClaudeBackend

        backend = ClaudeBackend()
        assert backend.name == "claude"


# ---------------------------------------------------------------------------
# TS-26-6: ClaudeBackend maps SDK types to canonical messages
# Requirement: 26-REQ-2.2
# ---------------------------------------------------------------------------


class TestSdkTypeMapping:
    """Verify the adapter maps SDK message types to canonical types."""

    @pytest.mark.asyncio
    async def test_maps_tool_use_and_result(self) -> None:
        from agent_fox.session.backends.claude import ClaudeBackend
        from agent_fox.session.backends.protocol import (
            AssistantMessage,
            ResultMessage,
            ToolUseMessage,
        )

        # This test requires mock SDK client - will be implemented with task 2.2
        # For now verify the types exist and the backend can be instantiated
        backend = ClaudeBackend()
        assert backend.name == "claude"

        # Type existence checks
        assert ToolUseMessage is not None
        assert AssistantMessage is not None
        assert ResultMessage is not None


# ---------------------------------------------------------------------------
# TS-26-7: ClaudeBackend constructs options and streams
# Requirement: 26-REQ-2.3
# ---------------------------------------------------------------------------


class TestExecuteConstructsOptions:
    """Verify execute() constructs ClaudeCodeOptions and yields messages."""

    @pytest.mark.asyncio
    async def test_execute_constructs_options(self) -> None:
        from agent_fox.session.backends.claude import ClaudeBackend

        # This test requires mock SDK client - will be implemented with task 2.2
        # For now, verify the backend has the execute method
        backend = ClaudeBackend()
        assert hasattr(backend, "execute")
        assert callable(backend.execute)


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
            "..", "..", "..", "..",
            "agent_fox", "session", "session.py",
        )
        session_path = os.path.normpath(session_path)
        with open(session_path, encoding="utf-8") as f:
            content = f.read()

        # Currently session.py imports claude_code_sdk directly.
        # This test will pass after task group 3 refactors session.py.
        assert "claude_code_sdk" not in content, (
            "session.py should not import from claude_code_sdk after refactor"
        )


# ---------------------------------------------------------------------------
# TS-26-E2: ClaudeSDKClient streaming error
# Requirement: 26-REQ-2.E1
# ---------------------------------------------------------------------------


class TestStreamingErrorYieldsResult:
    """Verify SDK streaming error yields a ResultMessage with is_error=True."""

    @pytest.mark.asyncio
    async def test_streaming_error_yields_error_result(self) -> None:
        from agent_fox.session.backends.claude import ClaudeBackend
        from agent_fox.session.backends.protocol import ResultMessage

        # This test requires mock SDK client - will be fully implemented with task 2.2
        # For now we verify the types are importable
        backend = ClaudeBackend()
        assert backend.name == "claude"
        assert ResultMessage is not None


# ---------------------------------------------------------------------------
# TS-26-P2: Message Type Completeness (Property)
# Property 2: Every message is a valid canonical type, stream ends with ResultMessage
# Validates: 26-REQ-1.3, 26-REQ-1.4
# ---------------------------------------------------------------------------


class TestPropertyMessageCompleteness:
    """Every ClaudeBackend message should be a canonical type."""

    def test_prop_message_types_are_union(self) -> None:
        from agent_fox.session.backends.protocol import (
            AssistantMessage,
            ResultMessage,
            ToolUseMessage,
        )

        # Verify AgentMessage type alias includes all three types
        # This is a structural check - the actual property test with
        # hypothesis will be added when the backend is implemented
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

        # All should be valid AgentMessage types
        for msg in [tm, am, rm]:
            assert isinstance(msg, (ToolUseMessage, AssistantMessage, ResultMessage))
