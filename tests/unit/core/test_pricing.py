"""Pricing configuration tests.

Test Spec: TS-34-6, TS-34-7, TS-34-8, TS-34-14, TS-34-E3, TS-34-E4
Requirements: 34-REQ-2.1, 34-REQ-2.2, 34-REQ-2.3, 34-REQ-2.4,
              34-REQ-2.E1, 34-REQ-2.E2, 34-REQ-5.1, 34-REQ-5.2
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_fox.core.config import (
    AgentFoxConfig,
    ModelPricing,
    PricingConfig,
    load_config,
)
from agent_fox.core.models import ModelEntry, calculate_cost


class TestPricingConfig:
    """TS-34-6, TS-34-7, TS-34-8: Pricing config defaults and cost calculation."""

    def test_defaults(self) -> None:
        """TS-34-6: PricingConfig provides correct default prices."""
        config = AgentFoxConfig()

        haiku = config.pricing.models["claude-haiku-4-5"]
        assert haiku.input_price_per_m == 1.00
        assert haiku.output_price_per_m == 5.00

        sonnet = config.pricing.models["claude-sonnet-4-6"]
        assert sonnet.input_price_per_m == 3.00
        assert sonnet.output_price_per_m == 15.00

        opus = config.pricing.models["claude-opus-4-6"]
        assert opus.input_price_per_m == 5.00
        assert opus.output_price_per_m == 25.00

    def test_cost_uses_config(self) -> None:
        """TS-34-7: calculate_cost uses pricing from config, not hardcoded."""
        custom = PricingConfig(
            models={
                "claude-haiku-4-5": ModelPricing(
                    input_price_per_m=10.0,
                    output_price_per_m=50.0,
                )
            }
        )

        cost = calculate_cost(1_000_000, 1_000_000, "claude-haiku-4-5", custom)

        assert cost == 60.0

    def test_unknown_model_zero(self, caplog: Any) -> None:
        """TS-34-8: Unknown model returns zero cost and logs warning."""
        pricing = PricingConfig()

        with caplog.at_level(logging.WARNING):
            cost = calculate_cost(1000, 500, "unknown-model", pricing)

        assert cost == 0.0
        assert any("unknown-model" in rec.message for rec in caplog.records)


class TestPricingEdgeCases:
    """TS-34-E3, TS-34-E4: Edge cases for pricing config."""

    def test_missing_section(self, tmp_path: Path) -> None:
        """TS-34-E3: Config without [pricing] section uses defaults."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nparallel = 1\n")

        config = load_config(config_file)

        assert "claude-haiku-4-5" in config.pricing.models
        assert config.pricing.models["claude-haiku-4-5"].input_price_per_m == 1.00

    def test_negative_clamped(self) -> None:
        """TS-34-E4: Negative pricing values are clamped to zero."""
        pricing = ModelPricing(
            input_price_per_m=-5.0,
            output_price_per_m=-10.0,
        )

        assert pricing.input_price_per_m == 0.0
        assert pricing.output_price_per_m == 0.0


class TestModelEntryCleanup:
    """TS-34-14: ModelEntry no longer has pricing fields."""

    def test_no_pricing_fields(self) -> None:
        """TS-34-14: ModelEntry does not have input/output_price_per_m."""
        assert not hasattr(ModelEntry, "input_price_per_m") or not any(
            f.name == "input_price_per_m"
            for f in ModelEntry.__dataclass_fields__.values()
        )
        assert not hasattr(ModelEntry, "output_price_per_m") or not any(
            f.name == "output_price_per_m"
            for f in ModelEntry.__dataclass_fields__.values()
        )
