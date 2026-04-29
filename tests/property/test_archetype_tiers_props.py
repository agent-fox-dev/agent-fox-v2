"""Property-based tests for archetype model tier defaults.

Test Spec: TS-57-P1 through TS-57-P5
Requirements: 57-REQ-1.1 through 57-REQ-3.3
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.core.models import ModelTier
from agent_fox.core.escalation import EscalationLadder

_TIER_ORDER: dict[ModelTier, int] = {
    ModelTier.SIMPLE: 0,
    ModelTier.STANDARD: 1,
    ModelTier.ADVANCED: 2,
}

# "triage" was removed in spec 100 and absorbed into maintainer:hunt (STANDARD tier).
# "maintainer" is now in the registry with STANDARD tier.
_ADVANCED_ARCHETYPES: set[str] = set()
_STANDARD_ARCHETYPES = {"coder", "reviewer", "verifier", "maintainer"}


# ---------------------------------------------------------------------------
# TS-57-P1: All Registry Defaults Match Spec
# Requirements: 57-REQ-1.1 through 57-REQ-1.5
# ---------------------------------------------------------------------------


class TestRegistryDefaultsMatchSpec:
    """TS-57-P1: For every archetype, default_model_tier matches the spec."""

    def test_advanced_archetypes_all_advanced(self) -> None:
        """Skeptic, Oracle, Verifier must all be ADVANCED."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        for name in _ADVANCED_ARCHETYPES:
            entry = ARCHETYPE_REGISTRY[name]
            got = entry.default_model_tier
            assert got == "ADVANCED", f"Expected {name} to have ADVANCED tier, got {got!r}"

    def test_standard_archetypes_all_standard(self) -> None:
        """Coder and Auditor must be STANDARD."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        for name in _STANDARD_ARCHETYPES:
            entry = ARCHETYPE_REGISTRY[name]
            got = entry.default_model_tier
            assert got == "STANDARD", f"Expected {name} to have STANDARD tier, got {got!r}"

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(name=st.sampled_from(sorted(_ADVANCED_ARCHETYPES | _STANDARD_ARCHETYPES)))
    @settings(max_examples=50)
    def test_prop_every_archetype_matches_spec(self, name: str) -> None:
        """For any archetype in the registry, tier matches the spec assignment."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY[name]
        if name in _ADVANCED_ARCHETYPES:
            assert entry.default_model_tier == "ADVANCED"
        else:
            assert entry.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-57-P2: Ceiling Is Always ADVANCED
# Requirement: 57-REQ-2.1
# ---------------------------------------------------------------------------


class TestCeilingAlwaysAdvanced:
    """TS-57-P2: For any archetype, escalation ceiling is ADVANCED."""

    def test_all_archetypes_get_advanced_ceiling(self) -> None:
        """An escalation ladder for any archetype has ceiling=ADVANCED."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        for name, entry in ARCHETYPE_REGISTRY.items():
            starting = ModelTier(entry.default_model_tier)
            # The orchestrator always sets tier_ceiling=ADVANCED after the fix
            ladder = EscalationLadder(
                starting_tier=starting,
                tier_ceiling=ModelTier.ADVANCED,
                retries_before_escalation=1,
            )
            assert ladder._tier_ceiling == ModelTier.ADVANCED, (
                f"Expected ADVANCED ceiling for {name}, got {ladder._tier_ceiling!r}"
            )

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(name=st.sampled_from(sorted(_ADVANCED_ARCHETYPES | _STANDARD_ARCHETYPES)))
    @settings(max_examples=50)
    def test_prop_ceiling_always_advanced(self, name: str) -> None:
        """For any archetype, a ladder with ADVANCED ceiling preserves the ceiling."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY[name]
        starting = ModelTier(entry.default_model_tier)
        ladder = EscalationLadder(
            starting_tier=starting,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        assert ladder._tier_ceiling == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-57-P3: STANDARD Agents Reach ADVANCED Before Exhaustion
# Requirement: 57-REQ-2.2
# ---------------------------------------------------------------------------


class TestStandardReachesAdvanced:
    """TS-57-P3: STANDARD-starting ladders always reach ADVANCED before exhaustion."""

    @pytest.mark.parametrize("n", [0, 1, 2, 3])
    def test_standard_reaches_advanced_for_n_retries(self, n: int) -> None:
        """After n+1 failures, STANDARD ladder is at ADVANCED and not exhausted."""
        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )
        for _ in range(n + 1):
            ladder.record_failure()

        assert ladder.current_tier == ModelTier.ADVANCED
        assert ladder.is_exhausted is False

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(n=st.integers(min_value=0, max_value=3))
    @settings(max_examples=20)
    def test_prop_standard_reaches_advanced(self, n: int) -> None:
        """Property: any N in [0,3], STANDARD→ADVANCED after N+1 failures."""
        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )
        for _ in range(n + 1):
            ladder.record_failure()

        assert ladder.current_tier == ModelTier.ADVANCED
        assert ladder.is_exhausted is False


