"""Knowledge query: Oracle RAG pipeline, pattern detection, and temporal queries.

Combines oracle.py, patterns.py, and temporal.py into a unified query module.

Requirements: 12-REQ-5.1, 12-REQ-5.2, 12-REQ-5.3, 12-REQ-6.1,
              12-REQ-8.1, 12-REQ-2.E2,
              13-REQ-5.1, 13-REQ-5.2, 13-REQ-5.3, 13-REQ-5.E1,
              13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import anthropic
import duckdb

from agent_fox.core.client import create_anthropic_client
from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.core.models import resolve_model
from agent_fox.core.token_tracker import record_auxiliary_usage
from agent_fox.knowledge.causal import CausalFact, traverse_causal_chain
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.search import SearchResult, VectorSearch

# ---------------------------------------------------------------------------
# Oracle (merged from oracle.py)
# ---------------------------------------------------------------------------

logger = logging.getLogger("agent_fox.knowledge.oracle")


@dataclass(frozen=True)
class OracleAnswer:
    """The result of an oracle query."""

    answer: str
    sources: list[SearchResult]
    contradictions: list[str] | None
    confidence: float  # [0.0, 1.0]


class Oracle:
    """RAG pipeline for the agent-fox ask command.

    Embeds a question, retrieves relevant facts via vector search,
    assembles context with provenance, and synthesizes a grounded
    answer using the STANDARD model in a single API call.
    """

    def __init__(
        self,
        embedder: EmbeddingGenerator,
        search: VectorSearch,
        config: KnowledgeConfig,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._config = config
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        """Lazy-initialize the Anthropic client for synthesis."""
        if self._client is None:
            self._client = create_anthropic_client()
        return self._client

    def ask(self, question: str) -> OracleAnswer:
        """Run the full RAG pipeline for a question.

        Steps:
        1. Embed the question using the configured embedding model.
        2. Perform vector search to retrieve the top-k most similar
           facts.
        3. Assemble a context prompt with retrieved facts and their
           provenance (spec name, session ID, commit SHA).
        4. Call the synthesis model (STANDARD / Sonnet) with the
           context prompt and question. Single API call, not streaming.
        5. Parse the response for the answer, source citations,
           contradiction flags, and confidence level.

        Returns:
            An OracleAnswer with the synthesized answer, sources,
            any detected contradictions, and a confidence indicator.

        Raises:
            KnowledgeStoreError: If the query embedding fails
                (embedding API unavailable).
        """
        # Step 1: Embed the question
        query_embedding = self._embedder.embed_text(question)
        if query_embedding is None:
            raise KnowledgeStoreError(
                "Failed to embed question. The embedding API may be "
                "unavailable. Please retry."
            )

        # Step 2: Vector search for top-k similar facts
        results = self._search.search(query_embedding)

        # Step 3: Assemble context with provenance
        context = self._assemble_context(results)

        # Step 4: Synthesize answer via single API call (not streaming)
        prompt = self._build_synthesis_prompt(question, context)
        model = resolve_model(self._config.ask_synthesis_model)

        response = self.client.messages.create(
            model=model.model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        # Track auxiliary token usage (34-REQ-1.5)
        usage = getattr(response, "usage", None)
        if usage is not None:
            record_auxiliary_usage(
                input_tokens=getattr(usage, "input_tokens", 0),
                output_tokens=getattr(usage, "output_tokens", 0),
                model=model.model_id,
            )
        else:
            logger.warning("API response for oracle synthesis lacks usage data")
            record_auxiliary_usage(0, 0, model.model_id)

        response_text = response.content[0].text  # type: ignore[union-attr]

        # Step 5: Parse the response
        return self._parse_synthesis_response(response_text, results)

    def _assemble_context(self, results: list[SearchResult]) -> str:
        """Build a context string from search results with provenance.

        Each fact is formatted with its source metadata so the
        synthesis model can cite sources and detect contradictions.
        """
        if not results:
            return "No relevant facts found."

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            provenance_parts: list[str] = []
            if r.spec_name:
                provenance_parts.append(f"spec: {r.spec_name}")
            if r.session_id:
                provenance_parts.append(f"session: {r.session_id}")
            if r.commit_sha:
                provenance_parts.append(f"commit: {r.commit_sha}")
            provenance = ", ".join(provenance_parts) if provenance_parts else "unknown"

            parts.append(
                f"[Fact {i}] (id: {r.fact_id}, {provenance}, "
                f"similarity: {r.similarity:.2f})\n{r.content}"
            )

        return "\n\n".join(parts)

    def _build_synthesis_prompt(
        self,
        question: str,
        context: str,
    ) -> str:
        """Build the prompt for the synthesis model.

        Instructs the model to:
        - Answer the question using only the provided facts.
        - Cite sources by fact ID and provenance.
        - Flag any contradictions between facts.
        - Indicate confidence level (high/medium/low).
        - Not hallucinate beyond the provided context.
        """
        return (
            "You are a knowledge oracle for a software project. Answer the "
            "question below using ONLY the provided facts. Do not hallucinate "
            "or add information beyond what the facts contain.\n\n"
            "Instructions:\n"
            "1. Provide a clear, grounded answer based on the facts.\n"
            "2. Cite which facts support your answer.\n"
            "3. If any facts contradict each other, flag each contradiction "
            "on its own line starting with 'CONTRADICTION:' followed by a "
            "description of the conflicting facts.\n"
            "4. Do not invent information that is not in the facts.\n\n"
            f"## Facts\n\n{context}\n\n"
            f"## Question\n\n{question}"
        )

    def _determine_confidence(self, results: list[SearchResult]) -> float:
        """Determine confidence based on result count and similarity.

        Returns a float in [0.0, 1.0]:
        - 0.9: 3+ results with similarity > 0.7
        - 0.6: 1-2 results with similarity > 0.5
        - 0.3: fewer or lower-similarity results

        Requirements: 37-REQ-4.1, 37-REQ-4.2
        """
        high_quality = [r for r in results if r.similarity > 0.7]
        if len(high_quality) >= 3:
            return 0.9

        medium_quality = [r for r in results if r.similarity > 0.5]
        if len(medium_quality) >= 1:
            return 0.6

        return 0.3

    def _parse_synthesis_response(
        self,
        response_text: str,
        results: list[SearchResult],
    ) -> OracleAnswer:
        """Parse the synthesis model's response into an OracleAnswer.

        Extracts the answer text, source citations, contradiction
        flags, and confidence indicator.
        """
        # Extract contradiction markers anywhere in the text.
        # The synthesis model may place "CONTRADICTION:" at the start of a
        # line or inline within a sentence.
        contradictions: list[str] = []
        for match in re.finditer(
            r"CONTRADICTION:\s*([^\n.]*(?:\.[^\n]*)?)", response_text, re.IGNORECASE
        ):
            desc = match.group(1).strip()
            if desc:
                contradictions.append(desc)
            else:
                contradictions.append(match.group(0).strip())

        # Build the answer text by removing contradiction markers
        answer = re.sub(
            r"CONTRADICTION:\s*[^\n]*", "", response_text, flags=re.IGNORECASE
        ).strip()
        confidence = self._determine_confidence(results)

        return OracleAnswer(
            answer=answer,
            sources=results,
            contradictions=contradictions if contradictions else None,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# Pattern detection (merged from patterns.py)
# ---------------------------------------------------------------------------

_patterns_logger = logging.getLogger("agent_fox.knowledge.patterns")


@dataclass(frozen=True)
class Pattern:
    """A recurring cause-effect pattern detected in history."""

    trigger: str  # e.g., "changes to src/auth/"
    effect: str  # e.g., "test_payments.py failures"
    occurrences: int  # number of times this pattern was observed
    last_seen: str  # ISO timestamp of most recent occurrence
    confidence: float  # 0.9 (5+), 0.7 (3-4), 0.4 (2)


def _assign_confidence(occurrences: int) -> float:
    """Assign confidence as float based on occurrence count.

    - 5+ occurrences → 0.9
    - 3-4 occurrences → 0.7
    - 2 or fewer → 0.4

    Requirements: 37-REQ-4.3, 37-REQ-4.4
    """
    if occurrences >= 5:
        return 0.9
    if occurrences >= 3:
        return 0.7
    return 0.4


def detect_patterns(
    conn: duckdb.DuckDBPyConnection,
    *,
    min_occurrences: int = 2,
) -> list[Pattern]:
    """Detect recurring cause-effect patterns.

    Analysis algorithm:
    1. Query session_outcomes for all sessions, grouping by spec_name
       and touched_path.
    2. For each pair of (path_changed, subsequent_failure), count
       co-occurrences across sessions.
    3. Cross-reference with fact_causes to find causal chains that
       connect the change to the failure.
    4. Rank patterns by occurrence count, then by recency.
    5. Assign confidence: high (5+ occurrences), medium (3-4), low (2).

    Returns patterns sorted by occurrence count descending.
    """
    query = """
    SELECT
        changed.touched_path AS trigger_path,
        failed.touched_path  AS failed_path,
        COUNT(*)             AS occurrences,
        MAX(failed.created_at) AS last_seen
    FROM session_outcomes changed
    JOIN session_outcomes failed
        ON changed.spec_name != failed.spec_name
        AND changed.created_at <= failed.created_at
        AND failed.created_at <= changed.created_at + INTERVAL 1 DAY
        AND failed.status = 'failed'
        AND changed.status = 'completed'
    -- Validate against causal graph: require a causal link between
    -- facts from the triggering and failing sessions.
    JOIN memory_facts mf_cause
        ON mf_cause.session_id = changed.node_id
    JOIN memory_facts mf_effect
        ON mf_effect.session_id = failed.node_id
    JOIN fact_causes fc
        ON fc.cause_id = mf_cause.id
        AND fc.effect_id = mf_effect.id
    WHERE changed.touched_path IS NOT NULL
      AND failed.touched_path IS NOT NULL
    GROUP BY changed.touched_path, failed.touched_path
    HAVING COUNT(*) >= ?
    ORDER BY occurrences DESC, last_seen DESC
    """
    try:
        rows = conn.execute(query, [min_occurrences]).fetchall()
    except Exception:
        _patterns_logger.warning("Pattern detection query failed", exc_info=True)
        return []

    patterns: list[Pattern] = []
    for row in rows:
        trigger_path = str(row[0])
        failed_path = str(row[1])
        occurrences = int(row[2])
        last_seen = str(row[3]) if row[3] is not None else ""

        patterns.append(
            Pattern(
                trigger=trigger_path,
                effect=f"{failed_path} failures",
                occurrences=occurrences,
                last_seen=last_seen,
                confidence=_assign_confidence(occurrences),
            )
        )

    return patterns


def render_patterns(patterns: list[Pattern], *, use_color: bool = True) -> str:
    """Render detected patterns as formatted text.

    Each pattern is rendered as:
        trigger -> effect (N occurrences, last seen DATE, confidence LEVEL)

    When use_color is False, no ANSI escape codes are included.
    """
    if not patterns:
        return "No recurring patterns detected. More session history is needed."

    lines: list[str] = []
    for p in patterns:
        line = (
            f"{p.trigger} -> {p.effect} "
            f"({p.occurrences} occurrences, "
            f"last seen {p.last_seen}, "
            f"confidence {p.confidence})"
        )
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Temporal query (merged from temporal.py)
# ---------------------------------------------------------------------------

_temporal_logger = logging.getLogger("agent_fox.knowledge.temporal")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]?")


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
            content = _ANSI_RE.sub("", node.content)
            ts = _ANSI_RE.sub("", node.timestamp or "unknown")
            spec = _ANSI_RE.sub("", node.spec_name or "n/a")
            session = _ANSI_RE.sub("", node.session_id or "n/a")
            commit = _ANSI_RE.sub("", node.commit_sha or "n/a")

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
        _temporal_logger.warning("Temporal vector search failed", exc_info=True)
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
        _temporal_logger.info("Temporal query found no matching facts")
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
