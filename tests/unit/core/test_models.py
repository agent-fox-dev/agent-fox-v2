"""Model registry tests.

Test Spec: TS-01-9 (tier resolution), TS-01-10 (cost calc), TS-01-E5 (unknown model)
Requirements: 01-REQ-5.1, 01-REQ-5.3, 01-REQ-5.4, 01-REQ-5.E1
"""

from __future__ import annotations

import pytest

from agent_fox.core.config import PricingConfig
from agent_fox.core.errors import ConfigError
from agent_fox.core.models import (
    ModelEntry,
    ModelTier,
    calculate_cost,
    resolve_model,
)


class TestModelResolutionByTier:
    """TS-01-9: Model resolution by tier name."""

    def test_resolve_simple_tier(self) -> None:
        """SIMPLE tier resolves to a valid model entry."""
        entry = resolve_model("SIMPLE")

        assert isinstance(entry, ModelEntry)
        assert entry.tier == ModelTier.SIMPLE
        assert entry.model_id != ""

    def test_resolve_standard_tier(self) -> None:
        """STANDARD tier resolves to a valid model entry."""
        entry = resolve_model("STANDARD")

        assert isinstance(entry, ModelEntry)
        assert entry.tier == ModelTier.STANDARD
        assert entry.model_id != ""

    def test_resolve_advanced_tier(self) -> None:
        """ADVANCED tier resolves to a valid model entry."""
        entry = resolve_model("ADVANCED")

        assert isinstance(entry, ModelEntry)
        assert entry.tier == ModelTier.ADVANCED
        assert entry.model_id != ""

    def test_resolve_by_model_id(self) -> None:
        """A specific model ID resolves to its entry."""
        entry = resolve_model("claude-sonnet-4-6")

        assert isinstance(entry, ModelEntry)
        assert entry.model_id == "claude-sonnet-4-6"
        assert entry.tier == ModelTier.STANDARD


class TestCostCalculation:
    """TS-01-10: Cost calculation."""

    def test_cost_standard_model(self) -> None:
        """Cost calculation returns correct USD value for Sonnet."""
        model = resolve_model("STANDARD")
        pricing = PricingConfig()

        # Sonnet: $3.00/M input, $15.00/M output
        # 1M input + 500K output = (1.0 * 3.00) + (0.5 * 15.00) = $10.50
        cost = calculate_cost(1_000_000, 500_000, model.model_id, pricing)

        assert abs(cost - 10.50) < 0.01

    def test_cost_zero_tokens(self) -> None:
        """Zero tokens produces zero cost."""
        model = resolve_model("STANDARD")
        pricing = PricingConfig()

        cost = calculate_cost(0, 0, model.model_id, pricing)

        assert cost == 0.0

    def test_cost_input_only(self) -> None:
        """Cost with only input tokens is correct."""
        model = resolve_model("SIMPLE")
        pricing = PricingConfig()

        # Haiku: $1.00/M input
        cost = calculate_cost(1_000_000, 0, model.model_id, pricing)

        assert abs(cost - 1.00) < 0.01


class TestUnknownModelID:
    """TS-01-E5: Unknown model ID raises ConfigError."""

    def test_unknown_model_raises_config_error(self) -> None:
        """Unknown model ID raises ConfigError."""
        with pytest.raises(ConfigError):
            resolve_model("nonexistent-model")

    def test_unknown_model_error_lists_valid_options(self) -> None:
        """ConfigError message includes at least one valid model ID."""
        with pytest.raises(ConfigError) as exc_info:
            resolve_model("nonexistent-model")

        error_msg = str(exc_info.value)
        assert "claude" in error_msg.lower(), (
            f"Expected valid model IDs in error, got: {error_msg!r}"
        )
