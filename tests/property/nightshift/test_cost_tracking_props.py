"""Property tests for nightshift cost tracking.

Test Spec: TS-91-P1, TS-91-P2, TS-91-P3
Properties: 2, 3, 4 from design.md
Requirements: 91-REQ-2.1, 91-REQ-3.1, 91-REQ-4.E1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.sink import SinkDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ARCHETYPES = [
    "triage",
    "fix_coder",
    "fix_reviewer",
    "hunt_critic",
    "batch_triage",
    "staleness_check",
    "quality_gate",
]


def _make_config() -> MagicMock:
    config = MagicMock()
    config.platform.type = "github"
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None
    config.orchestrator.retries_before_escalation = 1
    config.orchestrator.max_retries = 3
    config.archetypes = None
    config.pricing = MagicMock()
    config.pricing.models = {}
    config.theme = None
    return config


def _make_mock_outcome(
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int,
    cache_creation_input_tokens: int,
    duration_ms: int = 1000,
    status: str = "completed",
) -> MagicMock:
    """Build a mock SessionOutcome with the given token counts."""
    outcome = MagicMock()
    outcome.input_tokens = input_tokens
    outcome.output_tokens = output_tokens
    outcome.cache_read_input_tokens = cache_read_input_tokens
    outcome.cache_creation_input_tokens = cache_creation_input_tokens
    outcome.duration_ms = duration_ms
    outcome.status = status
    outcome.error_message = None
    return outcome


def _make_mock_response(
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> MagicMock:
    """Build a mock Anthropic API response with the given usage counts."""
    response = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.usage.cache_read_input_tokens = cache_read_input_tokens
    response.usage.cache_creation_input_tokens = cache_creation_input_tokens
    return response


# ---------------------------------------------------------------------------
# TS-91-P1: Cost calculation accuracy
# Property 2 from design.md
# Requirement: 91-REQ-3.1
# ---------------------------------------------------------------------------


class TestCostCalculationAccuracy:
    """TS-91-P1: Cost in session.complete equals calculate_cost() for any token counts."""

    @given(
        input_tokens=st.integers(min_value=0, max_value=1_000_000),
        output_tokens=st.integers(min_value=0, max_value=500_000),
        cache_read=st.integers(min_value=0, max_value=500_000),
        cache_creation=st.integers(min_value=0, max_value=500_000),
    )
    @settings(max_examples=50)
    def test_emit_session_event_cost_matches_calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read: int,
        cache_creation: int,
    ) -> None:
        """_emit_session_event payload cost equals calculate_cost() for arbitrary tokens.

        Property 2: cost accuracy invariant.
        """
        from agent_fox.core.models import calculate_cost
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = _make_config()
        mock_platform = MagicMock()
        mock_sink = MagicMock(spec=SinkDispatcher)

        # FAILS at construction until FixPipeline accepts sink_dispatcher
        pipeline = FixPipeline(config, mock_platform, sink_dispatcher=mock_sink)
        pipeline._run_id = "prop-test-run"  # type: ignore[attr-defined]

        mock_outcome = _make_mock_outcome(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

        model_id = "claude-sonnet-4-5"
        pricing = config.pricing

        captured_payload: dict = {}

        def _capture_emit(sink, run_id, event_type, *, payload=None, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal captured_payload
            captured_payload = payload or {}

        with patch(
            "agent_fox.nightshift.fix_pipeline.emit_audit_event",
            side_effect=_capture_emit,
            create=True,
        ):
            # FAILS until _emit_session_event method exists on FixPipeline
            pipeline._emit_session_event(  # type: ignore[attr-defined]
                mock_outcome,
                archetype="fix_coder",
                run_id="prop-test-run",
            )

        expected_cost = calculate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
            pricing=pricing,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

        # FAILS until cost is populated in the payload
        assert "cost" in captured_payload, "_emit_session_event must include 'cost' in payload"
        actual_cost = captured_payload["cost"]
        assert abs(actual_cost - expected_cost) < 1e-10, (
            f"payload cost {actual_cost!r} != calculate_cost() {expected_cost!r} "
            f"for tokens ({input_tokens}, {output_tokens}, {cache_read}, {cache_creation})"
        )


# ---------------------------------------------------------------------------
# TS-91-P2: Graceful degradation with None sink
# Property 3 from design.md
# Requirements: 91-REQ-1.3, 91-REQ-2.E1, 91-REQ-4.E1
# ---------------------------------------------------------------------------


class TestGracefulDegradationNoneSink:
    """TS-91-P2: emit_auxiliary_cost never raises when sink is None."""

    @given(
        archetype=st.sampled_from(_ARCHETYPES),
        run_id=st.text(min_size=0, max_size=50),
        input_tokens=st.integers(min_value=0, max_value=10_000),
        output_tokens=st.integers(min_value=0, max_value=10_000),
    )
    @settings(max_examples=50)
    def test_no_exception_with_none_sink(
        self,
        archetype: str,
        run_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """emit_auxiliary_cost(None, ...) never raises, for any archetype/run_id.

        Property 3: graceful degradation invariant.
        """
        # FAILS with ModuleNotFoundError until cost_helpers.py is created
        from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost  # type: ignore[import]

        mock_response = _make_mock_response(input_tokens, output_tokens)
        mock_pricing = MagicMock()
        mock_pricing.models = {}

        # Must not raise for any archetype or run_id
        emit_auxiliary_cost(
            None,
            run_id,
            archetype,
            mock_response,
            "claude-sonnet-4-5",
            mock_pricing,
        )


# ---------------------------------------------------------------------------
# TS-91-P3: Run ID uniqueness
# Property 4 from design.md
# Requirement: 91-REQ-2.1
# ---------------------------------------------------------------------------


class TestRunIdUniqueness:
    """TS-91-P3: Multiple calls to generate_run_id produce unique values."""

    @given(n=st.integers(min_value=2, max_value=100))
    @settings(max_examples=20)
    def test_generate_run_ids_are_unique(self, n: int) -> None:
        """n consecutive generate_run_id() calls produce n distinct values.

        Property 4: run ID uniqueness invariant.

        Note: This validates the existing generate_run_id() function that the
        nightshift cost tracking implementation will use. It passes on the
        current codebase since generate_run_id() already exists.
        """
        from agent_fox.knowledge.audit import generate_run_id

        ids = [generate_run_id() for _ in range(n)]
        assert len(set(ids)) == n, (
            f"Expected {n} unique run IDs from generate_run_id(), but got {len(set(ids))} unique values"
        )
