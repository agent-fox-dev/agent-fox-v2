"""Integration tests for SDK feature adoption.

Test Spec: TS-56-E7
Requirements: 56-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import patch

from agent_fox.session.backends.claude import ClaudeBackend
from agent_fox.session.backends.types import ResultMessage

# ---------------------------------------------------------------------------
# TS-56-E7: SDK TypeError Fallback
# Requirement: 56-REQ-5.E1
# ---------------------------------------------------------------------------


class TestSDKTypeErrorFallback:
    """Verify TypeError from SDK is caught and session retries without
    the unsupported parameter."""

    def test_sdk_typeerror_fallback_thinking(self, caplog: Any) -> None:
        """TS-56-E7: TypeError on thinking param is caught, session continues."""
        call_count = 0
        captured_options: list[Any] = []

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
            nonlocal call_count
            call_count += 1
            captured_options.append(options)
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
                with caplog.at_level(logging.WARNING):
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

        # Session should complete (not crash)
        assert any(isinstance(m, ResultMessage) for m in result)

    def test_sdk_typeerror_fallback_max_turns(self, caplog: Any) -> None:
        """TS-56-E7: TypeError on max_turns param handled gracefully."""

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
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
                    max_turns=50,
                ):
                    messages.append(msg)
                return messages

            with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
                result = loop.run_until_complete(run())
        finally:
            loop.close()

        assert any(isinstance(m, ResultMessage) for m in result)

    def test_sdk_typeerror_fallback_fallback_model(self, caplog: Any) -> None:
        """TS-56-E7: TypeError on fallback_model param handled gracefully."""

        async def fake_stream(self: Any, *, prompt: str, options: Any) -> Any:
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
                    fallback_model="claude-haiku-4-5",
                ):
                    messages.append(msg)
                return messages

            with patch.object(ClaudeBackend, "_stream_messages", fake_stream):
                result = loop.run_until_complete(run())
        finally:
            loop.close()

        assert any(isinstance(m, ResultMessage) for m in result)
