"""Command allowlist security tests.

Test Spec: TS-06-9 (default allowlist), TS-06-10 (allowed command),
           TS-06-11 (blocked command), TS-06-12 (path prefix),
           TS-06-13 (custom allowlist), TS-06-14 (allowlist extend)
Edge Cases: TS-06-E3 (empty command), TS-06-E4 (non-Bash tool passthrough),
            TS-06-E6 (both allowlist options)
Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.3, 06-REQ-8.E1, 06-REQ-8.E2,
              06-REQ-9.1, 06-REQ-9.2, 06-REQ-9.E1
"""

from __future__ import annotations

import logging

import pytest

from agent_fox.core.config import SecurityConfig
from agent_fox.core.errors import SecurityError
from agent_fox.hooks.security import (
    DEFAULT_ALLOWLIST,
    build_effective_allowlist,
    check_command_allowed,
    extract_command_name,
    make_pre_tool_use_hook,
)


class TestDefaultAllowlist:
    """TS-06-9: Default allowlist contains expected commands.

    Requirement: 06-REQ-8.3
    """

    def test_contains_core_commands(self) -> None:
        """DEFAULT_ALLOWLIST contains all documented commands."""
        expected = {
            "git", "python", "python3", "uv", "npm", "node", "pytest",
            "ruff", "mypy", "make", "cargo", "go", "ls", "cat", "mkdir",
            "cp", "mv", "rm", "find", "grep", "sed", "awk", "echo",
            "curl", "wget", "tar", "gzip", "which", "env", "printenv",
            "date", "head", "tail", "wc", "sort", "diff", "touch", "chmod",
        }
        assert expected.issubset(DEFAULT_ALLOWLIST)

    def test_contains_shell_builtins(self) -> None:
        """DEFAULT_ALLOWLIST contains shell builtins."""
        builtins = {"cd", "pwd", "test", "true", "false"}
        assert builtins.issubset(DEFAULT_ALLOWLIST)

    def test_contains_additional_tools(self) -> None:
        """DEFAULT_ALLOWLIST contains additional documented tools."""
        extra = {"pip", "npx", "rustc", "gcc"}
        assert extra.issubset(DEFAULT_ALLOWLIST)

    def test_is_frozenset(self) -> None:
        """DEFAULT_ALLOWLIST is a frozenset (immutable)."""
        assert isinstance(DEFAULT_ALLOWLIST, frozenset)


class TestAllowedCommandCheck:
    """TS-06-10: Allowed command passes allowlist check.

    Requirements: 06-REQ-8.1, 06-REQ-8.2
    """

    def test_allowed_command_returns_true(self) -> None:
        """A command on the allowlist returns (True, ...)."""
        allowed, msg = check_command_allowed("git status --short", DEFAULT_ALLOWLIST)
        assert allowed is True

    def test_allowed_python_command(self) -> None:
        """python3 command is allowed."""
        allowed, msg = check_command_allowed("python3 -m pytest", DEFAULT_ALLOWLIST)
        assert allowed is True

    def test_allowed_ls_command(self) -> None:
        """ls command is allowed."""
        allowed, msg = check_command_allowed("ls -la /tmp", DEFAULT_ALLOWLIST)
        assert allowed is True


class TestBlockedCommandCheck:
    """TS-06-11: Blocked command fails allowlist check.

    Requirement: 06-REQ-8.2
    """

    def test_blocked_command_returns_false(self) -> None:
        """A command not on the allowlist returns (False, ...)."""
        allowed, msg = check_command_allowed("docker run evil", DEFAULT_ALLOWLIST)
        assert allowed is False

    def test_blocked_message_mentions_command(self) -> None:
        """Block message identifies the disallowed command."""
        allowed, msg = check_command_allowed("docker run evil", DEFAULT_ALLOWLIST)
        assert "docker" in msg

    def test_blocked_sudo(self) -> None:
        """sudo command is blocked."""
        allowed, msg = check_command_allowed("sudo rm -rf /", DEFAULT_ALLOWLIST)
        assert allowed is False


