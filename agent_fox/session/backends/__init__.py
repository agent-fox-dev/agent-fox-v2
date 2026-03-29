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
    ToolDefinition,
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
    "ToolDefinition",
    "ToolUseMessage",
    "get_backend",
]


def get_backend() -> AgentBackend:
    """Return the ClaudeBackend.

    Agent-fox uses Claude exclusively for all coding agent workloads.
    This function exists to centralise backend instantiation and support
    future configuration (e.g., connection pooling), not to dispatch
    between providers.

    The AgentBackend protocol is preserved for test mock injection.
    """
    from agent_fox.session.backends.claude import ClaudeBackend

    return ClaudeBackend()
