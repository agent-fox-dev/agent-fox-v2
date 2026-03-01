"""Execution state persistence: data models, save/load, plan hash.

Requirements: 04-REQ-4.1, 04-REQ-4.2, 04-REQ-4.3
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


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


def _serialize_state(state: ExecutionState) -> dict:
    """Convert an ExecutionState to a JSON-serializable dict."""
    return asdict(state)


def _deserialize_state(data: dict) -> ExecutionState:
    """Reconstruct an ExecutionState from a JSON dict."""
    history = [
        SessionRecord(**record) for record in data.get("session_history", [])
    ]

    return ExecutionState(
        plan_hash=data["plan_hash"],
        node_states=data["node_states"],
        session_history=history,
        total_input_tokens=data.get("total_input_tokens", 0),
        total_output_tokens=data.get("total_output_tokens", 0),
        total_cost=data.get("total_cost", 0.0),
        total_sessions=data.get("total_sessions", 0),
        started_at=data.get("started_at", ""),
        updated_at=data.get("updated_at", ""),
        run_status=data.get("run_status", "running"),
    )


class StateManager:
    """Handles loading, saving, and querying execution state.

    Persists state as JSON lines to ``state.jsonl``. Each line is a
    complete snapshot of the execution state at a point in time. The
    last line is the current state.
    """

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path

    def load(self) -> ExecutionState | None:
        """Load the most recent execution state from state.jsonl.

        Reads the file, takes the last non-empty line, and deserializes
        it as an ExecutionState.

        Returns:
            The loaded state, or None if the file does not exist or is
            corrupted.
        """
        if not self._state_path.exists():
            return None

        try:
            text = self._state_path.read_text().strip()
            if not text:
                return None

            # Take the last non-empty line
            lines = text.split("\n")
            last_line = lines[-1].strip()
            if not last_line:
                return None

            data = json.loads(last_line)
            return _deserialize_state(data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "Corrupted state file %s: %s", self._state_path, exc,
            )
            return None

    def save(self, state: ExecutionState) -> None:
        """Append the current state as a JSON line to state.jsonl.

        Creates parent directories if they do not exist.
        """
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        data = _serialize_state(state)
        line = json.dumps(data, separators=(",", ":"))

        with self._state_path.open("a") as f:
            f.write(line + "\n")

    def record_session(
        self,
        state: ExecutionState,
        record: SessionRecord,
    ) -> ExecutionState:
        """Update state with a completed session record.

        - Appends record to session_history
        - Updates total_input_tokens, total_output_tokens, total_cost
        - Increments total_sessions
        - Updates updated_at timestamp

        Returns:
            The updated ExecutionState (same object, mutated).
        """
        state.session_history.append(record)
        state.total_input_tokens += record.input_tokens
        state.total_output_tokens += record.output_tokens
        state.total_cost += record.cost
        state.total_sessions += 1
        state.updated_at = datetime.now(UTC).isoformat()
        return state

    @staticmethod
    def compute_plan_hash(plan_path: Path) -> str:
        """Compute SHA-256 hash of plan.json for change detection."""
        content = plan_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
