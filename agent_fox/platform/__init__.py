"""Platform integration layer for agent-fox.

Provides GitHubPlatform (REST API) and parse_github_remote utility.

Requirements: 19-REQ-4.1, 19-REQ-6.1, 19-REQ-6.3
"""

from agent_fox.platform.github import GitHubPlatform, parse_github_remote

__all__ = [
    "GitHubPlatform",
    "parse_github_remote",
]
