"""Tests for fact extraction from session transcripts.

Test Spec: TS-05-3 (valid LLM response), TS-05-E1 (invalid JSON),
           TS-05-E2 (zero facts), TS-05-E3 (unknown category)
Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
              05-REQ-1.E2, 05-REQ-2.2
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.memory.extraction import (
    _parse_extraction_response,
    _strip_markdown_fences,
    extract_facts,
)
from agent_fox.memory.types import Category
from tests.unit.memory.conftest import (
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
        # Mock the LLM call to return valid JSON
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=VALID_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
        ):
            facts = await extract_facts(
                transcript="session transcript here",
                spec_name="02_planning_engine",
            )

        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_extracted_facts_have_correct_spec_name(self) -> None:
        """Verify each fact has the correct spec_name."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=VALID_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="02_planning_engine",
            )

        assert all(f.spec_name == "02_planning_engine" for f in facts)

    @pytest.mark.asyncio
    async def test_extracted_facts_have_uuid_and_timestamp(self) -> None:
        """Verify each fact has a non-empty UUID and created_at."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=VALID_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
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
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=INVALID_JSON_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert facts == []

    @pytest.mark.asyncio
    async def test_invalid_json_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify invalid JSON response logs a warning."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=INVALID_JSON_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with (
            patch(
                "agent_fox.memory.extraction.create_async_anthropic_client",
                return_value=mock_client,
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.memory.extraction"),
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
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=EMPTY_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
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

    def test_unknown_category_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify unknown category logs a warning."""
        with caplog.at_level(logging.WARNING, logger="agent_fox.memory.extraction"):
            _parse_extraction_response(UNKNOWN_CATEGORY_LLM_RESPONSE, "spec_01")

        assert any(
            "unknown" in r.message.lower() or "category" in r.message.lower()
            for r in caplog.records
        )


class TestStripMarkdownFences:
    """Tests for _strip_markdown_fences helper."""

    def test_strips_json_code_fence(self) -> None:
        result = _strip_markdown_fences('```json\n[{"a": 1}]\n```')
        assert result == '[{"a": 1}]'

    def test_strips_plain_code_fence(self) -> None:
        result = _strip_markdown_fences('```\n[{"a": 1}]\n```')
        assert result == '[{"a": 1}]'

    def test_extracts_array_from_prose(self) -> None:
        text = 'Here are results:\n[{"a": 1}]\nDone!'
        result = _strip_markdown_fences(text)
        assert result == '[{"a": 1}]'

    def test_returns_clean_json_unchanged(self) -> None:
        text = '[{"a": 1}]'
        result = _strip_markdown_fences(text)
        assert result == '[{"a": 1}]'

    def test_returns_garbage_unchanged(self) -> None:
        text = "not json at all"
        result = _strip_markdown_fences(text)
        assert result == "not json at all"

    def test_extracts_array_when_bracketed_refs_precede_json(self) -> None:
        """Prose with [bracketed] references before the JSON array."""
        text = (
            'Looking at [uuid1] and [uuid2], I found:\n\n'
            '[{"content": "a fact", "category": "gotcha", '
            '"confidence": "high", "keywords": ["k"]}]'
        )
        result = _strip_markdown_fences(text)
        parsed = __import__("json").loads(result)
        assert isinstance(parsed, list)
        assert parsed[0]["content"] == "a fact"

    def test_extracts_array_from_prose_with_multiple_brackets(self) -> None:
        """Multiple non-JSON brackets in prose before the real JSON array."""
        text = (
            "The fact [abc-123] caused [def-456] to change.\n"
            "Here is the result:\n\n"
            '[{"a": 1}]\n\n'
            "Done!"
        )
        result = _strip_markdown_fences(text)
        parsed = __import__("json").loads(result)
        assert parsed == [{"a": 1}]


class TestExtractionMarkdownFenced:
    """Extraction correctly handles LLM responses wrapped in markdown fences."""

    @pytest.mark.asyncio
    async def test_fenced_json_response_parses(self) -> None:
        """Verify ```json ... ``` fenced response is parsed correctly."""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=FENCED_JSON_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
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
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=FENCED_NO_LANG_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
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
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=PROSE_WRAPPED_JSON_LLM_RESPONSE)]
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "agent_fox.memory.extraction.create_async_anthropic_client",
            return_value=mock_client,
        ):
            facts = await extract_facts(
                transcript="session transcript",
                spec_name="spec_01",
            )

        assert len(facts) == 1
        assert "mock external" in facts[0].content.lower()
