"""Regression tests for async client cleanup (issue #506).

Verifies that ai_call() and direct create_async_anthropic_client() callers
close the AsyncAnthropic client after use, preventing RuntimeError('Event
loop is closed') tracebacks on shutdown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_client() -> MagicMock:
    """Build a mock AsyncAnthropic client with a trackable close()."""
    client = MagicMock()
    client.close = AsyncMock()

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=fake_response)
    return client


class TestAiCallClosesClient:
    """ai_call() must close the client even on success and on failure."""

    @pytest.mark.asyncio
    async def test_client_closed_on_success(self) -> None:
        mock_client = _make_mock_client()

        async def fake_retry(fn, **kw):  # noqa: ANN001, ANN003, ARG001
            return await fn()

        with (
            patch(
                "agent_fox.core.client.create_async_anthropic_client",
                return_value=mock_client,
            ),
            patch("agent_fox.core.models.resolve_model") as mock_resolve,
            patch("agent_fox.core.client.retry_api_call_async", side_effect=fake_retry),
            patch("agent_fox.core.token_tracker.track_response_usage"),
        ):
            mock_resolve.return_value = MagicMock(model_id="claude-sonnet-4-6")

            from agent_fox.core.client import ai_call

            await ai_call(
                model_tier="standard",
                max_tokens=100,
                messages=[{"role": "user", "content": "test"}],
                context="test",
            )

        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_closed_on_api_error(self) -> None:
        mock_client = _make_mock_client()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API error"))

        async def fake_retry(fn, **kw):  # noqa: ANN001, ANN003, ARG001
            return await fn()

        with (
            patch(
                "agent_fox.core.client.create_async_anthropic_client",
                return_value=mock_client,
            ),
            patch("agent_fox.core.models.resolve_model") as mock_resolve,
            patch("agent_fox.core.client.retry_api_call_async", side_effect=fake_retry),
            patch("agent_fox.core.token_tracker.track_response_usage"),
        ):
            mock_resolve.return_value = MagicMock(model_id="claude-sonnet-4-6")

            from agent_fox.core.client import ai_call

            with pytest.raises(RuntimeError, match="API error"):
                await ai_call(
                    model_tier="standard",
                    max_tokens=100,
                    messages=[{"role": "user", "content": "test"}],
                    context="test",
                )

        mock_client.close.assert_awaited_once()


