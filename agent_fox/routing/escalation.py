"""Escalation ladder for speculative execution.

Manages retry-at-tier and escalate-to-next-tier logic. The ladder tracks
the current tier, enforces the tier ceiling, and determines when all
retries and escalation steps are exhausted.

Requirements: 30-REQ-2.1, 30-REQ-2.2, 30-REQ-2.3, 30-REQ-2.4,
              30-REQ-2.E1, 30-REQ-2.E2
"""

from __future__ import annotations

from agent_fox.core.models import ModelTier

# Canonical tier ordering used for escalation.
_TIER_ORDER: list[ModelTier] = [
    ModelTier.SIMPLE,
    ModelTier.STANDARD,
    ModelTier.ADVANCED,
]
_TIER_INDEX: dict[ModelTier, int] = {t: i for i, t in enumerate(_TIER_ORDER)}


class EscalationLadder:
    """Tracks retry and escalation state for a single task group execution.

    The ladder starts at *starting_tier* and allows up to
    *retries_before_escalation* retries at the same tier before escalating
    to the next higher tier, up to *tier_ceiling*.

    Tier ordering: SIMPLE (0) < STANDARD (1) < ADVANCED (2).

    Properties:
      - Escalation order is strictly non-decreasing (Property 1).
      - No tier ever exceeds the ceiling (Property 2).
      - Total attempts = (retries + 1) * tiers_traversed + 1 (Property 3).
    """

    def __init__(
        self,
        starting_tier: ModelTier,
        tier_ceiling: ModelTier,
        retries_before_escalation: int,
    ) -> None:
        self._starting_tier = starting_tier
        self._tier_ceiling = tier_ceiling
        self._retries_before_escalation = retries_before_escalation

        # Build the list of tiers available for escalation (starting..ceiling).
        start_idx = _TIER_INDEX[starting_tier]
        ceiling_idx = _TIER_INDEX[tier_ceiling]
        self._available_tiers = _TIER_ORDER[start_idx : ceiling_idx + 1]

        # Index into _available_tiers for current tier.
        self._tier_idx = 0

        # How many failures recorded at the current tier (not counting initial).
        self._failures_at_tier = 0

        # Cumulative counters.
        self._total_failures = 0
        self._escalation_count = 0
        self._exhausted = False

    @property
    def current_tier(self) -> ModelTier:
        """The model tier to use for the next attempt."""
        return self._available_tiers[self._tier_idx]

    @property
    def is_exhausted(self) -> bool:
        """True if all retries and escalation steps have been used."""
        return self._exhausted

    @property
    def attempt_count(self) -> int:
        """Total number of attempts (initial + all recorded failures)."""
        return self._total_failures + 1

    @property
    def escalation_count(self) -> int:
        """Number of times the tier was escalated."""
        return self._escalation_count

    def record_failure(self) -> None:
        """Record a failed attempt.

        Increments the retry counter at the current tier. If retries at the
        current tier are exhausted, escalates to the next tier (if available).
        If no more tiers are available, marks the ladder as exhausted.
        """
        if self._exhausted:
            return

        self._total_failures += 1
        self._failures_at_tier += 1

        # Check if we've exhausted retries at this tier.
        # We get (retries_before_escalation + 1) total attempts per tier:
        # 1 initial + retries_before_escalation retries.
        if self._failures_at_tier > self._retries_before_escalation:
            # Try to escalate to next tier.
            if self._tier_idx + 1 < len(self._available_tiers):
                self._tier_idx += 1
                self._escalation_count += 1
                self._failures_at_tier = 0
            else:
                self._exhausted = True
        # If failures_at_tier <= retries_before_escalation, we still have
        # retries at this tier.

    def should_retry(self) -> bool:
        """True if there are remaining retries or escalation steps."""
        return not self._exhausted
