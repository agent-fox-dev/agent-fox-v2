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


class IntegrationError(AgentFoxError):
    """Error during workspace integration (harvest/merge).

    Attributes:
        retryable: Whether the error is retryable. Defaults to True for
            backward compatibility. Set to False for workspace-state errors
            (e.g. divergent untracked files) that cannot be resolved by
            re-running the same session.

    Requirements: 118-REQ-3.1
    """

    def __init__(self, message: str, *, retryable: bool = True, **context: Any) -> None:
        super().__init__(message, **context)
        self.retryable = retryable


class SessionTimeoutError(AgentFoxError): ...


class CostLimitError(AgentFoxError): ...


class SecurityError(AgentFoxError): ...


class KnowledgeStoreError(AgentFoxError): ...
