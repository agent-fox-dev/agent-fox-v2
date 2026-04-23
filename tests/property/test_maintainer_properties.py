"""Property-based tests for the maintainer archetype.

Covers: mode config correctness, triage removal, extraction stub safety,
and nightshift model tier resolution invariants.

Test Spec: TS-100-P1 through TS-100-P4
Requirements: 100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3,
              100-REQ-2.1, 100-REQ-4.3, 100-REQ-4.E1,
              100-REQ-5.1, 100-REQ-5.2
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


pytestmark = pytest.mark.property


_VALID_TIERS = {"SIMPLE", "STANDARD", "ADVANCED"}

# Expected allowlists per mode
_MAINTAINER_MODE_EXPECTED: dict[str, tuple[list[str], str]] = {
    "hunt": (["ls", "cat", "git", "wc", "head", "tail"], "STANDARD"),
    "extraction": ([], "STANDARD"),
}


# ===========================================================================
# TS-100-P1: Maintainer Mode Config
# Validates: 100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3
# ===========================================================================

if HAS_HYPOTHESIS:

    @given(mode=st.sampled_from(["hunt", "extraction"]))
    def test_maintainer_mode_config(mode: str) -> None:
        """TS-100-P1: Each maintainer mode resolves to correct allowlist and tier.

        For any mode in {"hunt", "extraction"}, the resolved effective config
        SHALL match the expected allowlist and model tier.
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, mode)

        expected_allowlist, expected_tier = _MAINTAINER_MODE_EXPECTED[mode]

        assert sorted(cfg.default_allowlist or []) == sorted(expected_allowlist), (
            f"Mode '{mode}': allowlist {sorted(cfg.default_allowlist or [])} != {sorted(expected_allowlist)}"
        )
        assert cfg.default_model_tier == expected_tier, (
            f"Mode '{mode}': tier {cfg.default_model_tier!r} != {expected_tier!r}"
        )

else:

    def test_maintainer_mode_config_no_hypothesis() -> None:  # type: ignore[misc]
        """TS-100-P1: Each maintainer mode resolves to correct allowlist and tier (without Hypothesis)."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        for mode, (expected_allowlist, expected_tier) in _MAINTAINER_MODE_EXPECTED.items():
            entry = ARCHETYPE_REGISTRY["maintainer"]
            cfg = resolve_effective_config(entry, mode)
            assert sorted(cfg.default_allowlist or []) == sorted(expected_allowlist), (
                f"Mode '{mode}': allowlist mismatch"
            )
            assert cfg.default_model_tier == expected_tier, f"Mode '{mode}': tier mismatch"


# ===========================================================================
# TS-100-P2: Triage Removed
# Validates: 100-REQ-2.1
# ===========================================================================


def test_triage_removed_from_registry() -> None:
    """TS-100-P2: 'triage' must not appear in ARCHETYPE_REGISTRY.

    This is an invariant — the registry should never contain 'triage'
    after the migration to maintainer:hunt.
    """
    from agent_fox.archetypes import ARCHETYPE_REGISTRY

    assert "triage" not in ARCHETYPE_REGISTRY, (
        "'triage' found in ARCHETYPE_REGISTRY — it should have been removed (100-REQ-2.1)"
    )


# ===========================================================================
# TS-100-P4: Nightshift Resolution
# Validates: 100-REQ-5.1, 100-REQ-5.2
# ===========================================================================


def test_nightshift_resolution_returns_valid_tier() -> None:
    """TS-100-P4: resolve_model_tier(config, 'maintainer', mode='hunt') returns a valid tier.

    The returned tier must be one of SIMPLE, STANDARD, or ADVANCED.
    """
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.sdk_params import resolve_model_tier

    config = AgentFoxConfig()
    tier = resolve_model_tier(config, "maintainer", mode="hunt")
    assert tier in _VALID_TIERS, f"resolve_model_tier returned invalid tier {tier!r}, expected one of {_VALID_TIERS}"


def test_nightshift_resolution_security_config_not_none() -> None:
    """TS-100-P4: resolve_security_config for maintainer:hunt returns a SecurityConfig.

    Since maintainer:hunt has a non-None allowlist, SecurityConfig should
    always be returned (not None).
    """
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.engine.sdk_params import resolve_security_config

    config = AgentFoxConfig()
    sec = resolve_security_config(config, "maintainer", mode="hunt")
    assert sec is not None, (
        "resolve_security_config should return SecurityConfig for maintainer:hunt "
        "since it has a defined allowlist (100-REQ-5.2)"
    )


if HAS_HYPOTHESIS:

    @given(
        model_override=st.one_of(st.none(), st.sampled_from(list(_VALID_TIERS))),
    )
    def test_nightshift_resolution_with_model_override(
        model_override: str | None,
    ) -> None:
        """TS-100-P4: resolve_model_tier with config overrides returns a valid tier.

        For any valid config, the resolved tier should be in VALID_TIERS.
        """
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        if model_override is not None:
            # Set per-archetype model override
            config = config.model_copy(
                update={"archetypes": config.archetypes.model_copy(update={"models": {"maintainer": model_override}})}
            )
        tier = resolve_model_tier(config, "maintainer", mode="hunt")
        assert tier in _VALID_TIERS, f"resolve_model_tier returned invalid tier {tier!r}"
