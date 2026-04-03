"""Tests for escalation ladder.

Test Spec: TS-30-7 through TS-30-10, TS-30-14, TS-30-E4, TS-30-E5,
           TS-30-P1, TS-30-P2, TS-30-P3
Requirements: 30-REQ-2.1 through 30-REQ-2.4, 30-REQ-2.E1, 30-REQ-2.E2, 30-REQ-3.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.models import ModelTier
from agent_fox.routing.escalation import EscalationLadder

TIER_ORDER = {ModelTier.SIMPLE: 0, ModelTier.STANDARD: 1, ModelTier.ADVANCED: 2}


def _tier_index(tier: ModelTier) -> int:
    return TIER_ORDER[tier]


# Strategy for valid tier pairs (starting <= ceiling)
tier_strategy = st.sampled_from([ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED])


class TestSameTierRetry:
    """TS-30-7: Same-tier retry on first failure."""

    def test_same_tier_retry(self) -> None:
        """TS-30-7: Verify retry at same tier before escalating.

        Requirement: 30-REQ-2.1
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.ADVANCED, retries_before_escalation=1)
        assert ladder.current_tier == ModelTier.SIMPLE

        ladder.record_failure()
        assert ladder.should_retry() is True
        assert ladder.current_tier == ModelTier.SIMPLE
        assert ladder.attempt_count == 2


class TestEscalationToNext:
    """TS-30-8: Escalation to next tier after retries exhausted."""

    def test_escalation_to_next(self) -> None:
        """TS-30-8: Verify escalation after same-tier retries used up.

        Requirement: 30-REQ-2.2
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.ADVANCED, retries_before_escalation=1)
        ladder.record_failure()  # retry at SIMPLE
        ladder.record_failure()  # exhausted SIMPLE, escalate

        assert ladder.current_tier == ModelTier.STANDARD
        assert ladder.escalation_count == 1
        assert ladder.should_retry() is True


class TestExhaustion:
    """TS-30-9: Exhaustion at highest tier."""

    def test_exhaustion(self) -> None:
        """TS-30-9: Verify ladder is exhausted after all tiers.

        Requirement: 30-REQ-2.3
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.ADVANCED, retries_before_escalation=1)
        for _ in range(6):
            ladder.record_failure()

        assert ladder.is_exhausted is True
        assert ladder.should_retry() is False
        assert ladder.attempt_count == 7  # 6 failures + 1 initial


class TestCeilingEnforcement:
    """TS-30-10: Tier ceiling enforcement."""

    def test_ceiling_enforcement(self) -> None:
        """TS-30-10: Verify escalation never exceeds ceiling.

        Requirement: 30-REQ-2.4
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.STANDARD, retries_before_escalation=1)
        tiers_seen = [ladder.current_tier]
        for _ in range(4):
            ladder.record_failure()
            if ladder.should_retry():
                tiers_seen.append(ladder.current_tier)

        assert all(t in [ModelTier.SIMPLE, ModelTier.STANDARD] for t in tiers_seen)
        assert ladder.is_exhausted is True


class TestActualTierReflectsEscalation:
    """TS-30-14: Actual tier reflects escalation."""

    def test_actual_tier_reflects_escalation(self) -> None:
        """TS-30-14: Verify current_tier matches the escalated tier.

        Requirement: 30-REQ-3.3
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.ADVANCED, retries_before_escalation=1)
        ladder.record_failure()
        ladder.record_failure()  # escalate to STANDARD
        assert ladder.current_tier == ModelTier.STANDARD


class TestNoEscalationFromAdvanced:
    """TS-30-E4: No escalation when starting at ADVANCED."""

    def test_no_escalation_from_advanced(self) -> None:
        """TS-30-E4: Assessment predicts ADVANCED, no escalation.

        Requirement: 30-REQ-2.E1
        """
        ladder = EscalationLadder(ModelTier.ADVANCED, ModelTier.ADVANCED, retries_before_escalation=1)
        ladder.record_failure()
        assert ladder.current_tier == ModelTier.ADVANCED
        ladder.record_failure()
        assert ladder.is_exhausted is True
        assert ladder.escalation_count == 0


