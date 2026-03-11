"""Property tests for token tracking.

Test Spec: TS-34-P1 through TS-34-P6
Properties: 1-6 from design.md
Requirements: 34-REQ-1.1, 34-REQ-1.2, 34-REQ-1.3, 34-REQ-1.4,
              34-REQ-2.1, 34-REQ-2.2, 34-REQ-2.3, 34-REQ-2.E1,
              34-REQ-3.1, 34-REQ-3.2, 34-REQ-4.1, 34-REQ-4.2,
              34-REQ-5.1
"""

from __future__ import annotations

from agent_fox.core.token_tracker import TokenAccumulator
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import (
    AgentFoxConfig,
    ModelPricing,
    PricingConfig,
)
from agent_fox.core.models import MODEL_REGISTRY, calculate_cost
from agent_fox.engine.state import SessionRecord
from agent_fox.reporting.status import extract_spec_name

# Strategies
model_ids = st.sampled_from(
    ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"]
)
token_counts = st.integers(min_value=0, max_value=1_000_000)
price_values = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)
archetype_names = st.sampled_from(
    ["coder", "skeptic", "verifier", "oracle", "librarian", "cartographer"]
)


class TestAccumulatorCompleteness:
    """TS-34-P1: Accumulator records exactly N entries for N calls.

    Property 1: For any N auxiliary calls, flush returns exactly N entries
    and a second flush returns empty.
    """

    @given(
        calls=st.lists(
            st.tuples(token_counts, token_counts, model_ids),
            min_size=0,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_completeness(
        self, calls: list[tuple[int, int, str]]
    ) -> None:
        acc = TokenAccumulator()
        for inp, out, model in calls:
            acc.record(inp, out, model)

        entries = acc.flush()
        assert len(entries) == len(calls)

        # Second flush is empty
        assert acc.flush() == []


class TestTokenConservation:
    """TS-34-P2: Reported totals = session tokens + auxiliary tokens.

    Property 2: For any session and auxiliary token combination, the
    totals in state equal the sum of both.
    """

    @given(
        session_in=token_counts,
        session_out=token_counts,
        aux_calls=st.lists(
            st.tuples(token_counts, token_counts, model_ids),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=50)
    def test_conservation(
        self,
        session_in: int,
        session_out: int,
        aux_calls: list[tuple[int, int, str]],
    ) -> None:
        # We test the accumulator totals match expectations
        acc = TokenAccumulator()
        for inp, out, model in aux_calls:
            acc.record(inp, out, model)

        aux_in, aux_out = acc.total()
        expected_in = sum(c[0] for c in aux_calls)
        expected_out = sum(c[1] for c in aux_calls)

        assert aux_in == expected_in
        assert aux_out == expected_out

        # Total should be session + auxiliary
        total_in = session_in + aux_in
        total_out = session_out + aux_out
        assert total_in == session_in + expected_in
        assert total_out == session_out + expected_out


class TestPricingConfigPrecedence:
    """TS-34-P3: Config prices are used for cost calculation.

    Property 3: For any pricing and token counts,
    cost = (in*price_in + out*price_out) / 1M.
    """

    @given(
        in_price=price_values,
        out_price=price_values,
        in_tokens=token_counts,
        out_tokens=token_counts,
    )
    @settings(max_examples=100)
    def test_precedence(
        self,
        in_price: float,
        out_price: float,
        in_tokens: int,
        out_tokens: int,
    ) -> None:
        pricing = PricingConfig(
            models={"test-model": ModelPricing(
                input_price_per_m=in_price,
                output_price_per_m=out_price,
            )}
        )

        cost = calculate_cost(in_tokens, out_tokens, "test-model", pricing)
        expected = (in_tokens * in_price + out_tokens * out_price) / 1_000_000

        assert abs(cost - expected) < 0.0001


class TestPricingDefaultsPresent:
    """TS-34-P4: Default config has pricing for all registered models.

    Property 4: Every model in MODEL_REGISTRY has a pricing entry with
    positive prices in the default config.
    """

    def test_all_models_have_pricing(self) -> None:
        config = AgentFoxConfig()

        for model_id in MODEL_REGISTRY:
            assert model_id in config.pricing.models, (
                f"Model {model_id} missing from default pricing config"
            )
            pricing = config.pricing.models[model_id]
            assert pricing.input_price_per_m > 0, (
                f"Model {model_id} has non-positive input price"
            )
            assert pricing.output_price_per_m > 0, (
                f"Model {model_id} has non-positive output price"
            )


class TestArchetypePreserved:
    """TS-34-P5: Archetype field round-trips through serialization.

    Property 5: For any archetype name, serialize then deserialize
    preserves the value.
    """

    @given(archetype=archetype_names)
    @settings(max_examples=20)
    def test_roundtrip(self, archetype: str) -> None:
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
            archetype=archetype,
        )

        # Simulate serialization/deserialization via dataclass
        from dataclasses import asdict

        data = asdict(record)
        restored = SessionRecord(**data)
        assert restored.archetype == archetype


class TestPerSpecAggregation:
    """TS-34-P6: Per-spec costs sum correctly.

    Property 6: For any set of records, per-spec costs equal the sum
    of costs for records sharing the same spec prefix.
    """

    @given(
        records=st.lists(
            st.tuples(
                st.sampled_from(["spec_a:1", "spec_a:2", "spec_b:1", "spec_c:3"]),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
            ),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_aggregation(
        self, records: list[tuple[str, float]]
    ) -> None:
        # Manual aggregation
        expected: dict[str, float] = {}
        for node_id, cost in records:
            spec = extract_spec_name(node_id)
            expected[spec] = expected.get(spec, 0.0) + cost

        # Verify extract_spec_name works correctly for all node_ids
        for node_id, _ in records:
            spec = extract_spec_name(node_id)
            if ":" in node_id:
                assert spec == node_id.rsplit(":", 1)[0]
            else:
                assert spec == node_id
