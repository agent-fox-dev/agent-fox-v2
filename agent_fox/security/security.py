"""Command allowlist enforcement for shell commands.

Restricts which commands the coding agent can execute via the Bash tool.
Provides a default allowlist of standard development commands and supports
customization through configuration.

In addition to checking the leading command name against an allowlist, the
module rejects commands that contain shell operators (pipes, semicolons,
subshells, redirects, etc.) which would allow invoking arbitrary commands
behind an allowed leading token.

Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.3, 06-REQ-9.1, 06-REQ-9.2
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from agent_fox.core.config import SecurityConfig
from agent_fox.core.errors import SecurityError  # noqa: F401

logger = logging.getLogger("agent_fox.security.security")

# Default allowlist: ~46 standard development commands
DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Version control
        "git",
        # Python ecosystem
        "python",
        "python3",
        "uv",
        "pip",
        "pytest",
        "ruff",
        "mypy",
        # JavaScript ecosystem
        "npm",
        "npx",
        "node",
        # Build tools
        "make",
        "cargo",
        "go",
        "rustc",
        "gcc",
        # File utilities
        "ls",
        "cat",
        "mkdir",
        "cp",
        "mv",
        "rm",
        "find",
        "grep",
        "sed",
        "awk",
        "echo",
        "head",
        "tail",
        "wc",
        "sort",
        "diff",
        "touch",
        "chmod",
        # Network utilities
        "curl",
        "wget",
        # Archive utilities
        "tar",
        "gzip",
        # System utilities
        "which",
        "printenv",
        "date",
        # Shell builtins / control
        "cd",
        "pwd",
        "test",
        "true",
        "false",
    }
)


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
    if config.bash_allowlist is not None:
        # 06-REQ-9.E1: if both are set, bash_allowlist takes precedence
        if config.bash_allowlist_extend:
            logger.warning(
                "Both bash_allowlist and bash_allowlist_extend are configured; "
                "bash_allowlist takes precedence, ignoring bash_allowlist_extend"
            )
        # 06-REQ-9.1: custom allowlist replaces default entirely
        return frozenset(config.bash_allowlist)

    if config.bash_allowlist_extend:
        # 06-REQ-9.2: extend adds to the default allowlist
        return DEFAULT_ALLOWLIST | frozenset(config.bash_allowlist_extend)

    # Neither set: use defaults
    return DEFAULT_ALLOWLIST


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
    stripped = command_string.strip()
    if not stripped:
        raise SecurityError(
            "Command string is empty or contains only whitespace",
            command=command_string,
        )

    # Take the first whitespace-delimited token
    first_token = stripped.split()[0]

    # Strip any path prefix to get the basename
    basename = PurePosixPath(first_token).name

    return basename


# Shell operators that allow chaining or embedding arbitrary commands.
# Matched against the raw command string before allowlist checking.
_SHELL_OPERATOR_PATTERN = re.compile(
    r"""
      \|          # pipe (including ||)
    | ;           # command separator
    | &&          # logical AND chaining
    | `           # backtick subshell
    | \$\(        # $() subshell
    | [<>]        # redirects (>, <, >>, etc.)
    """,
    re.VERBOSE,
)

# Argument patterns that allow a command to execute arbitrary sub-commands.
# Checked as whitespace-delimited tokens in the command string.
_DANGEROUS_ARG_TOKENS = frozenset({"-exec", "-execdir"})


def check_shell_operators(command_string: str) -> str | None:
    """Check for shell operators that could bypass the allowlist.

    Returns an error message if dangerous operators are found, or None
    if the command is safe.
    """
    match = _SHELL_OPERATOR_PATTERN.search(command_string)
    if match:
        operator = match.group()
        return (
            f"Command contains shell operator '{operator}' which can execute "
            f"arbitrary commands. Use simple, single commands instead."
        )

    # Check for newlines which act as command separators in shell
    if "\n" in command_string:
        return (
            "Command contains newline characters which can execute "
            "arbitrary commands. Use simple, single commands instead."
        )

    # Check for dangerous argument tokens (e.g., find -exec)
    tokens = command_string.split()
    for token in tokens:
        if token in _DANGEROUS_ARG_TOKENS:
            return (
                f"Command contains '{token}' which can execute arbitrary "
                f"sub-commands. Use alternative approaches instead."
            )

    return None


def check_command_allowed(
    command_string: str,
    allowlist: frozenset[str],
) -> tuple[bool, str]:
    """Check whether a command is permitted by the allowlist.

    Performs two checks:
    1. Rejects commands containing shell operators (pipes, semicolons,
       subshells, redirects) that could bypass the allowlist.
    2. Checks the leading command name against the allowlist.

    Args:
        command_string: The full command string.
        allowlist: Set of permitted command names.

    Returns:
        Tuple of (allowed: bool, message: str). If blocked, message
        identifies the command and lists up to 10 similar allowed commands.
    """
    # Check for shell operators before allowlist name check
    operator_error = check_shell_operators(command_string)
    if operator_error is not None:
        return False, operator_error

    name = extract_command_name(command_string)

    if name in allowlist:
        return True, f"Command '{name}' is allowed"

    # Build a helpful message listing up to 10 allowed commands
    sorted_allowed = sorted(allowlist)[:10]
    alternatives = ", ".join(sorted_allowed)
    msg = f"Command '{name}' is not on the allowlist. Allowed commands include: {alternatives}"
    if len(allowlist) > 10:
        msg += f" (and {len(allowlist) - 10} more)"

    return False, msg


def make_pre_tool_use_hook(
    config: SecurityConfig,
) -> Callable[..., dict[str, Any]]:
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
    allowlist = build_effective_allowlist(config)

    def hook(
        *,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """PreToolUse hook that enforces the command allowlist.

        Args:
            tool_name: Name of the tool being invoked (e.g. "Bash", "Read").
            tool_input: Input parameters for the tool invocation.

        Returns:
            Decision dict: {"decision": "allow"} or
            {"decision": "block", "message": "..."}.
        """
        # 06-REQ-8.E2: non-Bash tools pass through without inspection
        if tool_name != "Bash":
            return {"decision": "allow"}

        # Extract the command from tool_input
        command = tool_input.get("command", "")

        try:
            allowed, message = check_command_allowed(command, allowlist)
        except SecurityError:
            # 06-REQ-8.E1: empty/whitespace command is blocked
            return {
                "decision": "block",
                "message": "Command string is empty or contains only whitespace",
            }

        if allowed:
            return {"decision": "allow"}

        return {"decision": "block", "message": message}

    return hook
