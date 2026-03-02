"""Temporal queries: timeline construction and rendering.

Requirements: 13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import duckdb  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.temporal")


@dataclass(frozen=True)
class TimelineNode:
    """A single node in a rendered timeline."""

    fact_id: str
    content: str
    spec_name: str | None
    session_id: str | None
    commit_sha: str | None
    timestamp: str | None
    relationship: str  # "cause" | "effect" | "root"
    depth: int  # indentation level in timeline


@dataclass
class Timeline:
    """An ordered timeline of causally linked facts."""

    nodes: list[TimelineNode] = field(default_factory=list)
    query: str = ""

    def render(self, *, use_color: bool = True) -> str:
        """Render the timeline as indented text.

        Each node is rendered with indentation proportional to its depth.
        When use_color is False (stdout is not a TTY), no ANSI escape
        codes are included.
        """
        raise NotImplementedError


def build_timeline(
    conn: duckdb.DuckDBPyConnection,
    seed_fact_ids: list[str],
    *,
    max_depth: int = 10,
) -> Timeline:
    """Construct a timeline from seed facts by traversing the causal graph.

    1. For each seed fact, traverse the causal chain in both directions.
    2. Deduplicate facts that appear in multiple chains.
    3. Sort by timestamp, then by depth within the same timestamp.
    4. Return as a Timeline with ordered TimelineNodes.
    """
    raise NotImplementedError


def temporal_query(
    conn: duckdb.DuckDBPyConnection,
    question: str,
    query_embedding: list[float],
    *,
    top_k: int = 20,
    max_depth: int = 10,
) -> Timeline:
    """Execute a temporal query.

    1. Use the query embedding to find the top-k most similar facts
       via vector search (same as Fox Ball ask).
    2. From those seed facts, traverse the causal graph to build a
       timeline.
    3. Return the timeline for rendering and synthesis.
    """
    raise NotImplementedError
