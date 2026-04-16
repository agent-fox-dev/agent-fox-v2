"""Property tests for the adaptive retrieval subsystem.

Validates RRF invariants, intent profile defaults, context assembly properties,
and signal degradation behaviour using Hypothesis.

Test Spec: TS-104-P1 through TS-104-P7
Requirements: 104-REQ-2.1, 104-REQ-2.3, 104-REQ-3.E1, 104-REQ-4.1, 104-REQ-4.3
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# These imports will fail with ModuleNotFoundError until group 2 creates the module.
from agent_fox.knowledge.retrieval import (
    IntentProfile,
    RetrievalConfig,
    ScoredFact,
    assemble_ranked_context,
    derive_intent_profile,
    weighted_rrf_fusion,
)
from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

KNOWN_ARCHETYPES = ["coder", "auditor", "reviewer", "verifier"]

# A strategy for a single ScoredFact with a fixed or random fact_id
_fact_id_st = st.uuids().map(str)
_content_st = st.text(min_size=1, max_size=200, alphabet=st.characters(exclude_categories=("Cs",)))
_spec_name_st = st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_0123456789")
_confidence_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_score_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_weight_st = st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)
_k_st = st.integers(min_value=1, max_value=200)
_rank_st = st.integers(min_value=1, max_value=100)


def _scored_fact_st(fact_id: str | None = None) -> st.SearchStrategy[ScoredFact]:
    """Strategy for a single ScoredFact, optionally with a fixed fact_id."""
    id_st = st.just(fact_id) if fact_id is not None else _fact_id_st
    return st.builds(
        ScoredFact,
        fact_id=id_st,
        content=_content_st,
        spec_name=_spec_name_st,
        confidence=_confidence_st,
        created_at=st.just("2026-01-01T00:00:00+00:00"),
        category=st.just("pattern"),
        score=_score_st,
    )


@st.composite
def _signal_lists_st(
    draw: st.DrawFn,
    num_signals: int = 4,
    max_facts_per_signal: int = 20,
    allow_empty: bool = True,
) -> dict[str, list[ScoredFact]]:
    """Strategy: a dict of signal_name → list[ScoredFact], may overlap."""
    signal_names = ["keyword", "vector", "entity", "causal"][:num_signals]
    # Pick a pool of fact_ids that may appear in multiple signals
    pool_size = draw(st.integers(min_value=1, max_value=max_facts_per_signal))
    fact_ids = [str(uuid.UUID(int=i)) for i in range(pool_size)]

    result: dict[str, list[ScoredFact]] = {}
    for name in signal_names:
        if allow_empty and draw(st.booleans()):
            result[name] = []
            continue
        n = draw(st.integers(min_value=1, max_value=min(pool_size, max_facts_per_signal)))
        chosen_ids = draw(st.lists(st.sampled_from(fact_ids), min_size=n, max_size=n, unique=True))
        facts = [
            ScoredFact(
                fact_id=fid,
                content=draw(_content_st),
                spec_name=draw(_spec_name_st),
                confidence=draw(_confidence_st),
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
            for fid in chosen_ids
        ]
        result[name] = facts

    return result


@st.composite
def _profile_st(draw: st.DrawFn) -> IntentProfile:
    """Strategy: an arbitrary IntentProfile with positive weights."""
    return IntentProfile(
        keyword_weight=draw(_weight_st),
        vector_weight=draw(_weight_st),
        entity_weight=draw(_weight_st),
        causal_weight=draw(_weight_st),
    )


# ---------------------------------------------------------------------------
# TS-104-P1: RRF score monotonicity
# ---------------------------------------------------------------------------


class TestRrfMonotonicity:
    """TS-104-P1: Adding a fact to more signals can only increase its score.

    Property 1 from design.md
    Requirements: 104-REQ-2.1, 104-REQ-2.E1
    """

    @given(
        profile=_profile_st(),
        k=_k_st,
        rank_in_s1=_rank_st,
        rank_in_s2=_rank_st,
    )
    @settings(max_examples=100, deadline=None)
    def test_score_increases_with_more_signals(
        self,
        profile: IntentProfile,
        k: int,
        rank_in_s1: int,
        rank_in_s2: int,
    ) -> None:
        """Fact d gets higher score in S2 (has extra signal) than in S1."""
        fact_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        filler_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        # Build S1: fact_d appears in keyword signal only at rank_in_s1
        # (need rank_in_s1 - 1 filler facts before it)
        keyword_list_s1 = [
            ScoredFact(
                fact_id=filler_id + str(i),
                content="filler",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
            for i in range(rank_in_s1 - 1)
        ] + [
            ScoredFact(
                fact_id=fact_id,
                content="the fact",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
        ]
        s1 = {"keyword": keyword_list_s1, "vector": [], "entity": [], "causal": []}

        # Build S2: same as S1 but also in entity signal at rank_in_s2
        entity_list = [
            ScoredFact(
                fact_id=filler_id + str(i + 100),
                content="filler2",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
            for i in range(rank_in_s2 - 1)
        ] + [
            ScoredFact(
                fact_id=fact_id,
                content="the fact",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
        ]
        s2 = {"keyword": keyword_list_s1, "vector": [], "entity": entity_list, "causal": []}

        result_s1 = weighted_rrf_fusion(s1, profile, k=k)
        result_s2 = weighted_rrf_fusion(s2, profile, k=k)

        score_s1 = next(r.score for r in result_s1 if r.fact_id == fact_id)
        score_s2 = next(r.score for r in result_s2 if r.fact_id == fact_id)

        assert score_s2 >= score_s1, (
            f"Score must not decrease when fact appears in more signals: s1={score_s1:.6f}, s2={score_s2:.6f}"
        )


# ---------------------------------------------------------------------------
# TS-104-P2: RRF deduplication invariant
# ---------------------------------------------------------------------------


class TestRrfDedupInvariant:
    """TS-104-P2: Every fact ID appears at most once in fusion output.

    Property 2 from design.md
    Requirements: 104-REQ-2.3
    """

    @given(signal_lists=_signal_lists_st(), profile=_profile_st(), k=_k_st)
    @settings(max_examples=100, deadline=None)
    def test_no_duplicate_fact_ids(
        self,
        signal_lists: dict[str, list[ScoredFact]],
        profile: IntentProfile,
        k: int,
    ) -> None:
        """Fusion output has no duplicate fact IDs."""
        result = weighted_rrf_fusion(signal_lists, profile, k=k)
        ids = [r.fact_id for r in result]
        assert len(ids) == len(set(ids)), f"Duplicate fact IDs found in fusion output: {ids}"

    @given(signal_lists=_signal_lists_st(), profile=_profile_st(), k=_k_st)
    @settings(max_examples=100, deadline=None)
    def test_output_count_equals_unique_input_count(
        self,
        signal_lists: dict[str, list[ScoredFact]],
        profile: IntentProfile,
        k: int,
    ) -> None:
        """Output has exactly as many entries as unique fact IDs across all signals."""
        unique_ids = {f.fact_id for lst in signal_lists.values() for f in lst}
        result = weighted_rrf_fusion(signal_lists, profile, k=k)
        assert len(result) == len(unique_ids), f"Expected {len(unique_ids)} facts, got {len(result)}"


# ---------------------------------------------------------------------------
# TS-104-P3: Weight application correctness
# ---------------------------------------------------------------------------


class TestWeightApplicationCorrectness:
    """TS-104-P3: Single-signal fact score equals weight / (k + rank).

    Property 3 from design.md
    Requirements: 104-REQ-2.1, 104-REQ-3.2
    """

    @given(
        weight=_weight_st,
        rank=_rank_st,
        k=_k_st,
        signal_name=st.sampled_from(["keyword", "vector", "entity", "causal"]),
    )
    @settings(max_examples=200, deadline=None)
    def test_single_signal_score_equals_weight_over_k_plus_rank(
        self,
        weight: float,
        rank: int,
        k: int,
        signal_name: str,
    ) -> None:
        """score = weight / (k + rank) for a fact appearing in exactly one signal."""
        fact_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        filler_base = "dddddddd-dddd-dddd-dddd-"

        # Build the signal list: (rank - 1) fillers, then the target fact
        facts = [
            ScoredFact(
                fact_id=filler_base + str(i).zfill(12),
                content="filler",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
            for i in range(rank - 1)
        ] + [
            ScoredFact(
                fact_id=fact_id,
                content="target",
                spec_name="s",
                confidence=0.5,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=0.0,
            )
        ]

        # Build profile: only the target signal has the specified weight
        weight_kwargs = {
            "keyword_weight": 1.0,
            "vector_weight": 1.0,
            "entity_weight": 1.0,
            "causal_weight": 1.0,
        }
        weight_kwargs[f"{signal_name}_weight"] = weight
        profile = IntentProfile(**weight_kwargs)

        signal_lists: dict[str, list[ScoredFact]] = {
            "keyword": [],
            "vector": [],
            "entity": [],
            "causal": [],
        }
        signal_lists[signal_name] = facts

        result = weighted_rrf_fusion(signal_lists, profile, k=k)
        target = next(r for r in result if r.fact_id == fact_id)

        expected = weight / (k + rank)
        assert abs(target.score - expected) < 1e-10, (
            f"Expected score {expected}, got {target.score} (weight={weight}, k={k}, rank={rank})"
        )


# ---------------------------------------------------------------------------
# TS-104-P4: Graceful signal degradation
# ---------------------------------------------------------------------------


class TestGracefulSignalDegradation:
    """TS-104-P4: Fusion works with any combination of empty/non-empty signals.

    Property 4 from design.md
    Requirements: 104-REQ-1.E1, 104-REQ-1.E2
    """

    @given(signal_lists=_signal_lists_st(allow_empty=True), profile=_profile_st(), k=_k_st)
    @settings(max_examples=100, deadline=None)
    def test_no_exception_with_any_combination(
        self,
        signal_lists: dict[str, list[ScoredFact]],
        profile: IntentProfile,
        k: int,
    ) -> None:
        """weighted_rrf_fusion never raises regardless of empty signals."""
        # Must not raise
        result = weighted_rrf_fusion(signal_lists, profile, k=k)
        assert isinstance(result, list)

    @given(signal_lists=_signal_lists_st(allow_empty=True), profile=_profile_st(), k=_k_st)
    @settings(max_examples=100, deadline=None)
    def test_output_count_correct_with_empties(
        self,
        signal_lists: dict[str, list[ScoredFact]],
        profile: IntentProfile,
        k: int,
    ) -> None:
        """Output count equals unique IDs across all non-empty signals."""
        unique_ids = {f.fact_id for lst in signal_lists.values() for f in lst}
        result = weighted_rrf_fusion(signal_lists, profile, k=k)
        assert len(result) == len(unique_ids)


# ---------------------------------------------------------------------------
# TS-104-P5: Causal ordering consistency
# ---------------------------------------------------------------------------


class TestCausalOrderingConsistency:
    """TS-104-P5: Causal predecessors always appear before effects in output.

    Property 5 from design.md
    Requirements: 104-REQ-4.1
    """

    @given(
        scores=st.lists(
            st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=6,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_causal_predecessor_before_effect_in_output(self, scores: list[float]) -> None:
        """For every edge A→B in causal graph, A appears before B in context."""
        assume(len(scores) >= 2)

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        n = len(scores)
        # Build a chain: f0 → f1 → f2 → ... → f_{n-1}
        fact_ids = [f"{'a' * 8}-{'a' * 4}-{'a' * 4}-{'a' * 4}-{str(i).zfill(12)}" for i in range(n)]

        try:
            # Insert facts
            for i, (fid, score) in enumerate(zip(fact_ids, scores)):
                conn.execute(
                    """
                    INSERT INTO memory_facts
                        (id, content, spec_name, category, confidence, created_at, keywords)
                    VALUES (?, ?, 'myspec', 'pattern', 0.9, CURRENT_TIMESTAMP, [])
                    """,
                    [fid, f"fact_{i} unique content marker {fid[:8]}"],
                )

            # Insert causal chain: f0→f1, f1→f2, ..., f_{n-2}→f_{n-1}
            for i in range(n - 1):
                conn.execute(
                    "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
                    [fact_ids[i], fact_ids[i + 1]],
                )

            # Build anchors with potentially reversed score order
            anchors = [
                ScoredFact(
                    fact_id=fact_ids[i],
                    content=f"fact_{i} unique content marker {fact_ids[i][:8]}",
                    spec_name="myspec",
                    confidence=0.9,
                    created_at="2026-01-01T00:00:00+00:00",
                    category="pattern",
                    score=scores[i],
                )
                for i in range(n)
            ]

            config = RetrievalConfig(token_budget=100_000)
            context = assemble_ranked_context(anchors, conn, config)

            # Verify causal ordering: f_i should appear before f_{i+1}
            for i in range(n - 1):
                marker_i = f"fact_{i} unique content marker {fact_ids[i][:8]}"
                marker_j = f"fact_{i + 1} unique content marker {fact_ids[i + 1][:8]}"
                if marker_i in context and marker_j in context:
                    pos_i = context.index(marker_i)
                    pos_j = context.index(marker_j)
                    assert pos_i < pos_j, f"Causal predecessor fact_{i} should appear before fact_{i + 1}"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-P6: Token budget compliance
# ---------------------------------------------------------------------------


class TestTokenBudgetCompliance:
    """TS-104-P6: Output never exceeds configured token budget.

    Property 6 from design.md
    Requirements: 104-REQ-4.3
    """

    @given(
        n_facts=st.integers(min_value=1, max_value=30),
        content_size=st.integers(min_value=10, max_value=500),
        budget=st.integers(min_value=100, max_value=10_000),
    )
    @settings(max_examples=50, deadline=None)
    def test_output_within_budget(self, n_facts: int, content_size: int, budget: int) -> None:
        """assemble_ranked_context output length ≤ token_budget."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        config = RetrievalConfig(token_budget=budget)

        anchors = [
            ScoredFact(
                fact_id=str(uuid.UUID(int=i)),
                content="X" * content_size,
                spec_name="myspec",
                confidence=0.9,
                created_at="2026-01-01T00:00:00+00:00",
                category="pattern",
                score=1.0 / (i + 1),
            )
            for i in range(n_facts)
        ]

        try:
            context = assemble_ranked_context(anchors, conn, config)
            assert len(context) <= budget, f"Output length {len(context)} exceeds budget {budget}"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-P7: Default fallback profile
# ---------------------------------------------------------------------------


class TestDefaultFallbackProfile:
    """TS-104-P7: Unknown archetypes produce all-1.0 profiles.

    Property 7 from design.md
    Requirements: 104-REQ-3.E1
    """

    @given(
        archetype=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        node_status=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    )
    @settings(max_examples=100, deadline=None)
    def test_unknown_archetype_returns_balanced_profile(self, archetype: str, node_status: str) -> None:
        """Unknown archetypes return IntentProfile with all weights 1.0."""
        if archetype in KNOWN_ARCHETYPES:
            return  # skip known archetypes
        profile = derive_intent_profile(archetype, node_status)
        assert profile == IntentProfile(1.0, 1.0, 1.0, 1.0), (
            f"Unknown archetype '{archetype}' should return balanced default profile, got {profile}"
        )