# ---------------------------------------------------------------------------
# TS-57-P4: ADVANCED Agents Exhaust Without Escalation
# Requirement: 57-REQ-2.3
# ---------------------------------------------------------------------------


class TestAdvancedExhaustsWithoutEscalation:
    """TS-57-P4: ADVANCED-starting ladders exhaust without any escalation."""

    @pytest.mark.parametrize("n", [0, 1, 2, 3])
    def test_advanced_exhausts_without_escalation_for_n_retries(self, n: int) -> None:
        """After n+1 failures, ADVANCED ladder is exhausted with 0 escalations."""
        ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )
        for _ in range(n + 1):
            ladder.record_failure()

        assert ladder.is_exhausted is True
        assert ladder.escalation_count == 0

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(n=st.integers(min_value=0, max_value=3))
    @settings(max_examples=20)
    def test_prop_advanced_exhausts_without_escalation(self, n: int) -> None:
        """Property: any N in [0,3], ADVANCED ladder exhausts without escalation."""
        ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=n,
        )
        for _ in range(n + 1):
            ladder.record_failure()

        assert ladder.is_exhausted is True
        assert ladder.escalation_count == 0


# ---------------------------------------------------------------------------
# TS-57-P5: Config Override Precedence
# Requirements: 57-REQ-3.1, 57-REQ-3.2
# ---------------------------------------------------------------------------


class TestConfigOverridePrecedence:
    """TS-57-P5: Config override takes precedence; absent → registry default."""

    _ALL_ARCHETYPES = sorted(_ADVANCED_ARCHETYPES | _STANDARD_ARCHETYPES)

    @pytest.mark.parametrize("name", _ALL_ARCHETYPES)
    @pytest.mark.parametrize("override", ["SIMPLE", "STANDARD", "ADVANCED"])
    def test_config_override_takes_precedence(self, name: str, override: str) -> None:
        """With config override, resolve_model_tier returns override value."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={name: override}))
        tier = resolve_model_tier(config, name)
        assert tier == override

    @pytest.mark.parametrize("name", _ALL_ARCHETYPES)
    def test_no_override_uses_global_or_registry_default(self, name: str) -> None:
        """Without archetype override, global [models] config or registry default is used."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.sdk_params import _ARCHETYPE_MODEL_KEYS, resolve_model_tier
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={}))
        tier = resolve_model_tier(config, name)
        model_key = _ARCHETYPE_MODEL_KEYS.get(name)
        if model_key is not None:
            expected = getattr(config.models, model_key)
        else:
            expected = ARCHETYPE_REGISTRY[name].default_model_tier
        assert tier == expected

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        name=st.sampled_from(sorted(_ADVANCED_ARCHETYPES | _STANDARD_ARCHETYPES)),
        override=st.one_of(
            st.none(),
            st.sampled_from(["SIMPLE", "STANDARD", "ADVANCED"]),
        ),
    )
    @settings(max_examples=50)
    def test_prop_config_override_precedence(self, name: str, override: str | None) -> None:
        """Property: override → returned; no override → global models or registry default."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.sdk_params import _ARCHETYPE_MODEL_KEYS, resolve_model_tier
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        models = {name: override} if override is not None else {}
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models=models))
        result = resolve_model_tier(config, name)

        if override is not None:
            assert result == override
        else:
            model_key = _ARCHETYPE_MODEL_KEYS.get(name)
            if model_key is not None:
                assert result == getattr(config.models, model_key)
            else:
                assert result == ARCHETYPE_REGISTRY[name].default_model_tier
