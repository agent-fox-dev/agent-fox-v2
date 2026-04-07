"""Tests for NightShiftConfig spec generator extensions.

Test Spec: TS-86-31, TS-86-E16
Requirements: 86-REQ-9.1, 86-REQ-9.2, 86-REQ-9.3, 86-REQ-9.E1
"""

from __future__ import annotations

from agent_fox.nightshift.config import NightShiftConfig

# ---------------------------------------------------------------------------
# TS-86-31: config default values
# Requirements: 86-REQ-9.1, 86-REQ-9.2, 86-REQ-9.3
# ---------------------------------------------------------------------------


class TestSpecGenConfigDefaults:
    """Verify new config fields have correct defaults."""

    def test_max_clarification_rounds_default(self) -> None:
        """TS-86-31: max_clarification_rounds defaults to 3."""
        config = NightShiftConfig()
        assert config.max_clarification_rounds == 3

    def test_max_budget_usd_default(self) -> None:
        """TS-86-31: max_budget_usd defaults to 2.0."""
        config = NightShiftConfig()
        assert config.max_budget_usd == 2.0

    def test_spec_gen_model_tier_default(self) -> None:
        """TS-86-31: spec_gen_model_tier defaults to 'ADVANCED'."""
        config = NightShiftConfig()
        assert config.spec_gen_model_tier == "ADVANCED"


# ---------------------------------------------------------------------------
# TS-86-E16: config clamps max_clarification_rounds
# Requirements: 86-REQ-9.E1
# ---------------------------------------------------------------------------


class TestSpecGenConfigClamping:
    """Verify values below 1 are clamped to 1."""

    def test_zero_clamped_to_one(self) -> None:
        """TS-86-E16: max_clarification_rounds=0 -> 1."""
        config = NightShiftConfig(max_clarification_rounds=0)
        assert config.max_clarification_rounds == 1

    def test_negative_clamped_to_one(self) -> None:
        """TS-86-E16: max_clarification_rounds=-5 -> 1."""
        config = NightShiftConfig(max_clarification_rounds=-5)
        assert config.max_clarification_rounds == 1

    def test_one_stays_one(self) -> None:
        """TS-86-E16: max_clarification_rounds=1 stays 1."""
        config = NightShiftConfig(max_clarification_rounds=1)
        assert config.max_clarification_rounds == 1

    def test_valid_value_unchanged(self) -> None:
        """TS-86-E16: max_clarification_rounds=5 stays 5."""
        config = NightShiftConfig(max_clarification_rounds=5)
        assert config.max_clarification_rounds == 5
