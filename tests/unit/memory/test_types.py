"""Tests for memory data types: Fact, Category, ConfidenceLevel.

Test Spec: TS-05-1 (fact creation), TS-05-2 (category enum)
Requirements: 05-REQ-2.1, 05-REQ-3.2
"""

from __future__ import annotations

from agent_fox.memory.memory import _fact_to_dict
from agent_fox.memory.types import Category, ConfidenceLevel, Fact


class TestFactCreation:
    """TS-05-1: Fact creation with all fields.

    Requirement: 05-REQ-3.2
    """

    def test_fact_has_all_fields(self) -> None:
        """Verify a Fact can be created with all required fields."""
        fact = Fact(
            id="uuid-1",
            content="test content",
            category="gotcha",
            spec_name="spec_01",
            keywords=["k1", "k2"],
            confidence="high",
            created_at="2026-03-01T00:00:00+00:00",
            supersedes=None,
        )
        assert fact.id == "uuid-1"
        assert fact.content == "test content"
        assert fact.category == "gotcha"
        assert fact.spec_name == "spec_01"
        assert fact.keywords == ["k1", "k2"]
        assert fact.confidence == "high"
        assert fact.created_at == "2026-03-01T00:00:00+00:00"
        assert fact.supersedes is None

    def test_fact_with_supersedes(self) -> None:
        """Verify a Fact can be created with supersedes reference."""
        fact = Fact(
            id="uuid-2",
            content="superseding fact",
            category="pattern",
            spec_name="spec_01",
            keywords=["k1"],
            confidence="medium",
            created_at="2026-03-01T00:00:00+00:00",
            supersedes="uuid-1",
        )
        assert fact.supersedes == "uuid-1"

    def test_fact_to_dict_has_all_keys(self) -> None:
        """Verify _fact_to_dict() produces a dict with all keys present."""
        fact = Fact(
            id="uuid-1",
            content="test",
            category="gotcha",
            spec_name="spec_01",
            keywords=["k1"],
            confidence="high",
            created_at="2026-03-01T00:00:00+00:00",
            supersedes=None,
        )
        d = _fact_to_dict(fact)
        assert "id" in d
        assert "content" in d
        assert "category" in d
        assert "spec_name" in d
        assert "keywords" in d
        assert "confidence" in d
        assert "created_at" in d
        assert "supersedes" in d


class TestCategoryEnum:
    """TS-05-2: Category enum has six values.

    Requirement: 05-REQ-2.1
    """

    def test_category_has_six_values(self) -> None:
        """Verify the Category enum defines exactly six categories."""
        values = [c.value for c in Category]
        assert len(values) == 6
        assert set(values) == {
            "gotcha",
            "pattern",
            "decision",
            "convention",
            "anti_pattern",
            "fragile_area",
        }

    def test_category_values_are_strings(self) -> None:
        """Verify all Category values are lowercase strings."""
        for cat in Category:
            assert isinstance(cat.value, str)
            assert cat.value == cat.value.lower()


class TestConfidenceLevelEnum:
    """Verify ConfidenceLevel enum defines three levels."""

    def test_confidence_has_three_values(self) -> None:
        """Verify the ConfidenceLevel enum has high, medium, low."""
        values = [c.value for c in ConfidenceLevel]
        assert len(values) == 3
        assert set(values) == {"high", "medium", "low"}