class TestCommandExtraction:
    """TS-06-12: Command extraction strips path prefix.

    Requirement: 06-REQ-8.1
    """

    def test_strips_absolute_path(self) -> None:
        """Path prefix is stripped from command."""
        assert extract_command_name("/usr/bin/python3 -m pytest") == "python3"

    def test_strips_local_bin_path(self) -> None:
        """Home directory path prefix is stripped."""
        assert extract_command_name("/home/user/.local/bin/ruff check .") == "ruff"

    def test_simple_command(self) -> None:
        """Simple command without path works correctly."""
        assert extract_command_name("git status") == "git"

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is handled."""
        assert extract_command_name("  ls -la  ") == "ls"

    def test_command_with_no_args(self) -> None:
        """Single command with no arguments works."""
        assert extract_command_name("pwd") == "pwd"


class TestCustomAllowlistReplaces:
    """TS-06-13: Custom allowlist replaces default.

    Requirement: 06-REQ-9.1
    """

    def test_custom_replaces_default(self) -> None:
        """Setting bash_allowlist replaces the default allowlist entirely."""
        config = SecurityConfig(bash_allowlist=["git", "make"])
        result = build_effective_allowlist(config)

        assert result == frozenset({"git", "make"})

    def test_default_commands_not_present(self) -> None:
        """Default commands not in custom list are excluded."""
        config = SecurityConfig(bash_allowlist=["git", "make"])
        result = build_effective_allowlist(config)

        assert "python" not in result
        assert "ls" not in result


class TestAllowlistExtend:
    """TS-06-14: Allowlist extend adds to default.

    Requirement: 06-REQ-9.2
    """

    def test_extend_adds_to_default(self) -> None:
        """bash_allowlist_extend adds commands to the default list."""
        config = SecurityConfig(bash_allowlist_extend=["docker", "kubectl"])
        result = build_effective_allowlist(config)

        assert "git" in result  # from default
        assert "docker" in result  # from extension
        assert "kubectl" in result  # from extension

    def test_extend_preserves_defaults(self) -> None:
        """Extension preserves all default commands."""
        config = SecurityConfig(bash_allowlist_extend=["docker"])
        result = build_effective_allowlist(config)

        assert DEFAULT_ALLOWLIST.issubset(result)


# -- Edge case tests ---------------------------------------------------------


class TestEmptyCommandBlocked:
    """TS-06-E3: Empty command string blocked.

    Requirement: 06-REQ-8.E1
    """

    def test_empty_string_raises(self) -> None:
        """Empty command string raises SecurityError."""
        with pytest.raises(SecurityError):
            extract_command_name("")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only command string raises SecurityError."""
        with pytest.raises(SecurityError):
            extract_command_name("   ")

    def test_tabs_only_raises(self) -> None:
        """Tab-only command string raises SecurityError."""
        with pytest.raises(SecurityError):
            extract_command_name("\t\t")


class TestNonBashToolPassthrough:
    """TS-06-E4: Non-Bash tool passes through.

    Requirement: 06-REQ-8.E2
    """

    def test_read_tool_allowed(self) -> None:
        """Read tool invocation is allowed without inspection."""
        hook = make_pre_tool_use_hook(SecurityConfig())
        result = hook(tool_name="Read", tool_input={"file_path": "/tmp/test"})
        assert result.get("decision") != "block"

    def test_write_tool_allowed(self) -> None:
        """Write tool invocation is allowed without inspection."""
        hook = make_pre_tool_use_hook(SecurityConfig())
        result = hook(tool_name="Write", tool_input={"file_path": "/tmp/out"})
        assert result.get("decision") != "block"

    def test_bash_tool_is_inspected(self) -> None:
        """Bash tool invocations are inspected by the hook."""
        hook = make_pre_tool_use_hook(SecurityConfig())
        # docker is not on the default allowlist
        result = hook(
            tool_name="Bash",
            tool_input={"command": "docker run evil"},
        )
        assert result.get("decision") == "block"


class TestBothAllowlistOptions:
    """TS-06-E6: Both bash_allowlist and bash_allowlist_extend set.

    Requirement: 06-REQ-9.E1
    """

    def test_allowlist_takes_precedence(self) -> None:
        """bash_allowlist takes precedence when both are set."""
        config = SecurityConfig(
            bash_allowlist=["git"],
            bash_allowlist_extend=["docker"],
        )
        result = build_effective_allowlist(config)

        assert result == frozenset({"git"})
        assert "docker" not in result

    def test_warning_logged(self, caplog) -> None:
        """Warning is logged when both options are set."""
        config = SecurityConfig(
            bash_allowlist=["git"],
            bash_allowlist_extend=["docker"],
        )

        with caplog.at_level(logging.WARNING, logger="agent_fox.hooks.security"):
            build_effective_allowlist(config)

        assert any("bash_allowlist" in record.message.lower()
                    or "precedence" in record.message.lower()
                    or "ignor" in record.message.lower()
                    for record in caplog.records)
