"""Execution state persistence: data models, save/load, plan hash.

Stub module -- implementation in task group 2.
Requirements: 04-REQ-4.1, 04-REQ-4.2, 04-REQ-4.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class RunStatus(StrEnum):
    """Overall orchestrator run status."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    COST_LIMIT = "cost_limit"
    SESSION_LIMIT = "session_limit"
    STALLED = "stalled"


@dataclass
class SessionRecord:
    """Record of a single session attempt."""

    node_id: str
    attempt: int  # 1-indexed attempt number
    status: str  # "completed" | "failed"
    input_tokens: int
    output_tokens: int
    cost: float
    duration_ms: int
    error_message: str | None
    timestamp: str  # ISO 8601


@dataclass
class ExecutionState:
    """Full execution state, persisted after every session."""

    plan_hash: str  # SHA-256 of plan.json
    node_states: dict[str, str]  # node_id -> NodeStatus value
    session_history: list[SessionRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_sessions: int = 0
    started_at: str = ""  # ISO 8601
    updated_at: str = ""  # ISO 8601
    run_status: str = "running"


class StateManager:
    """Handles loading, saving, and querying execution state."""

    def __init__(self, state_path: Path) -> None:
        raise NotImplementedError

    def load(self) -> ExecutionState | None:
        raise NotImplementedError

    def save(self, state: ExecutionState) -> None:
        raise NotImplementedError

    def record_session(
        self,
        state: ExecutionState,
        record: SessionRecord,
    ) -> ExecutionState:
        raise NotImplementedError

    @staticmethod
    def compute_plan_hash(plan_path: Path) -> str:
        raise NotImplementedError
