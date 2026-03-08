"""Property tests for compaction: idempotency, dedup determinism, supersession.

Test Spec: TS-05-P2 (idempotency), TS-05-P4 (dedup determinism),
           TS-05-P6 (supersession chains)
Properties: Property 2, Property 5, Property 6 from design.md
Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.E2
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.memory.compaction import (
    _content_hash,
    _deduplicate_by_content,
    _resolve_supersession,
    compact,
)
from agent_fox.memory.memory import write_facts
from agent_fox.memory.types import Category, Fact

# -- Hypothesis strategies ---------------------------------------------------

CATEGORIES = [c.value for c in Category]


@st.composite
def fact_strategy(
    draw: st.DrawFn,
    *,
    content: str | None = None,
    fact_id: str | None = None,
    supersedes: str | None = None,
) -> Fact:
    """Generate a random valid Fact with optional overrides."""
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content or draw(st.text(min_size=1, max_size=50)),
        category=draw(st.sampled_from(CATEGORIES)),
        spec_name=draw(st.text(min_size=1, max_size=20)),
        keywords=draw(
            st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5)
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


@st.composite
def facts_with_duplicates(draw: st.DrawFn) -> list[Fact]:
    """Generate a list of facts where some may share content."""
    # Generate 2-5 unique content strings, then create facts that may reuse them
    unique_contents = draw(
        st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)
    )
    facts: list[Fact] = []
    n = draw(st.integers(min_value=1, max_value=20))
    for _ in range(n):
        content = draw(st.sampled_from(unique_contents))
        fact = draw(fact_strategy(content=content))
        facts.append(fact)
    return facts


@st.composite
def supersession_chain(draw: st.DrawFn) -> list[Fact]:
    """Generate a chain of facts where each supersedes the previous."""
    chain_length = draw(st.integers(min_value=2, max_value=10))
    ids = [str(uuid.uuid4()) for _ in range(chain_length)]

    facts: list[Fact] = []
    for i, fid in enumerate(ids):
        supersedes = ids[i - 1] if i > 0 else None
        fact = draw(fact_strategy(fact_id=fid, supersedes=supersedes))
        facts.append(fact)
    return facts


# -- Property tests ----------------------------------------------------------


class TestCompactionIdempotency:
    """TS-05-P2: Compaction idempotency.

    Running compaction twice produces the same result as running it once.

    Property 2 from design.md.
    """

    @given(facts=st.lists(fact_strategy(), min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_double_compact_same_as_single(
        self,
        facts: list[Fact],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """compact() is idempotent: second run changes nothing."""
        tmp_dir = tmp_path_factory.mktemp("compact")
        path = tmp_dir / "memory.jsonl"

        write_facts(facts, path)
        compact(path)
        content_after_first = path.read_text()

        compact(path)
        content_after_second = path.read_text()

        assert content_after_first == content_after_second


class TestDeduplicationDeterminism:
    """TS-05-P4: Deduplication determinism.

    Deduplication always keeps the earliest instance regardless of input order.

    Property 5 from design.md.
    """

    @given(facts=facts_with_duplicates())
    @settings(max_examples=100)
    def test_keeps_earliest_for_each_hash(self, facts: list[Fact]) -> None:
        """The surviving fact for each content hash has the minimum created_at."""
        if not facts:
            return

        result = _deduplicate_by_content(facts)

        for r in result:
            h = _content_hash(r.content)
            all_with_hash = [f for f in facts if _content_hash(f.content) == h]
            earliest = min(all_with_hash, key=lambda f: f.created_at)
            assert r.created_at == earliest.created_at


class TestSupersessionChainResolution:
    """TS-05-P6: Supersession chain resolution.

    In any supersession chain, only the terminal fact survives.

    Property 6 from design.md.
    """

    @given(chain=supersession_chain())
    @settings(max_examples=100)
    def test_only_terminal_survives(self, chain: list[Fact]) -> None:
        """After resolve_supersession, only the last fact in a chain remains."""
        result = _resolve_supersession(chain)

        # The terminal fact (last in chain) should survive
        terminal = chain[-1]
        assert len(result) == 1
        assert result[0].id == terminal.id
