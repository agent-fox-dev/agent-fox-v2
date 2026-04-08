"""Session runner: execute coding sessions via an AgentBackend.

Depends only on the AgentBackend protocol and canonical message types.
All SDK-specific code is isolated in the backend adapter modules.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1,
              18-REQ-2.1, 18-REQ-2.2, 18-REQ-2.3, 18-REQ-2.E1,
              26-REQ-2.4, 40-REQ-8.1, 40-REQ-8.2, 40-REQ-8.3
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.hooks.security import make_pre_tool_use_hook
from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
)
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher, ToolCall, ToolError
from agent_fox.session.backends.protocol import (
    AgentBackend,
    AgentMessage,
    AssistantMessage,
    ResultMessage,
    ToolUseMessage,
)
from agent_fox.ui.progress import ActivityCallback, ActivityEvent, abbreviate_arg
from agent_fox.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


@dataclass
class _QueryExecutionState:
    """Mutable query metrics/status snapshot (supports timeout partials)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    duration_ms: int = 0
    error_message: str | None = None
    status: str = "completed"
    saw_result: bool = False
    last_response: str = ""  # Last AssistantMessage content
    is_transport_error: bool = False  # True when failure is a transient connection error


async def with_timeout[T](
    coro: Coroutine[None, None, T],
    timeout_minutes: int,
) -> T:
    """Run *coro* with a timeout (minutes → seconds)."""
    return await asyncio.wait_for(coro, timeout=timeout_minutes * 60)


async def run_session(
    workspace: WorkspaceInfo,
    node_id: str,
    system_prompt: str,
    task_prompt: str,
    config: AgentFoxConfig,
    *,
    backend: AgentBackend | None = None,
    activity_callback: ActivityCallback | None = None,
    model_id: str | None = None,
    security_config: Any | None = None,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    fallback_model: str | None = None,
    thinking: dict[str, Any] | None = None,
    session_timeout: int | None = None,
    archetype: str | None = None,
) -> SessionOutcome:
    """Execute a coding session in the given workspace.

    1. Resolve the coding model
    2. Build a permission callback from the security allowlist
    3. Stream messages from the backend via AgentBackend.execute()
    4. Collect the terminal ResultMessage for outcome metrics
    5. Wrap the entire query in asyncio.wait_for with the
       configured session_timeout
    6. Build and return a SessionOutcome

    Args:
        workspace: Workspace information for the session.
        node_id: Identifier for the task graph node.
        system_prompt: System instructions for the agent.
        task_prompt: Task prompt to send to the agent.
        config: Application configuration.
        backend: AgentBackend to use. Defaults to ClaudeBackend via factory.
        activity_callback: Optional callback for UI activity events.
        model_id: Optional model tier or model ID override. When set,
            overrides ``config.models.coding`` for this session.
        security_config: Optional SecurityConfig override for the allowlist.
            When set, overrides ``config.security`` for this session.
        max_turns: Optional maximum turn count to pass to the backend.
            Requirements: 56-REQ-1.2
        max_budget_usd: Optional USD budget cap to pass to the backend.
            Requirements: 56-REQ-2.2
        fallback_model: Optional fallback model ID. Requirements: 56-REQ-3.2
        thinking: Optional extended thinking config dict. Requirements: 56-REQ-4.2
        session_timeout: Optional session timeout in minutes. When set, overrides
            config.orchestrator.session_timeout for this session.
            Requirements: 75-REQ-3.2, 75-REQ-3.5

    Requirements: 26-REQ-1.E1, 26-REQ-2.4, 26-REQ-3.4, 26-REQ-4.4
    """
    # Resolve the coding model (archetype override or config default)
    model_entry = resolve_model(model_id or config.models.coding)

    # Resolve security config (archetype override or config default)
    effective_security = security_config if security_config is not None else config.security

    # Resolve backend (lazy import to keep SDK isolation)
    if backend is None:
        from agent_fox.session.backends import get_backend

        backend = get_backend()

    # Track metrics via mutable state (supports partial reads on timeout/failure)
    state = _QueryExecutionState()

    try:
        # 03-REQ-3.1, 03-REQ-6.1: Execute query wrapped in timeout
        await with_timeout(
            _execute_query(
                task_prompt=task_prompt,
                system_prompt=system_prompt,
                model_id=model_entry.model_id,
                cwd=str(workspace.path),
                config=config,
                backend=backend,
                state=state,
                node_id=node_id,
                activity_callback=activity_callback,
                security_config_override=effective_security,
                sink_dispatcher=sink_dispatcher,
                run_id=run_id,
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
                fallback_model=fallback_model,
                thinking=thinking,
                archetype=archetype,
            ),
            timeout_minutes=(session_timeout if session_timeout is not None else config.orchestrator.session_timeout),
        )

    except TimeoutError:
        # 03-REQ-6.2, 03-REQ-6.E1: Timeout with partial metrics
        state.status = "timeout"

    except Exception as exc:
        # 03-REQ-3.E1, 26-REQ-1.E1: Catch backend errors, return failed outcome
        state.status = "failed"
        state.error_message = str(exc)
        logger.warning("Session failed with error: %s", state.error_message)

    return SessionOutcome(
        spec_name=workspace.spec_name,
        task_group=str(workspace.task_group),
        node_id=node_id,
        status=state.status,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
        cache_read_input_tokens=state.cache_read_input_tokens,
        cache_creation_input_tokens=state.cache_creation_input_tokens,
        duration_ms=state.duration_ms,
        error_message=state.error_message,
        response=state.last_response,
        is_transport_error=state.is_transport_error,
    )


