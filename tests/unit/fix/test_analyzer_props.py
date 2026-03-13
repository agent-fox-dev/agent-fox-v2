"""Analyzer property tests.

Test Spec: TS-31-P2 (filtering soundness), TS-31-P3 (tier priority ordering)
Properties: Property 5, Property 6 from design.md
Requirements: 31-REQ-3.4, 31-REQ-3.5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.analyzer import Improvement, filter_improvements

TIERS = ["quick_win", "structural", "design_level"]
CONFIDENCES = [0.9, 0.6, 0.3]
IMPACTS = ["low", "medium", "high"]
TIER_ORDER = {"quick_win": 0, "structural": 1, "design_level": 2}


def improvement_strategy() -> st.SearchStrategy[Improvement]:
    """Generate random Improvement objects."""
    return st.builds(
        Improvement,
        id=st.text(min_size=1, max_size=10),
        tier=st.sampled_from(TIERS),
        title=st.text(min_size=1, max_size=50),
        description=st.text(min_size=1, max_size=100),
        files=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=5),
        impact=st.sampled_from(IMPACTS),
        confidence=st.sampled_from(CONFIDENCES),
    )


class TestFilteringSoundness:
    """TS-31-P2: Filtered improvements never contain low-confidence items."""

    @given(improvements=st.lists(improvement_strategy(), max_size=20))
    @settings(max_examples=50)
    def test_no_low_confidence_in_output(self, improvements: list[Improvement]) -> None:
        filtered = filter_improvements(improvements)
        assert all(i.confidence >= 0.5 for i in filtered)


class TestTierPriorityOrdering:
    """TS-31-P3: Filtered improvements maintain tier priority order."""

    @given(
        improvements=st.lists(
            improvement_strategy().filter(lambda i: i.confidence >= 0.5),
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_tier_order_maintained(self, improvements: list[Improvement]) -> None:
        filtered = filter_improvements(improvements)
        orders = [TIER_ORDER[i.tier] for i in filtered]
        assert orders == sorted(orders)
