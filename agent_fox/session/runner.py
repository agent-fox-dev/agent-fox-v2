"""Session runner: execute coding sessions via the claude-code-sdk.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from claude_code_sdk import ClaudeCodeOptions, query  # noqa: F401
from claude_code_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.hooks.security import make_pre_tool_use_hook
from agent_fox.knowledge.sink import SessionOutcome
from agent_fox.workspace.worktree import WorkspaceInfo

logger = logging.getLogger(__name__)


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
    2. Call query(prompt=task_prompt, options=options)
    3. Iterate messages, collecting the final ResultMessage
    4. Wrap the entire query in asyncio.wait_for with the
       configured session_timeout
    5. Build and return a SessionOutcome

    Raises:
        SessionTimeoutError: Propagated if caller does not catch.
        SessionError: On SDK errors.
    """
    # Resolve the coding model
    model_entry = resolve_model(config.models.coding)

    # Track metrics (potentially partial for timeout case)
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

    except Exception as exc:
        # 03-REQ-3.E1: Catch SDK errors, return failed outcome
        status = "failed"
        error_message = str(exc)
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
) -> dict[str, Any]:
    """Execute the SDK query and collect results from messages.

    Returns a dict with token usage, duration, status, and error info.
    """
    input_tokens = 0
    output_tokens = 0
    duration_ms = 0
    error_message: str | None = None
    status = "completed"

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

    # 03-REQ-3.1, 03-REQ-3.4: Call query with options + allowlist hook
    options = ClaudeCodeOptions(
        cwd=cwd,
        model=model_id,
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
        can_use_tool=_can_use_tool,
    )
    async for message in query(
        prompt=task_prompt,
        options=options,
    ):
        # 03-REQ-3.2: Collect the ResultMessage
        if getattr(message, "type", None) == "result":
            usage = getattr(message, "usage", None)
            if usage is not None:
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
            duration_ms = getattr(message, "duration_ms", 0)

            # 03-REQ-3.E2: Check is_error flag
            if getattr(message, "is_error", False):
                status = "failed"
                error_message = getattr(message, "result", None) or "Unknown error"

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "error_message": error_message,
        "status": status,
    }
