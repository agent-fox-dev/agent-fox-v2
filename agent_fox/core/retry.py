"""Retry helpers for Anthropic API calls with fixed backoff schedule.

Retries on RateLimitError (429), server errors (5xx), and network-level
transport errors (OSError family) using a fixed delay schedule of
2s → 30s → 60s, then aborts.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine

from anthropic import APIStatusError, RateLimitError

logger = logging.getLogger(__name__)

# Fixed backoff delays (seconds) before each retry attempt.
# After all delays are exhausted the final attempt is made with no further retry.
_RETRY_DELAYS: tuple[float, ...] = (2.0, 30.0, 60.0)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return True
    if isinstance(exc, OSError):
        return True
    return False


async def retry_api_call_async[T](
    fn: Callable[[], Coroutine[object, object, T]],
    *,
    context: str = "API call",
) -> T:
    """Execute *fn* with retry on transient Anthropic errors.

    Args:
        fn: An async callable (zero-arg) that performs the API call.
        context: A human-readable label for log messages.

    Returns:
        The result of *fn* on success.

    Raises:
        The original exception after all retries are exhausted.
    """
    max_attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(max_attempts):
        try:
            return await fn()
        except (RateLimitError, APIStatusError, OSError) as exc:
            if not _is_retryable(exc) or attempt == max_attempts - 1:
                raise
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "%s: transient error (attempt %d/%d), retrying in %.0fs — %s",
                context,
                attempt + 1,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def retry_api_call[T](
    fn: Callable[[], T],
    *,
    context: str = "API call",
) -> T:
    """Synchronous version of :func:`retry_api_call_async`."""
    max_attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(max_attempts):
        try:
            return fn()
        except (RateLimitError, APIStatusError, OSError) as exc:
            if not _is_retryable(exc) or attempt == max_attempts - 1:
                raise
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "%s: transient error (attempt %d/%d), retrying in %.0fs — %s",
                context,
                attempt + 1,
                max_attempts,
                delay,
                exc,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
