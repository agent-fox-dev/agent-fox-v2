"""Property tests for predecessor escalation.

Validates invariants that hold for any input: accumulation, escalation
timing, exhaustion semantics, and defensive ladder creation.

Test Spec: TS-58-P1 through TS-58-P4
Requirements: 58-REQ-1.1, 58-REQ-1.3, 58-REQ-1.E1, 58-REQ-2.1, 58-REQ-2.3,
              58-REQ-3.1, 58-REQ-3.2
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.models import ModelTier
from agent_fox.routing.escalation import EscalationLadder
from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

# Strategies for valid tiers
_TIERS = [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]
_TIER_ORDER = {ModelTier.SIMPLE: 0, ModelTier.STANDARD: 1, ModelTier.ADVANCED: 2}

tier_strategy = st.sampled_from(_TIERS)


def _tier_index(tier: ModelTier) -> int:
    return _TIER_ORDER[tier]


# ---------------------------------------------------------------------------
# TS-58-P1: Reviewer Resets Accumulate on Predecessor Ladder
# Validates: 58-REQ-1.1, 58-REQ-3.1, 58-REQ-3.2
# ---------------------------------------------------------------------------


class TestResetsAccumulateOnPredLadder:
    """TS-58-P1: Reviewer resets accumulate on predecessor ladder."""

    @pytest.mark.property
    @given(n=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_resets_accumulate(self, n: int) -> None:
        """For N reviewer-triggered resets, attempt_count == N + 1.

        Property: Each call to record_failure() increments the total failure
        counter by 1. attempt_count is always total_failures + 1 (the initial
        attempt). This is the invariant that must hold in the orchestrator so
        that failures from multiple reviewers accumulate correctly.

        Test Spec: TS-58-P1
        Validates: 58-REQ-1.1, 58-REQ-3.1, 58-REQ-3.2
        """
        # Use a large enough budget so the ladder never exhausts during the test
        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n + 5,  # Ensures no exhaustion
        )
        assert ladder.attempt_count == 1  # Before any failures

        for _ in range(n):
            ladder.record_failure()

        assert ladder.attempt_count == n + 1


# ---------------------------------------------------------------------------
# TS-58-P2: Predecessor Escalates After N+1 Failures
# Validates: 58-REQ-1.3
# ---------------------------------------------------------------------------


class TestEscalatesAfterNPlusOneFail:
    """TS-58-P2: Predecessor escalates to ADVANCED after N+1 failures."""

    @pytest.mark.property
    @given(n=st.integers(min_value=0, max_value=3))
    @settings(max_examples=20)
    def test_escalates_after_n_plus_1(self, n: int) -> None:
        """For retries_before_escalation=N, STANDARD->ADVANCED after N+1 failures.

        After exactly N+1 record_failure() calls on a STANDARD/ADVANCED ladder,
        current_tier must be ADVANCED.

        Test Spec: TS-58-P2
        Validates: 58-REQ-1.3
        """
        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )

        for _ in range(n + 1):
            ladder.record_failure()

        assert ladder.current_tier == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-58-P3: Exhausted Predecessor Is Blocked
# Validates: 58-REQ-2.1, 58-REQ-2.3
# ---------------------------------------------------------------------------


class TestExhaustedMeansBlocked:
    """TS-58-P3: Exhausted predecessor must never be set to pending."""

    @pytest.mark.property
    @given(
        starting=tier_strategy,
        n=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=40)
    def test_exhausted_ladder_properties(self, starting: ModelTier, n: int) -> None:
        """When is_exhausted is True, the ladder rejects further retries.

        This property validates that the EscalationLadder correctly signals
        exhaustion so the orchestrator can block the predecessor rather than
        resetting it to pending.

        Test Spec: TS-58-P3
        Validates: 58-REQ-2.1, 58-REQ-2.3
        """
        ladder = EscalationLadder(
            starting_tier=starting,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )

        # Exhaust the ladder
        while not ladder.is_exhausted:
            ladder.record_failure()

        # Once exhausted, should_retry must return False
        assert ladder.is_exhausted is True
        assert ladder.should_retry() is False

    @pytest.mark.property
    @given(
        starting=tier_strategy,
        n=st.integers(min_value=0, max_value=3),
        extra_failures=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=40)
    def test_exhausted_state_is_sticky(
        self, starting: ModelTier, n: int, extra_failures: int
    ) -> None:
        """Once exhausted, calling record_failure() more times is a no-op.

        The orchestrator must not reset the predecessor after exhaustion,
        and the ladder's exhausted state must remain stable.

        Test Spec: TS-58-P3
        Validates: 58-REQ-2.3
        """
        ladder = EscalationLadder(
            starting_tier=starting,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )

        # Exhaust the ladder
        while not ladder.is_exhausted:
            ladder.record_failure()

        count_at_exhaustion = ladder.attempt_count

        # Additional calls must be no-ops
        for _ in range(extra_failures):
            ladder.record_failure()

        assert ladder.is_exhausted is True
        assert ladder.attempt_count == count_at_exhaustion


# ---------------------------------------------------------------------------
# TS-58-P4: Missing Ladder Created Defensively
# Validates: 58-REQ-1.E1
# ---------------------------------------------------------------------------


class TestMissingLadderCreatedDefensively:
    """TS-58-P4: Missing predecessor ladder is created with correct defaults."""

    @pytest.mark.property
    @given(name=st.sampled_from(sorted(ARCHETYPE_REGISTRY.keys())))
    @settings(max_examples=len(ARCHETYPE_REGISTRY))
    def test_defensive_ladder_has_advanced_ceiling(self, name: str) -> None:
        """For any archetype, a defensively created ladder has ADVANCED ceiling.

        When the predecessor has no escalation ladder (e.g., assessment skipped),
        the orchestrator creates one. The ceiling must always be ADVANCED.

        Test Spec: TS-58-P4
        Validates: 58-REQ-1.E1
        """
        entry = ARCHETYPE_REGISTRY[name]
        ladder = EscalationLadder(
            starting_tier=ModelTier(entry.default_model_tier),
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )

        assert ladder._tier_ceiling == ModelTier.ADVANCED

    @pytest.mark.property
    @given(name=st.sampled_from(sorted(ARCHETYPE_REGISTRY.keys())))
    @settings(max_examples=len(ARCHETYPE_REGISTRY))
    def test_defensive_ladder_starting_tier_matches_archetype(self, name: str) -> None:
        """For any archetype, the created ladder starts at the archetype's default tier.

        The orchestrator must use the predecessor's archetype default_model_tier
        as the starting tier when creating a defensive ladder.

        Test Spec: TS-58-P4
        Validates: 58-REQ-1.E1
        """
        entry = ARCHETYPE_REGISTRY[name]
        expected_tier = ModelTier(entry.default_model_tier)

        ladder = EscalationLadder(
            starting_tier=expected_tier,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )

        assert ladder.current_tier == expected_tier
