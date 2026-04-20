"""Tests for deferred review injection (issue #491).

Verifies that review nodes for already-completed specs are injected as
'deferred' instead of 'pending', and that promotion only occurs when no
coder candidates are available.
"""

from __future__ import annotations

from agent_fox.engine.graph_sync import GraphSync


class TestDeferReadyReviews:
    """Tests for _defer_ready_reviews helper."""

    def test_review_node_deferred_when_deps_completed(self) -> None:
        """Auto_post review node with completed deps is set to deferred."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        coder = Node(
            id="myspec:1",
            spec_name="myspec",
            group_number=1,
            title="Coder",
            optional=False,
            archetype="coder",
        )
        verifier = Node(
            id="myspec:2",
            spec_name="myspec",
            group_number=2,
            title="Verifier Check",
            optional=False,
            archetype="verifier",
        )
        graph = TaskGraph(
            nodes={coder.id: coder, verifier.id: verifier},
            edges=[Edge(source="myspec:1", target="myspec:2", kind="intra_spec")],
            order=["myspec:1", "myspec:2"],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {"myspec:1": "completed", "myspec:2": "pending"}
        edges_dict = {"myspec:1": [], "myspec:2": ["myspec:1"]}
        gs = GraphSync(node_states, edges_dict)

        deferred = _defer_ready_reviews(graph, gs)

        assert deferred == ["myspec:2"]
        assert gs.node_states["myspec:2"] == "deferred"

    def test_auto_pre_node_never_deferred(self) -> None:
        """Auto_pre (group 0) review nodes are exempt from deferral."""
        from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        pre_review = Node(
            id="myspec:0:reviewer:pre-review",
            spec_name="myspec",
            group_number=0,
            title="Reviewer (pre-review)",
            optional=False,
            archetype="reviewer",
            mode="pre-review",
        )
        graph = TaskGraph(
            nodes={pre_review.id: pre_review},
            edges=[],
            order=[pre_review.id],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {"myspec:0:reviewer:pre-review": "pending"}
        gs = GraphSync(node_states, {})

        deferred = _defer_ready_reviews(graph, gs)

        assert deferred == []
        assert gs.node_states["myspec:0:reviewer:pre-review"] == "pending"

    def test_coder_node_never_deferred(self) -> None:
        """Coder nodes are never deferred, even with all deps completed."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        setup = Node(
            id="myspec:1",
            spec_name="myspec",
            group_number=1,
            title="Setup",
            optional=False,
            archetype="coder",
        )
        impl = Node(
            id="myspec:2",
            spec_name="myspec",
            group_number=2,
            title="Implement",
            optional=False,
            archetype="coder",
        )
        graph = TaskGraph(
            nodes={setup.id: setup, impl.id: impl},
            edges=[Edge(source="myspec:1", target="myspec:2", kind="intra_spec")],
            order=["myspec:1", "myspec:2"],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {"myspec:1": "completed", "myspec:2": "pending"}
        edges_dict = {"myspec:1": [], "myspec:2": ["myspec:1"]}
        gs = GraphSync(node_states, edges_dict)

        deferred = _defer_ready_reviews(graph, gs)

        assert deferred == []
        assert gs.node_states["myspec:2"] == "pending"

    def test_review_node_not_deferred_when_deps_incomplete(self) -> None:
        """Review node stays pending when deps are not yet completed."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        coder = Node(
            id="myspec:1",
            spec_name="myspec",
            group_number=1,
            title="Coder",
            optional=False,
            archetype="coder",
        )
        verifier = Node(
            id="myspec:2",
            spec_name="myspec",
            group_number=2,
            title="Verifier Check",
            optional=False,
            archetype="verifier",
        )
        graph = TaskGraph(
            nodes={coder.id: coder, verifier.id: verifier},
            edges=[Edge(source="myspec:1", target="myspec:2", kind="intra_spec")],
            order=["myspec:1", "myspec:2"],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {"myspec:1": "in_progress", "myspec:2": "pending"}
        edges_dict = {"myspec:1": [], "myspec:2": ["myspec:1"]}
        gs = GraphSync(node_states, edges_dict)

        deferred = _defer_ready_reviews(graph, gs)

        assert deferred == []
        assert gs.node_states["myspec:2"] == "pending"

    def test_audit_review_deferred_when_deps_completed(self) -> None:
        """Auto_mid reviewer:audit-review node is deferred when deps completed."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        coder = Node(
            id="myspec:2",
            spec_name="myspec",
            group_number=2,
            title="Write tests",
            optional=False,
            archetype="coder",
        )
        audit = Node(
            id="myspec:2:reviewer:audit-review",
            spec_name="myspec",
            group_number=2,
            title="Reviewer (audit-review)",
            optional=False,
            archetype="reviewer",
            mode="audit-review",
        )
        graph = TaskGraph(
            nodes={coder.id: coder, audit.id: audit},
            edges=[Edge(source="myspec:2", target="myspec:2:reviewer:audit-review", kind="intra_spec")],
            order=["myspec:2", "myspec:2:reviewer:audit-review"],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {
            "myspec:2": "completed",
            "myspec:2:reviewer:audit-review": "pending",
        }
        edges_dict = {
            "myspec:2": [],
            "myspec:2:reviewer:audit-review": ["myspec:2"],
        }
        gs = GraphSync(node_states, edges_dict)

        deferred = _defer_ready_reviews(graph, gs)

        assert deferred == ["myspec:2:reviewer:audit-review"]
        assert gs.node_states["myspec:2:reviewer:audit-review"] == "deferred"


class TestDeferredPromotionIntegration:
    """Integration tests for deferred → promotion → ready flow."""

    def test_deferred_then_promoted_then_ready(self) -> None:
        """Full lifecycle: defer at init, promote when idle, appear in ready."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        coder = Node(
            id="s:1", spec_name="s", group_number=1,
            title="Coder", optional=False, archetype="coder",
        )
        review = Node(
            id="s:2", spec_name="s", group_number=2,
            title="Verifier", optional=False, archetype="verifier",
        )
        graph = TaskGraph(
            nodes={coder.id: coder, review.id: review},
            edges=[Edge(source="s:1", target="s:2", kind="intra_spec")],
            order=["s:1", "s:2"],
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {"s:1": "completed", "s:2": "pending"}
        edges_dict = {"s:1": [], "s:2": ["s:1"]}
        gs = GraphSync(node_states, edges_dict)

        _defer_ready_reviews(graph, gs)
        assert gs.node_states["s:2"] == "deferred"
        assert gs.ready_tasks() == []

        promoted = gs.promote_deferred(limit=1)
        assert promoted == ["s:2"]
        assert gs.ready_tasks() == ["s:2"]

    def test_promotion_respects_review_cap_interaction(self) -> None:
        """Promoted deferred nodes still go through normal ready_tasks ordering."""
        from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

        from agent_fox.engine.engine import _defer_ready_reviews

        nodes_dict = {}
        edges_list = []
        for i in range(1, 4):
            spec = f"spec{i:02d}"
            coder = Node(
                id=f"{spec}:1", spec_name=spec, group_number=1,
                title="Coder", optional=False, archetype="coder",
            )
            verifier = Node(
                id=f"{spec}:2", spec_name=spec, group_number=2,
                title="Verifier", optional=False, archetype="verifier",
            )
            nodes_dict[coder.id] = coder
            nodes_dict[verifier.id] = verifier
            edges_list.append(Edge(source=f"{spec}:1", target=f"{spec}:2", kind="intra_spec"))

        graph = TaskGraph(
            nodes=nodes_dict,
            edges=edges_list,
            order=list(nodes_dict.keys()),
            metadata=PlanMetadata(created_at="2026-01-01"),
        )

        node_states = {nid: "completed" if ":1" in nid else "pending" for nid in nodes_dict}
        edges_dict_map = {nid: [] for nid in nodes_dict}
        for e in edges_list:
            edges_dict_map[e.target] = [e.source]
        gs = GraphSync(node_states, edges_dict_map)

        deferred = _defer_ready_reviews(graph, gs)
        assert len(deferred) == 3

        promoted = gs.promote_deferred(limit=2)
        assert len(promoted) == 2

        ready = gs.ready_tasks()
        assert len(ready) == 2
