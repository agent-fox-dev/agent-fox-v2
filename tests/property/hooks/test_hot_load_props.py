"""Property tests for hot-loading.

Test Spec: TS-06-P4 (hot-load monotonicity)
Property: Property 5 from design.md
Requirements: 06-REQ-7.1, 06-REQ-7.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.hot_load import hot_load_specs
from agent_fox.graph.types import Node, NodeStatus, PlanMetadata, TaskGraph


def _make_tasks_md() -> str:
    """Create minimal tasks.md content."""
    return (
        "# Tasks\n"
        "\n"
        "- [ ] 1. Test task\n"
        "  - [ ] 1.1 Subtask\n"
    )


def _make_prd_md() -> str:
    """Create minimal prd.md content without dependencies."""
    return "# Requirements\n\n## Dependencies\n\nNo dependencies.\n"


def _make_graph(spec_names: list[str]) -> TaskGraph:
    """Create a TaskGraph with nodes for each spec name."""
    nodes = {}
    order = []
    for name in spec_names:
        node_id = f"{name}:1"
        nodes[node_id] = Node(
            id=node_id,
            spec_name=name,
            group_number=1,
            title=f"Task for {name}",
            optional=False,
            status=NodeStatus.COMPLETED,
        )
        order.append(node_id)

    return TaskGraph(
        nodes=nodes,
        edges=[],
        order=order,
        metadata=PlanMetadata(created_at="2026-03-01T00:00:00"),
    )


# Strategy for spec names: two-digit prefix followed by underscore and name
_spec_name = st.from_regex(r"[0-9]{2}_[a-z_]{3,15}", fullmatch=True)


class TestHotLoadMonotonicity:
    """TS-06-P4: Hot-load monotonicity.

    Property 5: After hot-loading, the set of node IDs in the graph
    is always a superset of the node IDs before hot-loading.
    No existing node is removed or modified.
    """

    @given(
        existing_specs=st.lists(
            _spec_name,
            min_size=1,
            max_size=3,
            unique=True,
        ),
        new_specs=st.lists(
            _spec_name,
            min_size=0,
            max_size=2,
            unique=True,
        ),
    )
    @settings(max_examples=20)
    def test_original_nodes_preserved(
        self,
        existing_specs: list[str],
        new_specs: list[str],
        tmp_path_factory,
    ) -> None:
        """All original node IDs remain after hot-loading."""
        # Ensure new specs don't overlap with existing
        new_specs = [s for s in new_specs if s not in existing_specs]

        base = tmp_path_factory.mktemp("hotload")
        specs_dir = base / ".specs"
        specs_dir.mkdir()

        # Create existing spec dirs
        for name in existing_specs:
            d = specs_dir / name
            d.mkdir()
            (d / "tasks.md").write_text(_make_tasks_md())
            (d / "prd.md").write_text(_make_prd_md())

        # Create new spec dirs
        for name in new_specs:
            d = specs_dir / name
            d.mkdir()
            (d / "tasks.md").write_text(_make_tasks_md())
            (d / "prd.md").write_text(_make_prd_md())

        graph = _make_graph(existing_specs)
        original_ids = set(graph.nodes.keys())

        updated_graph, _ = hot_load_specs(graph, specs_dir)

        assert original_ids.issubset(set(updated_graph.nodes.keys())), (
            f"Lost node IDs: {original_ids - set(updated_graph.nodes.keys())}"
        )

    @given(
        existing_specs=st.lists(
            _spec_name,
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    @settings(max_examples=15)
    def test_no_new_specs_preserves_exactly(
        self,
        existing_specs: list[str],
        tmp_path_factory,
    ) -> None:
        """When no new specs exist, graph is unchanged."""
        base = tmp_path_factory.mktemp("hotload_noop")
        specs_dir = base / ".specs"
        specs_dir.mkdir()

        for name in existing_specs:
            d = specs_dir / name
            d.mkdir()
            (d / "tasks.md").write_text(_make_tasks_md())
            (d / "prd.md").write_text(_make_prd_md())

        graph = _make_graph(existing_specs)

        updated_graph, new_spec_names = hot_load_specs(graph, specs_dir)

        assert new_spec_names == []
        assert set(updated_graph.nodes.keys()) == set(graph.nodes.keys())
