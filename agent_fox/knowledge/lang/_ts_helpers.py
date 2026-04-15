"""Shared tree-sitter helpers for language analyzers.

Common utility functions used across all tree-sitter-based language analyzers,
plus entity/edge factory functions that reduce construction boilerplate.

Requirements: 102-REQ-2.1, 102-REQ-3.1
"""

from __future__ import annotations

import uuid

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType

# Epoch timestamp used for entity created_at when no real timestamp is available.
ENTITY_EPOCH = "1970-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Tree-sitter node helpers
# ---------------------------------------------------------------------------


def node_text(node) -> str | None:
    """Safely decode text from a tree-sitter node."""
    if node is None:
        return None
    return node.text.decode("utf-8") if node.text else None


def field_text(node, field_name: str) -> str | None:
    """Get decoded text of the named field child."""
    child = node.child_by_field_name(field_name)
    return node_text(child)


def child_by_type(node, *types: str):
    """Return the first child whose type is in *types*, or None."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def child_text_by_type(node, *types: str) -> str | None:
    """Return text of the first child whose type is in *types*, or None."""
    return node_text(child_by_type(node, *types))


# ---------------------------------------------------------------------------
# Entity / edge factory helpers
# ---------------------------------------------------------------------------


def make_entity(
    entity_type: EntityType,
    name: str,
    path: str,
    *,
    now: str = ENTITY_EPOCH,
) -> Entity:
    """Create an Entity with a fresh UUID and standard defaults."""
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_name=name,
        entity_path=path,
        created_at=now,
        deleted_at=None,
    )


def make_edge(
    source_id: str,
    target_id: str,
    relationship: str,
) -> EntityEdge:
    """Create an EntityEdge."""
    return EntityEdge(
        source_id=source_id,
        target_id=target_id,
        relationship=relationship,
    )
