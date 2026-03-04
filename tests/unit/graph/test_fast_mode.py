"""Fast-mode filter tests.

Test Spec: TS-02-8 (remove optional), TS-02-9 (rewire deps)
Requirements: 02-REQ-5.1, 02-REQ-5.2, 02-REQ-5.3
"""

from __future__ import annotations

from agent_fox.graph.fast_mode import apply_fast_mode
from agent_fox.graph.types import NodeStatus, TaskGraph


class TestFastModeRemovesOptional:
    """TS-02-8: Fast mode removes optional tasks."""

    def test_optional_node_skipped(self, graph_with_optional: TaskGraph) -> None:
        """Optional node B gets SKIPPED status."""
        result = apply_fast_mode(graph_with_optional)

        assert result.nodes["spec:2"].status == NodeStatus.SKIPPED

    def test_optional_node_not_in_ordering(
        self, graph_with_optional: TaskGraph
    ) -> None:
        """Optional node is excluded from the ordering."""
        result = apply_fast_mode(graph_with_optional)

        assert "spec:2" not in result.order

    def test_ordering_count_after_removal(self, graph_with_optional: TaskGraph) -> None:
        """Ordering contains only required nodes."""
        result = apply_fast_mode(graph_with_optional)

        assert len(result.order) == 2

    def test_required_nodes_remain_pending(
        self, graph_with_optional: TaskGraph
    ) -> None:
        """Required nodes keep their PENDING status."""
        result = apply_fast_mode(graph_with_optional)

        assert result.nodes["spec:1"].status == NodeStatus.PENDING
        assert result.nodes["spec:3"].status == NodeStatus.PENDING

    def test_fast_mode_metadata_flag(self, graph_with_optional: TaskGraph) -> None:
        """Fast mode sets the metadata flag to True."""
        result = apply_fast_mode(graph_with_optional)

        assert result.metadata.fast_mode is True

    def test_no_optional_nodes_unchanged(self, simple_acyclic_graph: TaskGraph) -> None:
        """Graph with no optional nodes is unchanged."""
        result = apply_fast_mode(simple_acyclic_graph)

        assert len(result.order) == 3
        assert all(n.status == NodeStatus.PENDING for n in result.nodes.values())


class TestFastModeRewiresDeps:
    """TS-02-9: Fast mode rewires dependencies."""

    def test_direct_edge_created(self, graph_with_optional: TaskGraph) -> None:
        """Removing optional B creates edge A -> C."""
        result = apply_fast_mode(graph_with_optional)

        edge_pairs = [(e.source, e.target) for e in result.edges]
        assert ("spec:1", "spec:3") in edge_pairs

    def test_no_edges_reference_removed_node(
        self, graph_with_optional: TaskGraph
    ) -> None:
        """No edges reference the removed optional node B."""
        result = apply_fast_mode(graph_with_optional)

        for edge in result.edges:
            assert edge.source != "spec:2", (
                f"Edge {edge} still references removed node spec:2"
            )
            assert edge.target != "spec:2", (
                f"Edge {edge} still references removed node spec:2"
            )

    def test_returns_task_graph(self, graph_with_optional: TaskGraph) -> None:
        """apply_fast_mode returns a TaskGraph instance."""
        result = apply_fast_mode(graph_with_optional)

        assert isinstance(result, TaskGraph)
