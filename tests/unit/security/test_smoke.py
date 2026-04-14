"""Integration smoke test for security allowlist enforcement.

Test Spec: TS-103-SMOKE-1
Requirements: 103-REQ-2.2
"""

from __future__ import annotations

from agent_fox.core.config import SecurityConfig


class TestSecurityAllowlistEnforcementEndToEnd:
    """TS-103-SMOKE-1: Security allowlist enforcement via relocated module."""

    def test_disallowed_bash_command_is_blocked(self) -> None:
        """make_pre_tool_use_hook blocks a command not on the allowlist."""
        from agent_fox.security.security import make_pre_tool_use_hook  # noqa: PLC0415

        hook = make_pre_tool_use_hook(SecurityConfig())
        # docker is not on the default allowlist
        result = hook(tool_name="Bash", tool_input={"command": "docker run evil/image"})
        assert result["decision"] == "block"

    def test_allowed_bash_command_passes_through(self) -> None:
        """make_pre_tool_use_hook allows a command on the allowlist."""
        from agent_fox.security.security import make_pre_tool_use_hook  # noqa: PLC0415

        hook = make_pre_tool_use_hook(SecurityConfig())
        result = hook(tool_name="Bash", tool_input={"command": "git status"})
        assert result["decision"] == "allow"

    def test_non_bash_tool_passes_through(self) -> None:
        """make_pre_tool_use_hook passes non-Bash tools without inspection."""
        from agent_fox.security.security import make_pre_tool_use_hook  # noqa: PLC0415

        hook = make_pre_tool_use_hook(SecurityConfig())
        result = hook(tool_name="Read", tool_input={"path": "/tmp/foo"})
        assert result["decision"] == "allow"
