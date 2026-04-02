"""Property-based tests for prompt caching helper.

Test Spec: TS-77-P1 through TS-77-P4
Requirements: 77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5, 77-REQ-2.2, 77-REQ-2.4,
              77-REQ-2.E1, 77-REQ-4.1, 77-REQ-4.2, 77-REQ-4.3, 77-REQ-5.1
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import anthropic
import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.core.client import (
    _CACHE_TOKEN_THRESHOLDS,
    _DEFAULT_THRESHOLD,
    cached_messages_create,
)
from agent_fox.core.config import CachePolicy

pytestmark = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")

# ---------------------------------------------------------------------------
# Mock helpers (mirrored from unit tests for property tests)
# ---------------------------------------------------------------------------

_FAKE_MESSAGE = MagicMock(spec=anthropic.types.Message)


class _MockMessages:
    def __init__(self) -> None:
        self.last_call_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> anthropic.types.Message:
        self.last_call_kwargs = kwargs
        return _FAKE_MESSAGE


class _MockAsyncAnthropic:
    def __init__(self) -> None:
        self.messages = _MockMessages()

    @property
    def last_call_kwargs(self) -> dict[str, Any]:
        return self.messages.last_call_kwargs


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TS-77-P1: Policy Fidelity
# ---------------------------------------------------------------------------


@given(
    policy=st.sampled_from(list(CachePolicy)),
    # Large string exceeding all model thresholds (sonnet=8192 chars).
    # st.text(min_size=20000) exceeds Hypothesis's buffer; use integers.map.
    system_text=st.integers(min_value=8200, max_value=10000).map(lambda n: "x" * n),
)
@settings(max_examples=30)
def test_policy_fidelity(policy: CachePolicy, system_text: str) -> None:
    """TS-77-P1: Correct cache_control (or none) for any policy + large prompt.

    77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5, 77-REQ-2.2, 77-REQ-2.4
    """
    client = _MockAsyncAnthropic()

    _run(
        cached_messages_create(
            client,  # type: ignore[arg-type]
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": "hi"}],
            system=system_text,
            cache_policy=policy,
        )
    )

    captured = client.last_call_kwargs

    if policy == CachePolicy.NONE:
        assert "cache_control" not in str(captured)
    elif policy == CachePolicy.DEFAULT:
        system_blocks = captured["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[-1]["cache_control"] == {"type": "ephemeral"}
    elif policy == CachePolicy.EXTENDED:
        system_blocks = captured["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[-1]["cache_control"] == {
            "type": "ephemeral",
            "ttl": "1h",
        }


# ---------------------------------------------------------------------------
# TS-77-P2: String-to-Block Normalization
# ---------------------------------------------------------------------------


@given(
    # Same large-text strategy as test_policy_fidelity (above Hypothesis buffer limit).
    system_text=st.integers(min_value=8200, max_value=10000).map(lambda n: "x" * n),
    policy=st.sampled_from([CachePolicy.DEFAULT, CachePolicy.EXTENDED]),
)
@settings(max_examples=30)
def test_string_to_block_normalization(system_text: str, policy: CachePolicy) -> None:
    """TS-77-P2: String system prompt normalised to list of content blocks.

    77-REQ-2.E1
    """
    client = _MockAsyncAnthropic()

    _run(
        cached_messages_create(
            client,  # type: ignore[arg-type]
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": "hi"}],
            system=system_text,
            cache_policy=policy,
        )
    )

    blocks = client.last_call_kwargs["system"]
    assert isinstance(blocks, list)
    assert all(b["type"] == "text" for b in blocks)


# ---------------------------------------------------------------------------
# TS-77-P3: Threshold Gate
# ---------------------------------------------------------------------------

_KNOWN_MODELS = list(_CACHE_TOKEN_THRESHOLDS.keys())


@given(
    n=st.integers(min_value=1, max_value=8000),
    model=st.sampled_from(_KNOWN_MODELS),
    policy=st.sampled_from([CachePolicy.DEFAULT, CachePolicy.EXTENDED]),
)
@settings(max_examples=50)
def test_threshold_gate(n: int, model: str, policy: CachePolicy) -> None:
    """TS-77-P3: Prompts below threshold never receive cache_control.

    77-REQ-4.1, 77-REQ-4.2, 77-REQ-4.3
    """
    client = _MockAsyncAnthropic()
    system_text = "x" * n

    _run(
        cached_messages_create(
            client,  # type: ignore[arg-type]
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": "hi"}],
            system=system_text,
            cache_policy=policy,
        )
    )

    threshold = _CACHE_TOKEN_THRESHOLDS.get(model, _DEFAULT_THRESHOLD)
    estimated = n // 4
    if estimated < threshold:
        assert "cache_control" not in str(client.last_call_kwargs)


# ---------------------------------------------------------------------------
# TS-77-P4: NONE-Policy Passthrough
# ---------------------------------------------------------------------------


@given(system_text=st.text(min_size=1, max_size=30000))
@settings(max_examples=50)
def test_none_policy_passthrough_property(system_text: str) -> None:
    """TS-77-P4: NONE policy never modifies the system prompt.

    77-REQ-2.4, 77-REQ-5.1
    """
    client = _MockAsyncAnthropic()

    _run(
        cached_messages_create(
            client,  # type: ignore[arg-type]
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": "hi"}],
            system=system_text,
            cache_policy=CachePolicy.NONE,
        )
    )

    assert client.last_call_kwargs["system"] == system_text
