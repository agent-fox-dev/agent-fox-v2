"""Plan persistence: serialize/deserialize TaskGraph to/from JSON.

Requirements: 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3, 02-REQ-6.4, 02-REQ-6.E1
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any

from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph

logger = logging.getLogger(__name__)


def _serialize(obj: object) -> dict[str, Any]:
    """Convert a dataclass to a JSON-safe dict (stringifies enums)."""
    raw = asdict(obj)  # type: ignore[arg-type]

    def _fixup(value: object) -> object:
        if isinstance(value, Enum):
            return str(value)
        if isinstance(value, dict):
            return {k: _fixup(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_fixup(v) for v in value]
        return value

    return _fixup(raw)  # type: ignore[return-value]


def _node_from_dict(data: dict[str, Any]) -> Node:
    """Deserialize a Node from a dictionary (handles defaults for older plans)."""
    return Node(
        id=data["id"],
        spec_name=data["spec_name"],
        group_number=data["group_number"],
        title=data["title"],
        optional=data["optional"],
        status=NodeStatus(data["status"]),
        subtask_count=data.get("subtask_count", 0),
        body=data.get("body", ""),
        archetype=data.get("archetype", "coder"),
        instances=data.get("instances", 1),
    )


def _metadata_from_dict(data: dict[str, Any]) -> PlanMetadata:
    """Deserialize PlanMetadata from a dictionary (handles defaults for older plans).

    Old plan.json files may contain legacy fields (specs_hash, config_hash) which
    are silently ignored for backward compatibility (63-REQ-3.E1).
    """
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
    data = _serialize(graph)

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
        nodes = {nid: _node_from_dict(node_data) for nid, node_data in data.get("nodes", {}).items()}
        edges = [Edge(**e) for e in data.get("edges", [])]
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


def load_plan_or_raise(plan_path: Path) -> TaskGraph:
    """Load the task graph from plan.json, raising on failure.

    Convenience wrapper around :func:`load_plan` that raises
    :class:`AgentFoxError` instead of returning ``None``.

    Args:
        plan_path: Path to .agent-fox/plan.json.

    Raises:
        AgentFoxError: If the plan file cannot be read.
    """
    from agent_fox.core.errors import AgentFoxError

    graph = load_plan(plan_path)
    if graph is None:
        raise AgentFoxError(
            "No plan file found. Run `agent-fox plan` first.",
            path=str(plan_path),
        )
    return graph
