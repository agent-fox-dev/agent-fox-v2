"""Property tests for fast-mode filter and node ID uniqueness.

Test Spec: TS-02-P2 (dependency preservation), TS-02-P3 (node ID uniqueness)
Properties: Property 2 (fast-mode dep preservation), Property 3 (ID uniqueness)
             Property 7 (fast-mode skipped count) from design.md
Requirements: 02-REQ-5.2, 02-REQ-3.3, 02-REQ-5.1
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.graph.builder import build_graph
from agent_fox.graph.fast_mode import apply_fast_mode
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import TaskGroupDef

# -- Helpers -----------------------------------------------------------------


def _is_reachable(graph: TaskGraph, source: str, target: str) -> bool:
    """Check if target is reachable from source via edges."""
    visited: set[str] = set()
    queue: deque[str] = deque([source])
    while queue:
        current = queue.popleft()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        for edge in graph.edges:
            if edge.source == current and edge.target not in visited:
                queue.append(edge.target)
    return False


# -- Strategies for graphs with optional nodes --------------------------------


@st.composite
def graphs_with_optional_nodes(draw: st.DrawFn) -> TaskGraph:
    """Generate graphs where some nodes are optional, structured as a chain.

    Creates a chain of 3-8 nodes where at least one middle node is optional.
    """
    n = draw(st.integers(min_value=3, max_value=8))
    spec_name = "test_spec"

    # Choose at least one middle node to be optional
    optional_indices = set()
    for i in range(2, n):  # Skip first and last
        if draw(st.booleans()):
            optional_indices.add(i)
    if not optional_indices:
        # Ensure at least one optional
        optional_indices.add(draw(st.integers(min_value=2, max_value=n - 1)))

    nodes: list[Node] = []
    for i in range(1, n + 1):
        nodes.append(
            Node(
                id=f"{spec_name}:{i}",
                spec_name=spec_name,
                group_number=i,
                title=f"Task {i}",
                optional=i in optional_indices,
            )
        )

    # Create a chain of edges
    edges: list[Edge] = []
    for i in range(1, n):
        edges.append(
            Edge(
                source=f"{spec_name}:{i}",
                target=f"{spec_name}:{i + 1}",
                kind="intra_spec",
            )
        )

    node_map = {node.id: node for node in nodes}
    return TaskGraph(
        nodes=node_map,
        edges=edges,
        order=[],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


class TestFastModeDependencyPreservation:
    """TS-02-P2: Removing optional nodes preserves reachability.

    Property 2: For any task graph where optional node B has predecessor A
    and successor C, after apply_fast_mode(), C is reachable from A through
    remaining edges.
    """

    @given(graph=graphs_with_optional_nodes())
    @settings(max_examples=50)
    def test_reachability_preserved(self, graph: TaskGraph) -> None:
        """After removing optional nodes, reachability is preserved."""
        # Record predecessors and successors of optional nodes
        optional_ids = {nid for nid, node in graph.nodes.items() if node.optional}
        pred_succ_pairs: list[tuple[str, str]] = []
        for opt_id in optional_ids:
            preds = graph.predecessors(opt_id)
            succs = graph.successors(opt_id)
            for p in preds:
                for s in succs:
                    if p not in optional_ids and s not in optional_ids:
                        pred_succ_pairs.append((p, s))

        result = apply_fast_mode(graph)

        for pred, succ in pred_succ_pairs:
            assert _is_reachable(result, pred, succ), (
                f"After fast mode, {succ} should be reachable from {pred}"
            )


class TestNodeIdUniqueness:
    """TS-02-P3: No two nodes share the same ID.

    Property 3: For any set of specs with task groups, every node in the
    constructed TaskGraph has a unique ID.
    """

    @given(
        num_specs=st.integers(min_value=1, max_value=5),
        groups_per_spec=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_node_ids_unique(self, num_specs: int, groups_per_spec: int) -> None:
        """All node IDs in a built graph are unique."""
        specs: list[SpecInfo] = []
        task_groups: dict[str, list[TaskGroupDef]] = {}

        for s in range(1, num_specs + 1):
            spec_name = f"{s:02d}_spec_{s}"
            specs.append(
                SpecInfo(
                    name=spec_name,
                    prefix=s,
                    path=Path(f".specs/{spec_name}"),
                    has_tasks=True,
                    has_prd=False,
                )
            )
            groups: list[TaskGroupDef] = []
            for g in range(1, groups_per_spec + 1):
                groups.append(
                    TaskGroupDef(
                        number=g,
                        title=f"Task {g}",
                        optional=False,
                        completed=False,
                        subtasks=(),
                        body=f"Body {g}",
                    )
                )
            task_groups[spec_name] = groups

        graph = build_graph(specs, task_groups, [])

        ids = list(graph.nodes.keys())
        assert len(ids) == len(set(ids)), f"Duplicate node IDs found: {ids}"
        assert len(ids) == num_specs * groups_per_spec


class TestFastModeSkippedCount:
    """Property 7: Fast-mode skipped count.

    For any task graph with K optional nodes, after apply_fast_mode(),
    exactly K nodes have status SKIPPED and the ordering contains
    total_nodes - K entries.
    """

    @given(graph=graphs_with_optional_nodes())
    @settings(max_examples=50)
    def test_skipped_count_matches_optional(self, graph: TaskGraph) -> None:
        """Number of SKIPPED nodes equals number of optional nodes."""
        optional_count = sum(1 for n in graph.nodes.values() if n.optional)

        result = apply_fast_mode(graph)

        skipped_count = sum(
            1 for n in result.nodes.values() if n.status == NodeStatus.SKIPPED
        )
        assert skipped_count == optional_count

    @given(graph=graphs_with_optional_nodes())
    @settings(max_examples=50)
    def test_order_length_matches(self, graph: TaskGraph) -> None:
        """Ordering length equals total nodes minus optional nodes."""
        total = len(graph.nodes)
        optional_count = sum(1 for n in graph.nodes.values() if n.optional)

        result = apply_fast_mode(graph)

        assert len(result.order) == total - optional_count
