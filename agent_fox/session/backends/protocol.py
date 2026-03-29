"""AgentBackend protocol and canonical message types.

Defines the contract that any agent SDK adapter must implement, plus
three frozen dataclass message types that constitute the canonical
message model.

Requirements: 26-REQ-1.1, 26-REQ-1.2, 26-REQ-1.3, 26-REQ-1.4,
              29-REQ-6.1, 29-REQ-6.E1
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

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
    """

    status: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    error_message: str | None
    is_error: bool
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


# Union of all canonical message types
AgentMessage = ToolUseMessage | AssistantMessage | ResultMessage


# ---------------------------------------------------------------------------
# Permission callback type
# ---------------------------------------------------------------------------

PermissionCallback = Callable[
    [str, dict[str, Any]],  # tool_name, tool_input
    Awaitable[bool],  # True = allow, False = deny
]


# ---------------------------------------------------------------------------
# Custom tool definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolDefinition:
    """A custom tool to be registered with the backend.

    Requirements: 29-REQ-6.1

    Attributes:
        name: Tool name (e.g. ``"fox_read"``).
        description: Human-readable description.
        input_schema: JSON Schema for tool input.
        handler: Sync callable ``(tool_input: dict) -> result``.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


# ---------------------------------------------------------------------------
# AgentBackend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentBackend(Protocol):
    """Protocol defining the contract for agent SDK adapters.

    ``ClaudeBackend`` is the only production implementation of this protocol.
    The protocol exists to allow test mock injection — tests can create
    lightweight mock backends that satisfy ``isinstance(obj, AgentBackend)``
    checks without importing the Claude SDK directly.

    Any class implementing this protocol can be used as a backend for
    session execution. The protocol is runtime-checkable, so
    ``isinstance(obj, AgentBackend)`` works.

    Requirements: 26-REQ-1.1, 26-REQ-1.2
    """

    @property
    def name(self) -> str:
        """Unique identifier for this backend (e.g. ``"claude"``)."""
        ...

    async def execute(
        self,
        prompt: str,
        *,
        system_prompt: str,
        model: str,
        cwd: str,
        permission_callback: PermissionCallback | None = None,
        tools: list[ToolDefinition] | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        fallback_model: str | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Execute a session and yield canonical messages.

        Args:
            prompt: The task prompt to send to the agent.
            system_prompt: System instructions for the agent.
            model: Model identifier (e.g. ``"claude-sonnet-4-6"``).
            cwd: Working directory for the session.
            permission_callback: Optional callback invoked before each tool
                use. Returns ``True`` to allow, ``False`` to deny.
            tools: Optional list of custom tool definitions to register
                with the backend alongside built-in tools.
                Requirements: 29-REQ-6.1, 29-REQ-6.E1
            max_turns: Optional maximum number of turns for the session.
                Requirements: 56-REQ-1.2
            max_budget_usd: Optional maximum USD budget for the session.
                Requirements: 56-REQ-2.2
            fallback_model: Optional fallback model ID when primary is
                unavailable. Requirements: 56-REQ-3.2
            thinking: Optional extended thinking configuration dict with
                ``type`` and ``budget_tokens`` fields. Requirements: 56-REQ-4.2

        Yields:
            Canonical message objects. The stream MUST terminate with
            exactly one ``ResultMessage``.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by this backend."""
        ...