async def _execute_query(
    *,
    task_prompt: str,
    system_prompt: str,
    model_id: str,
    cwd: str,
    config: AgentFoxConfig,
    backend: AgentBackend,
    state: _QueryExecutionState,
    node_id: str = "",
    activity_callback: ActivityCallback | None = None,
    security_config_override: Any | None = None,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    fallback_model: str | None = None,
    thinking: dict[str, Any] | None = None,
    archetype: str | None = None,
) -> None:
    """Execute the query via an AgentBackend and collect results.

    Updates *state* in place with token usage, duration, status, and error info.
    """
    query_state = state

    # 03-REQ-3.4, 26-REQ-3.4: Build the allowlist-based permission callback
    # Use security override (per-archetype allowlist) if provided
    effective_security = security_config_override if security_config_override is not None else config.security
    allowlist_hook = make_pre_tool_use_hook(effective_security)

    async def _permission_callback(
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> bool:
        result = allowlist_hook(tool_name=tool_name, tool_input=tool_input)
        return result.get("decision") != "block"

    turn_count = 0
    cumulative_tokens = 0
    last_tool_name: str | None = None  # track most-recent tool for error attribution

    async for message in backend.execute(  # type: ignore[attr-defined]
        task_prompt,
        system_prompt=system_prompt,
        model=model_id,
        cwd=cwd,
        permission_callback=_permission_callback,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        fallback_model=fallback_model,
        thinking=thinking,
    ):
        is_result = isinstance(message, ResultMessage)

        # 18-REQ-2.1, 18-REQ-2.E1: Emit activity events for non-result messages
        if activity_callback is not None and not is_result:
            turn_count += 1
            event = _extract_activity(
                node_id,
                message,
                turn=turn_count,
                tokens=cumulative_tokens,
                archetype=archetype,
            )
            if event is not None:
                try:
                    activity_callback(event)
                except Exception:
                    logger.debug("Activity callback raised; ignoring")

        # 40-REQ-8.1, 40-REQ-8.2: Emit tool.invocation audit events
        if sink_dispatcher is not None and run_id and isinstance(message, ToolUseMessage):
            try:
                param_parts = []
                for v in message.tool_input.values():
                    if isinstance(v, str):
                        param_parts.append(abbreviate_arg(v))
                param_summary = ", ".join(param_parts) if param_parts else ""
                sink_dispatcher.emit_audit_event(
                    AuditEvent(
                        run_id=run_id,
                        event_type=AuditEventType.TOOL_INVOCATION,
                        node_id=node_id,
                        payload={
                            "tool_name": message.tool_name,
                            "param_summary": param_summary,
                            "called_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )
            except Exception:
                logger.debug(
                    "Failed to emit tool.invocation audit event",
                    exc_info=True,
                )

        # Record tool call telemetry for every ToolUseMessage (fixes #282)
        if sink_dispatcher is not None and isinstance(message, ToolUseMessage):
            last_tool_name = message.tool_name
            sink_dispatcher.record_tool_call(
                ToolCall(
                    session_id=run_id,
                    node_id=node_id,
                    tool_name=message.tool_name,
                )
            )

        # Capture assistant text for review archetype parsing.
        if isinstance(message, AssistantMessage) and message.content:
            query_state.last_response = message.content

        # Track cumulative tokens from ToolUseMessage / AssistantMessage
        # (canonical messages don't carry usage info on non-result messages,
        # so cumulative token tracking is now driven by the ResultMessage)

        # 03-REQ-3.2: Collect the ResultMessage.
        if not is_result:
            continue

        query_state.saw_result = True
        query_state.input_tokens = message.input_tokens
        query_state.output_tokens = message.output_tokens
        query_state.cache_read_input_tokens = message.cache_read_input_tokens
        query_state.cache_creation_input_tokens = message.cache_creation_input_tokens
        query_state.duration_ms = message.duration_ms

        # Update cumulative tokens from the final result
        cumulative_tokens = message.input_tokens + message.output_tokens

        # 03-REQ-3.E2: Check is_error flag
        if message.is_error:
            query_state.status = "failed"
            query_state.error_message = message.error_message or "Unknown error"
            query_state.is_transport_error = getattr(message, "is_transport_error", False)
            # Record tool error when the session fails after a tool invocation
            if sink_dispatcher is not None and last_tool_name is not None:
                sink_dispatcher.record_tool_error(
                    ToolError(
                        session_id=run_id,
                        node_id=node_id,
                        tool_name=last_tool_name,
                    )
                )
        else:
            query_state.status = "completed"
            query_state.error_message = None
            query_state.is_transport_error = False

    if not query_state.saw_result:
        query_state.status = "failed"
        query_state.error_message = query_state.error_message or "Session ended without a result message."


def _extract_activity(
    node_id: str,
    message: AgentMessage,
    *,
    turn: int = 0,
    tokens: int | None = None,
    archetype: str | None = None,
) -> ActivityEvent | None:
    """Extract an ActivityEvent from a canonical message.

    - ToolUseMessage: extract tool name and abbreviated first argument.
    - AssistantMessage: emit a thinking event.
    - ResultMessage: ignored (handled separately).
    """
    if isinstance(message, ToolUseMessage):
        arg = ""
        for v in message.tool_input.values():
            if isinstance(v, str):
                arg = abbreviate_arg(v)
                break
        return ActivityEvent(
            node_id=node_id,
            tool_name=message.tool_name,
            argument=arg,
            turn=turn,
            tokens=tokens,
            archetype=archetype,
        )

    if isinstance(message, AssistantMessage):
        return ActivityEvent(
            node_id=node_id,
            tool_name="thinking...",
            argument="",
            turn=turn,
            tokens=tokens,
            archetype=archetype,
        )

    # ResultMessage — no activity event
    return None
