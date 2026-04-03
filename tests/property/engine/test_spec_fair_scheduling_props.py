"""Property tests for spec-fair round-robin task scheduling.

Test Spec: TS-69-P1 through TS-69-P6
Properties: Fairness Guarantee, Single-Spec Identity, Duration Within-Spec,
            Completeness, Spec Order Consistency, Empty Stability
Requirements: 69-REQ-1.1, 69-REQ-1.2, 69-REQ-1.3, 69-REQ-2.1, 69-REQ-2.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.graph_sync import _interleave_by_spec, _spec_name

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

SPEC_NAMES = [
    "05_alpha",
    "10_beta",
    "20_gamma",
    "30_delta",
    "40_epsilon",
    "50_zeta",
    "60_eta",
    "70_theta",
    "80_iota",
    "90_kappa",
]

NON_NUMERIC_SPEC_NAMES = ["no_prefix", "also_no_prefix", "another_one"]


@st.composite
def spec_node_id(draw: st.DrawFn, spec_name: str | None = None) -> str:
    """Generate a single node ID with an optional fixed spec name."""
    if spec_name is None:
        spec = draw(st.sampled_from(SPEC_NAMES))
    else:
        spec = spec_name
    task_num = draw(st.integers(min_value=0, max_value=99))
    return f"{spec}:{task_num}"


@st.composite
def single_spec_list(draw: st.DrawFn) -> list[str]:
    """Generate a list of 1-20 node IDs all from the same spec."""
    spec = draw(st.sampled_from(SPEC_NAMES))
    size = draw(st.integers(min_value=1, max_value=20))
    # Use unique task numbers to avoid duplicates
    task_nums = draw(
        st.lists(
            st.integers(min_value=0, max_value=199),
            min_size=size,
            max_size=size,
            unique=True,
        )
    )
    return [f"{spec}:{n}" for n in task_nums]


@st.composite
def multi_spec_list(
    draw: st.DrawFn,
    min_specs: int = 2,
    max_specs: int = 10,
) -> list[str]:
    """Generate a list of node IDs across 2-10 different specs."""
    max_num_specs = min(max_specs, len(SPEC_NAMES))
    num_specs = draw(st.integers(min_value=min_specs, max_value=max_num_specs))
    chosen_specs = draw(
        st.lists(
            st.sampled_from(SPEC_NAMES),
            min_size=num_specs,
            max_size=num_specs,
            unique=True,
        )
    )
    tasks: list[str] = []
    for spec in chosen_specs:
        count = draw(st.integers(min_value=1, max_value=5))
        task_nums = draw(
            st.lists(
                st.integers(min_value=0, max_value=99),
                min_size=count,
                max_size=count,
                unique=True,
            )
        )
        for n in task_nums:
            tasks.append(f"{spec}:{n}")
    return tasks


@st.composite
def spec_list_with_hints(
    draw: st.DrawFn,
) -> tuple[list[str], dict[str, int]]:
    """Generate a list of node IDs with duration hints across 1-5 specs."""
    num_specs = draw(st.integers(min_value=1, max_value=5))
    chosen_specs = draw(
        st.lists(
            st.sampled_from(SPEC_NAMES),
            min_size=num_specs,
            max_size=num_specs,
            unique=True,
        )
    )
    tasks: list[str] = []
    hints: dict[str, int] = {}
    for spec in chosen_specs:
        count = draw(st.integers(min_value=1, max_value=5))
        task_nums = draw(
            st.lists(
                st.integers(min_value=0, max_value=99),
                min_size=count,
                max_size=count,
                unique=True,
            )
        )
        for n in task_nums:
            node_id = f"{spec}:{n}"
            tasks.append(node_id)
            # Randomly provide hints (at least for some tasks)
            if draw(st.booleans()):
                hints[node_id] = draw(st.integers(min_value=1, max_value=100000))
    return tasks, hints


def _unique_specs(node_ids: list[str]) -> list[str]:
    """Return unique spec names preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for nid in node_ids:
        s = _spec_name(nid)
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _spec_number(spec_name: str) -> tuple[int | float, str]:
    """Extract numeric prefix for sorting (mirrors implementation)."""
    parts = spec_name.split("_", 1)
    try:
        return (int(parts[0]), spec_name)
    except (ValueError, IndexError):
        return (float("inf"), spec_name)


# ---------------------------------------------------------------------------
# TS-69-P1: Fairness Guarantee
# ---------------------------------------------------------------------------


class TestFairnessGuarantee:
    """Property test: every spec's first task appears in the first N positions.

    Test Spec: TS-69-P1
    Properties: Property 1 from design.md
    Requirements: 69-REQ-1.1, 69-REQ-1.2
    """

    @given(ready=multi_spec_list(min_specs=2, max_specs=10))
    @settings(max_examples=200)
    def test_fairness_guarantee(self, ready: list[str]) -> None:
        """Every spec's first task must appear within the first N positions."""
        result = _interleave_by_spec(ready)
        specs = list({_spec_name(nid) for nid in ready})
        n = len(specs)

        for spec in specs:
            first_index = next(i for i, nid in enumerate(result) if _spec_name(nid) == spec)
            assert first_index < n, (
                f"Spec '{spec}' first appears at index {first_index}, "
                f"but should appear within first {n} positions. "
                f"Result: {result}"
            )


# ---------------------------------------------------------------------------
# TS-69-P2: Single-Spec Identity
# ---------------------------------------------------------------------------


