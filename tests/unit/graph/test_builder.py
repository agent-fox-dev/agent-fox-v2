"""Graph builder tests.

Test Spec: TS-02-5 (intra-spec edges), TS-02-6 (cross-spec edges),
           TS-02-E5 (dangling reference)
Requirements: 02-REQ-3.1, 02-REQ-3.2, 02-REQ-3.3, 02-REQ-3.4, 02-REQ-3.E1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.errors import PlanError
from agent_fox.graph.builder import build_graph
from agent_fox.graph.types import NodeStatus
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import CrossSpecDep, TaskGroupDef

# -- Helpers to create test data ---------------------------------------------


def _make_spec(name: str, prefix: int) -> SpecInfo:
    """Create a SpecInfo for testing."""
    return SpecInfo(
        name=name,
        prefix=prefix,
        path=Path(f".specs/{name}"),
        has_tasks=True,
        has_prd=False,
    )


def _make_group(
    number: int,
    title: str,
    optional: bool = False,
    completed: bool = False,
) -> TaskGroupDef:
    """Create a TaskGroupDef for testing."""
    return TaskGroupDef(
        number=number,
        title=title,
        optional=optional,
        completed=completed,
        subtasks=(),
        body=f"Body of task {number}",
    )


class TestBuildGraphIntraSpec:
    """TS-02-5: Build graph with intra-spec edges."""

    def test_creates_correct_node_count(self) -> None:
        """Graph has one node per task group."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A"),
                _make_group(2, "Task B"),
                _make_group(3, "Task C"),
            ]
        }

        graph = build_graph(specs, groups, [])

        assert len(graph.nodes) == 3

    def test_node_ids_follow_format(self) -> None:
        """Node IDs follow {spec_name}:{group_number} format."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A"),
                _make_group(2, "Task B"),
                _make_group(3, "Task C"),
            ]
        }

        graph = build_graph(specs, groups, [])

        assert "my_spec:1" in graph.nodes
        assert "my_spec:2" in graph.nodes
        assert "my_spec:3" in graph.nodes

    def test_all_nodes_pending_status(self) -> None:
        """All uncompleted nodes start with PENDING status."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A"),
                _make_group(2, "Task B"),
                _make_group(3, "Task C"),
            ]
        }

        graph = build_graph(specs, groups, [])

        assert all(n.status == NodeStatus.PENDING for n in graph.nodes.values())

    def test_completed_group_produces_completed_node(self) -> None:
        """A task group marked completed=[x] produces a COMPLETED node."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A", completed=True),
                _make_group(2, "Task B"),
            ]
        }

        graph = build_graph(specs, groups, [])

        assert graph.nodes["my_spec:1"].status == NodeStatus.COMPLETED
        assert graph.nodes["my_spec:2"].status == NodeStatus.PENDING

    def test_sequential_intra_spec_edges(self) -> None:
        """Intra-spec edges connect group N to N+1."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A"),
                _make_group(2, "Task B"),
                _make_group(3, "Task C"),
            ]
        }

        graph = build_graph(specs, groups, [])

        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert ("my_spec:1", "my_spec:2") in edge_pairs
        assert ("my_spec:2", "my_spec:3") in edge_pairs

    def test_intra_spec_edge_count(self) -> None:
        """Number of intra-spec edges is N-1 for N groups."""
        specs = [_make_spec("my_spec", 1)]
        groups = {
            "my_spec": [
                _make_group(1, "Task A"),
                _make_group(2, "Task B"),
                _make_group(3, "Task C"),
            ]
        }

        graph = build_graph(specs, groups, [])

        intra_edges = [e for e in graph.edges if e.kind == "intra_spec"]
        assert len(intra_edges) == 2


