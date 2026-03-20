"""Node ID parsing utilities.

Centralizes parsing of the ``{spec_name}:{group_number}[:{role}]`` format
used throughout the codebase for task graph node identifiers.
"""

from __future__ import annotations

from typing import NamedTuple


class ParsedNodeId(NamedTuple):
    """Components of a parsed node ID."""

    spec_name: str
    group_number: int
    role: str | None  # e.g. "skeptic", "auditor", "verifier", "oracle"


def parse_node_id(node_id: str) -> ParsedNodeId:
    """Parse a node ID into its components.

    Format: ``{spec_name}:{group_number}[:{role}]``

    Examples::

        >>> parse_node_id("11_echo_server:3")
        ParsedNodeId(spec_name='11_echo_server', group_number=3, role=None)
        >>> parse_node_id("11_echo_server:3:skeptic")
        ParsedNodeId(spec_name='11_echo_server', group_number=3, role='skeptic')
        >>> parse_node_id("11_echo_server")
        ParsedNodeId(spec_name='11_echo_server', group_number=0, role=None)
    """
    parts = node_id.split(":")
    spec_name = parts[0]
    group_number = int(parts[1]) if len(parts) > 1 else 0
    role = parts[2] if len(parts) > 2 else None
    return ParsedNodeId(spec_name, group_number, role)


def spec_name_of(node_id: str) -> str:
    """Extract just the spec name from a node ID.

    Equivalent to ``parse_node_id(node_id).spec_name`` but avoids
    parsing the group number.
    """
    idx = node_id.find(":")
    return node_id[:idx] if idx >= 0 else node_id
