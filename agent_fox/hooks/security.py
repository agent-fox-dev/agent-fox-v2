"""Command allowlist enforcement for shell commands.

Restricts which commands the coding agent can execute via the Bash tool.
Provides a default allowlist of standard development commands and supports
customization through configuration.

Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.3, 06-REQ-9.1, 06-REQ-9.2
"""

from __future__ import annotations

import logging

from agent_fox.core.config import SecurityConfig
from agent_fox.core.errors import SecurityError  # noqa: F401

logger = logging.getLogger("agent_fox.hooks.security")

# Default allowlist: ~46 standard development commands
DEFAULT_ALLOWLIST: frozenset[str] = frozenset({
    # Version control
    "git",
    # Python ecosystem
    "python", "python3", "uv", "pip", "pytest", "ruff", "mypy",
    # JavaScript ecosystem
    "npm", "npx", "node",
    # Build tools
    "make", "cargo", "go", "rustc", "gcc",
    # File utilities
    "ls", "cat", "mkdir", "cp", "mv", "rm", "find", "grep",
    "sed", "awk", "echo", "head", "tail", "wc", "sort", "diff",
    "touch", "chmod",
    # Network utilities
    "curl", "wget",
    # Archive utilities
    "tar", "gzip",
    # System utilities
    "which", "env", "printenv", "date",
    # Shell builtins / control
    "cd", "pwd", "test", "true", "false",
})


def build_effective_allowlist(config: SecurityConfig) -> frozenset[str]:
    """Compute the effective allowlist from configuration.

    - If bash_allowlist is set, use it as the complete list (replaces defaults).
    - If bash_allowlist_extend is set (and bash_allowlist is not), use
      DEFAULT_ALLOWLIST + extensions.
    - If both are set, bash_allowlist takes precedence and a warning is logged.
    - If neither is set, use DEFAULT_ALLOWLIST.

    Args:
        config: SecurityConfig with allowlist settings.

    Returns:
        Frozenset of permitted command names.
    """
    raise NotImplementedError


def extract_command_name(command_string: str) -> str:
    """Extract the command name from a shell command string.

    Takes the first whitespace-delimited token and strips any path prefix
    to yield the basename. For example:
    - "git status" -> "git"
    - "/usr/bin/python3 -m pytest" -> "python3"
    - "  ls -la  " -> "ls"

    Args:
        command_string: The full command string from the Bash tool.

    Returns:
        The extracted command name (basename only).

    Raises:
        SecurityError: If the command string is empty or whitespace-only.
    """
    raise NotImplementedError


def check_command_allowed(
    command_string: str,
    allowlist: frozenset[str],
) -> tuple[bool, str]:
    """Check whether a command is permitted by the allowlist.

    Args:
        command_string: The full command string.
        allowlist: Set of permitted command names.

    Returns:
        Tuple of (allowed: bool, message: str). If blocked, message
        identifies the command and lists up to 10 similar allowed commands.
    """
    raise NotImplementedError


def make_pre_tool_use_hook(
    config: SecurityConfig,
) -> object:
    """Create a PreToolUse hook function for the claude-code-sdk.

    The returned callable inspects Bash tool invocations and blocks
    commands not on the effective allowlist. Non-Bash tool invocations
    are passed through without inspection.

    The hook follows the claude-code-sdk PreToolUse protocol:
    - Receives tool_name and tool_input
    - Returns {"decision": "allow"} or {"decision": "block", "message": "..."}

    Args:
        config: SecurityConfig with allowlist settings.

    Returns:
        A callable suitable for use as a PreToolUse hook.
    """
    raise NotImplementedError
