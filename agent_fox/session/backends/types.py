"""Canonical message types for the agent backend layer.

Defines the frozen dataclass message types that constitute the canonical
message model, plus the permission callback type alias.

Requirements: 26-REQ-1.1, 26-REQ-1.2, 26-REQ-1.3, 26-REQ-1.4
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Canonical message types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolUseMessage:
    """A tool invocation message from the agent."""

    tool_name: str
    tool_input: dict[str, Any]


@dataclass(frozen=True)
class AssistantMessage:
    """A text/thinking message from the agent."""

    content: str


@dataclass(frozen=True)
class ResultMessage:
    """Terminal message carrying session outcome and token usage.

    Fields:
        status: ``"completed"`` or ``"failed"``.
        input_tokens: Total input tokens consumed.
        output_tokens: Total output tokens consumed.
        duration_ms: Session wall-clock duration in milliseconds.
        error_message: Error description if the session failed, else ``None``.
        is_error: Whether the session ended in an error state.
        is_transport_error: Whether the failure was a transient transport/
            connection error (e.g. OSError, empty stream) rather than a
            session-level failure.  When ``True`` the orchestrator should
            reset the node to pending without consuming an escalation retry.
    """

    status: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    error_message: str | None
    is_error: bool
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    is_transport_error: bool = False


# Union of all canonical message types
AgentMessage = ToolUseMessage | AssistantMessage | ResultMessage


# ---------------------------------------------------------------------------
# Permission callback type
# ---------------------------------------------------------------------------

PermissionCallback = Callable[
    [str, dict[str, Any]],  # tool_name, tool_input
    Awaitable[bool],  # True = allow, False = deny
]
