"""Tests for confidence-aware fact selection.

Test Spec: TS-39-11, TS-39-12, TS-39-13
Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3
"""

from __future__ import annotations

from tests.unit.knowledge.conftest import make_fact

# ---------------------------------------------------------------------------
# TS-39-11: Confidence Threshold Filtering
# ---------------------------------------------------------------------------


class TestConfidenceFiltering:
    """TS-39-11, TS-39-12, TS-39-13: Confidence-aware fact filtering.

    Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3
    """

    def test_threshold_filtering(self) -> None:
        """TS-39-11: Facts below confidence threshold are excluded.

        Requirement: 39-REQ-4.1
        """
        from agent_fox.knowledge.filtering import select_relevant_facts

        facts = [
            make_fact(id="f1", confidence="0.9", keywords=["test"], spec_name="s"),
            make_fact(id="f2", confidence="0.7", keywords=["test"], spec_name="s"),
            make_fact(id="f3", confidence="0.5", keywords=["test"], spec_name="s"),
            make_fact(id="f4", confidence="0.3", keywords=["test"], spec_name="s"),
            make_fact(id="f5", confidence="0.1", keywords=["test"], spec_name="s"),
        ]

        result = select_relevant_facts(facts, "s", ["test"], confidence_threshold=0.5)

        assert len(result) == 3
        assert all(float(f.confidence) >= 0.5 for f in result)

    def test_configurable_threshold(self) -> None:
        """TS-39-12: Confidence threshold configurable via config.

        Requirement: 39-REQ-4.2
        """
        # Verify the config schema supports the knowledge.confidence_threshold
        from agent_fox.core.config import KnowledgeConfig

        # KnowledgeConfig should accept confidence_threshold
        config = KnowledgeConfig(confidence_threshold=0.7)
        assert config.confidence_threshold == 0.7

    def test_filter_before_scoring(self) -> None:
        """TS-39-13: Confidence filtering occurs before keyword scoring.

        Requirement: 39-REQ-4.3
        """
        from agent_fox.knowledge.filtering import select_relevant_facts

        # Low confidence fact with high keyword relevance
        low_conf_high_rel = make_fact(
            id="low_conf",
            confidence="0.3",
            keywords=["exact_match"],
            spec_name="other",
        )
        # High confidence fact with low keyword relevance
        high_conf_low_rel = make_fact(
            id="high_conf",
            confidence="0.9",
            keywords=["exact_match"],
            spec_name="other",
        )

        result = select_relevant_facts(
            [low_conf_high_rel, high_conf_low_rel],
            "spec1",
            ["exact_match"],
            confidence_threshold=0.5,
        )

        result_ids = {f.id for f in result}
        assert "low_conf" not in result_ids, (
            "Low-confidence fact should be excluded regardless of keyword score"
        )
        assert "high_conf" in result_ids

    def test_default_threshold(self) -> None:
        """Default confidence threshold is 0.5."""
        from agent_fox.knowledge.filtering import select_relevant_facts

        facts = [
            make_fact(id="f1", confidence="0.4", keywords=["test"], spec_name="s"),
            make_fact(id="f2", confidence="0.6", keywords=["test"], spec_name="s"),
        ]

        # Default threshold should be 0.5
        result = select_relevant_facts(facts, "s", ["test"])
        result_ids = {f.id for f in result}
        # f1 with 0.4 confidence should be excluded at default threshold
        assert "f1" not in result_ids
        assert "f2" in result_ids
