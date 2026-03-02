"""Causal graph operations: add links, query causes/effects, traverse chains.

Requirements: 13-REQ-3.1, 13-REQ-3.2, 13-REQ-3.3, 13-REQ-3.4,
              13-REQ-3.E1, 13-REQ-2.E2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb  # noqa: F401

logger = logging.getLogger("agent_fox.knowledge.causal")


@dataclass(frozen=True)
class CausalLink:
    """A directed edge in the causal graph."""

    cause_id: str  # UUID as string
    effect_id: str  # UUID as string


@dataclass(frozen=True)
class CausalFact:
    """A fact with its position in a causal chain."""

    fact_id: str
    content: str
    spec_name: str | None
    session_id: str | None
    commit_sha: str | None
    created_at: str | None
    depth: int  # 0 = starting fact, positive = effects, negative = causes
    relationship: str  # "root" | "cause" | "effect"


def add_causal_link(
    conn: duckdb.DuckDBPyConnection,
    cause_id: str,
    effect_id: str,
) -> bool:
    """Insert a causal link into fact_causes.

    Validates that both fact IDs exist in memory_facts. Silently ignores
    duplicate links (idempotent). Returns True if a new link was inserted,
    False if it already existed or validation failed.
    """
    raise NotImplementedError


def get_causes(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
) -> list[CausalFact]:
    """Return all direct causes of the given fact.

    Queries fact_causes WHERE effect_id = fact_id, joining with
    memory_facts for content and provenance.
    """
    raise NotImplementedError


def get_effects(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
) -> list[CausalFact]:
    """Return all direct effects of the given fact.

    Queries fact_causes WHERE cause_id = fact_id, joining with
    memory_facts for content and provenance.
    """
    raise NotImplementedError


def traverse_causal_chain(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    *,
    max_depth: int = 10,
    direction: str = "both",  # "causes" | "effects" | "both"
) -> list[CausalFact]:
    """Traverse the causal graph from a starting fact.

    Performs breadth-first traversal following causal links up to
    max_depth. Returns all reachable facts with their depth relative
    to the starting fact. Causes have negative depth, effects have
    positive depth, the starting fact has depth 0.

    Direction controls traversal:
    - "causes": follow links backward (cause direction only)
    - "effects": follow links forward (effect direction only)
    - "both": follow links in both directions
    """
    raise NotImplementedError
