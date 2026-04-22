"""Platform-aware Anthropic client factory and cached message helper.

Detects whether the runtime is configured for Vertex AI, Bedrock,
or direct Anthropic API access and returns the appropriate SDK client.

Detection order (first match wins):
1. CLAUDE_CODE_USE_VERTEX=1  → AnthropicVertex / AsyncAnthropicVertex
2. CLAUDE_CODE_USE_BEDROCK=1 → AnthropicBedrock / AsyncAnthropicBedrock
3. Otherwise                 → Anthropic / AsyncAnthropic

No API keys are passed explicitly — each SDK variant auto-loads its
own environment variables.

Also provides ``cached_messages_create()`` / ``cached_messages_create_sync()``
which wrap ``client.messages.create()`` with prompt-caching ``cache_control``
injection based on a ``CachePolicy``.

Requirements: 77-REQ-2.1, 77-REQ-2.2, 77-REQ-2.3, 77-REQ-2.4,
              77-REQ-2.E1, 77-REQ-2.E2, 77-REQ-4.1, 77-REQ-4.2,
              77-REQ-4.3, 77-REQ-4.E1
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any

import anthropic

from agent_fox.core.config import CachePolicy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token threshold constants (77-REQ-4.1)
# ---------------------------------------------------------------------------

#: Minimum estimated tokens for caching to take effect, keyed by model ID.
_CACHE_TOKEN_THRESHOLDS: dict[str, int] = {
    "claude-sonnet-4-6": 2048,
    "claude-opus-4-6": 4096,
    "claude-haiku-4-5": 4096,
}

#: Default threshold used when the model is not in ``_CACHE_TOKEN_THRESHOLDS``.
_DEFAULT_THRESHOLD: int = 4096

# ---------------------------------------------------------------------------
# cache_control values per policy (77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5)
# ---------------------------------------------------------------------------

_CACHE_CONTROL: dict[CachePolicy, dict[str, Any] | None] = {
    CachePolicy.NONE: None,
    CachePolicy.DEFAULT: {"type": "ephemeral"},
    CachePolicy.EXTENDED: {"type": "ephemeral", "ttl": "1h"},
}


# ---------------------------------------------------------------------------
# Token estimation helper (77-REQ-4.3)
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) // 4."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# Internal cache_control injection logic
# ---------------------------------------------------------------------------


def _inject_cache_control(
    system: str | list[dict[str, Any]] | None,
    *,
    model: str,
    cache_policy: CachePolicy,
) -> str | list[dict[str, Any]] | None:
    """Return a (possibly modified) system prompt with cache_control injected.

    Rules:
    - If ``cache_policy`` is NONE, return *system* unchanged.
    - If *system* is None, return None unchanged.
    - Convert plain string to a single-element content-block list.
    - If estimated tokens < model threshold, return unchanged.
    - Attach ``cache_control`` to the **last** block only.

    Requirements: 77-REQ-2.2, 77-REQ-2.3, 77-REQ-2.4, 77-REQ-2.E1,
                  77-REQ-4.1, 77-REQ-4.2, 77-REQ-4.3, 77-REQ-4.E1
    """
    if cache_policy is CachePolicy.NONE or system is None:
        return system

    cache_control = _CACHE_CONTROL[cache_policy]

    # Determine total text for threshold estimation
    if isinstance(system, str):
        total_text = system
    else:
        total_text = "".join(block.get("text", "") if isinstance(block, dict) else "" for block in system)

    threshold = _CACHE_TOKEN_THRESHOLDS.get(model, _DEFAULT_THRESHOLD)
    if model not in _CACHE_TOKEN_THRESHOLDS:
        logger.debug(
            "Unknown model '%s' for cache threshold lookup; defaulting to %d",
            model,
            _DEFAULT_THRESHOLD,
        )

    if _estimate_tokens(total_text) < threshold:
        # Below threshold — skip caching (77-REQ-4.2)
        return system

    # Normalise string to content-block list (77-REQ-2.E1)
    if isinstance(system, str):
        blocks: list[dict[str, Any]] = [{"type": "text", "text": system}]
    else:
        blocks = [copy.copy(b) for b in system]

    # Attach cache_control to last block only (77-REQ-2.2)
    blocks[-1] = {**blocks[-1], "cache_control": cache_control}
    return blocks


# ---------------------------------------------------------------------------
# Async helper (77-REQ-2.1)
# ---------------------------------------------------------------------------


async def cached_messages_create(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    cache_policy: CachePolicy = CachePolicy.DEFAULT,
    **kwargs: Any,
) -> anthropic.types.Message:
    """Wrap ``client.messages.create()`` with cache_control injection.

    - If ``cache_policy`` is NONE, passes through unchanged.
    - If ``system`` is provided and above the token threshold, attaches
      ``cache_control`` to the last system block.
    - If ``system`` is a plain string, converts to content-block list first.
    - On ``cache_control``-related API errors, retries without caching.

    Requirements: 77-REQ-2.1, 77-REQ-2.2, 77-REQ-2.3, 77-REQ-2.4,
                  77-REQ-2.E1, 77-REQ-2.E2
    """
    modified_system = _inject_cache_control(system, model=model, cache_policy=cache_policy)

    call_kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        **kwargs,
    )
    if modified_system is not None:
        call_kwargs["system"] = modified_system

    try:
        return await client.messages.create(**call_kwargs)
    except anthropic.BadRequestError as exc:
        if "cache_control" in str(exc).lower():
            logger.warning(
                "cache_control caused API error (%s); retrying without caching",
                exc,
            )
            # Retry without cache_control (77-REQ-2.E2)
            fallback_kwargs: dict[str, Any] = dict(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                **kwargs,
            )
            if system is not None:
                fallback_kwargs["system"] = system
            return await client.messages.create(**fallback_kwargs)
        raise


# ---------------------------------------------------------------------------
# Sync helper for legacy callers (77-REQ-2.1)
# ---------------------------------------------------------------------------


def cached_messages_create_sync(
    client: anthropic.Anthropic,
    *,
    model: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    cache_policy: CachePolicy = CachePolicy.DEFAULT,
    **kwargs: Any,
) -> anthropic.types.Message:
    """Synchronous variant of ``cached_messages_create()``.

    Used by sync callers: knowledge_harvest, query_oracle, clusterer.

    Requirements: 77-REQ-2.1
    """
    modified_system = _inject_cache_control(system, model=model, cache_policy=cache_policy)

    call_kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        **kwargs,
    )
    if modified_system is not None:
        call_kwargs["system"] = modified_system

    try:
        return client.messages.create(**call_kwargs)
    except anthropic.BadRequestError as exc:
        if "cache_control" in str(exc).lower():
            logger.warning(
                "cache_control caused API error (%s); retrying without caching",
                exc,
            )
            fallback_kwargs: dict[str, Any] = dict(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                **kwargs,
            )
            if system is not None:
                fallback_kwargs["system"] = system
            return client.messages.create(**fallback_kwargs)
        raise


def _check_vertex_deps() -> None:
    """Fail fast if the Vertex extras are missing."""
    try:
        import google.auth  # noqa: F401
    except ModuleNotFoundError:
        raise RuntimeError(
            "CLAUDE_CODE_USE_VERTEX=1 is set but google-auth is not installed. Run: pip install 'anthropic[vertex]'"
        ) from None


def _check_bedrock_deps() -> None:
    """Fail fast if the Bedrock extras are missing."""
    try:
        import boto3  # type: ignore[import-untyped]  # noqa: F401
    except ModuleNotFoundError:
        raise RuntimeError(
            "CLAUDE_CODE_USE_BEDROCK=1 is set but boto3 is not installed. Run: pip install 'anthropic[bedrock]'"
        ) from None


def create_anthropic_client() -> anthropic.Anthropic:
    """Return a synchronous Anthropic client for the current platform."""
    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        _check_vertex_deps()
        from anthropic import AnthropicVertex

        return AnthropicVertex()  # type: ignore[return-value]

    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        _check_bedrock_deps()
        from anthropic import AnthropicBedrock

        return AnthropicBedrock()  # type: ignore[return-value]

    return anthropic.Anthropic()


def create_async_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return an async Anthropic client for the current platform."""
    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        _check_vertex_deps()
        from anthropic import AsyncAnthropicVertex

        return AsyncAnthropicVertex()  # type: ignore[return-value]

    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        _check_bedrock_deps()
        from anthropic import AsyncAnthropicBedrock

        return AsyncAnthropicBedrock()  # type: ignore[return-value]

    return anthropic.AsyncAnthropic()


