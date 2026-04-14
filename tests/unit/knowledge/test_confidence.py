"""Tests for confidence normalization in the memory subsystem.

Test Spec: TS-37-1 through TS-37-4, TS-37-7, TS-37-8, TS-37-13,
           TS-37-E1, TS-37-E2, TS-37-E4
Requirements: 37-REQ-1.*, 37-REQ-3.*, 37-REQ-6.1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.knowledge.facts import Fact


class TestParseConfidence:
    """TS-37-1, TS-37-2, TS-37-E1, TS-37-E2, TS-37-E4: parse_confidence().

    Requirements: 37-REQ-1.2, 37-REQ-1.3, 37-REQ-1.E1, 37-REQ-1.E2
    """

    def test_string_high(self) -> None:
        """TS-37-1: 'high' maps to 0.9."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence("high") == 0.9

    def test_string_medium(self) -> None:
        """TS-37-1: 'medium' maps to 0.6."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence("medium") == 0.6

    def test_string_low(self) -> None:
        """TS-37-1: 'low' maps to 0.3."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence("low") == 0.3

    def test_numeric_unchanged(self) -> None:
        """TS-37-2: Numeric values in [0, 1] are returned unchanged."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence(0.75) == 0.75
        assert parse_confidence(0.0) == 0.0
        assert parse_confidence(1.0) == 1.0
        assert parse_confidence(0.5) == 0.5

    def test_unknown_string_defaults(self) -> None:
        """TS-37-E1: Unknown strings default to 0.6."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence("very_high") == 0.6
        assert parse_confidence("uncertain") == 0.6
        assert parse_confidence("") == 0.6

    def test_out_of_range_clamping(self) -> None:
        """TS-37-E2: Values outside [0, 1] are clamped."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence(-0.5) == 0.0
        assert parse_confidence(1.5) == 1.0
        assert parse_confidence(100) == 1.0
        assert parse_confidence(-1) == 0.0

    def test_none_defaults(self) -> None:
        """TS-37-E4: None input defaults to 0.6."""
        from agent_fox.knowledge.facts import parse_confidence

        assert parse_confidence(None) == 0.6


class TestFactConfidenceType:
    """TS-37-3: Fact dataclass uses float confidence.

    Requirement: 37-REQ-1.4
    """

    def test_fact_accepts_float_confidence(self) -> None:
        """Fact can be created with float confidence."""
        fact = Fact(
            id="test-uuid",
            content="test content",
            category="gotcha",
            spec_name="spec_01",
            keywords=["k1"],
            confidence=0.85,
            created_at="2026-03-01T00:00:00+00:00",
        )
        assert fact.confidence == 0.85
        assert isinstance(fact.confidence, float)

    def test_fact_default_confidence(self) -> None:
        """Fact defaults to 0.6 confidence."""
        from agent_fox.knowledge.facts import DEFAULT_CONFIDENCE

        assert DEFAULT_CONFIDENCE == 0.6


class TestExtractionConfidence:
    """TS-37-4: Extraction produces float confidence.

    Requirement: 37-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_extraction_stores_float(self) -> None:
        """Extracted facts have float confidence from string LLM output."""
        response_text = '[{"content": "Test fact", "category": "gotcha", "confidence": "high", "keywords": ["test"]}]'

        with patch(
            "agent_fox.knowledge.extraction.ai_call",
            new_callable=AsyncMock,
            return_value=(response_text, MagicMock()),
        ):
            from agent_fox.knowledge.extraction import extract_facts

            facts = await extract_facts("test transcript", "test_spec")

        assert len(facts) >= 1
        assert isinstance(facts[0].confidence, float)
        assert facts[0].confidence == 0.9


class TestRenderConfidence:
    """TS-37-13: Rendered fact shows two-decimal confidence.

    Requirement: 37-REQ-6.1
    """

    def test_render_fact_shows_float(self) -> None:
        """Rendered fact contains 'confidence: 0.90'."""
        from agent_fox.knowledge.rendering import _render_fact

        fact = Fact(
            id="test-uuid",
            content="Test fact content",
            category="pattern",
            spec_name="test_spec",
            keywords=["test"],
            confidence=0.9,
            created_at="2026-03-01T00:00:00+00:00",
        )
        rendered = _render_fact(fact)
        assert "confidence: 0.90" in rendered


class TestJsonlConfidence:
    """TS-37-7, TS-37-8: JSONL backward compatibility.

    Requirements: 37-REQ-3.1, 37-REQ-3.2, 37-REQ-3.3
    """

    def test_load_string_confidence(self, tmp_path: Path) -> None:
        """TS-37-7: String confidence converts to float via _dict_to_fact."""
        from agent_fox.knowledge.store import _dict_to_fact

        # Old-format JSONL entry with string confidence
        old_entry = {
            "id": "test-uuid-1",
            "content": "Test fact",
            "category": "gotcha",
            "spec_name": "spec_01",
            "keywords": ["test"],
            "confidence": "high",
            "created_at": "2026-03-01T00:00:00+00:00",
            "supersedes": None,
        }

        fact = _dict_to_fact(old_entry)
        assert fact.confidence == 0.9
        assert isinstance(fact.confidence, float)

    @pytest.mark.skip(reason="JSONL append_facts removed per spec 104-REQ-6")
    def test_write_float_confidence(self, tmp_path: Path) -> None:
        """TS-37-8: Writing facts to JSONL outputs float confidence."""
        jsonl_path = tmp_path / "memory.jsonl"
        fact = Fact(
            id="test-uuid-1",
            content="Test fact",
            category="gotcha",
            spec_name="spec_01",
            keywords=["test"],
            confidence=0.85,
            created_at="2026-03-01T00:00:00+00:00",
        )

        from agent_fox.knowledge.store import append_facts

        append_facts([fact], jsonl_path)

        # Read raw JSON to verify float is written
        raw = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert raw["confidence"] == 0.85
        assert isinstance(raw["confidence"], float)
