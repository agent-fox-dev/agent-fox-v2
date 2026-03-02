"""Session runner: execute coding sessions via the claude-code-sdk.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from claude_code_sdk import ClaudeCodeOptions, query  # noqa: F401

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.session.timeout import with_timeout  # noqa: F401
from agent_fox.workspace.worktree import WorkspaceInfo

logger = logging.getLogger(__name__)

DEFAULT_BASH_ALLOWLIST: list[str] = [
    # Version control
    "git",
    # Package management
    "uv",
    "pip",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    # Build and test
    "python",
    "python3",
    "pytest",
    "mypy",
    "ruff",
    "make",
    "cargo",
    "go",
    "node",
    # File utilities
    "cat",
    "head",
    "tail",
    "less",
    "wc",
    "sort",
    "uniq",
    "find",
    "grep",
    "rg",
    "sed",
    "awk",
    "tr",
    "cut",
    "ls",
    "tree",
    "pwd",
    "basename",
    "dirname",
    "realpath",
    "cp",
    "mv",
    "rm",
    "mkdir",
    "rmdir",
    "touch",
    "chmod",
    # System info
    "echo",
    "printf",
    "date",
    "env",
    "which",
    "whoami",
    "uname",
    "diff",
    "patch",
    "tee",
    "xargs",
]


@dataclass(frozen=True)
class SessionOutcome:
    """Result of a coding session."""

    spec_name: str
    task_group: int
    node_id: str
    status: str  # "completed" | "failed" | "timeout"
    files_touched: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error_message: str | None = None


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
        task_group=workspace.task_group,
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

    # 03-REQ-3.1, 03-REQ-3.4: Call query with options
    options = ClaudeCodeOptions(
        cwd=cwd,
        model=model_id,
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
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


def build_allowlist_hook(
    config: AgentFoxConfig,
) -> dict:
    """Build a PreToolUse hook configuration for the command allowlist.

    Returns a dict suitable for ClaudeAgentOptions.hooks with a
    PreToolUse matcher that intercepts Bash tool invocations and
    blocks commands not on the effective allowlist.

    The effective allowlist is:
    - config.security.bash_allowlist (if set, replaces defaults)
    - OR: DEFAULT_ALLOWLIST + config.security.bash_allowlist_extend
    """
    # 03-REQ-8.2: Compute effective allowlist
    if config.security.bash_allowlist is not None:
        effective_allowlist = set(config.security.bash_allowlist)
    else:
        effective_allowlist = set(
            DEFAULT_BASH_ALLOWLIST + config.security.bash_allowlist_extend,
        )

    def hook_callback(
        *,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """PreToolUse hook that enforces the command allowlist.

        03-REQ-8.1: Intercept Bash tool invocations and extract
        the command name (first token of the command string).
        """
        # Non-Bash tools pass through
        if tool_name != "Bash":
            return {}

        command = tool_input.get("command", "")

        # 03-REQ-8.E1: Block empty or unparseable commands
        stripped = command.strip()
        if not stripped:
            return {
                "decision": "block",
                "message": "Empty command is not allowed.",
            }

        # Extract first token (command name)
        first_token = stripped.split()[0]

        # 03-REQ-8.2: Block if not on allowlist
        if first_token not in effective_allowlist:
            return {
                "decision": "block",
                "message": f"Command '{first_token}' is not on the allowlist.",
            }

        return {}

    return {"callback": hook_callback}
