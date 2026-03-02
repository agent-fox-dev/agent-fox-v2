"""SessionSink Protocol definition, sink dispatcher, event dataclasses.

Requirements: 11-REQ-4.1, 11-REQ-4.2, 11-REQ-4.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

logger = logging.getLogger("agent_fox.knowledge.sink")


@dataclass(frozen=True)
class SessionOutcome:
    """Structured record of a completed coding session."""

    id: UUID = field(default_factory=uuid4)
    spec_name: str = ""
    task_group: str = ""
    node_id: str = ""
    touched_paths: list[str] = field(default_factory=list)
    status: str = ""  # "completed" | "failed" | "timeout"
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class ToolCall:
    """Structured record of a tool invocation."""

    id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    node_id: str = ""
    tool_name: str = ""
    called_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class ToolError:
    """Structured record of a failed tool invocation."""

    id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    node_id: str = ""
    tool_name: str = ""
    failed_at: datetime = field(default_factory=datetime.utcnow)


@runtime_checkable
class SessionSink(Protocol):
    """Protocol for recording session events.

    Implementations must handle their own error suppression -- a sink
    failure must never prevent the session runner from continuing.
    """

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Record a session outcome. Called after every session."""
        ...

    def record_tool_call(self, call: ToolCall) -> None:
        """Record a tool invocation. May be a no-op in non-debug mode."""
        ...

    def record_tool_error(self, error: ToolError) -> None:
        """Record a tool error. May be a no-op in non-debug mode."""
        ...

    def close(self) -> None:
        """Release any resources held by this sink."""
        ...


class SinkDispatcher:
    """Dispatches events to multiple SessionSink implementations."""

    def __init__(self, sinks: list[SessionSink] | None = None) -> None:
        self._sinks: list[SessionSink] = sinks or []

    def add(self, sink: SessionSink) -> None:
        """Add a sink to the dispatch list."""
        raise NotImplementedError

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Dispatch to all sinks. Logs and swallows individual failures."""
        raise NotImplementedError

    def record_tool_call(self, call: ToolCall) -> None:
        """Dispatch to all sinks. Logs and swallows individual failures."""
        raise NotImplementedError

    def record_tool_error(self, error: ToolError) -> None:
        """Dispatch to all sinks. Logs and swallows individual failures."""
        raise NotImplementedError

    def close(self) -> None:
        """Close all sinks."""
        raise NotImplementedError
