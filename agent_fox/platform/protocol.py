"""Platform protocol: abstract interface for forge integration.

Defines the Platform Protocol with a single ``create_pr`` method.
Implementations handle the specific forge (e.g. GitHub REST API).

Requirements: 19-REQ-4.1, 19-REQ-6.2
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Platform(Protocol):
    """Interface for remote forge integration.

    Implementations handle pull request creation. The orchestrator
    calls ``create_pr`` without knowing the specific forge.

    Requirements: 19-REQ-6.2
    """

    async def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
    ) -> str:
        """Create a pull request.

        Args:
            branch: The feature branch (head).
            title: PR title.
            body: PR body/description.

        Returns:
            The PR URL as a string.

        Raises:
            IntegrationError: If PR creation fails.
        """
        ...
