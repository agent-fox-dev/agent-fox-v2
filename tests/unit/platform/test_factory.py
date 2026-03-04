"""Tests for create_platform factory function.

Test Spec: TS-10-11 (factory returns NullPlatform),
           TS-10-12 (factory returns GitHubPlatform),
           TS-10-E8 (unknown type raises ConfigError)
Requirements: 10-REQ-5.1, 10-REQ-5.2, 10-REQ-5.3, 10-REQ-5.E1
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import ConfigError
from agent_fox.platform.factory import create_platform
from agent_fox.platform.null import NullPlatform


class TestFactoryReturnsNullPlatform:
    """TS-10-11: Factory returns NullPlatform for type "none".

    Requirement: 10-REQ-5.2
    """

    def test_returns_null_platform(self) -> None:
        """create_platform(type='none') returns NullPlatform."""
        config = PlatformConfig(type="none")
        platform = create_platform(config)
        assert isinstance(platform, NullPlatform)

    def test_default_config_returns_null_platform(self) -> None:
        """Default PlatformConfig (type='none') returns NullPlatform."""
        config = PlatformConfig()
        platform = create_platform(config)
        assert isinstance(platform, NullPlatform)


class TestFactoryReturnsGitHubPlatform:
    """TS-10-12: Factory returns GitHubPlatform for type "github".

    Requirement: 10-REQ-5.3
    """

    def test_returns_github_platform(self) -> None:
        """create_platform(type='github') returns GitHubPlatform."""
        from agent_fox.platform.github import GitHubPlatform

        with (
            patch(
                "agent_fox.platform.github.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "agent_fox.platform.github.subprocess.run",
                return_value=__import__("subprocess").CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
            ),
        ):
            config = PlatformConfig(type="github", ci_timeout=300)
            platform = create_platform(config)
            assert isinstance(platform, GitHubPlatform)


class TestFactoryUnknownType:
    """TS-10-E8: Factory raises ConfigError for unknown platform type.

    Requirement: 10-REQ-5.E1
    """

    def test_raises_config_error(self) -> None:
        """create_platform raises ConfigError for unrecognized type."""
        config = PlatformConfig(type="gitlab")
        with pytest.raises(ConfigError) as exc_info:
            create_platform(config)
        assert "none" in str(exc_info.value)
        assert "github" in str(exc_info.value)

    def test_raises_for_empty_type(self) -> None:
        """create_platform raises ConfigError for empty string type."""
        config = PlatformConfig(type="")
        with pytest.raises(ConfigError):
            create_platform(config)

    def test_raises_for_random_string(self) -> None:
        """create_platform raises ConfigError for arbitrary string type."""
        config = PlatformConfig(type="bitbucket")
        with pytest.raises(ConfigError):
            create_platform(config)