class TestSingleSpecIdentity:
    """Property test: single-spec result equals sorted(input).

    Test Spec: TS-69-P2
    Properties: Property 2 from design.md
    Requirements: 69-REQ-1.3, 69-REQ-1.E1
    """

    @given(ready=single_spec_list())
    @settings(max_examples=200)
    def test_single_spec_identity(self, ready: list[str]) -> None:
        """When all tasks belong to one spec, result equals sorted(input)."""
        result = _interleave_by_spec(ready)
        assert result == sorted(ready), f"Single-spec result {result} != sorted input {sorted(ready)}"


# ---------------------------------------------------------------------------
# TS-69-P3: Duration Preserves Within-Spec Order
# ---------------------------------------------------------------------------


class TestDurationPreservesWithinSpecOrder:
    """Property test: within each spec, tasks are in duration-descending order.

    Test Spec: TS-69-P3
    Properties: Property 3 from design.md
    Requirements: 69-REQ-2.1, 69-REQ-2.2
    """

    @given(spec_list_with_hints())
    @settings(max_examples=200)
    def test_duration_preserves_within_spec_order(self, args: tuple[list[str], dict[str, int]]) -> None:
        """Within each spec, tasks are ordered by duration descending in result."""
        ready, hints = args
        if not ready:
            return

        result = _interleave_by_spec(ready, duration_hints=hints if hints else None)
        specs = list({_spec_name(nid) for nid in ready})

        for spec in specs:
            spec_tasks_in_result = [nid for nid in result if _spec_name(nid) == spec]
            # Hinted tasks should come before unhinted, hinted in descending order
            hinted = [(nid, hints[nid]) for nid in spec_tasks_in_result if nid in hints]
            durations = [d for _, d in hinted]
            assert durations == sorted(durations, reverse=True), (
                f"Spec '{spec}' hinted tasks not in descending duration order: "
                f"{hinted} in result {spec_tasks_in_result}"
            )

            # All hinted tasks should appear before unhinted tasks
            unhinted_indices = [i for i, nid in enumerate(spec_tasks_in_result) if nid not in hints]
            hinted_indices = [i for i, nid in enumerate(spec_tasks_in_result) if nid in hints]
            if hinted_indices and unhinted_indices:
                assert max(hinted_indices) < min(unhinted_indices), (
                    f"Spec '{spec}': hinted tasks don't all precede unhinted tasks. "
                    f"Hinted indices: {hinted_indices}, "
                    f"unhinted indices: {unhinted_indices}"
                )


# ---------------------------------------------------------------------------
# TS-69-P4: Completeness
# ---------------------------------------------------------------------------


class TestCompleteness:
    """Property test: interleaved result is a permutation of the input.

    Test Spec: TS-69-P4
    Properties: Property 4 from design.md
    Requirements: 69-REQ-1.1
    """

    @given(
        ready=st.lists(
            st.one_of(
                st.builds(
                    lambda s, n: f"{s}:{n}",
                    st.sampled_from(SPEC_NAMES),
                    st.integers(0, 99),
                ),
            ),
            min_size=0,
            max_size=50,
        )
    )
    @settings(max_examples=200)
    def test_completeness(self, ready: list[str]) -> None:
        """The interleaved result contains exactly the same elements as input."""
        result = _interleave_by_spec(ready)
        assert sorted(result) == sorted(ready), f"Result {result} is not a permutation of input {ready}"


# ---------------------------------------------------------------------------
# TS-69-P5: Spec Order Consistency
# ---------------------------------------------------------------------------


class TestSpecOrderConsistency:
    """Property test: lower-numbered specs appear before higher-numbered specs.

    Test Spec: TS-69-P5
    Properties: Property 5 from design.md
    Requirements: 69-REQ-1.2, 69-REQ-1.4
    """

    @given(ready=multi_spec_list(min_specs=2, max_specs=10))
    @settings(max_examples=200)
    def test_spec_order_consistency(self, ready: list[str]) -> None:
        """For specs A < B by number, A's first task appears before B's first task."""
        result = _interleave_by_spec(ready)
        specs = list({_spec_name(nid) for nid in ready})
        specs_sorted = sorted(specs, key=_spec_number)

        first_indices: dict[str, int] = {}
        for spec in specs_sorted:
            first_indices[spec] = next(i for i, nid in enumerate(result) if _spec_name(nid) == spec)

        for i in range(len(specs_sorted)):
            for j in range(i + 1, len(specs_sorted)):
                spec_a = specs_sorted[i]
                spec_b = specs_sorted[j]
                assert first_indices[spec_a] < first_indices[spec_b], (
                    f"Spec '{spec_a}' (number {_spec_number(spec_a)}) first appears "
                    f"at index {first_indices[spec_a]}, but spec '{spec_b}' "
                    f"(number {_spec_number(spec_b)}) first appears at "
                    f"index {first_indices[spec_b]}. Result: {result}"
                )


# ---------------------------------------------------------------------------
# TS-69-P6: Empty Stability
# ---------------------------------------------------------------------------


class TestEmptyStability:
    """Property test: empty input always produces empty output.

    Test Spec: TS-69-P6
    Properties: Property 6 from design.md
    Requirements: 69-REQ-1.E2
    """

    def test_empty_stability(self) -> None:
        """Empty input always produces empty output."""
        assert _interleave_by_spec([]) == []
