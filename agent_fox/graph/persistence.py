"""Plan persistence: serialize/deserialize TaskGraph to/from JSON.

Requirements: 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3, 02-REQ-6.4, 02-REQ-6.E1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph

logger = logging.getLogger(__name__)


def _node_to_dict(node: Node) -> dict[str, Any]:
    """Serialize a Node to a JSON-compatible dictionary."""
    return {
        "id": node.id,
        "spec_name": node.spec_name,
        "group_number": node.group_number,
        "title": node.title,
        "optional": node.optional,
        "status": str(node.status),
        "subtask_count": node.subtask_count,
        "body": node.body,
    }


def _node_from_dict(data: dict[str, Any]) -> Node:
    """Deserialize a Node from a dictionary."""
    return Node(
        id=data["id"],
        spec_name=data["spec_name"],
        group_number=data["group_number"],
        title=data["title"],
        optional=data["optional"],
        status=NodeStatus(data["status"]),
        subtask_count=data.get("subtask_count", 0),
        body=data.get("body", ""),
    )


def _edge_to_dict(edge: Edge) -> dict[str, str]:
    """Serialize an Edge to a JSON-compatible dictionary."""
    return {
        "source": edge.source,
        "target": edge.target,
        "kind": edge.kind,
    }


def _edge_from_dict(data: dict[str, str]) -> Edge:
    """Deserialize an Edge from a dictionary."""
    return Edge(
        source=data["source"],
        target=data["target"],
        kind=data["kind"],
    )


def _metadata_to_dict(metadata: PlanMetadata) -> dict[str, Any]:
    """Serialize PlanMetadata to a JSON-compatible dictionary."""
    return {
        "created_at": metadata.created_at,
        "fast_mode": metadata.fast_mode,
        "filtered_spec": metadata.filtered_spec,
        "version": metadata.version,
    }


def _metadata_from_dict(data: dict[str, Any]) -> PlanMetadata:
    """Deserialize PlanMetadata from a dictionary."""
    return PlanMetadata(
        created_at=data.get("created_at", ""),
        fast_mode=data.get("fast_mode", False),
        filtered_spec=data.get("filtered_spec"),
        version=data.get("version", ""),
    )


def save_plan(graph: TaskGraph, plan_path: Path) -> None:
    """Serialize a TaskGraph to JSON and write to disk.

    Args:
        graph: The task graph to persist.
        plan_path: Path to the plan.json file.
    """
    data: dict[str, Any] = {
        "metadata": _metadata_to_dict(graph.metadata),
        "nodes": {nid: _node_to_dict(node) for nid, node in graph.nodes.items()},
        "edges": [_edge_to_dict(edge) for edge in graph.edges],
        "order": graph.order,
    }

    # Ensure parent directory exists
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    plan_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_plan(plan_path: Path) -> TaskGraph | None:
    """Load a TaskGraph from a JSON plan file.

    Args:
        plan_path: Path to the plan.json file.

    Returns:
        The deserialized TaskGraph, or None if the file is missing
        or corrupted (with a logged warning).
    """
    if not plan_path.exists():
        logger.warning("Plan file not found: %s", plan_path)
        return None

    try:
        raw = plan_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupted plan file %s: %s", plan_path, exc)
        return None

    try:
        metadata = _metadata_from_dict(data.get("metadata", {}))
        nodes = {
            nid: _node_from_dict(node_data)
            for nid, node_data in data.get("nodes", {}).items()
        }
        edges = [_edge_from_dict(edge_data) for edge_data in data.get("edges", [])]
        order = data.get("order", [])

        return TaskGraph(
            nodes=nodes,
            edges=edges,
            order=order,
            metadata=metadata,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Invalid plan file structure %s: %s", plan_path, exc)
        return None
