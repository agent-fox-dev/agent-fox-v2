"""Agent backend abstraction layer.

Provides the AgentBackend protocol, canonical message types, and a backend
registry with factory function.

Requirements: 26-REQ-1.1, 26-REQ-2.1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_fox.session.backends.protocol import (
    AgentBackend,
    AgentMessage,
    AssistantMessage,
    PermissionCallback,
    ResultMessage,
    ToolUseMessage,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "AgentBackend",
    "AgentMessage",
    "AssistantMessage",
    "PermissionCallback",
    "ResultMessage",
    "ToolUseMessage",
    "get_backend",
]


def get_backend(name: str = "claude") -> AgentBackend:
    """Create an AgentBackend instance by name.

    Args:
        name: Backend identifier. Currently only ``"claude"`` is supported.

    Returns:
        An AgentBackend implementation.

    Raises:
        ValueError: If the backend name is not recognized.
    """
    if name == "claude":
        from agent_fox.session.backends.claude import ClaudeBackend

        return ClaudeBackend()

    raise ValueError(f"Unknown backend: {name!r}. Available: 'claude'")
