"""Exception hierarchy for agent-fox.

Defines a base AgentFoxError with optional structured context,
and specific subclasses for each error category in the system.

Requirements: 01-REQ-4.1, 01-REQ-4.2, 01-REQ-4.3
"""

from __future__ import annotations

from typing import Any


class AgentFoxError(Exception):
    """Base exception for all agent-fox errors."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.context = context


class ConfigError(AgentFoxError): ...


class InitError(AgentFoxError): ...


class PlanError(AgentFoxError): ...


class SessionError(AgentFoxError): ...


class WorkspaceError(AgentFoxError): ...


class IntegrationError(AgentFoxError): ...


class HookError(AgentFoxError): ...


class SessionTimeoutError(AgentFoxError): ...


class CostLimitError(AgentFoxError): ...


class SecurityError(AgentFoxError): ...


class KnowledgeStoreError(AgentFoxError): ...
