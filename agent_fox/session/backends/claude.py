"""ClaudeBackend adapter wrapping claude_agent_sdk.

All ``claude_agent_sdk`` imports are confined to this module. The adapter
maps SDK message types to canonical message types defined in
``protocol.py``.

Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.E1
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage as SDKAssistantMessage,
)
from claude_agent_sdk.types import (
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolUseBlock,
)
from claude_agent_sdk.types import (
    ResultMessage as SDKResultMessage,
)

from agent_fox.session.backends.protocol import (
    AgentMessage,
    AssistantMessage,
    PermissionCallback,
    ResultMessage,
    ToolUseMessage,
)
from agent_fox.ui.progress import ActivityCallback, ActivityEvent, abbreviate_arg

logger = logging.getLogger(__name__)

# Maximum number of transport-layer retry attempts before yielding a
# terminal failure ResultMessage.  Does not consume escalation ladder retries.
_MAX_TRANSPORT_RETRIES = 3
# Base delay in seconds; actual delay = _BACKOFF_BASE * 2^(attempt-1)
_BACKOFF_BASE = 1.0


class ClaudeBackend:
    """AgentBackend implementation wrapping claude_agent_sdk.

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
        activity_callback: ActivityCallback | None = None,
        node_id: str = "",
        archetype: str | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        fallback_model: str | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Execute a session via the Claude SDK and yield canonical messages.

        Constructs ``ClaudeAgentOptions``, opens a ``ClaudeSDKClient``,
        and maps each SDK message to a canonical type.

        On SDK streaming errors, yields a ``ResultMessage`` with
        ``is_error=True`` instead of propagating the exception.

        Requirements: 26-REQ-2.3, 26-REQ-2.E1, 56-REQ-1.2, 56-REQ-2.2,
                      56-REQ-3.2, 56-REQ-4.2, 56-REQ-5.E1
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

        # Build extra_args for parameters not directly supported by ClaudeAgentOptions
        # (56-REQ-2.2, 56-REQ-3.2)
        extra_args: dict[str, str | None] = {}
        if max_budget_usd:
            extra_args["max-budget-usd"] = str(max_budget_usd)
        if fallback_model:
            extra_args["fallback-model"] = fallback_model

        # Build core options — max_turns is a native ClaudeAgentOptions field
        options = ClaudeAgentOptions(
            cwd=cwd,
            model=model,
            system_prompt=system_prompt,
            permission_mode="bypassPermissions",
            can_use_tool=can_use_tool,
            extra_args=extra_args,
            **({"max_turns": max_turns} if max_turns is not None else {}),  # type: ignore[arg-type]
        )

        # Store thinking config as attribute on options (56-REQ-4.2, 56-REQ-5.E1)
        # ClaudeAgentOptions is a non-frozen dataclass; attribute assignment is safe.
        # If a future SDK version raises TypeError here, we catch it and omit.
        if thinking is not None:
            try:
                options.thinking = thinking  # type: ignore[assignment]
            except TypeError as exc:
                logger.warning("SDK does not support 'thinking' parameter, omitting: %s", exc)

        # Register a Notification hook when an activity_callback is provided.
        # The hook converts SDK NotificationHookInput to ActivityEvent and
        # forwards it to the callback. (AC-1, AC-2, AC-7 — issue #320)
        if activity_callback is not None:
            options.hooks = {
                "Notification": [
                    HookMatcher(
                        hooks=[_build_notification_hook(activity_callback, node_id=node_id, archetype=archetype)],
                    )
                ]
            }

        # Transport-layer retry loop (AC-1 through AC-4).
        # Transient errors (connection failure or missing ResultMessage) are
        # retried up to _MAX_TRANSPORT_RETRIES times with exponential backoff
        # before a terminal failure ResultMessage is emitted.  These retries
        # are invisible to the orchestrator's escalation ladder.
        last_error: str | None = None
        for _attempt in range(_MAX_TRANSPORT_RETRIES):
            if _attempt > 0:
                delay = _BACKOFF_BASE * (2 ** (_attempt - 1))
                logger.info(
                    "ClaudeBackend: transport retry %d/%d after %.1fs",
                    _attempt,
                    _MAX_TRANSPORT_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

            buffered: list[AgentMessage] = []
            saw_result = False
            is_transport_failure = False

            try:
                async for message in self._stream_messages(prompt=prompt, options=options):
                    if isinstance(message, ResultMessage):
                        saw_result = True
                    buffered.append(message)
            except Exception as exc:
                # 26-REQ-2.E1: Connection/OS errors are transient transport failures
                last_error = str(exc)
                logger.warning(
                    "ClaudeBackend transport error (attempt %d/%d): %s",
                    _attempt + 1,
                    _MAX_TRANSPORT_RETRIES,
                    exc,
                )
                is_transport_failure = True

            if not is_transport_failure and not saw_result:
                last_error = "Backend stream ended without a result message."
                logger.warning(
                    "ClaudeBackend stream ended without ResultMessage (attempt %d/%d)",
                    _attempt + 1,
                    _MAX_TRANSPORT_RETRIES,
                )
                is_transport_failure = True

            if not is_transport_failure:
                # Successful stream — yield buffered messages and return.
                for msg in buffered:
                    yield msg
                return

        # All transport retries exhausted — emit a terminal transport-error result.
        logger.error(
            "ClaudeBackend: all %d transport retries exhausted; last error: %s",
            _MAX_TRANSPORT_RETRIES,
            last_error,
        )
        yield ResultMessage(
            status="failed",
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
            error_message=(f"Transport error after {_MAX_TRANSPORT_RETRIES} retries: {last_error}"),
            is_error=True,
            is_transport_error=True,
        )

    async def _stream_messages(
        self,
        *,
        prompt: str,
        options: ClaudeAgentOptions,
    ) -> AsyncIterator[AgentMessage]:
        """Open an SDK client and stream canonical messages.

        This is separated from ``execute()`` so that the outer method can
        catch streaming exceptions and yield a failed ``ResultMessage``.

        The response stream is explicitly closed before the client context
        manager exits. Without this, the SDK's internal read loop may still
        be active when ``__aexit__`` sends SIGTERM to the subprocess,
        causing an unhandled ``ProcessError`` (exit code 143) that surfaces
        as an asyncio "Task exception was never retrieved" warning.

        See: https://github.com/nicholasgasior/agent-fox/issues/215
        """
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            response_stream = client.receive_response()
            try:
                async for message in response_stream:
                    for canonical in self._map_message(message):
                        yield canonical
            finally:
                # Ensure the SDK's message stream is closed before __aexit__
                # terminates the subprocess.  Without this,
                # _read_messages_impl may still be reading when SIGTERM
                # arrives, producing an unhandled ProcessError(exit code
                # 143).
                await response_stream.aclose()  # type: ignore[attr-defined]

    @staticmethod
    def _map_message(message: Any) -> list[AgentMessage]:
        """Map a single SDK message to one or more canonical types.

        An SDK ``AssistantMessage`` may contain multiple content blocks
        (text, thinking, tool_use), so a single SDK message can produce
        several canonical messages.

        Requirements: 26-REQ-2.2
        """
        # Check for SDK ResultMessage
        if isinstance(message, SDKResultMessage) or getattr(message, "type", None) == "result":
            usage = getattr(message, "usage", None)
            if isinstance(usage, dict):
                input_tokens = _coerce_int(usage.get("input_tokens", 0))
                output_tokens = _coerce_int(usage.get("output_tokens", 0))
                cache_read = _coerce_int(usage.get("cache_read_input_tokens", 0))
                cache_creation = _coerce_int(usage.get("cache_creation_input_tokens", 0))
            else:
                input_tokens = _coerce_int(getattr(usage, "input_tokens", 0))
                output_tokens = _coerce_int(getattr(usage, "output_tokens", 0))
                cache_read = _coerce_int(getattr(usage, "cache_read_input_tokens", 0))
                cache_creation = _coerce_int(getattr(usage, "cache_creation_input_tokens", 0))
            duration_ms = _coerce_int(getattr(message, "duration_ms", 0))
            is_error = bool(getattr(message, "is_error", False))
            error_message: str | None = None
            if is_error:
                error_message = getattr(message, "result", None) or "Unknown error"
            status = "failed" if is_error else "completed"

            return [
                ResultMessage(
                    status=status,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    error_message=error_message,
                    is_error=is_error,
                    cache_read_input_tokens=cache_read,
                    cache_creation_input_tokens=cache_creation,
                )
            ]

        # SDK AssistantMessage: iterate content blocks to extract tool uses
        if isinstance(message, SDKAssistantMessage):
            results: list[AgentMessage] = []
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    results.append(ToolUseMessage(tool_name=block.name, tool_input=block.input))
                elif isinstance(block, ThinkingBlock):
                    # 56-REQ-4.4: Map ThinkingBlock to AssistantMessage
                    thinking_text = getattr(block, "thinking", "")
                    results.append(AssistantMessage(content=f"[thinking] {thinking_text}"))
                elif isinstance(block, TextBlock):
                    results.append(AssistantMessage(content=block.text))
            # If no content blocks produced output, emit a generic AssistantMessage
            if not results:
                results.append(AssistantMessage(content=""))
            return results

        # Legacy fallback: check for tool-use attributes directly on the message
        tool_name = getattr(message, "tool_name", None)
        msg_type = getattr(message, "type", None)
        if tool_name or msg_type == "tool_use":
            name = tool_name or "tool"
            tool_input = getattr(message, "tool_input", None)
            if not isinstance(tool_input, dict):
                tool_input = {}
            return [ToolUseMessage(tool_name=name, tool_input=tool_input)]

        # Everything else becomes an AssistantMessage
        return [AssistantMessage(content="")]

    async def close(self) -> None:
        """Release resources (no-op for ClaudeBackend)."""


def _build_notification_hook(
    activity_callback: ActivityCallback,
    *,
    node_id: str,
    archetype: str | None,
) -> Any:
    """Return an async Notification hook that emits ActivityEvents.

    The returned function satisfies the HookCallback signature:
    ``(hook_input, tool_use_id, context) -> Awaitable[HookJSONOutput]``.

    ``NotificationHookInput`` is a TypedDict (subclass of dict) with keys:
    ``message`` (str), ``title`` (str, optional), ``notification_type`` (str).

    Returns a SyncHookJSONOutput-compatible dict so execution continues.

    Requirements: 320-AC-1, 320-AC-2, 320-AC-5, 320-AC-6
    """
    turn_counter = [0]  # mutable int in a list for closure mutation

    async def _notification_hook(
        hook_input: Any,
        tool_use_id: Any,  # noqa: ARG001
        context: Any,  # noqa: ARG001
    ) -> dict[str, Any]:
        turn_counter[0] += 1

        # NotificationHookInput is a TypedDict (dict subclass)
        if isinstance(hook_input, dict):
            title: str | None = hook_input.get("title")
            message: str = hook_input.get("message", "")
            notification_type: str = hook_input.get("notification_type", "")
        else:
            title = getattr(hook_input, "title", None)
            message = getattr(hook_input, "message", "")
            notification_type = getattr(hook_input, "notification_type", "")

        tool_name = title if title else (notification_type or "notification")
        argument = abbreviate_arg(message) if message else ""

        event = ActivityEvent(
            node_id=node_id,
            tool_name=tool_name,
            argument=argument,
            turn=turn_counter[0],
            tokens=0,
            archetype=archetype,
        )
        try:
            activity_callback(event)
        except Exception:
            logger.debug("Activity callback raised in notification hook; ignoring")

        # Return an empty SyncHookJSONOutput — continue execution
        return {}

    return _notification_hook


def _coerce_int(value: Any) -> int:
    """Best-effort int conversion; invalid values become 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
