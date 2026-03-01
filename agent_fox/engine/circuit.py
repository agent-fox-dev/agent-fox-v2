"""Circuit breaker: pre-launch checks for cost, session, and retry limits.

Stub module -- implementation in task group 5.
Requirements: 04-REQ-5.1, 04-REQ-5.2, 04-REQ-5.3
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.state import ExecutionState


@dataclass
class LaunchDecision:
    """Result of a circuit breaker check."""

    allowed: bool
    reason: str | None = None  # None if allowed, explanation if denied


class CircuitBreaker:
    """Pre-launch checks: cost ceiling, session limit, retry counter."""

    def __init__(self, config: OrchestratorConfig) -> None:
        raise NotImplementedError

    def check_launch(
        self,
        node_id: str,
        attempt: int,
        state: ExecutionState,
    ) -> LaunchDecision:
        raise NotImplementedError

    def should_stop(self, state: ExecutionState) -> LaunchDecision:
        raise NotImplementedError
