"""SDK feature passthrough and resolution tests.

Test Spec: TS-56-2, TS-56-4, TS-56-6, TS-56-13,
           TS-56-15, TS-56-E2
Requirements: 56-REQ-1.2, 56-REQ-1.4, 56-REQ-2.2, 56-REQ-2.E1,
              56-REQ-4.2, 56-REQ-5.3
"""

from __future__ import annotations

import inspect
from typing import Any

# ---------------------------------------------------------------------------
# TS-56-15: Protocol Extended With New Parameters
# Requirement: 56-REQ-5.3
# ---------------------------------------------------------------------------


class TestClaudeBackendSignature:
    """Verify ClaudeBackend.execute() includes optional parameters."""

    def test_execute_has_max_turns(self) -> None:
        """TS-56-15: execute() signature includes max_turns."""
        from agent_fox.session.backends.claude import ClaudeBackend

        sig = inspect.signature(ClaudeBackend.execute)
        assert "max_turns" in sig.parameters

    def test_execute_has_max_budget_usd(self) -> None:
        """TS-56-15: execute() signature includes max_budget_usd."""
        from agent_fox.session.backends.claude import ClaudeBackend

        sig = inspect.signature(ClaudeBackend.execute)
        assert "max_budget_usd" in sig.parameters

    def test_execute_has_thinking(self) -> None:
        """TS-56-15: execute() signature includes thinking."""
        from agent_fox.session.backends.claude import ClaudeBackend

        sig = inspect.signature(ClaudeBackend.execute)
        assert "thinking" in sig.parameters


# ---------------------------------------------------------------------------
# TS-56-4: max_turns Zero Means Unlimited
# Requirement: 56-REQ-1.4
# ---------------------------------------------------------------------------


class TestMaxTurnsZeroUnlimited:
    """Verify max_turns=0 results in None (unlimited)."""

    def test_zero_max_turns_resolves_to_none(self) -> None:
        """TS-56-4: max_turns=0 resolves to None (no max_turns in options)."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes={"max_turns": {"coder": 0}},  # type: ignore[arg-type]
        )
        result = resolve_max_turns(config, "coder")
        assert result is None


# ---------------------------------------------------------------------------
# TS-56-E2: Zero Budget Means Unlimited
# Requirement: 56-REQ-2.E1
# ---------------------------------------------------------------------------


class TestBudgetZeroUnlimited:
    """Verify max_budget_usd=0 results in None (unlimited)."""

    def test_zero_budget_resolves_to_none(self) -> None:
        """TS-56-E2: max_budget_usd=0 resolves to None."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_max_budget

        config = AgentFoxConfig(
            orchestrator={"max_budget_usd": 0.0},  # type: ignore[arg-type]
        )
        result = resolve_max_budget(config)
        assert result is None


# ---------------------------------------------------------------------------
# TS-56-2: max_turns Passed to ClaudeCodeOptions
# Requirement: 56-REQ-1.2
# ---------------------------------------------------------------------------


class TestMaxTurnsPassthrough:
    """Verify max_turns is forwarded to SDK options."""

    def test_max_turns_forwarded_to_options(self) -> None:
        """TS-56-2: max_turns is passed through to ClaudeCodeOptions."""
        from unittest.mock import patch

        from agent_fox.session.backends.claude import ClaudeBackend

        captured_options: list[Any] = []

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
            from agent_fox.session.backends.types import ResultMessage

            captured_options.append(options)
            yield ResultMessage(
                status="completed",
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
                error_message=None,
                is_error=False,
            )

        backend = ClaudeBackend()

        import asyncio

        with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
            messages = []
            loop = asyncio.new_event_loop()
            try:

                async def run() -> None:
                    async for msg in backend.execute(
                        "test prompt",
                        system_prompt="sys",
                        model="claude-sonnet-4-6",
                        cwd="/tmp",
                        max_turns=50,
                    ):
                        messages.append(msg)

                loop.run_until_complete(run())
            finally:
                loop.close()

        assert len(captured_options) == 1
        assert captured_options[0].max_turns == 50


# ---------------------------------------------------------------------------
# TS-56-6: max_budget_usd Passed to ClaudeCodeOptions
# Requirement: 56-REQ-2.2
# ---------------------------------------------------------------------------


class TestBudgetPassthrough:
    """Verify max_budget_usd is forwarded to SDK options."""

    def test_budget_forwarded_to_options(self) -> None:
        """TS-56-6: max_budget_usd is passed through to ClaudeCodeOptions."""
        from unittest.mock import patch

        from agent_fox.session.backends.claude import ClaudeBackend

        captured_options: list[Any] = []

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
            from agent_fox.session.backends.types import ResultMessage

            captured_options.append(options)
            yield ResultMessage(
                status="completed",
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
                error_message=None,
                is_error=False,
            )

        backend = ClaudeBackend()

        import asyncio

        with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
            loop = asyncio.new_event_loop()
            try:

                async def run() -> None:
                    async for _ in backend.execute(
                        "test",
                        system_prompt="sys",
                        model="claude-sonnet-4-6",
                        cwd="/tmp",
                        max_budget_usd=3.0,
                    ):
                        pass

                loop.run_until_complete(run())
            finally:
                loop.close()

        assert len(captured_options) == 1
        # max_budget_usd may be stored as attr or in extra_args
        opts = captured_options[0]
        assert getattr(opts, "max_budget_usd", None) == 3.0 or opts.extra_args.get("max-budget-usd") == "3.0"


# ---------------------------------------------------------------------------
# TS-56-13: Thinking Passed to ClaudeCodeOptions
# Requirement: 56-REQ-4.2
# ---------------------------------------------------------------------------


class TestThinkingPassthrough:
    """Verify thinking config is forwarded to SDK options."""

    def test_thinking_forwarded_to_options(self) -> None:
        """TS-56-13: thinking config is passed through to ClaudeCodeOptions."""
        from unittest.mock import patch

        from agent_fox.session.backends.claude import ClaudeBackend

        captured_options: list[Any] = []

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
            from agent_fox.session.backends.types import ResultMessage

            captured_options.append(options)
            yield ResultMessage(
                status="completed",
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
                error_message=None,
                is_error=False,
            )

        backend = ClaudeBackend()

        import asyncio

        thinking = {"type": "adaptive", "budget_tokens": 10000}

        with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
            loop = asyncio.new_event_loop()
            try:

                async def run() -> None:
                    async for _ in backend.execute(
                        "test",
                        system_prompt="sys",
                        model="claude-sonnet-4-6",
                        cwd="/tmp",
                        thinking=thinking,
                    ):
                        pass

                loop.run_until_complete(run())
            finally:
                loop.close()

        assert len(captured_options) == 1
        opts = captured_options[0]
        # Thinking should be stored somehow in options
        stored_thinking = getattr(opts, "thinking", None)
        if stored_thinking is None:
            stored_thinking = opts.extra_args.get("thinking")
        assert stored_thinking is not None


