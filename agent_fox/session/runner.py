"""Session runner: execute coding sessions via the claude-code-sdk.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass
from typing import Any

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
from claude_code_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    ToolPermissionContext,
)

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.hooks.security import make_pre_tool_use_hook
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.workspace.worktree import WorkspaceInfo

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
) -> SessionOutcome:
    """Execute a coding session in the given workspace.

    1. Build ClaudeAgentOptions with:
       - cwd = workspace.path
       - model = resolved coding model
       - system_prompt = provided system prompt
       - permission_mode = "bypassPermissions"
       - hooks = PreToolUse allowlist hook
    2. Send task prompt through ClaudeSDKClient with can_use_tool callback
    3. Iterate streamed messages, collecting the terminal ResultMessage
    4. Wrap the entire query in asyncio.wait_for with the
       configured session_timeout
    5. Build and return a SessionOutcome

    Raises:
        SessionTimeoutError: Propagated if caller does not catch.
        SessionError: On SDK errors.
    """
    # Resolve the coding model
    model_entry = resolve_model(config.models.coding)

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
                state=execution_state,
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
        # 03-REQ-3.E1: Catch SDK errors, return failed outcome
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
    state: _QueryExecutionState | None = None,
) -> dict[str, Any]:
    """Execute the SDK query and collect results from messages.

    Returns a dict with token usage, duration, status, and error info.
    """
    query_state = state or _QueryExecutionState()

    # 03-REQ-3.4: Build the allowlist hook from security config
    allowlist_hook = make_pre_tool_use_hook(config.security)

    async def _can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        _ctx: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        result = allowlist_hook(tool_name=tool_name, tool_input=tool_input)
        if result.get("decision") == "block":
            return PermissionResultDeny(
                message=result.get("message", "Blocked by allowlist")
            )
        return PermissionResultAllow()

    # 03-REQ-3.1, 03-REQ-3.4: Configure SDK options + allowlist hook.
    options = ClaudeCodeOptions(
        cwd=cwd,
        model=model_id,
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
        can_use_tool=_can_use_tool,
    )

    async for message in _query_messages(task_prompt=task_prompt, options=options):
        # 03-REQ-3.2: Collect the ResultMessage.
        if not _is_result_message(message):
            continue

        query_state.saw_result = True
        usage = getattr(message, "usage", None)
        (
            query_state.input_tokens,
            query_state.output_tokens,
        ) = _extract_usage_tokens(usage)
        query_state.duration_ms = _coerce_int(getattr(message, "duration_ms", 0))

        # 03-REQ-3.E2: Check is_error flag
        if getattr(message, "is_error", False):
            query_state.status = "failed"
            query_state.error_message = (
                getattr(message, "result", None) or "Unknown error"
            )
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


async def _query_messages(
    *,
    task_prompt: str,
    options: ClaudeCodeOptions,
) -> AsyncIterator[Any]:
    """Send one prompt and yield all response messages through ResultMessage."""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(task_prompt)
        async for message in client.receive_response():
            yield message


def _is_result_message(message: Any) -> bool:
    """Return True for SDK ResultMessage and legacy test doubles."""
    return isinstance(message, ResultMessage) or (
        getattr(message, "type", None) == "result"
    )


def _coerce_int(value: Any) -> int:
    """Best-effort int conversion; invalid values become 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_usage_tokens(usage: Any) -> tuple[int, int]:
    """Extract usage token counts from dict- or object-shaped usage values."""
    if isinstance(usage, dict):
        return (
            _coerce_int(usage.get("input_tokens", 0)),
            _coerce_int(usage.get("output_tokens", 0)),
        )
    return (
        _coerce_int(getattr(usage, "input_tokens", 0)),
        _coerce_int(getattr(usage, "output_tokens", 0)),
    )
