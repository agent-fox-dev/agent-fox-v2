"""Tests for canonical message types.

Test Spec: TS-26-3, TS-26-4, TS-26-P1
Requirements: 26-REQ-1.3, 26-REQ-1.4, 26-REQ-2.4
"""

from __future__ import annotations

import dataclasses

import pytest

# ---------------------------------------------------------------------------
# TS-26-3: Canonical message types are frozen dataclasses
# Requirement: 26-REQ-1.3
# ---------------------------------------------------------------------------


class TestCanonicalMessagesFrozen:
    """Verify ToolUseMessage, AssistantMessage, ResultMessage are frozen."""

    def test_tool_use_message_frozen(self) -> None:
        from agent_fox.session.backends.types import ToolUseMessage

        tm = ToolUseMessage(tool_name="Bash", tool_input={"command": "ls"})
        assert tm.tool_name == "Bash"
        assert tm.tool_input == {"command": "ls"}
        with pytest.raises(dataclasses.FrozenInstanceError):
            tm.tool_name = "other"  # type: ignore[misc]

    def test_assistant_message_frozen(self) -> None:
        from agent_fox.session.backends.types import AssistantMessage

        am = AssistantMessage(content="thinking")
        assert am.content == "thinking"
        with pytest.raises(dataclasses.FrozenInstanceError):
            am.content = "other"  # type: ignore[misc]

    def test_result_message_frozen(self) -> None:
        from agent_fox.session.backends.types import ResultMessage

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
        from agent_fox.session.backends.types import ResultMessage

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
        from agent_fox.session.backends.types import ResultMessage

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
