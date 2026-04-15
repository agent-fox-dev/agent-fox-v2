"""Unified adaptive retriever: multi-signal fusion via weighted RRF.

Replaces the sequential single-signal retrieval pipeline with a unified
AdaptiveRetriever that queries four signals in parallel (keyword, vector,
entity graph, causal chain), fuses results via weighted Reciprocal Rank
Fusion (RRF), and assembles context with causal ordering and salience-based
token budgeting.

Requirements: 104-REQ-1.*, 104-REQ-2.*, 104-REQ-3.*, 104-REQ-4.*, 104-REQ-5.*
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

import duckdb

# Re-export RetrievalConfig from config so callers can import from here.
from agent_fox.core.config import KnowledgeConfig, RetrievalConfig  # noqa: F401
from agent_fox.knowledge.causal import traverse_causal_chain
from agent_fox.knowledge.entity_query import find_related_facts

logger = logging.getLogger("agent_fox.knowledge.retrieval")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredFact:
    """A fact with its per-signal rank and final fused score."""

    fact_id: str
    content: str
    spec_name: str
    confidence: float
    created_at: str
    category: str
    score: float = 0.0


@dataclass(frozen=True)
class IntentProfile:
    """Per-signal weight multipliers derived from task context."""

    keyword_weight: float = 1.0
    vector_weight: float = 1.0
    entity_weight: float = 1.0
    causal_weight: float = 1.0


@dataclass(frozen=True)
class RetrievalResult:
    """Complete retrieval output for observability."""

    context: str
    intent_profile: IntentProfile
    anchor_count: int
    signal_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Intent profile derivation
# ---------------------------------------------------------------------------

# Profile table: (archetype, node_status) → (keyword, vector, entity, causal)
_PROFILES: dict[tuple[str, str], IntentProfile] = {
    ("coder", "fresh"): IntentProfile(keyword_weight=1.0, vector_weight=0.8, entity_weight=1.5, causal_weight=1.0),
    ("coder", "retry"): IntentProfile(keyword_weight=0.8, vector_weight=0.6, entity_weight=1.0, causal_weight=2.0),
    ("auditor", "*"): IntentProfile(keyword_weight=0.6, vector_weight=0.8, entity_weight=2.0, causal_weight=1.0),
    ("reviewer", "*"): IntentProfile(keyword_weight=1.0, vector_weight=1.5, entity_weight=0.8, causal_weight=1.0),
    ("verifier", "*"): IntentProfile(keyword_weight=0.8, vector_weight=0.6, entity_weight=1.5, causal_weight=1.5),
}

_DEFAULT_PROFILE = IntentProfile(
    keyword_weight=1.0,
    vector_weight=1.0,
    entity_weight=1.0,
    causal_weight=1.0,
)

_KNOWN_ARCHETYPES = frozenset({"coder", "auditor", "reviewer", "verifier"})


def derive_intent_profile(archetype: str, node_status: str) -> IntentProfile:
    """Derive signal weights from task context.

    Looks up (archetype, node_status) in the profile table. Archetypes
    with wildcard status ("*") match any node_status. Unknown archetypes
    fall back to a balanced default profile with all weights = 1.0.

    Requirements: 104-REQ-3.1, 104-REQ-3.2, 104-REQ-3.3, 104-REQ-3.E1
    """
    if archetype not in _KNOWN_ARCHETYPES:
        return _DEFAULT_PROFILE

    # Try exact match first, then wildcard
    profile = _PROFILES.get((archetype, node_status))
    if profile is not None:
        return profile

    profile = _PROFILES.get((archetype, "*"))
    if profile is not None:
        return profile

    return _DEFAULT_PROFILE


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def weighted_rrf_fusion(
    signal_lists: dict[str, list[ScoredFact]],
    profile: IntentProfile,
    k: int = 60,
) -> list[ScoredFact]:
    """Fuse ranked lists via weighted RRF.

    Computes score(fact) = sum(weight_i / (k + rank_i(fact))) for each
    signal i where the fact appears. Facts are deduplicated by fact_id;
    each fact accumulates contributions from every signal where it appears.

    Returns facts sorted by descending fused score.

    Requirements: 104-REQ-2.1, 104-REQ-2.2, 104-REQ-2.3, 104-REQ-2.E1
    """
    weights: dict[str, float] = {
        "keyword": profile.keyword_weight,
        "vector": profile.vector_weight,
        "entity": profile.entity_weight,
        "causal": profile.causal_weight,
    }

    scores: dict[str, float] = {}
    best_fact: dict[str, ScoredFact] = {}

    for signal_name, facts in signal_lists.items():
        if not facts:
            continue
        weight = weights.get(signal_name, 1.0)
        for rank_0, fact in enumerate(facts):
            rank = rank_0 + 1  # 1-based rank
            contribution = weight / (k + rank)
            if fact.fact_id not in scores:
                scores[fact.fact_id] = 0.0
                best_fact[fact.fact_id] = fact
            scores[fact.fact_id] += contribution

    result: list[ScoredFact] = []
    for fact_id, total_score in scores.items():
        original = best_fact[fact_id]
        result.append(
            ScoredFact(
                fact_id=original.fact_id,
                content=original.content,
                spec_name=original.spec_name,
                confidence=original.confidence,
                created_at=original.created_at,
                category=original.category,
                score=total_score,
            )
        )

    result.sort(key=lambda f: f.score, reverse=True)
    return result


# ---------------------------------------------------------------------------
# Signal functions
# ---------------------------------------------------------------------------


def _keyword_signal(
    spec_name: str,
    keywords: list[str],
    conn: duckdb.DuckDBPyConnection,
    confidence_threshold: float,
    top_k: int = 100,
) -> list[ScoredFact]:
    """Query memory_facts using spec name matching and keyword overlap.

    Facts are ranked by keyword_match_count + recency_bonus, with
    confidence filtering applied before scoring.

    Requirements: 104-REQ-1.2
    """
    try:
        rows = conn.execute(
            """
            SELECT id::VARCHAR, content, spec_name, category,
                   confidence, created_at, keywords
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND confidence >= ?
            """,
            [confidence_threshold],
        ).fetchall()
    except Exception:
        logger.debug("Keyword signal: DB query failed", exc_info=True)
        return []

    if not rows:
        return []

    task_keywords_lower: set[str] = {kw.lower() for kw in keywords}
    now = datetime.now(tz=UTC)

    # Filter: spec name match OR keyword overlap (at least one required)
    relevant: list[tuple] = []
    relevant_ts: list[datetime] = []

    for row in rows:
        _fid, _content, s_name, _cat, _conf, created_at, fact_keywords = row
        fact_keywords_lower = {kw.lower() for kw in (fact_keywords or [])}

        if s_name == spec_name or (task_keywords_lower and fact_keywords_lower & task_keywords_lower):
            relevant.append(row)
            try:
                ts = datetime.fromisoformat(str(created_at))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                ts = now
            relevant_ts.append(ts)

    if not relevant:
        return []

    oldest = min(relevant_ts)
    total_range = (now - oldest).total_seconds()

    scored: list[ScoredFact] = []
    for row, ts in zip(relevant, relevant_ts):
        fact_id, content, s_name, category, confidence, _created_at, fact_keywords = row
        fact_keywords_lower = {kw.lower() for kw in (fact_keywords or [])}

        keyword_match_count = len(fact_keywords_lower & task_keywords_lower)

        if total_range > 0:
            age_from_oldest = (ts - oldest).total_seconds()
            recency_bonus = age_from_oldest / total_range
        else:
            recency_bonus = 1.0

        score = float(keyword_match_count) + recency_bonus

        scored.append(
            ScoredFact(
                fact_id=str(fact_id),
                content=content or "",
                spec_name=s_name or "",
                confidence=float(confidence) if confidence is not None else 0.6,
                created_at=str(_created_at) if _created_at is not None else "",
                category=category or "decision",
                score=score,
            )
        )

    scored.sort(key=lambda f: f.score, reverse=True)
    return scored[:top_k]


def _vector_signal(
    task_description: str,
    conn: duckdb.DuckDBPyConnection,
    embedder,
    config: KnowledgeConfig,
    top_k: int | None = None,
) -> list[ScoredFact]:
    """Embed task description, query memory_embeddings via cosine similarity.

    Returns facts ranked by descending cosine similarity score.

    Requirements: 104-REQ-1.3
    """
    embedding = embedder.embed_text(task_description)
    dim = getattr(embedder, "embedding_dimensions", config.embedding_dimensions)
    k = top_k if top_k is not None else config.retrieval.vector_top_k

    try:
        rows = conn.execute(
            f"""
            SELECT
                CAST(f.id AS VARCHAR),
                f.content,
                COALESCE(f.category, '') AS category,
                COALESCE(f.spec_name, '') AS spec_name,
                CAST(f.confidence AS DOUBLE) AS confidence,
                COALESCE(CAST(f.created_at AS VARCHAR), '') AS created_at,
                1 - array_cosine_distance(
                    e.embedding, ?::FLOAT[{dim}]
                ) AS similarity
            FROM memory_embeddings e
            JOIN memory_facts f ON e.id = f.id
            WHERE f.superseded_by IS NULL
            ORDER BY similarity DESC
            LIMIT ?
            """,
            [embedding, k],
        ).fetchall()
    except Exception:
        logger.warning("Vector signal: DB query failed", exc_info=True)
        return []

    return [
        ScoredFact(
            fact_id=str(row[0]),
            content=row[1] or "",
            category=row[2] or "",
            spec_name=row[3] or "",
            confidence=float(row[4]) if row[4] is not None else 0.6,
            created_at=row[5] or "",
            score=float(row[6]),
        )
        for row in rows
    ]


def _entity_signal(
    touched_files: list[str],
    conn: duckdb.DuckDBPyConnection,
    max_depth: int = 2,
    max_entities: int = 50,
) -> list[ScoredFact]:
    """Call find_related_facts for each touched file, return entity-linked facts.

    BFS-traverses the entity graph from the given file paths and returns
    all non-superseded facts linked to traversed entities. Returns empty
    list if entity_graph tables do not exist or no entities match.

    Requirements: 104-REQ-1.4, 104-REQ-1.E1
    """
    if not touched_files:
        return []

    try:
        all_facts = []
        seen_ids: set[str] = set()

        for file_path in touched_files:
            facts = find_related_facts(conn, file_path, max_depth=max_depth, max_entities=max_entities)
            for fact in facts:
                if fact.id not in seen_ids:
                    seen_ids.add(fact.id)
                    all_facts.append(fact)

    except Exception:
        logger.debug("Entity signal: traversal failed", exc_info=True)
        return []

    return [
        ScoredFact(
            fact_id=fact.id,
            content=fact.content or "",
            spec_name=fact.spec_name or "",
            confidence=float(fact.confidence) if fact.confidence is not None else 0.6,
            created_at=fact.created_at or "",
            category=fact.category or "decision",
            score=float(fact.confidence) if fact.confidence is not None else 0.6,
        )
        for fact in all_facts
    ]


def _causal_signal(
    spec_name: str,
    conn: duckdb.DuckDBPyConnection,
    max_depth: int = 3,
) -> list[ScoredFact]:
    """Traverse fact_causes from same-spec facts, return proximity-ordered facts.

    Finds all facts in the given spec, traverses their causal chains up to
    max_depth, and returns facts ordered by proximity (ascending absolute depth).

    Requirements: 104-REQ-1.5, 104-REQ-1.E1
    """
    try:
        rows = conn.execute(
            """
            SELECT id::VARCHAR
            FROM memory_facts
            WHERE spec_name = ? AND superseded_by IS NULL
            """,
            [spec_name],
        ).fetchall()
    except Exception:
        logger.debug("Causal signal: DB query failed for spec %s", spec_name, exc_info=True)
        return []

    if not rows:
        return []

    seen_ids: set[str] = set()
    all_causal: list = []

    for row in rows:
        fact_id = str(row[0])
        try:
            causal_results = traverse_causal_chain(conn, fact_id, max_depth=max_depth)
        except Exception:
            logger.debug("Causal signal: traversal failed for fact %s", fact_id, exc_info=True)
            continue

        for cf in causal_results:
            if cf.fact_id not in seen_ids:
                seen_ids.add(cf.fact_id)
                all_causal.append(cf)

    if not all_causal:
        return []

    # Sort by proximity (ascending absolute depth, then by created_at for ties)
    all_causal.sort(key=lambda cf: (abs(cf.depth), cf.created_at or ""))

    result: list[ScoredFact] = []
    for cf in all_causal:
        proximity_score = 1.0 / (abs(cf.depth) + 1)
        result.append(
            ScoredFact(
                fact_id=cf.fact_id,
                content=cf.content or "",
                spec_name=cf.spec_name or "",
                confidence=0.6,  # CausalFact does not carry confidence
                created_at=cf.created_at or "",
                category="pattern",  # CausalFact does not carry category
                score=proximity_score,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _get_causal_edges_for_anchors(
    conn: duckdb.DuckDBPyConnection,
    fact_ids: list[str],
) -> dict[str, set[str]]:
    """Return causal edges between the given anchor fact IDs.

    Returns a dict: cause_id → set of effect_ids (both in fact_ids).
    """
    if len(fact_ids) < 2:
        return {fid: set() for fid in fact_ids}

    try:
        placeholders = ", ".join("?" for _ in fact_ids)
        rows = conn.execute(
            f"""
            SELECT CAST(cause_id AS VARCHAR), CAST(effect_id AS VARCHAR)
            FROM fact_causes
            WHERE cause_id IN ({placeholders})
              AND effect_id IN ({placeholders})
            """,
            fact_ids + fact_ids,
        ).fetchall()
    except Exception:
        logger.debug("Failed to query causal edges for context assembly", exc_info=True)
        return {fid: set() for fid in fact_ids}

    edges: dict[str, set[str]] = {fid: set() for fid in fact_ids}
    for cause_str, effect_str in rows:
        if cause_str in edges:
            edges[cause_str].add(effect_str)
    return edges


def _topological_sort_with_causal(
    facts: list[ScoredFact],
    conn: duckdb.DuckDBPyConnection,
) -> list[ScoredFact]:
    """Sort facts with causal predecessors before their effects.

    Uses Kahn's topological sort algorithm. Ties (no causal relationship
    between two facts) are broken by score (higher score first).

    Requirements: 104-REQ-4.1
    """
    if not facts:
        return []

    fact_by_id = {f.fact_id: f for f in facts}
    fact_ids = list(fact_by_id.keys())

    edges = _get_causal_edges_for_anchors(conn, fact_ids)

    # Compute in-degree for each fact
    in_degree: dict[str, int] = {fid: 0 for fid in fact_ids}
    for cause_id, effects in edges.items():
        for effect_id in effects:
            if effect_id in in_degree:
                in_degree[effect_id] += 1

    # Initialize queue with zero in-degree facts, highest score first
    ready = sorted(
        [fid for fid, deg in in_degree.items() if deg == 0],
        key=lambda fid: fact_by_id[fid].score,
        reverse=True,
    )
    queue: deque[str] = deque(ready)

    result: list[ScoredFact] = []
    while queue:
        current_id = queue.popleft()
        if current_id not in fact_by_id:
            continue
        result.append(fact_by_id[current_id])

        effects = edges.get(current_id, set())
        newly_ready: list[str] = []
        for effect_id in effects:
            if effect_id in in_degree:
                in_degree[effect_id] -= 1
                if in_degree[effect_id] == 0:
                    newly_ready.append(effect_id)

        # Insert newly ready facts sorted by score (highest first)
        newly_ready.sort(key=lambda fid: fact_by_id[fid].score, reverse=True)
        queue.extend(newly_ready)

    # Handle any remaining facts (cycles — should not occur in practice)
    processed_ids = {f.fact_id for f in result}
    remaining = sorted(
        [f for f in facts if f.fact_id not in processed_ids],
        key=lambda f: f.score,
        reverse=True,
    )
    result.extend(remaining)

    return result


def _one_line_summary(content: str, max_len: int = 80) -> str:
    """Extract a one-line summary from content, truncating if necessary."""
    first_line = content.split("\n")[0]
    if len(first_line) <= max_len:
        return first_line
    return first_line[: max_len - 3] + "..."


def _render_fact_section(fact: ScoredFact, tier: str, *, full_detail: bool) -> str:
    """Render a single fact section with provenance header."""
    conf_str = f"{fact.confidence:.1f}"
    short_id = fact.fact_id[:8] if len(fact.fact_id) >= 8 else fact.fact_id
    header = f"\n### [{tier}] {short_id} — spec: {fact.spec_name} (confidence: {conf_str})\n"
    if full_detail:
        return header + fact.content + "\n"
    else:
        return header + _one_line_summary(fact.content) + "\n"


def assemble_ranked_context(
    anchors: list[ScoredFact],
    conn: duckdb.DuckDBPyConnection,
    config: RetrievalConfig,
) -> str:
    """Format scored facts into ordered context with provenance and budgeting.

    1. Select top max_facts by score.
    2. Topological sort by causal precedence (causes before effects).
    3. Assign salience tiers: top 20% high, next 40% medium, bottom 40% low.
    4. If all facts fit at full detail within the budget, render all fully.
    5. Otherwise: high=full, medium=one-line summary, low=omit if over budget.
    6. Final truncation guarantees len(output) <= token_budget.

    Requirements: 104-REQ-4.1, 104-REQ-4.2, 104-REQ-4.3, 104-REQ-4.E1
    """
    if not anchors:
        return ""

    # Select top max_facts by score
    selected = sorted(anchors, key=lambda f: f.score, reverse=True)[: config.max_facts]
    n = len(selected)

    # Assign salience tiers based on score percentile
    high_count = max(1, round(n * 0.2))
    medium_count = max(high_count, round(n * 0.6))

    sorted_by_score = sorted(selected, key=lambda f: f.score, reverse=True)
    tier_map: dict[str, str] = {}
    for i, fact in enumerate(sorted_by_score):
        if i < high_count:
            tier_map[fact.fact_id] = "high"
        elif i < medium_count:
            tier_map[fact.fact_id] = "medium"
        else:
            tier_map[fact.fact_id] = "low"

    # Topological sort: causal predecessors before effects
    sorted_facts = _topological_sort_with_causal(selected, conn)

    preamble = "## Knowledge Context\n"

    # Try to render all at full detail first (104-REQ-4.E1)
    full_render = preamble
    for fact in sorted_facts:
        tier = tier_map.get(fact.fact_id, "low")
        full_render += _render_fact_section(fact, tier, full_detail=True)

    if len(full_render) <= config.token_budget:
        return full_render[: config.token_budget]

    # Budget exceeded: apply salience-based trimming
    result = preamble
    omitted_count = 0

    for fact in sorted_facts:
        tier = tier_map.get(fact.fact_id, "low")

        if tier == "high":
            section = _render_fact_section(fact, tier, full_detail=True)
        elif tier == "medium":
            section = _render_fact_section(fact, tier, full_detail=False)
        else:  # low
            section = _render_fact_section(fact, tier, full_detail=True)

        if len(result) + len(section) <= config.token_budget:
            result += section
        else:
            if tier == "low":
                omitted_count += 1
            # For high/medium: also skip if no budget, count as omitted
            elif tier in ("medium", "high"):
                omitted_count += 1

    if omitted_count > 0:
        omit_msg = f"\n<!-- {omitted_count} additional fact(s) omitted (token budget) -->\n"
        if len(result) + len(omit_msg) <= config.token_budget:
            result += omit_msg

    return result[: config.token_budget]


# ---------------------------------------------------------------------------
# AdaptiveRetriever
# ---------------------------------------------------------------------------


class AdaptiveRetriever:
    """Unified retriever fusing four signals via weighted RRF.

    Queries keyword, vector, entity graph, and causal chain signals,
    fuses their results via weighted RRF with intent-derived weights,
    and assembles a formatted context string with causal ordering and
    salience-based token budgeting.

    Requirements: 104-REQ-1.1, 104-REQ-1.E1, 104-REQ-1.E2, 104-REQ-1.E3
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        config: RetrievalConfig,
        embedder=None,
    ) -> None:
        self._conn = conn
        self._config = config
        self._embedder = embedder

    def retrieve(
        self,
        *,
        spec_name: str,
        archetype: str,
        node_status: str,
        touched_files: list[str],
        task_description: str,
        confidence_threshold: float = 0.5,
    ) -> RetrievalResult:
        """Run all four signals, fuse via RRF, assemble formatted context.

        Requirements: 104-REQ-1.1, 104-REQ-5.1, 104-REQ-5.2
        """
        # Derive intent profile
        profile = derive_intent_profile(archetype, node_status)

        signal_lists: dict[str, list[ScoredFact]] = {}

        # Keyword signal
        task_keywords = task_description.split() if task_description else []
        kw_results = _keyword_signal(
            spec_name,
            task_keywords,
            self._conn,
            confidence_threshold,
            top_k=self._config.keyword_top_k,
        )
        signal_lists["keyword"] = kw_results

        # Vector signal (graceful degradation on failure)
        if self._embedder is not None:
            try:
                knowledge_config = KnowledgeConfig(
                    embedding_dimensions=getattr(self._embedder, "embedding_dimensions", 384)
                )
                vec_results = _vector_signal(
                    task_description,
                    self._conn,
                    self._embedder,
                    knowledge_config,
                    top_k=self._config.vector_top_k,
                )
                signal_lists["vector"] = vec_results
            except Exception:
                logger.warning(
                    "Vector signal failed for spec '%s'; excluding from RRF",
                    spec_name,
                    exc_info=True,
                )
                signal_lists["vector"] = []
        else:
            signal_lists["vector"] = []

        # Entity signal
        ent_results = _entity_signal(
            touched_files,
            self._conn,
            max_depth=self._config.entity_max_depth,
            max_entities=self._config.entity_max_entities,
        )
        signal_lists["entity"] = ent_results

        # Causal signal
        cau_results = _causal_signal(
            spec_name,
            self._conn,
            max_depth=self._config.causal_max_depth,
        )
        signal_lists["causal"] = cau_results

        # Weighted RRF fusion
        anchors = weighted_rrf_fusion(signal_lists, profile, k=self._config.rrf_k)
        anchors = anchors[: self._config.max_facts]

        # Assemble formatted context
        context = assemble_ranked_context(anchors, self._conn, self._config)

        signal_counts = {name: len(lst) for name, lst in signal_lists.items()}

        return RetrievalResult(
            context=context,
            intent_profile=profile,
            anchor_count=len(anchors),
            signal_counts=signal_counts,
        )
