"""AI model registry.

Defines the model tier enum, model entry dataclass, a registry of known
models, and functions for model resolution and cost calculation.

Pricing has been moved to config.toml via PricingConfig (spec 34).

Requirements: 01-REQ-5.1, 01-REQ-5.2, 01-REQ-5.3, 01-REQ-5.4, 01-REQ-5.E1,
              34-REQ-2.3, 34-REQ-2.4, 34-REQ-5.2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.core.config import PricingConfig

logger = logging.getLogger(__name__)


class ModelTier(StrEnum):
    SIMPLE = "SIMPLE"
    STANDARD = "STANDARD"
    ADVANCED = "ADVANCED"


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    tier: ModelTier


MODEL_REGISTRY: dict[str, ModelEntry] = {
    "claude-haiku-4-5": ModelEntry("claude-haiku-4-5", ModelTier.SIMPLE),
    "claude-sonnet-4-6": ModelEntry("claude-sonnet-4-6", ModelTier.STANDARD),
    "claude-opus-4-6": ModelEntry("claude-opus-4-6", ModelTier.ADVANCED),
}

TIER_DEFAULTS: dict[ModelTier, str] = {
    ModelTier.SIMPLE: "claude-haiku-4-5",
    ModelTier.STANDARD: "claude-sonnet-4-6",
    ModelTier.ADVANCED: "claude-opus-4-6",
}


def resolve_model(name: str) -> ModelEntry:
    """Resolve a tier name or model ID to a ModelEntry.

    Accepts either a tier name (e.g. "SIMPLE", "STANDARD", "ADVANCED")
    or a specific model ID (e.g. "claude-sonnet-4-6").

    Raises:
        ConfigError: If the name is not a recognized tier or model ID.
    """
    from agent_fox.core.errors import ConfigError

    # Try as a tier name first
    try:
        tier = ModelTier(name)
        model_id = TIER_DEFAULTS[tier]
        return MODEL_REGISTRY[model_id]
    except ValueError:
        pass

    # Try as a direct model ID
    if name in MODEL_REGISTRY:
        return MODEL_REGISTRY[name]

    valid_options = sorted(MODEL_REGISTRY.keys())
    raise ConfigError(
        f"Unknown model '{name}'. Valid options: {', '.join(valid_options)}",
        model=name,
        valid_options=valid_options,
    )


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model_id: str,
    pricing: PricingConfig,
    *,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    """Calculate estimated cost in USD using config-based pricing.

    Falls back to zero cost if model not found in pricing config.

    Args:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens produced.
        model_id: The model identifier string.
        pricing: The pricing configuration with per-model rates.
        cache_read_input_tokens: Number of cache-read input tokens.
        cache_creation_input_tokens: Number of cache-creation input tokens.

    Returns:
        Estimated cost in USD as a float.

    Requirements: 34-REQ-2.3, 34-REQ-2.4
    """
    model_pricing = pricing.models.get(model_id)
    if model_pricing is None:
        logger.warning(
            "Model '%s' not found in pricing config; using zero cost",
            model_id,
        )
        return 0.0

    input_cost = (input_tokens / 1_000_000) * model_pricing.input_price_per_m
    output_cost = (output_tokens / 1_000_000) * model_pricing.output_price_per_m
    cache_read_cost = (
        cache_read_input_tokens / 1_000_000
    ) * model_pricing.cache_read_price_per_m
    cache_creation_cost = (
        cache_creation_input_tokens / 1_000_000
    ) * model_pricing.cache_creation_price_per_m
    return input_cost + output_cost + cache_read_cost + cache_creation_cost
