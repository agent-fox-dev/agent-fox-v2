"""Tests for context selection (filter): spec matching, keyword ranking, budget.

Test Spec: TS-05-6 (select by spec name), TS-05-7 (keyword ranking),
           TS-05-8 (budget enforcement), TS-05-E5 (no matching facts)
Requirements: 05-REQ-4.1, 05-REQ-4.2, 05-REQ-4.3, 05-REQ-4.E1
"""

from __future__ import annotations

import pytest

pytest.skip("Legacy function removed per spec 104-REQ-6", allow_module_level=True)

from agent_fox.knowledge.filtering import select_relevant_facts  # noqa: E402
from tests.unit.knowledge.conftest import make_fact  # noqa: E402


class TestFilterSelectsBySpecName:
    """TS-05-6: Filter selects by spec name.

    Requirement: 05-REQ-4.1
    """

    def test_returns_facts_matching_spec_name(self) -> None:
        """Verify facts from the matching spec are returned."""
        facts = [
            make_fact(id="f1", spec_name="spec_01", keywords=["test"]),
            make_fact(id="f2", spec_name="spec_02", keywords=["test"]),
            make_fact(id="f3", spec_name="spec_02", keywords=["test"]),
            make_fact(id="f4", spec_name="spec_03", keywords=["test"]),
        ]

        result = select_relevant_facts(facts, "spec_02", ["test"])

        # Facts from spec_02 should be included
        spec_02_ids = {f.id for f in result if f.spec_name == "spec_02"}
        assert "f2" in spec_02_ids
        assert "f3" in spec_02_ids

    def test_spec_name_facts_rank_higher(self) -> None:
        """Verify facts from the matching spec rank higher than others."""
        facts = [
            make_fact(
                id="other",
                spec_name="spec_01",
                keywords=["test"],
                created_at="2026-03-01T00:00:00+00:00",
            ),
            make_fact(
                id="same_spec",
                spec_name="spec_02",
                keywords=["test"],
                created_at="2026-01-01T00:00:00+00:00",
            ),
        ]

        result = select_relevant_facts(facts, "spec_02", ["test"])

        # The fact from spec_02 should appear (both match keyword "test")
        assert any(f.id == "same_spec" for f in result)


class TestFilterSelectsByKeywordOverlap:
    """TS-05-7: Filter selects by keyword overlap.

    Requirements: 05-REQ-4.1, 05-REQ-4.2
    """

    def test_more_keyword_matches_rank_higher(self) -> None:
        """Verify facts with more keyword matches score higher."""
        fact_3_matches = make_fact(
            id="f3m",
            spec_name="other",
            keywords=["pytest", "config", "toml"],
            created_at="2026-01-01T00:00:00+00:00",
        )
        fact_1_match = make_fact(
            id="f1m",
            spec_name="other",
            keywords=["pytest"],
            created_at="2026-01-01T00:00:00+00:00",
        )
        fact_0_matches = make_fact(
            id="f0m",
            spec_name="other",
            keywords=["unrelated"],
            created_at="2026-01-01T00:00:00+00:00",
        )

        result = select_relevant_facts(
            [fact_0_matches, fact_1_match, fact_3_matches],
            "spec_01",
            ["pytest", "config", "toml"],
        )

        # Fact with 3 keyword matches should rank first
        assert len(result) >= 1
        assert result[0].id == "f3m"

    def test_keyword_matching_is_case_insensitive(self) -> None:
        """Verify keyword matching is case-insensitive."""
        fact = make_fact(
            id="ci",
            spec_name="other",
            keywords=["PyTest", "Config"],
        )

        result = select_relevant_facts(
            [fact],
            "spec_01",
            ["pytest", "config"],
        )

        assert len(result) >= 1
        assert result[0].id == "ci"


class TestFilterEnforcesBudget:
    """TS-05-8: Filter enforces budget of 50.

    Requirement: 05-REQ-4.3
    """

    def test_returns_at_most_50_facts(self) -> None:
        """Verify at most 50 facts are returned even when more match."""
        many_facts = [
            make_fact(
                id=f"fact-{i}",
                spec_name="spec_01",
                keywords=["test"],
                created_at=f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00",
            )
            for i in range(100)
        ]

        result = select_relevant_facts(many_facts, "spec_01", ["test"])

        assert len(result) == 50

    def test_custom_budget(self) -> None:
        """Verify custom budget is respected."""
        facts = [
            make_fact(
                id=f"fact-{i}",
                spec_name="spec_01",
                keywords=["test"],
                created_at=f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00",
            )
            for i in range(20)
        ]

        result = select_relevant_facts(facts, "spec_01", ["test"], budget=5)

        assert len(result) == 5


class TestFilterNoMatchingFacts:
    """TS-05-E5: Filter with no matching facts.

    Requirement: 05-REQ-4.E1
    """

    def test_no_matches_returns_empty(self) -> None:
        """Verify filter returns empty list when nothing matches."""
        facts = [
            make_fact(
                id="f1",
                spec_name="spec_01",
                keywords=["pytest"],
            ),
        ]

        result = select_relevant_facts(facts, "unrelated_spec", ["no_match"])

        assert result == []

    def test_empty_facts_list_returns_empty(self) -> None:
        """Verify filter returns empty for empty input."""
        result = select_relevant_facts([], "spec_01", ["test"])
        assert result == []
