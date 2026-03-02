"""Platform integration layer for agent-fox.

Provides the Platform protocol, NullPlatform (direct merge),
GitHubPlatform (gh CLI), and the create_platform factory.
"""

from agent_fox.platform.factory import create_platform
from agent_fox.platform.protocol import Platform

__all__ = ["Platform", "create_platform"]
