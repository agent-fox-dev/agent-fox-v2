"""Allowlist hook tests.

Test Spec: TS-03-12 (allowlist enforcement), TS-03-E7 (empty command)
Requirements: 03-REQ-8.1, 03-REQ-8.2, 03-REQ-8.E1
"""

from __future__ import annotations

from agent_fox.core.config import AgentFoxConfig
from agent_fox.security.security import make_pre_tool_use_hook


class TestAllowlistHookEnforcement:
    """TS-03-12: Allowlist hook blocks disallowed commands."""

    def test_blocks_disallowed_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """A command not on the allowlist is blocked."""
        hook = make_pre_tool_use_hook(small_allowlist_config.security)

        result = hook(tool_name="Bash", tool_input={"command": "rm -rf /"})
        assert result.get("decision") == "block"

    def test_allows_allowlisted_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """A command on the allowlist is allowed."""
        hook = make_pre_tool_use_hook(small_allowlist_config.security)

        result = hook(tool_name="Bash", tool_input={"command": "git status"})
        assert result.get("decision") != "block"

    def test_allows_second_allowlisted_command(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """Both allowlisted commands are permitted."""
        hook = make_pre_tool_use_hook(small_allowlist_config.security)

        result = hook(tool_name="Bash", tool_input={"command": "python script.py"})
        assert result.get("decision") != "block"

    def test_blocks_command_not_on_default_when_replaced(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """When bash_allowlist is set, default allowlist commands are blocked."""
        hook = make_pre_tool_use_hook(small_allowlist_config.security)

        # 'ls' is in DEFAULT_ALLOWLIST but not in ['git', 'python']
        result = hook(tool_name="Bash", tool_input={"command": "ls -la"})
        assert result.get("decision") == "block"

    def test_non_bash_tool_not_blocked(
        self,
        small_allowlist_config: AgentFoxConfig,
    ) -> None:
        """Non-Bash tool invocations are not blocked by the hook."""
        hook = make_pre_tool_use_hook(small_allowlist_config.security)

        result = hook(tool_name="Read", tool_input={})
        assert result.get("decision") != "block"


class TestAllowlistHookEmptyCommand:
    """TS-03-E7: Allowlist hook blocks empty command."""

    def test_blocks_empty_command(self, default_config: AgentFoxConfig) -> None:
        """An empty command string is blocked."""
        hook = make_pre_tool_use_hook(default_config.security)

        result = hook(tool_name="Bash", tool_input={"command": ""})
        assert result.get("decision") == "block"

    def test_blocks_whitespace_command(
        self,
        default_config: AgentFoxConfig,
    ) -> None:
        """A whitespace-only command string is blocked."""
        hook = make_pre_tool_use_hook(default_config.security)

        result = hook(tool_name="Bash", tool_input={"command": "   "})
        assert result.get("decision") == "block"
