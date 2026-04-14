"""Tests asserting the security module is importable at its new path.

Test Spec: TS-103-4, TS-103-E1
Requirements: 103-REQ-2.1, 103-REQ-2.E1
"""

from __future__ import annotations

import pytest


class TestNewImportPath:
    """TS-103-4: Security module importable at agent_fox.security.security."""

    def test_make_pre_tool_use_hook_importable(self) -> None:
        """make_pre_tool_use_hook is callable from new path."""
        from agent_fox.security.security import make_pre_tool_use_hook  # noqa: PLC0415

        assert callable(make_pre_tool_use_hook)

    def test_default_allowlist_importable(self) -> None:
        """DEFAULT_ALLOWLIST is a frozenset at new path."""
        from agent_fox.security.security import DEFAULT_ALLOWLIST  # noqa: PLC0415

        assert isinstance(DEFAULT_ALLOWLIST, frozenset)

    def test_build_effective_allowlist_importable(self) -> None:
        """build_effective_allowlist is callable from new path."""
        from agent_fox.security.security import build_effective_allowlist  # noqa: PLC0415

        assert callable(build_effective_allowlist)

    def test_check_command_allowed_importable(self) -> None:
        """check_command_allowed is callable from new path."""
        from agent_fox.security.security import check_command_allowed  # noqa: PLC0415

        assert callable(check_command_allowed)

    def test_extract_command_name_importable(self) -> None:
        """extract_command_name is callable from new path."""
        from agent_fox.security.security import extract_command_name  # noqa: PLC0415

        assert callable(extract_command_name)

    def test_check_shell_operators_importable(self) -> None:
        """check_shell_operators is callable from new path."""
        from agent_fox.security.security import check_shell_operators  # noqa: PLC0415

        assert callable(check_shell_operators)


class TestOldImportFails:
    """TS-103-E1: Old hooks.security import path must raise ImportError."""

    def test_old_hooks_security_import_fails(self) -> None:
        """Importing from agent_fox.hooks.security must raise ImportError."""
        with pytest.raises(ImportError):
            from agent_fox.hooks.security import make_pre_tool_use_hook  # noqa: F401, PLC0415
