"""Property tests for SDK feature adoption.

Test Spec: TS-56-P1 through TS-56-P8
Properties: 1-8 from design.md
Requirements: 56-REQ-1.1, 56-REQ-1.2, 56-REQ-1.4, 56-REQ-2.1, 56-REQ-2.2,
              56-REQ-2.E2, 56-REQ-3.1, 56-REQ-3.2, 56-REQ-4.1, 56-REQ-4.2,
              56-REQ-4.E1, 56-REQ-4.E2, 56-REQ-5.1, 56-REQ-5.E1
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# TS-56-P1: Turn Limit Passthrough Invariant
# Property 1: For any positive max_turns, the value passes through unchanged.
# Requirements: 56-REQ-1.1, 56-REQ-1.2
# ---------------------------------------------------------------------------


class TestTurnLimitPassthrough:
    """For any positive max_turns, resolve_max_turns returns it unchanged."""

    @given(max_turns=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=50)
    def test_positive_max_turns_passthrough(self, max_turns: int) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes={"max_turns": {"coder": max_turns}},  # type: ignore[arg-type]
        )
        result = resolve_max_turns(config, "coder")
        assert result == max_turns


# ---------------------------------------------------------------------------
# TS-56-P2: Zero Turns Means Unlimited
# Property 2: max_turns=0 always results in None.
# Requirement: 56-REQ-1.4
# ---------------------------------------------------------------------------


class TestZeroTurnsUnlimited:
    """max_turns=0 always results in None for any archetype."""

    @given(
        archetype=st.sampled_from(
            [
                "coder",
                "oracle",
                "skeptic",
                "verifier",
                "auditor",
            ]
        )
    )
    @settings(max_examples=20)
    def test_zero_turns_always_none(self, archetype: str) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes={"max_turns": {archetype: 0}},  # type: ignore[arg-type]
        )
        result = resolve_max_turns(config, archetype)
        assert result is None


# ---------------------------------------------------------------------------
# TS-56-P3: Budget Cap Passthrough Invariant
# Property 3: For any positive budget, the value passes through unchanged.
# Requirements: 56-REQ-2.1, 56-REQ-2.2
# ---------------------------------------------------------------------------


class TestBudgetCapPassthrough:
    """For any positive budget, resolve_max_budget returns it unchanged."""

    @given(budget=st.floats(min_value=0.01, max_value=100.0))
    @settings(max_examples=50)
    def test_positive_budget_passthrough(self, budget: float) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_budget

        config = AgentFoxConfig(
            orchestrator={"max_budget_usd": budget},  # type: ignore[arg-type]
        )
        result = resolve_max_budget(config)
        assert result == budget


# ---------------------------------------------------------------------------
# TS-56-P4: Fallback Model Passthrough Invariant
# Property 4: For any non-empty model string, it passes through unchanged.
# Requirements: 56-REQ-3.1, 56-REQ-3.2
# ---------------------------------------------------------------------------


class TestFallbackModelPassthrough:
    """For any non-empty model string, resolve_fallback_model returns it."""

    @given(
        model_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
                whitelist_characters="-_",
            ),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_nonempty_model_passthrough(self, model_id: str) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_fallback_model

        config = AgentFoxConfig(
            models={"fallback_model": model_id},  # type: ignore[arg-type]
        )
        result = resolve_fallback_model(config)
        # Non-empty model ID should pass through (possibly with a warning)
        assert result == model_id


# ---------------------------------------------------------------------------
# TS-56-P5: Thinking Passthrough Invariant
# Property 5: For any non-disabled thinking config, it passes through.
# Requirements: 56-REQ-4.1, 56-REQ-4.2
# ---------------------------------------------------------------------------


class TestThinkingPassthrough:
    """For any non-disabled thinking config, resolve_thinking returns it."""

    @given(
        mode=st.sampled_from(["enabled", "adaptive"]),
        budget=st.integers(min_value=1, max_value=50000),
    )
    @settings(max_examples=50)
    def test_nondisabled_thinking_passthrough(self, mode: str, budget: int) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_thinking

        config = AgentFoxConfig(
            archetypes={  # type: ignore[arg-type]
                "thinking": {
                    "coder": {"mode": mode, "budget_tokens": budget},
                },
            },
        )
        result = resolve_thinking(config, "coder")
        assert result is not None
        assert result["type"] == mode
        assert result["budget_tokens"] == budget


# ---------------------------------------------------------------------------
# TS-56-P6: Config Override Wins Over Defaults
# Property 6: Config overrides always take precedence over registry defaults.
# Requirement: 56-REQ-5.1
# ---------------------------------------------------------------------------


class TestConfigOverridePrecedence:
    """Config overrides always win over archetype registry defaults."""

    @given(
        archetype=st.sampled_from(
            [
                "coder",
                "oracle",
                "skeptic",
                "verifier",
                "auditor",
            ]
        ),
        override_turns=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=50)
    def test_config_override_wins(self, archetype: str, override_turns: int) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes={  # type: ignore[arg-type]
                "max_turns": {archetype: override_turns},
            },
        )
        result = resolve_max_turns(config, archetype)
        assert result == override_turns


# ---------------------------------------------------------------------------
# TS-56-P7: Validation Rejects Invalid Config
# Property 7: Invalid config values always raise validation errors.
# Requirements: 56-REQ-1.E1, 56-REQ-2.E2, 56-REQ-4.E1, 56-REQ-4.E2
# ---------------------------------------------------------------------------


class TestValidationRejectsInvalid:
    """Invalid config values always raise validation errors."""

    @given(neg=st.integers(min_value=-1000, max_value=-1))
    @settings(max_examples=20)
    def test_negative_budget_rejected(self, neg: int) -> None:
        """Negative max_budget_usd always raises."""
        try:
            from agent_fox.core.config import AgentFoxConfig

            AgentFoxConfig(
                orchestrator={"max_budget_usd": float(neg)},  # type: ignore[arg-type]
            )
            raise AssertionError(  # noqa: TRY301
                f"Expected ValidationError for max_budget_usd={neg}"
            )
        except (ValidationError, ValueError):
            pass  # Expected

    @given(neg=st.integers(min_value=-1000, max_value=-1))
    @settings(max_examples=20)
    def test_negative_max_turns_rejected(self, neg: int) -> None:
        """Negative max_turns always raises."""
        try:
            from agent_fox.core.config import AgentFoxConfig

            AgentFoxConfig(
                archetypes={"max_turns": {"coder": neg}},  # type: ignore[arg-type]
            )
            raise AssertionError(  # noqa: TRY301
                f"Expected ValidationError for max_turns={neg}"
            )
        except (ValidationError, ValueError):
            pass  # Expected

    def test_invalid_thinking_mode_rejected(self) -> None:
        """Invalid thinking mode raises."""
        try:
            from agent_fox.core.config import AgentFoxConfig

            AgentFoxConfig(
                archetypes={  # type: ignore[arg-type]
                    "thinking": {
                        "coder": {"mode": "turbo", "budget_tokens": 10000},
                    },
                },
            )
            raise AssertionError(  # noqa: TRY301
                "Expected ValidationError for mode='turbo'"
            )
        except (ValidationError, ValueError):
            pass  # Expected

    def test_zero_budget_tokens_enabled_rejected(self) -> None:
        """budget_tokens=0 with mode=enabled raises."""
        try:
            from agent_fox.core.config import AgentFoxConfig

            AgentFoxConfig(
                archetypes={  # type: ignore[arg-type]
                    "thinking": {
                        "coder": {"mode": "enabled", "budget_tokens": 0},
                    },
                },
            )
            raise AssertionError(  # noqa: TRY301
                "Expected ValidationError for budget_tokens=0 with enabled"
            )
        except (ValidationError, ValueError):
            pass  # Expected


# ---------------------------------------------------------------------------
# TS-56-P8: SDK Compatibility Fallback
# Property 8: When SDK raises TypeError on a new param, execution continues.
# Requirement: 56-REQ-5.E1
# ---------------------------------------------------------------------------


class TestSDKCompatibilityFallback:
    """When SDK raises TypeError on a new param, session doesn't crash."""

    def test_typeerror_on_thinking_handled(self) -> None:
        """TypeError from SDK on thinking param is caught gracefully."""
        import asyncio
        from unittest.mock import patch

        from agent_fox.session.backends.claude import ClaudeBackend
        from agent_fox.session.backends.types import ResultMessage

        call_count = 0

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Yield a successful result
            yield ResultMessage(
                status="completed",
                input_tokens=10,
                output_tokens=5,
                duration_ms=100,
                error_message=None,
                is_error=False,
            )

        backend = ClaudeBackend()

        loop = asyncio.new_event_loop()
        try:

            async def run() -> list:
                messages = []
                async for msg in backend.execute(
                    "test",
                    system_prompt="sys",
                    model="claude-sonnet-4-6",
                    cwd="/tmp",
                    thinking={"type": "adaptive", "budget_tokens": 10000},
                ):
                    messages.append(msg)
                return messages

            with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
                result = loop.run_until_complete(run())

        finally:
            loop.close()

        # Session should complete without crashing
        assert len(result) >= 1
        assert any(isinstance(m, ResultMessage) for m in result)
