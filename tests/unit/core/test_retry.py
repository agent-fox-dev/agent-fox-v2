"""Tests for the API retry utility."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import APIStatusError, RateLimitError

from agent_fox.core.retry import (
    _RETRY_DELAYS,
    retry_api_call,
    retry_api_call_async,
)


def _make_rate_limit_error() -> RateLimitError:
    exc = RateLimitError.__new__(RateLimitError)
    exc.status_code = 429
    exc.message = "rate limited"
    exc.body = None
    exc.response = MagicMock(status_code=429, headers={})
    return exc


def _make_server_error(status: int = 500) -> APIStatusError:
    exc = APIStatusError.__new__(APIStatusError)
    exc.status_code = status
    exc.message = "server error"
    exc.body = None
    exc.response = MagicMock(status_code=status, headers={})
    return exc


class TestRetryDelays:
    """Verify the fixed delay schedule."""

    def test_delays_are_2_30_60(self) -> None:
        assert _RETRY_DELAYS == (2.0, 30.0, 60.0)

    def test_max_attempts_is_four(self) -> None:
        assert len(_RETRY_DELAYS) + 1 == 4


class TestRetryApiCallAsync:
    @pytest.mark.asyncio
    async def test_succeeds_without_retry(self) -> None:
        fn = AsyncMock(return_value="ok")
        result = await retry_api_call_async(fn, context="test")
        assert result == "ok"
        assert fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self) -> None:
        exc = _make_rate_limit_error()
        fn = AsyncMock(side_effect=[exc, exc, "ok"])

        with patch(
            "agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await retry_api_call_async(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(30.0)

    @pytest.mark.asyncio
    async def test_retries_on_server_error_then_succeeds(self) -> None:
        exc = _make_server_error(502)
        fn = AsyncMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_api_call_async(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        exc = _make_rate_limit_error()
        fn = AsyncMock(side_effect=exc)

        with patch(
            "agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(RateLimitError):
                await retry_api_call_async(fn, context="test")

        # 4 attempts total: 1 initial + 3 retries
        assert fn.call_count == 4
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(60.0)

    @pytest.mark.asyncio
    async def test_does_not_retry_client_error(self) -> None:
        exc = _make_server_error(400)
        fn = AsyncMock(side_effect=exc)

        with pytest.raises(APIStatusError):
            await retry_api_call_async(fn, context="test")

        assert fn.call_count == 1


class TestRetryApiCallAsyncNetworkErrors:
    """Verify that network-level transport errors trigger retries."""

    @pytest.mark.asyncio
    async def test_retries_on_oserror_then_succeeds(self) -> None:
        exc = OSError(50, "Network is down")
        fn = AsyncMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_api_call_async(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_connection_error_then_succeeds(self) -> None:
        exc = ConnectionError("Connection refused")
        fn = AsyncMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_api_call_async(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_timeout_error_then_succeeds(self) -> None:
        exc = TimeoutError("Connection timed out")
        fn = AsyncMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_api_call_async(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_oserror_after_all_retries_exhausted(self) -> None:
        exc = OSError(50, "Network is down")
        fn = AsyncMock(side_effect=exc)

        with patch("agent_fox.core.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OSError):
                await retry_api_call_async(fn, context="test")

        assert fn.call_count == 4

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_exception(self) -> None:
        fn = AsyncMock(side_effect=ValueError("bad value"))

        with pytest.raises(ValueError):
            await retry_api_call_async(fn, context="test")

        assert fn.call_count == 1


class TestRetryApiCallSync:
    def test_succeeds_without_retry(self) -> None:
        fn = MagicMock(return_value="ok")
        result = retry_api_call(fn, context="test")
        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_rate_limit_then_succeeds(self) -> None:
        exc = _make_rate_limit_error()
        fn = MagicMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.time.sleep") as mock_sleep:
            result = retry_api_call(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

    def test_raises_after_all_retries_exhausted(self) -> None:
        exc = _make_rate_limit_error()
        fn = MagicMock(side_effect=exc)

        with patch("agent_fox.core.retry.time.sleep"):
            with pytest.raises(RateLimitError):
                retry_api_call(fn, context="test")

        assert fn.call_count == 4

    def test_does_not_retry_client_error(self) -> None:
        exc = _make_server_error(422)
        fn = MagicMock(side_effect=exc)

        with pytest.raises(APIStatusError):
            retry_api_call(fn, context="test")

        assert fn.call_count == 1


class TestRetryApiCallSyncNetworkErrors:
    """Verify sync retry handles network-level transport errors."""

    def test_retries_on_oserror_then_succeeds(self) -> None:
        exc = OSError(50, "Network is down")
        fn = MagicMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.time.sleep"):
            result = retry_api_call(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    def test_retries_on_connection_error_then_succeeds(self) -> None:
        exc = ConnectionError("Connection refused")
        fn = MagicMock(side_effect=[exc, "ok"])

        with patch("agent_fox.core.retry.time.sleep"):
            result = retry_api_call(fn, context="test")

        assert result == "ok"
        assert fn.call_count == 2

    def test_raises_oserror_after_all_retries_exhausted(self) -> None:
        exc = OSError(50, "Network is down")
        fn = MagicMock(side_effect=exc)

        with patch("agent_fox.core.retry.time.sleep"):
            with pytest.raises(OSError):
                retry_api_call(fn, context="test")

        assert fn.call_count == 4

    def test_does_not_retry_non_retryable_exception(self) -> None:
        fn = MagicMock(side_effect=ValueError("bad value"))

        with pytest.raises(ValueError):
            retry_api_call(fn, context="test")

        assert fn.call_count == 1
