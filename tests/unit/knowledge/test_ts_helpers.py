"""Tests for shared tree-sitter helper functions.

Covers: make_entity, make_edge factory helpers in _ts_helpers.
Requirements: 102-REQ-2.1, 102-REQ-3.1
"""

from __future__ import annotations

import typing
import uuid

from agent_fox.knowledge.entities import EdgeType, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import make_edge, make_entity


class TestMakeEntity:
    """make_entity returns a well-formed Entity with a fresh UUID."""

    def test_returns_entity_with_fresh_uuid(self) -> None:
        entity = make_entity(EntityType.CLASS, "MyClass", "src/foo.py")
        assert entity.entity_type == EntityType.CLASS
        assert entity.entity_name == "MyClass"
        assert entity.entity_path == "src/foo.py"
        # UUID must be parseable as UUID v4
        parsed = uuid.UUID(entity.id)
        assert parsed.version == 4

    def test_default_created_at_is_epoch(self) -> None:
        entity = make_entity(EntityType.FUNCTION, "fn", "x.py")
        assert entity.created_at == "1970-01-01T00:00:00"

    def test_custom_now(self) -> None:
        entity = make_entity(EntityType.MODULE, "mod", "m.py", now="2024-01-01T00:00:00")
        assert entity.created_at == "2024-01-01T00:00:00"

    def test_deleted_at_is_none(self) -> None:
        entity = make_entity(EntityType.FILE, "f", "f.py")
        assert entity.deleted_at is None

    def test_each_call_produces_unique_id(self) -> None:
        a = make_entity(EntityType.CLASS, "C", "c.py")
        b = make_entity(EntityType.CLASS, "C", "c.py")
        assert a.id != b.id


class TestMakeEdge:
    """make_edge accepts EdgeType and returns a correctly typed EntityEdge."""

    def test_returns_entity_edge(self) -> None:
        edge = make_edge("src-id", "tgt-id", EdgeType.CONTAINS)
        assert isinstance(edge, EntityEdge)

    def test_relationship_is_edgetype_instance(self) -> None:
        """regression: relationship must be EdgeType, not a bare str."""
        edge = make_edge("src-id", "tgt-id", EdgeType.CONTAINS)
        # EdgeType is a StrEnum — a bare "contains" string would NOT be an
        # instance of EdgeType, so this assertion catches the regression.
        assert isinstance(edge.relationship, EdgeType)

    def test_contains_relationship(self) -> None:
        edge = make_edge("a", "b", EdgeType.CONTAINS)
        assert edge.relationship == EdgeType.CONTAINS
        assert edge.source_id == "a"
        assert edge.target_id == "b"

    def test_imports_relationship(self) -> None:
        edge = make_edge("a", "b", EdgeType.IMPORTS)
        assert edge.relationship == EdgeType.IMPORTS

    def test_extends_relationship(self) -> None:
        edge = make_edge("a", "b", EdgeType.EXTENDS)
        assert edge.relationship == EdgeType.EXTENDS

    def test_relationship_parameter_annotated_as_edgetype(self) -> None:
        """regression #399: make_edge signature must use EdgeType, not str.

        Uses typing.get_type_hints() to resolve annotations that may be
        stringified by 'from __future__ import annotations' (PEP 563).
        """
        hints = typing.get_type_hints(make_edge)
        annotation = hints.get("relationship")
        assert annotation is EdgeType, (
            f"make_edge 'relationship' parameter must be annotated as EdgeType, "
            f"got: {annotation!r}"
        )
