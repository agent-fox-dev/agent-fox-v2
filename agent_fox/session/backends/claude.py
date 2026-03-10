"""ClaudeBackend adapter wrapping claude_code_sdk.

All ``claude_code_sdk`` imports are confined to this module. The adapter
maps SDK message types to canonical message types defined in
``protocol.py``.

Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.E1
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
from claude_code_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from claude_code_sdk.types import (
    ResultMessage as SDKResultMessage,
)

from agent_fox.session.backends.protocol import (
    AgentMessage,
    AssistantMessage,
    PermissionCallback,
    ResultMessage,
    ToolDefinition,
    ToolUseMessage,
)

logger = logging.getLogger(__name__)


class ClaudeBackend:
    """AgentBackend implementation wrapping claude_code_sdk.

    Maps SDK message types to canonical types:

    ============================================  ====================
    SDK Type                                      Canonical Type
    ============================================  ====================
    SDK ``ResultMessage``                          ``ResultMessage``
    Tool-use messages (``tool_name`` attr)         ``ToolUseMessage``
    Other messages (thinking, text)                ``AssistantMessage``
    ``PermissionResultAllow`` / ``Deny``           ``bool`` via callback
    ============================================  ====================

    Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3
    """

    @property
    def name(self) -> str:
        """Return backend identifier."""
        return "claude"

    async def execute(
        self,
        prompt: str,
        *,
        system_prompt: str,
        model: str,
        cwd: str,
        permission_callback: PermissionCallback | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Execute a session via the Claude SDK and yield canonical messages.

        Constructs ``ClaudeCodeOptions``, opens a ``ClaudeSDKClient``,
        and maps each SDK message to a canonical type.

        On SDK streaming errors, yields a ``ResultMessage`` with
        ``is_error=True`` instead of propagating the exception.

        Requirements: 26-REQ-2.3, 26-REQ-2.E1
        """
        # Build the can_use_tool callback if a permission_callback is provided
        can_use_tool = None
        if permission_callback is not None:
            _cb = permission_callback  # capture for closure

            async def _can_use_tool_wrapper(
                tool_name: str,
                tool_input: dict[str, Any],
                _ctx: ToolPermissionContext,
            ) -> PermissionResultAllow | PermissionResultDeny:
                allowed = await _cb(tool_name, tool_input)
                if allowed:
                    return PermissionResultAllow()
                return PermissionResultDeny(message="Denied by permission callback")

            can_use_tool = _can_use_tool_wrapper

        options = ClaudeCodeOptions(
            cwd=cwd,
            model=model,
            system_prompt=system_prompt,
            permission_mode="bypassPermissions",
            can_use_tool=can_use_tool,
        )

        try:
            async for message in self._stream_messages(prompt=prompt, options=options):
                yield message
        except Exception as exc:
            # 26-REQ-2.E1: Streaming error yields ResultMessage with is_error=True
            logger.warning("ClaudeBackend streaming error: %s", exc)
            yield ResultMessage(
                status="failed",
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
                error_message=str(exc),
                is_error=True,
            )

    async def _stream_messages(
        self,
        *,
        prompt: str,
        options: ClaudeCodeOptions,
    ) -> AsyncIterator[AgentMessage]:
        """Open an SDK client and stream canonical messages.

        This is separated from ``execute()`` so that the outer method can
        catch streaming exceptions and yield a failed ``ResultMessage``.
        """
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                canonical = self._map_message(message)
                if canonical is not None:
                    yield canonical

    @staticmethod
    def _map_message(message: Any) -> AgentMessage | None:
        """Map a single SDK message to a canonical type.

        Returns ``None`` for messages that don't map to any canonical type
        (should not normally happen).

        Requirements: 26-REQ-2.2
        """
        # Check for SDK ResultMessage
        if (
            isinstance(message, SDKResultMessage)
            or getattr(message, "type", None) == "result"
        ):
            usage = getattr(message, "usage", None)
            if isinstance(usage, dict):
                input_tokens = _coerce_int(usage.get("input_tokens", 0))
                output_tokens = _coerce_int(usage.get("output_tokens", 0))
            else:
                input_tokens = _coerce_int(getattr(usage, "input_tokens", 0))
                output_tokens = _coerce_int(getattr(usage, "output_tokens", 0))
            duration_ms = _coerce_int(getattr(message, "duration_ms", 0))
            is_error = bool(getattr(message, "is_error", False))
            error_message: str | None = None
            if is_error:
                error_message = getattr(message, "result", None) or "Unknown error"
            status = "failed" if is_error else "completed"

            return ResultMessage(
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                error_message=error_message,
                is_error=is_error,
            )

        # Check for tool-use messages
        tool_name = getattr(message, "tool_name", None)
        msg_type = getattr(message, "type", None)
        if tool_name or msg_type == "tool_use":
            name = tool_name or "tool"
            tool_input = getattr(message, "tool_input", None)
            if not isinstance(tool_input, dict):
                tool_input = {}
            return ToolUseMessage(tool_name=name, tool_input=tool_input)

        # Everything else becomes an AssistantMessage
        content = getattr(message, "content", None) or getattr(message, "text", "")
        if not isinstance(content, str):
            content = str(content) if content else ""
        return AssistantMessage(content=content)

    async def close(self) -> None:
        """Release resources (no-op for ClaudeBackend)."""


def _coerce_int(value: Any) -> int:
    """Best-effort int conversion; invalid values become 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
