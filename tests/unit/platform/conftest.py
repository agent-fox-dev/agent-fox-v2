"""Fixtures for platform integration tests.

Provides PlatformConfig for testing.  Old NullPlatform and gh-CLI-based
GitHubPlatform fixtures have been removed (spec 19 overhaul).
"""

from __future__ import annotations

import pytest

from agent_fox.core.config import PlatformConfig


@pytest.fixture
def platform_config() -> PlatformConfig:
    """Default PlatformConfig for testing."""
    return PlatformConfig()
