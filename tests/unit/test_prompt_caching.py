"""Unit tests for prompt caching configuration and helper.

Test Spec: TS-77-1 through TS-77-10, TS-77-E1 through TS-77-E4
Requirements: 77-REQ-1.1, 77-REQ-1.2, 77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5,
              77-REQ-1.E1, 77-REQ-2.1, 77-REQ-2.2, 77-REQ-2.3, 77-REQ-2.4,
              77-REQ-2.E1, 77-REQ-2.E2, 77-REQ-3.1, 77-REQ-3.2, 77-REQ-3.3,
              77-REQ-4.2, 77-REQ-4.3, 77-REQ-4.E1, 77-REQ-5.1
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import anthropic
import pytest
from pydantic import ValidationError

from agent_fox.core.client import (
    _estimate_tokens,
    cached_messages_create,
)
from agent_fox.core.config import AgentFoxConfig, CachePolicy, CachingConfig

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

_FAKE_MESSAGE = MagicMock(spec=anthropic.types.Message)


class MockMessages:
    """Captures kwargs passed to messages.create() / messages.acreate()."""

    def __init__(self, *, fail_first_with: Exception | None = None) -> None:
        self.call_count = 0
        self.last_call_kwargs: dict[str, Any] = {}
        self._fail_first_with = fail_first_with

    async def create(self, **kwargs: Any) -> anthropic.types.Message:
        self.call_count += 1
        if self._fail_first_with is not None and self.call_count == 1:
            raise self._fail_first_with
        self.last_call_kwargs = kwargs
        return _FAKE_MESSAGE


class MockAsyncAnthropic:
    """Minimal async Anthropic client stub."""

    def __init__(self, *, fail_first_with: Exception | None = None) -> None:
        self.messages = MockMessages(fail_first_with=fail_first_with)

    @property
    def call_count(self) -> int:
        return self.messages.call_count

    @property
    def last_call_kwargs(self) -> dict[str, Any]:
        return self.messages.last_call_kwargs


# ---------------------------------------------------------------------------
# TS-77-1: Default Cache Policy
# ---------------------------------------------------------------------------


class TestDefaultCachePolicy:
    """TS-77-1: Omitting [caching] defaults to DEFAULT policy."""

    def test_default_cache_policy(self) -> None:
        """77-REQ-1.2: No [caching] section → DEFAULT policy."""
        config = AgentFoxConfig()
        assert config.caching.cache_policy == CachePolicy.DEFAULT


# ---------------------------------------------------------------------------
# TS-77-2: Cache Policy Parsing
# ---------------------------------------------------------------------------


class TestCachePolicyParsing:
    """TS-77-2: All three values parse correctly, case-insensitive."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            ("NONE", CachePolicy.NONE),
            ("default", CachePolicy.DEFAULT),
            ("Extended", CachePolicy.EXTENDED),
        ],
    )
    def test_cache_policy_parsing(self, input_str: str, expected: CachePolicy) -> None:
        """77-REQ-1.1: Valid policy strings (case-insensitive) parse correctly."""
        config = CachingConfig(cache_policy=input_str)  # type: ignore[arg-type]
        assert config.cache_policy == expected


# ---------------------------------------------------------------------------
# TS-77-3: NONE Policy Passthrough
# ---------------------------------------------------------------------------


class TestNonePolicyPassthrough:
    """TS-77-3: NONE policy produces no cache_control in requests."""

    def test_none_policy_passthrough(self) -> None:
        """77-REQ-1.3, 77-REQ-2.4, 77-REQ-5.1: NONE passes system unchanged."""
        client = MockAsyncAnthropic()

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system="You are a helpful assistant.",
                cache_policy=CachePolicy.NONE,
            )
        )

        captured = client.last_call_kwargs
        assert captured["system"] == "You are a helpful assistant."
        assert "cache_control" not in str(captured)


# ---------------------------------------------------------------------------
# TS-77-4: DEFAULT Policy Marker
# ---------------------------------------------------------------------------


