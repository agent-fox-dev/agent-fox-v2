"""Temporal query: causal timeline construction and rendering.

Requirements: 13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb

from agent_fox.core._text_utils import escape_markdown, strip_ansi
from agent_fox.knowledge.causal import CausalFact, traverse_causal_chain
from agent_fox.knowledge.search import SearchResult

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
    """A causal timeline built from a temporal query."""

    nodes: list[TimelineNode]
    query: str

    def render(self, *, use_color: bool = True) -> str:
        """Render the timeline as indented text.

        Each node is rendered with indentation proportional to its depth.
        When use_color is False (stdout is not a TTY), no ANSI escape
        codes are included.

        Requirements: 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
        """
        if not self.nodes:
            return "No causal timeline found for this query."

        lines: list[str] = []
        for node in self.nodes:
            indent = "  " * max(0, node.depth)
            if node.relationship == "effect":
                connector = "-> "
            elif node.relationship == "cause":
                connector = "<- "
            else:
                connector = "** "

            # 13-REQ-6.3: always emit plain text (strip any ANSI
            # escapes that may be embedded in stored data).
            # Issue #193: escape markdown special characters.
            content = escape_markdown(strip_ansi(node.content))
            ts = escape_markdown(strip_ansi(node.timestamp or "unknown"))
            spec = escape_markdown(strip_ansi(node.spec_name or "n/a"))
            session = escape_markdown(strip_ansi(node.session_id or "n/a"))
            commit = escape_markdown(strip_ansi(node.commit_sha or "n/a"))

            line_1 = f"{indent}{connector}{content}"
            line_2 = f"{indent}   [{ts}] spec:{spec} session:{session} commit:{commit}"
            lines.append(line_1)
            lines.append(line_2)

        return "\n".join(lines)


def _causal_fact_to_node(fact: CausalFact) -> TimelineNode:
    """Convert a CausalFact to a TimelineNode."""
    return TimelineNode(
        fact_id=fact.fact_id,
        content=fact.content,
        spec_name=fact.spec_name,
        session_id=fact.session_id,
        commit_sha=fact.commit_sha,
        timestamp=fact.created_at,
        relationship=fact.relationship,
        depth=fact.depth,
    )


def _vector_search(
    conn: duckdb.DuckDBPyConnection,
    query_embedding: list[float],
    top_k: int,
) -> list[SearchResult]:
    """Run vector similarity search for temporal query seeds."""
    dim = len(query_embedding)
    query = f"""
        SELECT
            CAST(f.id AS VARCHAR) AS fact_id,
            f.content,
            COALESCE(f.category, '') AS category,
            COALESCE(f.spec_name, '') AS spec_name,
            CAST(f.session_id AS VARCHAR) AS session_id,
            CAST(f.commit_sha AS VARCHAR) AS commit_sha,
            1 - array_cosine_distance(
                e.embedding, ?::FLOAT[{dim}]
            ) AS similarity
        FROM memory_embeddings e
        JOIN memory_facts f ON e.id = f.id
        WHERE f.superseded_by IS NULL
        ORDER BY similarity DESC
        LIMIT ?
    """
    try:
        rows = conn.execute(query, [query_embedding, top_k]).fetchall()
    except duckdb.Error:
        logger.warning("Temporal vector search failed", exc_info=True)
        return []

    return [
        SearchResult(
            fact_id=row[0],
            content=row[1],
            category=row[2],
            spec_name=row[3],
            session_id=row[4],
            commit_sha=row[5],
            similarity=float(row[6]),
        )
        for row in rows
    ]


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
       via vector search.
    2. From those seed facts, traverse the causal graph to build a
       timeline.
    3. Return the timeline for rendering and synthesis.

    Requirements: 13-REQ-4.1, 13-REQ-4.2
    """
    # Step 1: Vector search for seed facts
    search_results = _vector_search(conn, query_embedding, top_k)

    if not search_results:
        logger.info("Temporal query found no matching facts")
        return Timeline(nodes=[], query=question)

    # Step 2: Traverse causal graph from each seed fact
    seen_ids: set[str] = set()
    all_nodes: list[TimelineNode] = []

    for result in search_results:
        if result.fact_id in seen_ids:
            continue

        chain = traverse_causal_chain(
            conn,
            result.fact_id,
            max_depth=max_depth,
            direction="both",
        )

        for causal_fact in chain:
            if causal_fact.fact_id not in seen_ids:
                seen_ids.add(causal_fact.fact_id)
                all_nodes.append(_causal_fact_to_node(causal_fact))

    # Sort by timestamp then depth for consistent rendering
    all_nodes.sort(key=lambda n: (n.timestamp or "", n.depth))

    return Timeline(nodes=all_nodes, query=question)
