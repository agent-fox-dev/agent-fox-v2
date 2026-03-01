"""Session runner: execute coding sessions via the claude-code-sdk.

Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
              03-REQ-8.1 through 03-REQ-8.E1
"""

from __future__ import annotations

from dataclasses import dataclass, field

from claude_code_sdk import query  # noqa: F401

from agent_fox.core.config import AgentFoxConfig
from agent_fox.session.timeout import with_timeout  # noqa: F401
from agent_fox.workspace.worktree import WorkspaceInfo

DEFAULT_BASH_ALLOWLIST: list[str] = [
    # Version control
    "git",
    # Package management
    "uv", "pip", "npm", "npx", "yarn", "pnpm",
    # Build and test
    "python", "python3", "pytest", "mypy", "ruff",
    "make", "cargo", "go", "node",
    # File utilities
    "cat", "head", "tail", "less", "wc", "sort", "uniq",
    "find", "grep", "rg", "sed", "awk", "tr", "cut",
    "ls", "tree", "pwd", "basename", "dirname", "realpath",
    "cp", "mv", "rm", "mkdir", "rmdir", "touch", "chmod",
    # System info
    "echo", "printf", "date", "env", "which", "whoami",
    "uname", "diff", "patch", "tee", "xargs",
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
    raise NotImplementedError


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
    raise NotImplementedError
