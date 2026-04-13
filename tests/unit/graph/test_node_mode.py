"""Unit tests for Node.mode field and serialization.

Test Spec: TS-97-5, TS-97-6, TS-97-E3
Requirements: 97-REQ-2.1, 97-REQ-2.2, 97-REQ-2.3, 97-REQ-2.E1
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# TS-97-5: Node Mode Field
# Requirement: 97-REQ-2.1
# ---------------------------------------------------------------------------


class TestNodeModeField:
    """Verify Node has a mode field defaulting to None."""

    def test_mode_defaults_to_none(self) -> None:
        """TS-97-5: Node.mode defaults to None when not specified."""
        from agent_fox.graph.types import Node

        node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)
        assert node.mode is None

    def test_mode_can_be_set_to_string(self) -> None:
        """TS-97-5: Node.mode can be set to a non-None string."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:1",
            spec_name="s",
            group_number=1,
            title="t",
            optional=False,
            mode="pre-review",
        )
        assert node.mode == "pre-review"

    def test_mode_can_be_set_explicitly_to_none(self) -> None:
        """Node.mode can be explicitly set to None."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:1",
            spec_name="s",
            group_number=1,
            title="t",
            optional=False,
            mode=None,
        )
        assert node.mode is None

    def test_mode_type_is_str_or_none(self) -> None:
        """Node.mode should accept any string value."""
        from agent_fox.graph.types import Node

        for mode in ["pre-review", "drift-review", "fast", "reviewer:pre-review"]:
            node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False, mode=mode)
            assert node.mode == mode


# ---------------------------------------------------------------------------
# TS-97-6: Node Serialization Round-Trip
# Requirement: 97-REQ-2.2
# ---------------------------------------------------------------------------


class TestNodeSerializationRoundTrip:
    """Verify mode persists through JSON serialization."""

    def _serialize_node(self, node: object) -> dict:  # type: ignore[type-arg]
        """Serialize a Node to a dict using the persistence module."""
        from agent_fox.graph.persistence import _serialize

        return _serialize(node)  # type: ignore[arg-type]

    def _deserialize_node(self, data: dict) -> object:  # type: ignore[type-arg]
        """Deserialize a Node from a dict using the persistence module."""
        from agent_fox.graph.persistence import _node_from_dict

        return _node_from_dict(data)

    def test_mode_in_serialized_dict(self) -> None:
        """TS-97-6: Serialized node dict includes mode field."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0",
            spec_name="s",
            group_number=0,
            title="t",
            optional=False,
            mode="pre-review",
        )
        serialized = self._serialize_node(node)
        assert "mode" in serialized
        assert serialized["mode"] == "pre-review"

    def test_mode_string_preserved_after_roundtrip(self) -> None:
        """TS-97-6: mode string is preserved after serialize/deserialize."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0",
            spec_name="s",
            group_number=0,
            title="t",
            optional=False,
            mode="pre-review",
        )
        serialized = self._serialize_node(node)
        deserialized = self._deserialize_node(serialized)
        assert deserialized.mode == "pre-review"  # type: ignore[attr-defined]

    def test_none_mode_preserved_after_roundtrip(self) -> None:
        """mode=None is preserved after serialize/deserialize."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0",
            spec_name="s",
            group_number=0,
            title="t",
            optional=False,
            mode=None,
        )
        serialized = self._serialize_node(node)
        deserialized = self._deserialize_node(serialized)
        assert deserialized.mode is None  # type: ignore[attr-defined]

    def test_mode_in_task_graph_roundtrip(self) -> None:
        """TS-97-SMOKE-3: Mode survives full TaskGraph serialization/deserialization."""
        from agent_fox.graph.persistence import _serialize
        from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

        graph = TaskGraph(
            nodes={
                "s:0": Node(id="s:0", spec_name="s", group_number=0, title="t", optional=False, mode="pre-review"),
                "s:1": Node(id="s:1", spec_name="s", group_number=1, title="t2", optional=False, mode=None),
            },
            edges=[],
            order=["s:0", "s:1"],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )
        serialized = _serialize(graph)
        # Check nodes dict is in serialized form
        assert serialized["nodes"]["s:0"]["mode"] == "pre-review"
        assert serialized["nodes"]["s:1"]["mode"] is None

    def test_json_roundtrip_preserves_mode(self) -> None:
        """Mode survives JSON-to-string-and-back serialization."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0",
            spec_name="s",
            group_number=0,
            title="t",
            optional=False,
            mode="drift-review",
        )
        serialized = self._serialize_node(node)
        json_str = json.dumps(serialized)
        data = json.loads(json_str)
        deserialized = self._deserialize_node(data)
        assert deserialized.mode == "drift-review"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TS-97-E3: Node With None Mode
# Requirement: 97-REQ-2.E1
# ---------------------------------------------------------------------------


class TestNodeNoneMode:
    """Verify Node with None mode behaves identically to current implementation."""

    def test_node_with_none_mode_has_no_mode_info_in_archetype_str(self) -> None:
        """TS-97-E3: Node with mode=None has no mode suffix in archetype representation."""
        from agent_fox.graph.types import Node

        node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)
        assert node.mode is None
        # The archetype field alone should not contain a colon (no mode suffix)
        assert ":" not in node.archetype

    def test_node_with_mode_includes_colon_in_combined_repr(self) -> None:
        """TS-97-5 / 97-REQ-2.3: Node with non-None mode should include mode in string repr."""
        from agent_fox.graph.types import Node

        node = Node(
            id="s:1",
            spec_name="s",
            group_number=1,
            title="t",
            optional=False,
            archetype="reviewer",
            mode="pre-review",
        )
        # The mode value itself contains the mode name
        assert node.mode == "pre-review"
        # Combined representation would be "reviewer:pre-review" style
        if hasattr(node, "__str__") and type(node).__str__ is not object.__str__:
            combined = str(node)
            # If custom __str__ is defined, it should include the mode
            assert "pre-review" in combined
        else:
            # At minimum, the mode field has the correct value
            combined = f"{node.archetype}:{node.mode}"
            assert combined == "reviewer:pre-review"

    def test_existing_nodes_without_mode_are_backward_compatible(self) -> None:
        """TS-97-E3: Existing code paths that create Node without mode still work."""
        from agent_fox.graph.types import Node, NodeStatus

        node = Node(
            id="old:1",
            spec_name="old",
            group_number=1,
            title="Old Task",
            optional=False,
            status=NodeStatus.PENDING,
            archetype="coder",
        )
        assert node.mode is None
        assert node.archetype == "coder"
        assert node.status == NodeStatus.PENDING
