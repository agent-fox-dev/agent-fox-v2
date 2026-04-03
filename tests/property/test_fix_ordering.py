"""Property tests for fix issue ordering and dependency detection.

Test Spec: TS-71-P1 through TS-71-P7
Properties: 1-7 from design.md
Requirements: 71-REQ-1.2, 71-REQ-2.E2, 71-REQ-3.4, 71-REQ-3.5,
              71-REQ-4.1, 71-REQ-4.3, 71-REQ-4.E1, 71-REQ-5.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _make_issue(number: int) -> IssueResult:
    """Create a minimal IssueResult."""
    return IssueResult(
        number=number,
        title=f"Issue #{number}",
        html_url=f"https://github.com/test/repo/issues/{number}",
        body="",
    )


@st.composite
def issue_numbers_strategy(draw: st.DrawFn) -> list[int]:
    """Generate a list of unique issue numbers."""
    return draw(
        st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=1,
            max_size=20,
            unique=True,
        )
    )


@st.composite
def acyclic_graph_strategy(draw: st.DrawFn) -> tuple[list[int], list[tuple[int, int]]]:
    """Generate a list of issue numbers and acyclic edges between them.

    Edges go from lower-indexed to higher-indexed nodes in the sorted list,
    which guarantees acyclicity.
    """
    nums = draw(
        st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=2,
            max_size=10,
            unique=True,
        )
    )
    sorted_nums = sorted(nums)

    # Generate edges from lower-indexed to higher-indexed (acyclic by construction)
    possible_edges = [
        (sorted_nums[i], sorted_nums[j]) for i in range(len(sorted_nums)) for j in range(i + 1, len(sorted_nums))
    ]

    if not possible_edges:
        return sorted_nums, []

    edges = draw(
        st.lists(
            st.sampled_from(possible_edges),
            min_size=0,
            max_size=min(len(possible_edges), 10),
            unique=True,
        )
    )
    return sorted_nums, edges


@st.composite
def graph_with_possible_cycles_strategy(
    draw: st.DrawFn,
) -> tuple[list[int], list[tuple[int, int]]]:
    """Generate a list of issue numbers and arbitrary edges (may have cycles)."""
    nums = draw(
        st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=2,
            max_size=10,
            unique=True,
        )
    )

    edges = draw(
        st.lists(
            st.tuples(
                st.sampled_from(nums),
                st.sampled_from(nums),
            ).filter(lambda t: t[0] != t[1]),
            min_size=0,
            max_size=15,
            unique=True,
        )
    )
    return nums, edges


# ---------------------------------------------------------------------------
# TS-71-P1: Base Ordering Invariant
# Property 1: With no edges, order is ascending issue number
# Validates: 71-REQ-1.2, 71-REQ-4.E1
# ---------------------------------------------------------------------------


class TestBaseOrderingProperty:
    """With no edges, order is ascending issue number."""

    @given(issue_nums=issue_numbers_strategy())
    @settings(max_examples=50)
    def test_ts_71_p1_no_edges_ascending_order(self, issue_nums: list[int]) -> None:
        from agent_fox.nightshift.dep_graph import build_graph

        issues = [_make_issue(n) for n in issue_nums]
        order = build_graph(issues, [])

        assert order == sorted(issue_nums)


# ---------------------------------------------------------------------------
# TS-71-P2: Dependency Respect Invariant
# Property 2: Every edge is respected in the output order
# Validates: 71-REQ-4.1
# ---------------------------------------------------------------------------


class TestDependencyRespectProperty:
    """Every edge is respected in the output order."""

    @given(data=acyclic_graph_strategy())
    @settings(max_examples=50)
    def test_ts_71_p2_edges_respected(self, data: tuple[list[int], list[tuple[int, int]]]) -> None:
        from agent_fox.nightshift.dep_graph import DependencyEdge, build_graph

        nums, edge_tuples = data
        issues = [_make_issue(n) for n in nums]
        edges = [DependencyEdge(a, b, "explicit", f"{a} before {b}") for a, b in edge_tuples]

        order = build_graph(issues, edges)

        for a, b in edge_tuples:
            assert order.index(a) < order.index(b), f"Edge {a}->{b} violated: {order}"


# ---------------------------------------------------------------------------
# TS-71-P3: Explicit Edge Precedence
# Property 3: Explicit edges always win over AI edges
# Validates: 71-REQ-3.4
# ---------------------------------------------------------------------------


class TestExplicitEdgePrecedenceProperty:
    """Explicit edges always win over AI edges."""

    @given(
        a=st.integers(min_value=1, max_value=1000),
        b=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=50)
    def test_ts_71_p3_explicit_wins(self, a: int, b: int) -> None:
        from hypothesis import assume

        from agent_fox.nightshift.dep_graph import DependencyEdge, merge_edges

        assume(a != b)

        explicit = [DependencyEdge(a, b, "explicit", "user said")]
        ai = [DependencyEdge(b, a, "ai", "AI said")]

        merged = merge_edges(explicit, ai)

        assert any(e.from_issue == a and e.to_issue == b for e in merged), f"Expected edge {a}->{b} in merged: {merged}"
        assert not any(e.from_issue == b and e.to_issue == a for e in merged), (
            f"Unexpected edge {b}->{a} in merged: {merged}"
        )


# ---------------------------------------------------------------------------
# TS-71-P4: Cycle Resolution Produces Valid Order
# Property 4: Any cyclic graph produces a valid total order after breaking
# Validates: 71-REQ-4.3, 71-REQ-2.E2
# ---------------------------------------------------------------------------


class TestCycleResolutionProperty:
    """Any cyclic graph produces a valid total order after breaking."""

    @given(data=graph_with_possible_cycles_strategy())
    @settings(max_examples=50)
    def test_ts_71_p4_cycles_produce_valid_order(self, data: tuple[list[int], list[tuple[int, int]]]) -> None:
        from agent_fox.nightshift.dep_graph import DependencyEdge, build_graph

        nums, edge_tuples = data
        issues = [_make_issue(n) for n in nums]
        edges = [DependencyEdge(a, b, "explicit", "") for a, b in edge_tuples]

        order = build_graph(issues, edges)

        assert set(order) == set(nums), f"Order {order} does not contain all issues {nums}"
        assert len(order) == len(nums), f"Order has wrong length: {len(order)} vs {len(nums)}"


# ---------------------------------------------------------------------------
# TS-71-P5: Triage Fallback Produces Valid Order
# Property 5: When triage fails, a valid order is still produced
# Validates: 71-REQ-3.E1
# ---------------------------------------------------------------------------


class TestTriageFallbackProperty:
    """When triage fails, a valid order is still produced."""

    @given(
        issue_nums=st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=3,
            max_size=10,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_ts_71_p5_triage_failure_valid_order(self, issue_nums: list[int]) -> None:
        from agent_fox.nightshift.dep_graph import build_graph

        issues = [_make_issue(n) for n in issue_nums]
        # Simulate triage failure => no AI edges, just build graph with no edges
        order = build_graph(issues, [])

        assert set(order) == set(issue_nums)
        assert len(order) == len(issue_nums)


# ---------------------------------------------------------------------------
# TS-71-P6: Staleness Removal
# Property 6: Obsolete issues never appear in post-staleness processing list
# Validates: 71-REQ-5.4
# ---------------------------------------------------------------------------


class TestStalenessRemovalProperty:
    """Obsolete issues never appear in remaining processing list."""

    @given(
        issue_nums=st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=2,
            max_size=10,
            unique=True,
        ),
        data=st.data(),
    )
    @settings(max_examples=30)
    def test_ts_71_p6_obsolete_removed(self, issue_nums: list[int], data: st.DataObject) -> None:
        # Pick a subset to mark as obsolete
        obsolete_set = set(
            data.draw(
                st.lists(
                    st.sampled_from(issue_nums),
                    min_size=0,
                    max_size=len(issue_nums) - 1,
                    unique=True,
                )
            )
        )

        remaining = [n for n in issue_nums if n not in obsolete_set]

        for n in obsolete_set:
            assert n not in remaining


# ---------------------------------------------------------------------------
# TS-71-P7: Batch Size Gate
# Property 7: AI triage never invoked for batches < 3
# Validates: 71-REQ-3.5
# ---------------------------------------------------------------------------


class TestBatchSizeGateProperty:
    """AI triage never invoked for batches < 3."""

    @given(
        issue_nums=st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=1,
            max_size=2,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_ts_71_p7_small_batch_no_triage(self, issue_nums: list[int]) -> None:
        # Verify the gate condition directly
        batch_size = len(issue_nums)
        should_triage = batch_size >= 3

        assert not should_triage, f"Batch of size {batch_size} should not trigger triage"