# ---------------------------------------------------------------------------
# Response text extraction (shared helper)
# ---------------------------------------------------------------------------


def extract_response_text(response: Any) -> str | None:
    """Extract text from the first content block of an Anthropic API response.

    Returns the text string, or None if the response has no text content.
    Works with both real SDK response objects and test mocks.
    """
    content = getattr(response, "content", None)
    if not content:
        return None
    return getattr(content[0], "text", None)


# ---------------------------------------------------------------------------
# High-level AI call helpers
# ---------------------------------------------------------------------------


async def ai_call(
    *,
    model_tier: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    context: str,
    cache_policy: CachePolicy = CachePolicy.DEFAULT,
) -> tuple[str | None, Any]:
    """Async AI call: resolve model, create client, retry, track usage, extract text.

    Combines the repeated pattern of resolve_model + create_async_client +
    cached_messages_create + retry + track_response_usage + extract text
    into a single call.

    Returns:
        A tuple of (response_text_or_none, raw_response). Callers should
        check for None text and handle accordingly.
    """
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call_async
    from agent_fox.core.token_tracker import track_response_usage

    model_entry = resolve_model(model_tier)

    async def _call() -> Any:
        client = create_async_anthropic_client()
        try:
            return await cached_messages_create(
                client,
                model=model_entry.model_id,
                max_tokens=max_tokens,
                messages=messages,
                system=system,
                cache_policy=cache_policy,
            )
        finally:
            await client.close()

    response = await retry_api_call_async(_call, context=context)
    track_response_usage(response, model_entry.model_id, context)
    return extract_response_text(response), response


def ai_call_sync(
    *,
    model_tier: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    context: str,
    cache_policy: CachePolicy = CachePolicy.DEFAULT,
) -> tuple[str | None, Any]:
    """Synchronous AI call: resolve model, create client, retry, track usage, extract text.

    Synchronous variant of :func:`ai_call` for callers that cannot use async.

    Returns:
        A tuple of (response_text_or_none, raw_response).
    """
    from agent_fox.core.models import resolve_model
    from agent_fox.core.retry import retry_api_call
    from agent_fox.core.token_tracker import track_response_usage

    model_entry = resolve_model(model_tier)
    client = create_anthropic_client()

    def _call() -> Any:
        return cached_messages_create_sync(
            client,
            model=model_entry.model_id,
            max_tokens=max_tokens,
            messages=messages,
            system=system,
            cache_policy=cache_policy,
        )

    response = retry_api_call(_call, context=context)
    track_response_usage(response, model_entry.model_id, context)
    return extract_response_text(response), response