class TestBuildGraphCrossSpec:
    """TS-02-6: Build graph with cross-spec edges."""

    def test_cross_spec_edge_exists(self) -> None:
        """Cross-spec edge connects last group of depended spec to first group."""
        specs = [
            _make_spec("01_alpha", 1),
            _make_spec("02_beta", 2),
        ]
        groups = {
            "01_alpha": [_make_group(1, "Alpha 1"), _make_group(2, "Alpha 2")],
            "02_beta": [_make_group(1, "Beta 1"), _make_group(2, "Beta 2")],
        }
        cross_deps = [
            CrossSpecDep(
                from_spec="02_beta",
                from_group=1,
                to_spec="01_alpha",
                to_group=2,
            ),
        ]

        graph = build_graph(specs, groups, cross_deps)

        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert ("01_alpha:2", "02_beta:1") in edge_pairs

    def test_cross_spec_edge_kind(self) -> None:
        """Cross-spec edges have kind='cross_spec'."""
        specs = [
            _make_spec("01_alpha", 1),
            _make_spec("02_beta", 2),
        ]
        groups = {
            "01_alpha": [_make_group(1, "Alpha 1"), _make_group(2, "Alpha 2")],
            "02_beta": [_make_group(1, "Beta 1"), _make_group(2, "Beta 2")],
        }
        cross_deps = [
            CrossSpecDep(
                from_spec="02_beta",
                from_group=1,
                to_spec="01_alpha",
                to_group=2,
            ),
        ]

        graph = build_graph(specs, groups, cross_deps)

        cross_edges = [e for e in graph.edges if e.kind == "cross_spec"]
        assert len(cross_edges) >= 1

    def test_total_node_count_multi_spec(self) -> None:
        """Graph contains nodes from all specs."""
        specs = [
            _make_spec("01_alpha", 1),
            _make_spec("02_beta", 2),
        ]
        groups = {
            "01_alpha": [_make_group(1, "Alpha 1"), _make_group(2, "Alpha 2")],
            "02_beta": [_make_group(1, "Beta 1"), _make_group(2, "Beta 2")],
        }

        graph = build_graph(specs, groups, [])

        assert len(graph.nodes) == 4


class TestBuildGraphCrossSpecGroupLevel:
    """Group-level cross-spec edges connect specific groups, not first/last."""

    def test_group_level_cross_spec_edge(self) -> None:
        """Cross-spec dep with explicit groups creates correct edge."""
        specs = [
            _make_spec("01_alpha", 1),
            _make_spec("02_beta", 2),
        ]
        groups = {
            "01_alpha": [
                _make_group(1, "Alpha 1"),
                _make_group(2, "Alpha 2"),
                _make_group(3, "Alpha 3"),
            ],
            "02_beta": [
                _make_group(1, "Beta 1"),
                _make_group(2, "Beta 2"),
            ],
        }
        # Beta group 1 depends on Alpha group 2 (not Alpha's last group 3)
        cross_deps = [
            CrossSpecDep(
                from_spec="02_beta",
                from_group=1,
                to_spec="01_alpha",
                to_group=2,
            ),
        ]

        graph = build_graph(specs, groups, cross_deps)

        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert ("01_alpha:2", "02_beta:1") in edge_pairs
        # Should NOT have an edge from alpha:3 (the last group)
        assert ("01_alpha:3", "02_beta:1") not in edge_pairs

    def test_group_level_enables_earlier_scheduling(self) -> None:
        """Group-level deps allow dependent tasks to start earlier."""
        specs = [
            _make_spec("01_alpha", 1),
            _make_spec("02_beta", 2),
        ]
        groups = {
            "01_alpha": [
                _make_group(1, "Alpha 1"),
                _make_group(2, "Alpha 2"),
                _make_group(3, "Alpha 3"),
                _make_group(4, "Alpha 4"),
            ],
            "02_beta": [
                _make_group(1, "Beta 1"),
                _make_group(2, "Beta 2"),
            ],
        }
        # Beta:1 only needs Alpha:2, not all of Alpha
        cross_deps = [
            CrossSpecDep(
                from_spec="02_beta",
                from_group=1,
                to_spec="01_alpha",
                to_group=2,
            ),
        ]

        graph = build_graph(specs, groups, cross_deps)

        # Beta:1 should depend on Alpha:2, not Alpha:4
        beta_1_preds = graph.predecessors("02_beta:1")
        assert "01_alpha:2" in beta_1_preds
        assert "01_alpha:4" not in beta_1_preds


class TestDanglingCrossSpecRef:
    """TS-02-E5: Dangling cross-spec reference raises PlanError."""

    def test_missing_spec_raises_plan_error(self) -> None:
        """Cross-dep referencing non-existent spec raises PlanError."""
        specs = [_make_spec("01_alpha", 1)]
        groups = {
            "01_alpha": [_make_group(1, "Alpha 1"), _make_group(2, "Alpha 2")],
        }
        bad_dep = CrossSpecDep(
            from_spec="01_alpha",
            from_group=1,
            to_spec="99_missing",
            to_group=1,
        )

        with pytest.raises(PlanError):
            build_graph(specs, groups, [bad_dep])

    def test_error_mentions_missing_spec(self) -> None:
        """PlanError message mentions the missing spec name."""
        specs = [_make_spec("01_alpha", 1)]
        groups = {
            "01_alpha": [_make_group(1, "Alpha 1"), _make_group(2, "Alpha 2")],
        }
        bad_dep = CrossSpecDep(
            from_spec="01_alpha",
            from_group=1,
            to_spec="99_missing",
            to_group=1,
        )

        with pytest.raises(PlanError) as exc_info:
            build_graph(specs, groups, [bad_dep])

        assert "99_missing" in str(exc_info.value)
