"""Property tests for context selection budget enforcement.

Test Spec: TS-05-P1 (budget enforcement)
Property: Property 1 from design.md
Requirement: 05-REQ-4.3
"""

from __future__ import annotations

import pytest

pytest.skip("Legacy function removed per spec 104-REQ-6", allow_module_level=True)

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.facts import Category, Fact
from agent_fox.knowledge.filtering import select_relevant_facts

# -- Hypothesis strategies ---------------------------------------------------

CATEGORIES = [c.value for c in Category]


@st.composite
def fact_strategy(draw: st.DrawFn) -> Fact:
    """Generate a random valid Fact."""
    return Fact(
        id=str(uuid.uuid4()),
        content=draw(st.text(min_size=1, max_size=100)),
        category=draw(st.sampled_from(CATEGORIES)),
        spec_name=draw(st.text(min_size=1, max_size=30)),
        keywords=draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5)),
        confidence=draw(st.sampled_from([0.9, 0.6, 0.3])),
        created_at=draw(
            st.from_regex(
                r"2026-0[1-9]-[0-2][0-9]T[0-2][0-9]:00:00\+00:00",
                fullmatch=True,
            )
        ),
        supersedes=None,
    )


# -- Property tests ----------------------------------------------------------


class TestContextBudgetEnforcement:
    """TS-05-P1: Context budget enforcement.

    For any list of facts, any spec_name, any keyword list, and any budget,
    the context selection function never returns more than the budget.

    Property 1 from design.md.
    """

    @given(
        facts=st.lists(fact_strategy(), min_size=0, max_size=200),
        spec_name=st.text(min_size=1, max_size=30),
        keywords=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
        budget=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_result_never_exceeds_budget(
        self,
        facts: list[Fact],
        spec_name: str,
        keywords: list[str],
        budget: int,
    ) -> None:
        """The returned list never exceeds the budget."""
        result = select_relevant_facts(facts, spec_name, keywords, budget)
        assert len(result) <= budget
