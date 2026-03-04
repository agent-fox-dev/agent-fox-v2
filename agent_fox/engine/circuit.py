"""Circuit breaker: pre-launch checks for cost, session, and retry limits.

Checks cost ceiling, session count limit, and retry counter before each
session launch. Returns a go/no-go decision (LaunchDecision) so the
orchestrator can stop launching when limits are reached.

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
    """Pre-launch checks: cost ceiling, session limit, retry counter.

    The circuit breaker is consulted before every session launch. It
    checks three conditions (in order):

    1. **Cost ceiling:** cumulative cost >= config.max_cost
    2. **Session limit:** total sessions >= config.max_sessions
    3. **Retry limit:** attempt number > config.max_retries + 1

    If any check fails, the launch is denied with an explanatory reason.
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    def _check_global_limits(
        self,
        state: ExecutionState,
    ) -> LaunchDecision | None:
        """Check cost ceiling and session limit.

        Returns a denied LaunchDecision if a limit is hit, or None if
        both checks pass.
        """
        if (
            self._config.max_cost is not None
            and state.total_cost >= self._config.max_cost
        ):
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Cost limit reached: cumulative cost "
                    f"${state.total_cost:.2f} >= "
                    f"max_cost ${self._config.max_cost:.2f}"
                ),
            )

        if (
            self._config.max_sessions is not None
            and state.total_sessions >= self._config.max_sessions
        ):
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Session limit reached: {state.total_sessions} "
                    f"sessions >= max_sessions {self._config.max_sessions}"
                ),
            )

        return None

    def check_launch(
        self,
        node_id: str,
        attempt: int,
        state: ExecutionState,
    ) -> LaunchDecision:
        """Determine whether a session launch is permitted.

        Checks (in order):
        1. Cost ceiling: state.total_cost >= config.max_cost
        2. Session limit: state.total_sessions >= config.max_sessions
        3. Retry limit: attempt > config.max_retries + 1

        Args:
            node_id: The task to check.
            attempt: The proposed attempt number (1-indexed).
            state: Current execution state.

        Returns:
            LaunchDecision with allowed=True or allowed=False with reason.
        """
        denied = self._check_global_limits(state)
        if denied is not None:
            return denied

        # Retry limit check
        max_attempts = self._config.max_retries + 1
        if attempt > max_attempts:
            return LaunchDecision(
                allowed=False,
                reason=(
                    f"Retry limit exceeded for {node_id}: "
                    f"attempt {attempt} > max_retries + 1 "
                    f"({max_attempts})"
                ),
            )

        return LaunchDecision(allowed=True)

    def should_stop(self, state: ExecutionState) -> LaunchDecision:
        """Check whether the orchestrator should stop launching entirely.

        This is called before picking the next batch of ready tasks.
        Checks cost ceiling and session limit only (not per-task retry).

        Args:
            state: Current execution state.

        Returns:
            LaunchDecision with allowed=True or allowed=False with reason.
        """
        return self._check_global_limits(state) or LaunchDecision(allowed=True)
