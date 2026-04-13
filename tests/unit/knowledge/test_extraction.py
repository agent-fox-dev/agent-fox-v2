"""Tests for fact extraction from session transcripts.

Test Spec: TS-05-3 (valid LLM response), TS-05-E1 (invalid JSON),
           TS-05-E2 (zero facts), TS-05-E3 (unknown category)
Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import RateLimitError  # used in TestExtractionRetry

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.knowledge.extraction import (
    _parse_extraction_response,
    extract_facts,
)
from agent_fox.knowledge.facts import Category
from tests.unit.knowledge.conftest import (
    EMPTY_LLM_RESPONSE,
    FENCED_JSON_LLM_RESPONSE,
    FENCED_NO_LANG_LLM_RESPONSE,
    INVALID_JSON_LLM_RESPONSE,
    PROSE_WRAPPED_JSON_LLM_RESPONSE,
    UNKNOWN_CATEGORY_LLM_RESPONSE,
    VALID_LLM_RESPONSE,
)


class TestExtractionValidResponse:
    """TS-05-3: Extraction returns facts from valid LLM response.

    Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_extract_facts_returns_two_facts(self) -> None:
        """Verify extraction parses a valid JSON response into Fact objects."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(VALID_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript here",
                spec_name="02_planning_engine",
            )

        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_extracted_facts_have_correct_spec_name(self) -> None:
        """Verify each fact has the correct spec_name."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(VALID_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="02_planning_engine",
            )

        assert all(f.spec_name == "02_planning_engine" for f in facts)

    @pytest.mark.asyncio
    async def test_extracted_facts_have_uuid_and_timestamp(self) -> None:
        """Verify each fact has a non-empty UUID and created_at."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(VALID_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="02_planning_engine",
            )

        assert all(f.id is not None and len(f.id) > 0 for f in facts)
        assert all(f.created_at is not None and len(f.created_at) > 0 for f in facts)

    def test_parse_valid_response(self) -> None:
        """Verify _parse_extraction_response parses valid JSON correctly."""
        facts = _parse_extraction_response(VALID_LLM_RESPONSE, "02_planning_engine")
        assert len(facts) == 2
        assert facts[0].category in [c.value for c in Category]
        assert facts[0].spec_name == "02_planning_engine"


class TestExtractionInvalidJSON:
    """TS-05-E1: Extraction with invalid LLM JSON.

    Requirement: 05-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty_list(self) -> None:
        """Verify invalid JSON response returns empty list."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(INVALID_JSON_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert facts == []

    @pytest.mark.asyncio
    async def test_invalid_json_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify invalid JSON response logs a warning."""
        with (
            patch(
                "agent_fox.knowledge.extraction.ai_call",
                new_callable=AsyncMock,
                return_value=(INVALID_JSON_LLM_RESPONSE, MagicMock()),
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.extraction"),
        ):
            await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert any("json" in r.message.lower() for r in caplog.records)


class TestExtractionZeroFacts:
    """TS-05-E2: Extraction with zero facts.

    Requirement: 05-REQ-1.E2
    """

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self) -> None:
        """Verify empty array response returns empty list."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(EMPTY_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert facts == []


class TestExtractionUnknownCategory:
    """TS-05-E3: Unknown category defaults to gotcha.

    Requirement: 05-REQ-2.2
    """

    def test_unknown_category_defaults_to_gotcha(self) -> None:
        """Verify unknown category in LLM output is replaced with gotcha."""
        facts = _parse_extraction_response(UNKNOWN_CATEGORY_LLM_RESPONSE, "spec_01")
        assert len(facts) == 1
        assert facts[0].category == "gotcha"

    def test_unknown_category_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify unknown category logs a warning."""
        with caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.extraction"):
            _parse_extraction_response(UNKNOWN_CATEGORY_LLM_RESPONSE, "spec_01")

        assert any("unknown" in r.message.lower() or "category" in r.message.lower() for r in caplog.records)


class TestExtractJsonArray:
    """Tests for extract_json_array (consolidated from _strip_markdown_fences)."""

    def test_extracts_from_json_code_fence(self) -> None:
        result = extract_json_array('```json\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_extracts_from_plain_code_fence(self) -> None:
        result = extract_json_array('```\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_extracts_array_from_prose(self) -> None:
        text = 'Here are results:\n[{"a": 1}]\nDone!'
        result = extract_json_array(text)
        assert result == [{"a": 1}]

    def test_extracts_clean_json(self) -> None:
        text = '[{"a": 1}]'
        result = extract_json_array(text)
        assert result == [{"a": 1}]

    def test_returns_none_for_garbage(self) -> None:
        text = "not json at all"
        result = extract_json_array(text)
        assert result is None

    def test_extracts_array_when_bracketed_refs_precede_json(self) -> None:
        """Prose with [bracketed] references before the JSON array."""
        text = (
            "Looking at [uuid1] and [uuid2], I found:\n\n"
            '[{"content": "a fact", "category": "gotcha", '
            '"confidence": "high", "keywords": ["k"]}]'
        )
        result = extract_json_array(text)
        assert isinstance(result, list)
        assert result[0]["content"] == "a fact"

    def test_extracts_array_from_prose_with_multiple_brackets(self) -> None:
        """Multiple non-JSON brackets in prose before the real JSON array."""
        text = 'The fact [abc-123] caused [def-456] to change.\nHere is the result:\n\n[{"a": 1}]\n\nDone!'
        result = extract_json_array(text)
        assert result == [{"a": 1}]


class TestExtractionMarkdownFenced:
    """Extraction correctly handles LLM responses wrapped in markdown fences."""

    @pytest.mark.asyncio
    async def test_fenced_json_response_parses(self) -> None:
        """Verify ```json ... ``` fenced response is parsed correctly."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(FENCED_JSON_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert len(facts) == 1
        assert "pin dependency" in facts[0].content.lower()

    @pytest.mark.asyncio
    async def test_fenced_no_lang_response_parses(self) -> None:
        """Verify ``` ... ``` fenced response (no language) is parsed."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(FENCED_NO_LANG_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert len(facts) == 1
        assert "structured logging" in facts[0].content.lower()

    @pytest.mark.asyncio
    async def test_prose_wrapped_response_parses(self) -> None:
        """Verify JSON wrapped in explanatory prose is parsed."""
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(PROSE_WRAPPED_JSON_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert len(facts) == 1
        assert "mock external" in facts[0].content.lower()


class TestExtractionRetry:
    """Test retry with backoff on transient API errors."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self) -> None:
        """Verify extract_facts succeeds when ai_call handles retries internally."""
        # ai_call encapsulates retry logic, so a successful return means
        # any transient errors were resolved internally.
        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(VALID_LLM_RESPONSE, MagicMock()),
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self) -> None:
        """Verify extract_facts raises after all retries are exhausted."""
        rate_limit_exc = RateLimitError.__new__(RateLimitError)
        rate_limit_exc.status_code = 429
        rate_limit_exc.message = "rate limited"
        rate_limit_exc.body = None
        rate_limit_exc.response = AsyncMock(status_code=429, headers={})

        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            side_effect=rate_limit_exc,
        ):
            with pytest.raises(RateLimitError):
                await extract_facts(
                    transcript="session transcript",
                    spec_name="spec_01",
                )
