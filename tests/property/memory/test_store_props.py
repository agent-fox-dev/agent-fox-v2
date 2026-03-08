"""Property tests for fact serialization round-trip.

Test Spec: TS-05-P3 (serialization round-trip)
Property: Property 4 from design.md
Requirement: 05-REQ-3.2
"""

from __future__ import annotations

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.memory.memory import _dict_to_fact, _fact_to_dict
from agent_fox.memory.types import Category, Fact

# -- Hypothesis strategies ---------------------------------------------------

CATEGORIES = [c.value for c in Category]


@st.composite
def valid_fact(draw: st.DrawFn) -> Fact:
    """Generate a random valid Fact."""
    supersedes = draw(st.one_of(st.none(), st.just(str(uuid.uuid4()))))
    return Fact(
        id=str(uuid.uuid4()),
        content=draw(st.text(min_size=1, max_size=200)),
        category=draw(st.sampled_from(CATEGORIES)),
        spec_name=draw(st.text(min_size=1, max_size=50)),
        keywords=draw(
            st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5)
        ),
        confidence=draw(st.sampled_from(["high", "medium", "low"])),
        created_at=draw(
            st.from_regex(
                r"2026-0[1-9]-[0-2][0-9]T[0-2][0-9]:00:00\+00:00",
                fullmatch=True,
            )
        ),
        supersedes=supersedes,
    )


# -- Property tests ----------------------------------------------------------


class TestFactSerializationRoundTrip:
    """TS-05-P3: Fact serialization round-trip.

    Any valid Fact survives a serialize-deserialize cycle.

    Property 4 from design.md.
    """

    @given(fact=valid_fact())
    @settings(max_examples=200)
    def test_round_trip_preserves_all_fields(self, fact: Fact) -> None:
        """_dict_to_fact(_fact_to_dict(fact)) equals the original."""
        d = _fact_to_dict(fact)
        restored = _dict_to_fact(d)

        assert restored.id == fact.id
        assert restored.content == fact.content
        assert restored.category == fact.category
        assert restored.spec_name == fact.spec_name
        assert restored.keywords == fact.keywords
        assert restored.confidence == fact.confidence
        assert restored.created_at == fact.created_at
        assert restored.supersedes == fact.supersedes
