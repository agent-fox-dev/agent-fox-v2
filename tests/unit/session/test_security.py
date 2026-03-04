"""Allowlist hook tests.

Test Spec: TS-03-12 (allowlist enforcement), TS-03-E7 (empty command)
Requirements: 03-REQ-8.1, 03-REQ-8.2, 03-REQ-8.E1
"""

from __future__ import annotations

from agent_fox.core.config import AgentFoxConfig
from agent_fox.session.runner import build_allowlist_hook


class TestAllowlistHookEnforcement:
    """TS-03-12: Allowlist hook blocks disallowed commands."""

    def test_blocks_disallowed_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """A command not on the allowlist is blocked."""
        hook = build_allowlist_hook(small_allowlist_config)

        # The hook should be a callable or dict with a callback
        # that blocks 'rm' (not in ['git', 'python'])
        result = _invoke_hook(hook, tool_name="Bash", command="rm -rf /")
        assert result.get("decision") == "block"

    def test_allows_allowlisted_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """A command on the allowlist is allowed."""
        hook = build_allowlist_hook(small_allowlist_config)

        result = _invoke_hook(hook, tool_name="Bash", command="git status")
        # Either no decision key or decision is not "block"
        assert result.get("decision") != "block"

    def test_allows_second_allowlisted_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """Both allowlisted commands are permitted."""
        hook = build_allowlist_hook(small_allowlist_config)

        result = _invoke_hook(hook, tool_name="Bash", command="python script.py")
        assert result.get("decision") != "block"

    def test_blocks_command_not_on_default_when_replaced(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """When bash_allowlist is set, default allowlist commands are blocked."""
        hook = build_allowlist_hook(small_allowlist_config)

        # 'ls' is in DEFAULT_BASH_ALLOWLIST but not in ['git', 'python']
        result = _invoke_hook(hook, tool_name="Bash", command="ls -la")
        assert result.get("decision") == "block"

    def test_non_bash_tool_not_blocked(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """Non-Bash tool invocations are not blocked by the hook."""
        hook = build_allowlist_hook(small_allowlist_config)

        result = _invoke_hook(hook, tool_name="Read", command="")
        # Non-Bash tools should pass through
        assert result.get("decision") != "block"


class TestAllowlistHookEmptyCommand:
    """TS-03-E7: Allowlist hook blocks empty command."""

    def test_blocks_empty_command(self, default_config: AgentFoxConfig) -> None:
        """An empty command string is blocked."""
        hook = build_allowlist_hook(default_config)

        result = _invoke_hook(hook, tool_name="Bash", command="")
        assert result.get("decision") == "block"

    def test_blocks_whitespace_command(
        self,
        default_config: AgentFoxConfig,
    ) -> None:
        """A whitespace-only command string is blocked."""
        hook = build_allowlist_hook(default_config)

        result = _invoke_hook(hook, tool_name="Bash", command="   ")
        assert result.get("decision") == "block"


def _invoke_hook(
    hook: dict,
    *,
    tool_name: str,
    command: str,
) -> dict:
    """Simulate invoking a PreToolUse hook.

    Extracts the hook callback from the hook configuration dict and
    calls it with a simulated tool invocation. Returns the hook's
    decision dict.

    The hook dict is expected to contain a callback function that
    accepts tool_name and tool_input parameters.
    """
    callback = hook.get("callback")
    if callback is None:
        # Try alternative hook structure
        raise ValueError(f"Hook dict does not contain a 'callback' key: {hook!r}")

    tool_input = {"command": command} if tool_name == "Bash" else {}

    # The callback may be sync or async; handle both
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(callback):
        result = asyncio.get_event_loop().run_until_complete(
            callback(tool_name=tool_name, tool_input=tool_input),
        )
    else:
        result = callback(tool_name=tool_name, tool_input=tool_input)

    return result if isinstance(result, dict) else {}
