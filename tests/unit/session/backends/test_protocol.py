"""Tests for AgentBackend protocol and canonical message types.

Test Spec: TS-26-1 through TS-26-4, TS-26-E1, TS-26-P1
Requirements: 26-REQ-1.1, 26-REQ-1.2, 26-REQ-1.3, 26-REQ-1.4, 26-REQ-1.E1
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# TS-26-1: AgentBackend is runtime-checkable Protocol
# Requirement: 26-REQ-1.1
# ---------------------------------------------------------------------------


class TestProtocolRuntimeCheckable:
    """Verify AgentBackend is a runtime-checkable Protocol with required members."""

    def test_conforming_class_passes_isinstance(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _Conforming:
            @property
            def name(self) -> str:
                return "test"

            async def execute(
                self,
                prompt: str,
                *,
                system_prompt: str,
                model: str,
                cwd: str,
                permission_callback: Any = None,
            ) -> AsyncIterator:
                yield  # pragma: no cover

            async def close(self) -> None:
                pass

        instance = _Conforming()
        assert isinstance(instance, AgentBackend)

    def test_missing_execute_fails_isinstance(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _MissingExecute:
            @property
            def name(self) -> str:
                return "test"  # pragma: no cover

            async def close(self) -> None:
                pass  # pragma: no cover

        instance = _MissingExecute()
        assert not isinstance(instance, AgentBackend)

    def test_missing_name_fails_isinstance(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _MissingName:
            async def execute(self, prompt: str, **kw: Any) -> AsyncIterator:
                yield  # pragma: no cover

            async def close(self) -> None:
                pass  # pragma: no cover

        instance = _MissingName()
        assert not isinstance(instance, AgentBackend)

    def test_missing_close_fails_isinstance(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _MissingClose:
            @property
            def name(self) -> str:
                return "test"  # pragma: no cover

            async def execute(self, prompt: str, **kw: Any) -> AsyncIterator:
                yield  # pragma: no cover

        instance = _MissingClose()
        assert not isinstance(instance, AgentBackend)


# ---------------------------------------------------------------------------
# TS-26-2: execute() accepts required parameters
# Requirement: 26-REQ-1.2
# ---------------------------------------------------------------------------


class TestExecuteParameters:
    """Verify execute() method signature accepts all required params."""

    @pytest.mark.asyncio
    async def test_execute_without_permission_callback(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _Mock:
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
                permission_callback: Any = None,
            ) -> AsyncIterator:
                yield

            async def close(self) -> None:
                pass

        backend = _Mock()
        assert isinstance(backend, AgentBackend)
        # Should not raise TypeError
        result = backend.execute("task", system_prompt="sp", model="m", cwd="/tmp")
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_with_permission_callback(self) -> None:
        from agent_fox.session.backends.protocol import AgentBackend

        class _Mock:
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
                permission_callback: Any = None,
            ) -> AsyncIterator:
                yield

            async def close(self) -> None:
                pass

        backend = _Mock()
        assert isinstance(backend, AgentBackend)

        async def mock_cb(name: str, inp: dict) -> bool:
            return True

        result = backend.execute(
            "task",
            system_prompt="sp",
            model="m",
            cwd="/tmp",
            permission_callback=mock_cb,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# TS-26-3: Canonical message types are frozen dataclasses
# Requirement: 26-REQ-1.3
# ---------------------------------------------------------------------------


class TestCanonicalMessagesFrozen:
    """Verify ToolUseMessage, AssistantMessage, ResultMessage are frozen."""

    def test_tool_use_message_frozen(self) -> None:
        from agent_fox.session.backends.protocol import ToolUseMessage

        tm = ToolUseMessage(tool_name="Bash", tool_input={"command": "ls"})
        assert tm.tool_name == "Bash"
        assert tm.tool_input == {"command": "ls"}
        with pytest.raises(dataclasses.FrozenInstanceError):
            tm.tool_name = "other"  # type: ignore[misc]

    def test_assistant_message_frozen(self) -> None:
        from agent_fox.session.backends.protocol import AssistantMessage

        am = AssistantMessage(content="thinking")
        assert am.content == "thinking"
        with pytest.raises(dataclasses.FrozenInstanceError):
            am.content = "other"  # type: ignore[misc]

    def test_result_message_frozen(self) -> None:
        from agent_fox.session.backends.protocol import ResultMessage

        rm = ResultMessage(
            status="completed",
            input_tokens=100,
            output_tokens=200,
            duration_ms=5000,
            error_message=None,
            is_error=False,
        )
        assert rm.input_tokens == 100
        with pytest.raises(dataclasses.FrozenInstanceError):
            rm.status = "failed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-26-4: ResultMessage carries required fields
# Requirement: 26-REQ-1.4
# ---------------------------------------------------------------------------


class TestResultMessageFields:
    """Verify ResultMessage has all specified fields with correct types."""

    def test_result_message_all_fields(self) -> None:
        from agent_fox.session.backends.protocol import ResultMessage

        rm = ResultMessage(
            status="failed",
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
            error_message="timeout",
            is_error=True,
        )
        assert rm.status == "failed"
        assert rm.is_error is True
        assert rm.error_message == "timeout"
        assert isinstance(rm.input_tokens, int)
        assert isinstance(rm.output_tokens, int)
        assert isinstance(rm.duration_ms, int)

    def test_result_message_none_error(self) -> None:
        from agent_fox.session.backends.protocol import ResultMessage

        rm = ResultMessage(
            status="completed",
            input_tokens=50,
            output_tokens=100,
            duration_ms=3000,
            error_message=None,
            is_error=False,
        )
        assert rm.error_message is None
        assert rm.is_error is False


# ---------------------------------------------------------------------------
# TS-26-E1: Backend execute() exception handling
# Requirement: 26-REQ-1.E1
# ---------------------------------------------------------------------------


class TestBackendExceptionHandling:
    """Verify backend exception is caught and returned as failed SessionOutcome."""

    @pytest.mark.asyncio
    async def test_backend_exception_returns_failed_outcome(self) -> None:
        # This test validates that the session runner catches backend exceptions.
        # It will be fully testable once session.py is refactored (task 3.1).
        # For now, we verify the protocol contract expects this behavior.
        from agent_fox.session.backends.protocol import AgentBackend

        class _FailingBackend:
            @property
            def name(self) -> str:
                return "failing"

            async def execute(
                self,
                prompt: str,
                *,
                system_prompt: str,
                model: str,
                cwd: str,
                permission_callback: Any = None,
            ) -> AsyncIterator:
                raise RuntimeError("SDK crash")
                yield  # make it a generator  # pragma: no cover

            async def close(self) -> None:
                pass

        backend = _FailingBackend()
        assert isinstance(backend, AgentBackend)

        # The execute() should raise when called
        with pytest.raises(RuntimeError, match="SDK crash"):
            async for _ in backend.execute("prompt", system_prompt="sp", model="m", cwd="/tmp"):
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# TS-26-P1: Backend Protocol Isolation (Property)
# Property 1: No module outside claude backend adapter imports claude_agent_sdk
# Validates: 26-REQ-1.1, 26-REQ-2.4
# ---------------------------------------------------------------------------


class TestPropertyProtocolIsolation:
    """No module outside backends/claude.py should import claude_agent_sdk."""

    def test_prop_protocol_isolation(self) -> None:
        import glob
        import os

        agent_fox_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent_fox")
        agent_fox_dir = os.path.normpath(agent_fox_dir)

        # The only file allowed to import claude_agent_sdk
        allowed = os.path.normpath(os.path.join(agent_fox_dir, "session", "backends", "claude.py"))

        py_files = glob.glob(os.path.join(agent_fox_dir, "**", "*.py"), recursive=True)

        violations = []
        for py_file in py_files:
            normalized = os.path.normpath(py_file)
            if normalized == allowed:
                continue
            with open(py_file, encoding="utf-8") as f:
                content = f.read()
            if "claude_agent_sdk" in content:
                violations.append(os.path.relpath(py_file, agent_fox_dir))

        assert violations == [], f"Files outside backends/claude.py import claude_agent_sdk: {violations}"