class TestNoEscalationCeilingSimple:
    """TS-30-E5: No escalation when ceiling is SIMPLE."""

    def test_no_escalation_ceiling_simple(self) -> None:
        """TS-30-E5: Tier ceiling = SIMPLE, no escalation.

        Requirement: 30-REQ-2.E2
        """
        ladder = EscalationLadder(ModelTier.SIMPLE, ModelTier.SIMPLE, retries_before_escalation=1)
        ladder.record_failure()
        ladder.record_failure()
        assert ladder.is_exhausted is True
        assert ladder.escalation_count == 0


# -- Property Tests -----------------------------------------------------------


class TestP1OrderPreservation:
    """TS-30-P1: Escalation order preservation."""

    @pytest.mark.property
    @given(
        starting=tier_strategy,
        ceiling=tier_strategy,
        retries=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=50)
    def test_p1_order_preservation(self, starting: ModelTier, ceiling: ModelTier, retries: int) -> None:
        """TS-30-P1: Tiers are always non-decreasing.

        Requirement: 30-REQ-2.1, 30-REQ-2.2
        """
        if _tier_index(ceiling) < _tier_index(starting):
            return  # skip invalid combos

        ladder = EscalationLadder(starting, ceiling, retries_before_escalation=retries)
        tiers = [ladder.current_tier]
        while ladder.should_retry():
            ladder.record_failure()
            tiers.append(ladder.current_tier)

        tier_indices = [_tier_index(t) for t in tiers]
        assert tier_indices == sorted(tier_indices)


class TestP2CeilingEnforcement:
    """TS-30-P2: Tier ceiling enforcement property."""

    @pytest.mark.property
    @given(
        starting=tier_strategy,
        ceiling=tier_strategy,
        retries=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=50)
    def test_p2_ceiling_enforcement(self, starting: ModelTier, ceiling: ModelTier, retries: int) -> None:
        """TS-30-P2: No tier exceeds the ceiling.

        Requirement: 30-REQ-2.4, 30-REQ-5.3
        """
        if _tier_index(ceiling) < _tier_index(starting):
            return

        ladder = EscalationLadder(starting, ceiling, retries_before_escalation=retries)
        assert _tier_index(ladder.current_tier) <= _tier_index(ceiling)
        while ladder.should_retry():
            ladder.record_failure()
            assert _tier_index(ladder.current_tier) <= _tier_index(ceiling)


class TestP3RetryBudget:
    """TS-30-P3: Retry budget correctness."""

    @pytest.mark.property
    @given(
        starting=tier_strategy,
        ceiling=tier_strategy,
        retries=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=50)
    def test_p3_retry_budget(self, starting: ModelTier, ceiling: ModelTier, retries: int) -> None:
        """TS-30-P3: Total attempts = (retries+1) * tiers_traversed + 1.

        Requirement: 30-REQ-2.1, 30-REQ-2.2, 30-REQ-2.3
        """
        if _tier_index(ceiling) < _tier_index(starting):
            return

        ladder = EscalationLadder(starting, ceiling, retries_before_escalation=retries)
        while ladder.should_retry():
            ladder.record_failure()

        num_tiers = _tier_index(ceiling) - _tier_index(starting) + 1
        # Total attempts: initial + retries per tier * num tiers
        # = 1 + (retries + 1 - 1) per tier for failures + ... but let's
        # calculate: each tier gets (retries + 1) failures before moving on,
        # so total failures = (retries + 1) * num_tiers, and
        # attempt_count = total_failures + 1 (the initial attempt)
        # Actually: attempt_count = 1 (initial) + total failures recorded
        # Each tier: (retries + 1) failures = initial attempt + retries
        expected_attempts = (retries + 1) * num_tiers + 1
        assert ladder.attempt_count == expected_attempts