class TestDefaultPolicyMarker:
    """TS-77-4: DEFAULT policy attaches ephemeral cache_control to last system block."""

    def test_default_policy_marker(self) -> None:
        """77-REQ-1.4, 77-REQ-2.2: DEFAULT adds {"type": "ephemeral"} to last block."""
        client = MockAsyncAnthropic()
        long_prompt = "x" * 20000

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system=long_prompt,
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        system_blocks = client.last_call_kwargs["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[-1]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# TS-77-5: EXTENDED Policy Marker
# ---------------------------------------------------------------------------


class TestExtendedPolicyMarker:
    """TS-77-5: EXTENDED policy uses 1-hour TTL."""

    def test_extended_policy_marker(self) -> None:
        """77-REQ-1.5: EXTENDED adds {"type": "ephemeral", "ttl": "1h"}."""
        client = MockAsyncAnthropic()

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system="x" * 20000,
                cache_policy=CachePolicy.EXTENDED,
            )
        )

        last_block = client.last_call_kwargs["system"][-1]
        assert last_block["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


# ---------------------------------------------------------------------------
# TS-77-6: Multi-Block System Prompt
# ---------------------------------------------------------------------------


class TestMultiBlockSystemPrompt:
    """TS-77-6: cache_control attached only to last block in multi-block system."""

    def test_multi_block_system_prompt(self) -> None:
        """77-REQ-2.2: Only the last block gets cache_control."""
        client = MockAsyncAnthropic()
        system_blocks = [
            {"type": "text", "text": "a" * 10000},
            {"type": "text", "text": "b" * 10000},
        ]

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system=system_blocks,
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        result = client.last_call_kwargs["system"]
        assert "cache_control" not in result[0]
        assert result[-1]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# TS-77-7: No System Parameter
# ---------------------------------------------------------------------------


class TestNoSystemParameter:
    """TS-77-7: No system param → no cache_control added."""

    def test_no_system_parameter(self) -> None:
        """77-REQ-2.3: Without system, no cache_control injected."""
        client = MockAsyncAnthropic()

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        captured = client.last_call_kwargs
        # system should be absent or None
        system_val = captured.get("system")
        assert system_val is None or "system" not in captured
        assert "cache_control" not in str(captured)


# ---------------------------------------------------------------------------
# TS-77-8: Auxiliary Modules Use Helper
# ---------------------------------------------------------------------------

AUXILIARY_MODULES = [
    "agent_fox/knowledge/extraction.py",
    "agent_fox/nightshift/critic.py",
    "agent_fox/nightshift/staleness.py",
    "agent_fox/nightshift/triage.py",
    "agent_fox/spec/ai_validation.py",
    "agent_fox/engine/knowledge_harvest.py",
    "agent_fox/knowledge/query_oracle.py",
    "agent_fox/fix/clusterer.py",
]


class TestAuxiliaryModulesUseHelper:
    """TS-77-8: All auxiliary modules use cached_messages_create."""

    @pytest.mark.parametrize("module_path", AUXILIARY_MODULES)
    def test_auxiliary_modules_use_helper(self, module_path: str) -> None:
        """77-REQ-3.1, 77-REQ-3.2: Each module uses cached helper, not raw create."""
        repo_root = Path(__file__).parent.parent.parent
        full_path = repo_root / module_path
        assert full_path.exists(), f"Module not found: {full_path}"

        source = full_path.read_text(encoding="utf-8")
        caching_helpers = ("cached_messages_create", "ai_call", "ai_call_sync", "nightshift_ai_call")
        assert any(h in source for h in caching_helpers), (
            f"{module_path} does not call any caching helper ({', '.join(caching_helpers)})"
        )
        assert ".messages.create(" not in source, f"{module_path} still has a raw .messages.create() call"


# ---------------------------------------------------------------------------
# TS-77-9: Token Threshold Estimation
# ---------------------------------------------------------------------------


class TestTokenThresholdEstimation:
    """TS-77-9: _estimate_tokens uses characters ÷ 4 heuristic."""

    @pytest.mark.parametrize(
        ("chars", "expected_tokens"),
        [
            (0, 0),
            (100, 25),
            (8192, 2048),
            (16384, 4096),
        ],
    )
    def test_token_threshold_estimation(self, chars: int, expected_tokens: int) -> None:
        """77-REQ-4.3: len(text) // 4 gives expected token estimate."""
        text = "x" * chars
        assert _estimate_tokens(text) == expected_tokens


# ---------------------------------------------------------------------------
# TS-77-10: Threshold Gating Skips Small Prompts
# ---------------------------------------------------------------------------


class TestThresholdGatingSkipsSmall:
    """TS-77-10: Short prompts below threshold don't get cache_control."""

    def test_threshold_gating_skips_small(self) -> None:
        """77-REQ-4.2: Prompt below threshold passes through unchanged."""
        client = MockAsyncAnthropic()

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system="short prompt",
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        assert client.last_call_kwargs["system"] == "short prompt"


# ---------------------------------------------------------------------------
# TS-77-E1: Invalid Cache Policy Value
# ---------------------------------------------------------------------------


class TestInvalidCachePolicyValue:
    """TS-77-E1: Unrecognized policy value raises ValidationError."""

    def test_invalid_cache_policy_value(self) -> None:
        """77-REQ-1.E1: Bad policy string raises pydantic ValidationError."""
        with pytest.raises(ValidationError):
            CachingConfig(cache_policy="AGGRESSIVE")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-77-E2: String System Prompt Conversion
# ---------------------------------------------------------------------------


class TestStringSystemPromptConversion:
    """TS-77-E2: Plain string system prompt converted to content-block list."""

    def test_string_system_prompt_conversion(self) -> None:
        """77-REQ-2.E1: String system normalised to [{type, text, cache_control}]."""
        client = MockAsyncAnthropic()
        long_text = "x" * 20000

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system=long_text,
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        blocks = client.last_call_kwargs["system"]
        assert isinstance(blocks, list)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == long_text
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# TS-77-E3: Cache Control API Error Retry
# ---------------------------------------------------------------------------


class TestCacheControlApiErrorRetry:
    """TS-77-E3: API error mentioning cache_control triggers retry without caching."""

    def test_cache_control_api_error_retry(self) -> None:
        """77-REQ-2.E2: Bad cache_control API error → retry without caching."""
        # Construct a BadRequestError that mentions cache_control
        fake_response = MagicMock()
        fake_response.status_code = 400
        fake_response.headers = {}
        error = anthropic.BadRequestError(
            message="invalid cache_control",
            response=fake_response,
            body={"error": {"message": "invalid cache_control"}},
        )

        client = MockAsyncAnthropic(fail_first_with=error)

        result = asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system="x" * 20000,
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        assert client.call_count == 2
        assert "cache_control" not in str(client.last_call_kwargs)
        assert result is not None


# ---------------------------------------------------------------------------
# TS-77-E4: Unknown Model Uses Default Threshold
# ---------------------------------------------------------------------------


class TestUnknownModelDefaultThreshold:
    """TS-77-E4: Unknown model uses highest threshold (4096 tokens)."""

    def test_unknown_model_default_threshold(self) -> None:
        """77-REQ-4.E1: ~3000 estimated tokens < 4096 default → no cache_control."""
        client = MockAsyncAnthropic()
        # 12000 chars ÷ 4 = 3000 tokens < 4096 default threshold
        system_text = "x" * 12000

        asyncio.run(
            cached_messages_create(
                client,  # type: ignore[arg-type]
                model="claude-unknown-99",
                max_tokens=1024,
                messages=[{"role": "user", "content": "hi"}],
                system=system_text,
                cache_policy=CachePolicy.DEFAULT,
            )
        )

        assert client.last_call_kwargs["system"] == system_text
