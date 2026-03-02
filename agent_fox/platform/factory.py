"""Platform factory: select the correct Platform implementation.

Provides create_platform(config) which returns either NullPlatform or
GitHubPlatform based on PlatformConfig.type.

Requirements: 10-REQ-5.1, 10-REQ-5.2, 10-REQ-5.3, 10-REQ-5.E1
"""

from __future__ import annotations

import logging

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import ConfigError
from agent_fox.platform.github import GitHubPlatform
from agent_fox.platform.null import NullPlatform
from agent_fox.platform.protocol import Platform

logger = logging.getLogger(__name__)

_VALID_TYPES = ("none", "github")


def create_platform(config: PlatformConfig) -> Platform:
    """Create a Platform implementation based on configuration.

    Args:
        config: Platform configuration from the project config.

    Returns:
        A Platform implementation (NullPlatform or GitHubPlatform).

    Raises:
        ConfigError: If config.type is not a recognized platform type.
    """
    if config.type == "none":
        logger.info("Platform: none (direct merge)")
        return NullPlatform()
    if config.type == "github":
        logger.info("Platform: GitHub (gh CLI)")
        return GitHubPlatform(
            ci_timeout=config.ci_timeout,
            auto_merge=config.auto_merge,
        )
    raise ConfigError(
        f"Unrecognized platform type: {config.type!r}. "
        f"Valid types: {', '.join(_VALID_TYPES)}",
        field="platform.type",
        value=config.type,
    )
