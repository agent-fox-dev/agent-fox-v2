"""Agent backend and canonical message types.

Provides the ClaudeBackend adapter and canonical message types used
throughout the session layer.

Requirements: 26-REQ-1.1, 26-REQ-2.1
"""

from agent_fox.session.backends.claude import ClaudeBackend
from agent_fox.session.backends.types import (
    AgentMessage,
    AssistantMessage,
    PermissionCallback,
    ResultMessage,
    ToolUseMessage,
)

__all__ = [
    "AgentMessage",
    "AssistantMessage",
    "ClaudeBackend",
    "PermissionCallback",
    "ResultMessage",
    "ToolUseMessage",
]
