"""Unit tests for PlatformProtocol, GitHubPlatform compliance, and factory.

Test Spec: TS-61-23, TS-61-24, TS-61-25, TS-61-E1, TS-61-E11
Requirements: 61-REQ-8.1, 61-REQ-8.2, 61-REQ-8.3, 61-REQ-1.E1, 61-REQ-8.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-61-23: Platform protocol completeness
# Requirement: 61-REQ-8.1
# ---------------------------------------------------------------------------


class TestPlatformProtocolCompleteness:
    """Verify that PlatformProtocol defines all required methods."""

    def test_protocol_has_required_methods(self) -> None:
        """Protocol defines create_issue, list_issues_by_label,
        add_issue_comment, assign_label, close.
        Note: create_pr was removed in spec 65 (65-REQ-4.1)."""
        from agent_fox.platform.protocol import PlatformProtocol

        methods = {m for m in dir(PlatformProtocol) if not m.startswith("_")}
        required = {
            "create_issue",
            "list_issues_by_label",
            "add_issue_comment",
            "assign_label",
            "close",
        }
        assert required.issubset(methods)


# ---------------------------------------------------------------------------
# TS-61-24: GitHub implements platform protocol
# Requirement: 61-REQ-8.2
# ---------------------------------------------------------------------------


class TestGitHubPlatformProtocol:
    """Verify that GitHubPlatform satisfies PlatformProtocol."""

    def test_isinstance_check(self) -> None:
        """GitHubPlatform is an instance of PlatformProtocol."""
        from agent_fox.platform.github import GitHubPlatform
        from agent_fox.platform.protocol import PlatformProtocol

        gh = GitHubPlatform(owner="x", repo="y", token="t")
        assert isinstance(gh, PlatformProtocol)


# ---------------------------------------------------------------------------
# TS-61-25: Platform instantiation from config
# Requirement: 61-REQ-8.3
# ---------------------------------------------------------------------------


class TestPlatformFactory:
    """Verify platform is instantiated from config."""

    def test_github_platform_from_config(self, tmp_path: object) -> None:
        """Config with type='github' returns a GitHubPlatform."""
        from unittest.mock import patch

        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.platform_factory import create_platform
        from agent_fox.platform.github import GitHubPlatform

        config = AgentFoxConfig()
        config.platform.type = "github"  # type: ignore[misc]

        with patch.dict("os.environ", {"GITHUB_PAT": "test-token"}):
            platform = create_platform(config, tmp_path)  # type: ignore[arg-type]

        assert isinstance(platform, GitHubPlatform)


# ---------------------------------------------------------------------------
# TS-61-E1: Platform not configured
# Requirement: 61-REQ-1.E1
# ---------------------------------------------------------------------------


class TestPlatformNotConfigured:
    """Verify abort when platform is not configured."""

    def test_abort_with_exit_code_1(self) -> None:
        """Raises SystemExit with code 1 when platform type is 'none'."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.engine import validate_night_shift_prerequisites

        config = AgentFoxConfig()
        assert config.platform.type == "none"

        with pytest.raises(SystemExit) as exc_info:
            validate_night_shift_prerequisites(config)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TS-61-E11: Unknown platform type
# Requirement: 61-REQ-8.E1
# ---------------------------------------------------------------------------


class TestUnknownPlatformType:
    """Verify abort on unknown platform type."""

    def test_abort_with_exit_code_1(self, tmp_path: object) -> None:
        """Raises SystemExit with code 1 for unknown platform type."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.platform_factory import create_platform

        config = AgentFoxConfig()
        config.platform.type = "bitbucket"  # type: ignore[misc]

        with pytest.raises(SystemExit) as exc_info:
            create_platform(config, tmp_path)  # type: ignore[arg-type]
        assert exc_info.value.code == 1
