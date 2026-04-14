"""Property tests for model registry and error hierarchy.

Test Spec: TS-01-P3 (cost non-negativity), TS-01-P4 (registry completeness),
           TS-01-P5 (error hierarchy catches)
Properties: Property 5, 6, 7 from design.md
Requirements: 01-REQ-4.1, 01-REQ-4.2, 01-REQ-5.1, 01-REQ-5.3, 01-REQ-5.4
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import PricingConfig
from agent_fox.core.errors import (
    AgentFoxError,
    ConfigError,
    CostLimitError,
    InitError,
    IntegrationError,
    KnowledgeStoreError,
    PlanError,
    SecurityError,
    SessionError,
    SessionTimeoutError,
    WorkspaceError,
)
from agent_fox.core.models import (
    MODEL_REGISTRY,
    ModelEntry,
    ModelTier,
    calculate_cost,
    resolve_model,
)

ALL_ERROR_CLASSES = [
    ConfigError,
    InitError,
    PlanError,
    SessionError,
    WorkspaceError,
    IntegrationError,
    SessionTimeoutError,
    CostLimitError,
    SecurityError,
    KnowledgeStoreError,
]


class TestCostNonNegativity:
    """TS-01-P3: Cost non-negativity.

    Property 6: For any non-negative token counts and any valid ModelEntry,
    calculate_cost() returns a non-negative float.
    """

    @given(
        input_tokens=st.integers(min_value=0, max_value=100_000_000),
        output_tokens=st.integers(min_value=0, max_value=100_000_000),
    )
    @settings(max_examples=100)
    def test_cost_non_negative_for_all_models(self, input_tokens: int, output_tokens: int) -> None:
        """Cost is never negative for any model and non-negative token counts."""
        pricing = PricingConfig()
        for model_entry in MODEL_REGISTRY.values():
            cost = calculate_cost(input_tokens, output_tokens, model_entry.model_id, pricing)
            assert cost >= 0.0, (
                f"Negative cost {cost} for {model_entry.model_id} with {input_tokens} input, {output_tokens} output"
            )


class TestModelRegistryCompleteness:
    """TS-01-P4: Model registry completeness.

    Property 5: For any tier in ModelTier, resolve_model(tier.value) returns
    a ModelEntry with matching tier.
    """

    @pytest.mark.parametrize("tier", list(ModelTier))
    def test_every_tier_resolves(self, tier: ModelTier) -> None:
        """Every tier resolves to a valid model entry."""
        entry = resolve_model(tier.value)

        assert isinstance(entry, ModelEntry)
        assert entry.tier == tier
        assert entry.model_id != ""


class TestErrorHierarchyCatches:
    """TS-01-P5: Error hierarchy catches.

    Property 7: Every custom exception is caught by `except AgentFoxError`.
    """

    @pytest.mark.parametrize("error_class", ALL_ERROR_CLASSES)
    def test_subclass_of_base(self, error_class: type[AgentFoxError]) -> None:
        """Every error class is a subclass of AgentFoxError."""
        assert issubclass(error_class, AgentFoxError)

    @pytest.mark.parametrize("error_class", ALL_ERROR_CLASSES)
    def test_catchable_by_base(self, error_class: type[AgentFoxError]) -> None:
        """Every error instance is caught by except AgentFoxError."""
        try:
            raise error_class("test")
        except AgentFoxError:
            pass  # Expected — the catch worked
        except Exception:
            pytest.fail(f"{error_class.__name__} was not caught by except AgentFoxError")
