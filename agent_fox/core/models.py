"""AI model registry with pricing.

Defines the model tier enum, model entry dataclass, a registry of known
models with pricing, and functions for model resolution and cost calculation.

Requirements: 01-REQ-5.1, 01-REQ-5.2, 01-REQ-5.3, 01-REQ-5.4, 01-REQ-5.E1
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelTier(StrEnum):
    SIMPLE = "SIMPLE"
    STANDARD = "STANDARD"
    ADVANCED = "ADVANCED"


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    tier: ModelTier
    input_price_per_m: float  # USD per million input tokens
    output_price_per_m: float  # USD per million output tokens


MODEL_REGISTRY: dict[str, ModelEntry] = {
    "claude-haiku-4-5-20251001": ModelEntry(
        "claude-haiku-4-5", ModelTier.SIMPLE, 1.00, 5.00
    ),
    "claude-sonnet-4-6": ModelEntry(
        "claude-sonnet-4-6", ModelTier.STANDARD, 3.00, 15.00
    ),
    "claude-opus-4-6": ModelEntry("claude-opus-4-6", ModelTier.ADVANCED, 5.00, 25.00),
}

TIER_DEFAULTS: dict[ModelTier, str] = {
    ModelTier.SIMPLE: "claude-haiku-4-5-20251001",
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


def calculate_cost(input_tokens: int, output_tokens: int, model: ModelEntry) -> float:
    """Calculate estimated cost in USD.

    Args:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens produced.
        model: The model entry with pricing information.

    Returns:
        Estimated cost in USD as a float.
    """
    input_cost = (input_tokens / 1_000_000) * model.input_price_per_m
    output_cost = (output_tokens / 1_000_000) * model.output_price_per_m
    return input_cost + output_cost
