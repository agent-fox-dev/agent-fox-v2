"""Session runner: execute coding sessions via an AgentBackend.

Depends only on the AgentBackend protocol and canonical message types.
All SDK-specific code is isolated in the backend adapter modules.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1,
              18-REQ-2.1, 18-REQ-2.2, 18-REQ-2.3, 18-REQ-2.E1,
              26-REQ-2.4
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.hooks.security import make_pre_tool_use_hook
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.session.backends.protocol import (
    AgentBackend,
    AgentMessage,
    AssistantMessage,
    ResultMessage,
    ToolUseMessage,
)
from agent_fox.ui.events import ActivityCallback, ActivityEvent, abbreviate_arg
from agent_fox.workspace.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


@dataclass
class _QueryExecutionState:
    """Mutable query metrics/status snapshot (supports timeout partials)."""

    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error_message: str | None = None
    status: str = "completed"
    saw_result: bool = False


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

    Requirements: 26-REQ-1.E1, 26-REQ-2.4
    """
    # Resolve the coding model
    model_entry = resolve_model(config.models.coding)

    # Resolve backend (lazy import to keep SDK isolation)
    if backend is None:
        from agent_fox.session.backends import get_backend

        backend = get_backend("claude")

    # Track metrics (including partials for timeout/failure cases)
    execution_state = _QueryExecutionState()
    input_tokens = 0
    output_tokens = 0
    duration_ms = 0
    error_message: str | None = None
    status = "completed"

    try:
        # 03-REQ-3.1, 03-REQ-6.1: Execute query wrapped in timeout
        result = await with_timeout(
            _execute_query(
                task_prompt=task_prompt,
                system_prompt=system_prompt,
                model_id=model_entry.model_id,
                cwd=str(workspace.path),
                config=config,
                backend=backend,
                state=execution_state,
                node_id=node_id,
                activity_callback=activity_callback,
            ),
            timeout_minutes=config.orchestrator.session_timeout,
        )
        input_tokens = result["input_tokens"]
        output_tokens = result["output_tokens"]
        duration_ms = result["duration_ms"]
        error_message = result["error_message"]
        status = result["status"]

    except TimeoutError:
        # 03-REQ-6.2, 03-REQ-6.E1: Timeout with partial metrics
        status = "timeout"
        input_tokens = execution_state.input_tokens
        output_tokens = execution_state.output_tokens
        duration_ms = execution_state.duration_ms
        error_message = execution_state.error_message

    except Exception as exc:
        # 03-REQ-3.E1, 26-REQ-1.E1: Catch backend errors, return failed outcome
        status = "failed"
        error_message = str(exc)
        input_tokens = execution_state.input_tokens
        output_tokens = execution_state.output_tokens
        duration_ms = execution_state.duration_ms
        logger.warning("Session failed with error: %s", error_message)

    return SessionOutcome(
        spec_name=workspace.spec_name,
        task_group=str(workspace.task_group),
        node_id=node_id,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        error_message=error_message,
    )


async def _execute_query(
    *,
    task_prompt: str,
    system_prompt: str,
    model_id: str,
    cwd: str,
    config: AgentFoxConfig,
    backend: AgentBackend,
    state: _QueryExecutionState | None = None,
    node_id: str = "",
    activity_callback: ActivityCallback | None = None,
) -> dict[str, Any]:
    """Execute the query via an AgentBackend and collect results.

    Returns a dict with token usage, duration, status, and error info.
    """
    query_state = state or _QueryExecutionState()

    # 03-REQ-3.4: Build the allowlist-based permission callback
    allowlist_hook = make_pre_tool_use_hook(config.security)

    async def _permission_callback(
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> bool:
        result = allowlist_hook(tool_name=tool_name, tool_input=tool_input)
        return result.get("decision") != "block"

    turn_count = 0
    cumulative_tokens = 0

    async for message in backend.execute(
        task_prompt,
        system_prompt=system_prompt,
        model=model_id,
        cwd=cwd,
        permission_callback=_permission_callback,
    ):
        is_result = isinstance(message, ResultMessage)

        # 18-REQ-2.1, 18-REQ-2.E1: Emit activity events for non-result messages
        if activity_callback is not None and not is_result:
            turn_count += 1
            event = _extract_activity(
                node_id, message, turn=turn_count, tokens=cumulative_tokens
            )
            if event is not None:
                try:
                    activity_callback(event)
                except Exception:
                    logger.debug("Activity callback raised; ignoring")

        # Track cumulative tokens from ToolUseMessage / AssistantMessage
        # (canonical messages don't carry usage info on non-result messages,
        # so cumulative token tracking is now driven by the ResultMessage)

        # 03-REQ-3.2: Collect the ResultMessage.
        if not is_result:
            continue

        query_state.saw_result = True
        query_state.input_tokens = message.input_tokens
        query_state.output_tokens = message.output_tokens
        query_state.duration_ms = message.duration_ms

        # Update cumulative tokens from the final result
        cumulative_tokens = message.input_tokens + message.output_tokens

        # 03-REQ-3.E2: Check is_error flag
        if message.is_error:
            query_state.status = "failed"
            query_state.error_message = message.error_message or "Unknown error"
        else:
            query_state.status = "completed"
            query_state.error_message = None

    if not query_state.saw_result:
        query_state.status = "failed"
        query_state.error_message = (
            query_state.error_message or "Session ended without a result message."
        )

    return {
        "input_tokens": query_state.input_tokens,
        "output_tokens": query_state.output_tokens,
        "duration_ms": query_state.duration_ms,
        "error_message": query_state.error_message,
        "status": query_state.status,
    }


def _extract_activity(
    node_id: str,
    message: AgentMessage,
    *,
    turn: int = 0,
    tokens: int | None = None,
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
        )

    if isinstance(message, AssistantMessage):
        return ActivityEvent(
            node_id=node_id,
            tool_name="thinking...",
            argument="",
            turn=turn,
            tokens=tokens,
        )

    # ResultMessage — no activity event
    return None
