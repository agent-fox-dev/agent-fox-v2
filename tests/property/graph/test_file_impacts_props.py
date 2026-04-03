"""Property tests for file impact detection.

Test Spec: TS-43-P3 (conflict symmetry), TS-43-P4 (dispatch safety)
Properties: Property 4 and Property 5 from design.md
Validates: 43-REQ-3.2, 43-REQ-3.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.graph.file_impacts import (
    FileImpact,
    detect_conflicts,
    filter_conflicts_from_dispatch,
)

# Strategy: generate file impact lists
file_path_strategy = st.sampled_from(
    [
        "a.py",
        "b.py",
        "c.py",
        "d.py",
        "e.py",
        "x/f.py",
        "x/g.py",
        "y/h.py",
    ]
)

node_id_strategy = st.text(alphabet="abcdefghij", min_size=1, max_size=3)


@st.composite
def file_impact_strategy(
    draw: st.DrawFn,
) -> list[FileImpact]:
    """Generate a list of FileImpact objects with unique node IDs."""
    n = draw(st.integers(min_value=0, max_value=6))
    node_ids = [f"node_{i}" for i in range(n)]
    impacts = []
    for nid in node_ids:
        files = draw(st.frozensets(file_path_strategy, max_size=4))
        impacts.append(FileImpact(nid, set(files)))
    return impacts


@st.composite
def dispatch_strategy(
    draw: st.DrawFn,
) -> tuple[list[str], list[FileImpact]]:
    """Generate ready list and matching file impacts."""
    impacts = draw(file_impact_strategy())
    node_ids = [imp.node_id for imp in impacts]
    # Ready list is some subset of node_ids, preserving order
    if node_ids:
        ready = draw(
            st.lists(
                st.sampled_from(node_ids),
                min_size=1,
                max_size=len(node_ids),
                unique=True,
            )
        )
    else:
        ready = []
    return ready, impacts


class TestConflictSymmetry:
    """TS-43-P3: Each conflict pair appears once with lower node_id first.

    Property: Property 4 from design.md
    Validates: 43-REQ-3.2
    """

    @given(impacts=file_impact_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_symmetry(self, impacts: list[FileImpact]) -> None:
        """All conflicts have first < second alphabetically, no duplicates."""
        conflicts = detect_conflicts(impacts)
        for a, b, _ in conflicts:
            assert a < b, f"Conflict pair ({a}, {b}) not ordered"
        pairs = [(a, b) for a, b, _ in conflicts]
        assert len(pairs) == len(set(pairs)), "Duplicate conflict pairs"


class TestDispatchSafety:
    """TS-43-P4: No two dispatched tasks share predicted files.

    Property: Property 5 from design.md
    Validates: 43-REQ-3.3
    """

    @given(data=dispatch_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_no_overlap(
        self,
        data: tuple[list[str], list[FileImpact]],
    ) -> None:
        """Pairwise file set intersection of dispatched tasks is empty."""
        ready, impacts = data
        dispatched = filter_conflicts_from_dispatch(ready, impacts)
        impact_map = {imp.node_id: imp.predicted_files for imp in impacts}

        for i in range(len(dispatched)):
            for j in range(i + 1, len(dispatched)):
                files_i = impact_map.get(dispatched[i], set())
                files_j = impact_map.get(dispatched[j], set())
                overlap = files_i & files_j
                assert overlap == set(), f"Tasks {dispatched[i]} and {dispatched[j]} share files: {overlap}"
