"""Knowledge consolidation pipeline.

Runs automatically during orchestration sync barrier and end-of-run.
Executes six ordered steps: entity graph refresh, fact-entity linking,
git verification, cross-spec merging, pattern promotion, and causal chain
pruning.

Requirements: 96-REQ-1.*, 96-REQ-2.*, 96-REQ-3.*, 96-REQ-4.*, 96-REQ-5.*,
              96-REQ-6.*, 96-REQ-7.*
"""

from __future__ import annotations

import contextvars
import json
import logging
import subprocess
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
from anthropic.types import TextBlock

from agent_fox.knowledge.entities import AnalysisResult, LinkResult
from agent_fox.knowledge.entity_linker import link_facts
from agent_fox.knowledge.static_analysis import analyze_codebase

if TYPE_CHECKING:
    from agent_fox.knowledge.embeddings import EmbeddingGenerator
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Deterministic sentinel UUID for stale facts invalidated by git verification.
# uuid5(NAMESPACE_DNS, "agent-fox.consolidation.stale")
CONSOLIDATION_STALE_SENTINEL: uuid.UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "agent-fox.consolidation.stale")

# Default similarity threshold for clustering
_DEFAULT_MERGE_THRESHOLD = 0.85
_DEFAULT_PATTERN_THRESHOLD = 0.85

# Minimum estimated USD cost of a single LLM call for budget pre-checks.
# Prevents LLM steps from running when the remaining budget is too small
# to afford even one call (96-REQ-7.E1).
_MIN_LLM_STEP_COST = 0.01

# ContextVar to prevent infinite recursion when the module-level
# run_consolidation is patched and the original function delegates to the mock,
# which in turn calls the original again.
_is_delegating: contextvars.ContextVar[bool] = contextvars.ContextVar("_consolidation_delegating", default=False)

# ---------------------------------------------------------------------------
# LLM prompt templates
# ---------------------------------------------------------------------------

MERGE_PROMPT = """\
You are a knowledge consolidation system. Given a cluster of semantically \
similar facts from different specifications, decide whether to MERGE them \
into a single consolidated fact or LINK them with causal edges.

Output valid JSON only (no markdown, no explanation):
{"action": "merge" | "link", "content": "...consolidated content if merge..."}

If action is "merge", provide a content string that best captures all facts.
If action is "link", content is optional."""

PATTERN_PROMPT = """\
You are a knowledge pattern analyzer. Given a group of facts from 3 or more \
different specifications, determine whether they represent a genuine recurring \
pattern in the codebase.

Output valid JSON only (no markdown, no explanation):
{"is_pattern": true | false, "description": "...pattern description if true..."}"""

CHAIN_PROMPT = """\
You are a knowledge graph pruner. Given three facts A, B, C where A→B→C \
and A→C causal relationships exist, determine if B provides independent value \
as a causal intermediate (i.e. B explains something that cannot be inferred \
from A→C alone).

Output valid JSON only (no markdown, no explanation):
{"meaningful": true | false, "reason": "...brief explanation..."}"""

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerificationResult:
    """Counts from the git verification step."""

    facts_checked: int
    superseded_count: int  # all linked files deleted
    decayed_count: int  # files significantly changed → confidence halved
    unchanged_count: int


@dataclass(frozen=True)
class MergeResult:
    """Counts from the cross-spec fact merging step."""

    clusters_found: int
    facts_merged: int  # original facts superseded by merge
    facts_linked: int  # causal edges added (link decision)
    consolidated_created: int


@dataclass(frozen=True)
class PromotionResult:
    """Counts from the pattern promotion step."""

    candidates_found: int
    patterns_confirmed: int
    pattern_facts_created: int


@dataclass(frozen=True)
class PruneResult:
    """Counts from the causal chain pruning step."""

    chains_evaluated: int
    intermediates_pruned: int
    edges_removed: int


@dataclass(frozen=True)
class ConsolidationResult:
    """Full result of a consolidation pipeline run."""

    entity_refresh: AnalysisResult | None
    facts_linked: int
    verification: VerificationResult | None
    merging: MergeResult | None
    promotion: PromotionResult | None
    pruning: PruneResult | None
    total_llm_cost: float
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _entity_graph_tables_exist(conn: duckdb.DuckDBPyConnection) -> bool:
    """Return True if entity graph tables (v8 migration) are present."""
    try:
        conn.execute("SELECT 1 FROM fact_entities LIMIT 0")
        conn.execute("SELECT 1 FROM entity_graph LIMIT 0")
        return True
    except Exception:
        return False


def _count_active_facts(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the number of active (non-superseded) facts."""
    try:
        row = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _compute_change_ratio(
    commit_sha: str,
    file_path: str,
    repo_root: Path,
) -> float | None:
    """Compute (insertions + deletions) / current_line_count via git diff.

    Runs ``git diff --numstat {commit_sha} HEAD -- {file_path}`` to measure
    how much the file has changed since the fact was recorded.

    Returns None if the file cannot be read or git fails.
    Returns 0.0 if git reports no changes.

    Zero-line files return None to avoid division by zero (96-REQ-3.3).
    """
    abs_path = repo_root / file_path
    try:
        content = abs_path.read_text(errors="replace")
        current_lines = len(content.splitlines())
    except OSError:
        return None

    if current_lines == 0:
        # Avoid division by zero; treat as no change
        return None

    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", commit_sha, "HEAD", "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
    except Exception:
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return 0.0

    # Parse numstat output: "insertions\tdeletions\tpath"
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                insertions = int(parts[0])
                deletions = int(parts[1])
                return (insertions + deletions) / current_lines
            except (ValueError, ZeroDivisionError):
                return None

    return 0.0


def _union_find_clusters(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Group IDs into connected-component clusters via union-find."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent.get(x, x), parent.get(x, x))
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for id1, id2 in pairs:
        if id1 not in parent:
            parent[id1] = id1
        if id2 not in parent:
            parent[id2] = id2
        union(id1, id2)

    cluster_map: dict[str, list[str]] = defaultdict(list)
    for fid in parent:
        cluster_map[find(fid)].append(fid)

    return [ids for ids in cluster_map.values() if len(ids) >= 2]


async def _call_llm_json(model: str, prompt: str, context: dict) -> dict:
    """Call an LLM and return the parsed JSON response.

    Sends a single-turn message with the prompt and JSON-serialized context.
    Raises on API error or JSON parse failure.
    """
    from agent_fox.core.client import create_async_anthropic_client

    client = create_async_anthropic_client()
    try:
        full_prompt = f"{prompt}\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": full_prompt}],
        )

        block = response.content[0]
        if not isinstance(block, TextBlock):
            raise TypeError(f"Expected TextBlock, got {type(block).__name__}")
        text = block.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(line for line in lines if not line.startswith("```")).strip()

        return json.loads(text)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Pipeline step implementations
# ---------------------------------------------------------------------------


def _refresh_entity_graph(
    conn: duckdb.DuckDBPyConnection,
    repo_root: Path,
) -> AnalysisResult:
    """Call analyze_codebase to refresh the entity graph.

    Requirements: 96-REQ-2.1
    """
    return analyze_codebase(repo_root, conn)


def _link_unlinked_facts(
    conn: duckdb.DuckDBPyConnection,
    repo_root: Path,
) -> LinkResult:
    """Find unlinked facts and pass them to link_facts.

    An "unlinked fact" is an active fact with no row in fact_entities.

    Requirements: 96-REQ-2.2
    """
    from agent_fox.knowledge.store import load_all_facts

    all_facts = load_all_facts(conn)
    if not all_facts:
        return LinkResult(facts_processed=0, links_created=0, facts_skipped=0)

    # Find fact IDs that already have entity links
    try:
        rows = conn.execute("SELECT DISTINCT CAST(fact_id AS VARCHAR) FROM fact_entities").fetchall()
        linked_ids = {r[0] for r in rows}
    except Exception:
        linked_ids = set()

    unlinked = [f for f in all_facts if f.id not in linked_ids]

    if not unlinked:
        return LinkResult(facts_processed=0, links_created=0, facts_skipped=0)

    return link_facts(conn, unlinked, repo_root)


def _verify_against_git(
    conn: duckdb.DuckDBPyConnection,
    repo_root: Path,
    change_ratio_threshold: float = 0.5,
) -> VerificationResult:
    """Verify active facts against current codebase state.

    For each active fact with file entity links:
    - If ALL linked files are deleted → supersede with sentinel
    - If fact has commit_sha and any linked file changed significantly
      (change ratio > threshold) → halve confidence

    Requirements: 96-REQ-3.1, 96-REQ-3.2, 96-REQ-3.3, 96-REQ-3.4,
                  96-REQ-3.E1, 96-REQ-3.E2
    """
    # Check if entity graph tables exist
    if not _entity_graph_tables_exist(conn):
        return VerificationResult(0, 0, 0, 0)

    # Query active facts with at least one file entity link
    try:
        rows = conn.execute(
            """
            SELECT f.id, f.commit_sha, f.confidence, eg.entity_path
            FROM memory_facts f
            JOIN fact_entities fe ON CAST(f.id AS VARCHAR) = CAST(fe.fact_id AS VARCHAR)
            JOIN entity_graph eg ON CAST(fe.entity_id AS VARCHAR) = CAST(eg.id AS VARCHAR)
                AND eg.entity_type = 'file'
            WHERE f.superseded_by IS NULL
            """
        ).fetchall()
    except Exception:
        logger.warning("Failed to query fact-entity links for git verification", exc_info=True)
        return VerificationResult(0, 0, 0, 0)

    if not rows:
        return VerificationResult(0, 0, 0, 0)

    # Group by fact: fact_id -> {commit_sha, confidence, file_paths}
    facts_data: dict[str, dict[str, Any]] = {}
    for fact_id, commit_sha, confidence, entity_path in rows:
        fid = str(fact_id)
        if fid not in facts_data:
            facts_data[fid] = {
                "commit_sha": commit_sha,
                "confidence": float(confidence) if confidence is not None else 0.6,
                "paths": [],
            }
        facts_data[fid]["paths"].append(entity_path)

    facts_checked = 0
    superseded_count = 0
    decayed_count = 0
    unchanged_count = 0

    sentinel_str = str(CONSOLIDATION_STALE_SENTINEL)

    for fact_id, data in facts_data.items():
        facts_checked += 1
        commit_sha = data["commit_sha"]
        confidence = data["confidence"]
        file_paths = data["paths"]

        # Check which files exist on disk
        existing_files = [p for p in file_paths if (repo_root / p).exists()]

        if not existing_files:
            # All linked files deleted → supersede  (96-REQ-3.2)
            conn.execute(
                "UPDATE memory_facts SET superseded_by = ? WHERE id = ?",
                [sentinel_str, fact_id],
            )
            superseded_count += 1
            continue

        # At least one file exists; check for significant changes if commit_sha present
        if commit_sha is not None:
            # Check change ratio for each existing file (96-REQ-3.3)
            significantly_changed = False
            for file_path in existing_files:
                ratio = _compute_change_ratio(commit_sha, file_path, repo_root)
                if ratio is not None and ratio > change_ratio_threshold:
                    significantly_changed = True
                    break

            if significantly_changed:
                new_confidence = confidence / 2.0
                conn.execute(
                    "UPDATE memory_facts SET confidence = ? WHERE id = ?",
                    [new_confidence, fact_id],
                )
                decayed_count += 1
                continue

        unchanged_count += 1

    return VerificationResult(
        facts_checked=facts_checked,
        superseded_count=superseded_count,
        decayed_count=decayed_count,
        unchanged_count=unchanged_count,
    )


async def _merge_related_facts(
    conn: duckdb.DuckDBPyConnection,
    model: str,
    threshold: float = _DEFAULT_MERGE_THRESHOLD,
    embedding_generator: EmbeddingGenerator | None = None,
) -> MergeResult:
    """Find and merge semantically similar facts from different specs.

    Uses embedding cosine similarity to cluster cross-spec facts, then
    asks the LLM to merge or link each cluster.

    Requirements: 96-REQ-4.1, 96-REQ-4.2, 96-REQ-4.3, 96-REQ-4.4,
                  96-REQ-4.E1, 96-REQ-4.E2
    """
    # cosine_distance = 1 - similarity; threshold similarity → max distance
    max_dist = 1.0 - threshold

    # Find cross-spec pairs above similarity threshold (96-REQ-4.E1: embedding
    # failures are already excluded — only facts with embeddings appear here)
    try:
        pair_rows = conn.execute(
            """
            SELECT ea.id AS id1, eb.id AS id2
            FROM memory_embeddings ea
            JOIN memory_embeddings eb ON CAST(ea.id AS VARCHAR) < CAST(eb.id AS VARCHAR)
            JOIN memory_facts fa ON ea.id = fa.id AND fa.superseded_by IS NULL
            JOIN memory_facts fb ON eb.id = fb.id AND fb.superseded_by IS NULL
                AND fa.spec_name != fb.spec_name
            WHERE array_cosine_distance(ea.embedding, eb.embedding) <= ?
            """,
            [max_dist],
        ).fetchall()
    except Exception:
        logger.warning("Failed to query embedding similarity for merge step", exc_info=True)
        return MergeResult(0, 0, 0, 0)

    if not pair_rows:
        return MergeResult(0, 0, 0, 0)

    pairs = [(str(r[0]), str(r[1])) for r in pair_rows]
    clusters = _union_find_clusters(pairs)

    clusters_found = 0
    facts_merged = 0
    facts_linked_count = 0
    consolidated_created = 0

    for cluster_ids in clusters:
        # Only include active facts (not already superseded from a prior iteration)
        placeholders = ", ".join("?" * len(cluster_ids))
        active_rows = conn.execute(
            f"SELECT id, content, spec_name, confidence FROM memory_facts "
            f"WHERE CAST(id AS VARCHAR) IN ({placeholders}) AND superseded_by IS NULL",
            cluster_ids,
        ).fetchall()

        if len(active_rows) < 2:
            continue

        # Verify cross-spec requirement: at least 2 different specs
        spec_names = {r[2] for r in active_rows}
        if len(spec_names) < 2:
            continue

        clusters_found += 1
        active_ids = [str(r[0]) for r in active_rows]

        facts_info = [
            {
                "id": str(r[0]),
                "content": r[1],
                "spec_name": r[2],
                "confidence": float(r[3]),
            }
            for r in active_rows
        ]

        try:
            decision = await _call_llm_json(model, MERGE_PROMPT, {"facts": facts_info})
        except Exception:
            # 96-REQ-4.E2: skip cluster on LLM failure
            logger.warning("Failed to classify merge cluster (skipping)", exc_info=True)
            continue

        action = decision.get("action", "link")

        if action == "merge":
            # 96-REQ-4.3: create consolidated fact, supersede originals
            content = decision.get("content", "Consolidated fact")
            max_confidence = max(f["confidence"] for f in facts_info)

            new_id = str(uuid.uuid4())
            # Use spec_name from the highest-confidence fact
            best_spec = max(facts_info, key=lambda f: f["confidence"])["spec_name"]
            conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, category, spec_name, confidence, created_at)
                VALUES (?, ?, 'decision', ?, ?, CURRENT_TIMESTAMP)
                """,
                [new_id, content, best_spec, max_confidence],
            )

            # Generate and store embedding for the consolidated fact (best-effort)
            if embedding_generator is not None:
                try:
                    embedding = embedding_generator.embed_text(content)
                    if embedding is not None:
                        dim = embedding_generator.embedding_dimensions
                        conn.execute(
                            f"INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{dim}])",
                            [new_id, embedding],
                        )
                    else:
                        logger.warning(
                            "Embedding generation returned None for consolidated fact %s",
                            new_id,
                        )
                except Exception:
                    logger.warning(
                        "Embedding write failed for consolidated fact %s",
                        new_id,
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "No embedder configured; consolidated fact %s stored without embedding",
                    new_id,
                )

            for fid in active_ids:
                conn.execute(
                    "UPDATE memory_facts SET superseded_by = ? WHERE id = ?",
                    [new_id, fid],
                )

            facts_merged += len(active_ids)
            consolidated_created += 1

        else:
            # 96-REQ-4.4: add causal edges between cluster facts
            for i, id1 in enumerate(active_ids):
                for id2 in active_ids[i + 1 :]:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) VALUES (?::UUID, ?::UUID)",
                            [id1, id2],
                        )
                        facts_linked_count += 1
                    except Exception:
                        pass

    return MergeResult(
        clusters_found=clusters_found,
        facts_merged=facts_merged,
        facts_linked=facts_linked_count,
        consolidated_created=consolidated_created,
    )


async def _promote_patterns(
    conn: duckdb.DuckDBPyConnection,
    model: str,
    threshold: float = _DEFAULT_PATTERN_THRESHOLD,
    embedding_generator: EmbeddingGenerator | None = None,
) -> PromotionResult:
    """Identify recurring patterns across 3+ specs and create pattern facts.

    Requirements: 96-REQ-5.1, 96-REQ-5.2, 96-REQ-5.3, 96-REQ-5.E1
    """
    max_dist = 1.0 - threshold

    # Find cross-spec pairs above similarity threshold
    try:
        pair_rows = conn.execute(
            """
            SELECT ea.id AS id1, eb.id AS id2
            FROM memory_embeddings ea
            JOIN memory_embeddings eb ON CAST(ea.id AS VARCHAR) < CAST(eb.id AS VARCHAR)
            JOIN memory_facts fa ON ea.id = fa.id AND fa.superseded_by IS NULL
            JOIN memory_facts fb ON eb.id = fb.id AND fb.superseded_by IS NULL
                AND fa.spec_name != fb.spec_name
            WHERE array_cosine_distance(ea.embedding, eb.embedding) <= ?
            """,
            [max_dist],
        ).fetchall()
    except Exception:
        logger.warning("Failed to query embedding similarity for pattern promotion", exc_info=True)
        return PromotionResult(0, 0, 0)

    if not pair_rows:
        return PromotionResult(0, 0, 0)

    pairs = [(str(r[0]), str(r[1])) for r in pair_rows]
    all_clusters = _union_find_clusters(pairs)

    candidates_found = 0
    patterns_confirmed = 0
    pattern_facts_created = 0

    for cluster_ids in all_clusters:
        # Only include active facts
        placeholders = ", ".join("?" * len(cluster_ids))
        active_rows = conn.execute(
            f"SELECT id, content, spec_name FROM memory_facts "
            f"WHERE CAST(id AS VARCHAR) IN ({placeholders}) AND superseded_by IS NULL",
            cluster_ids,
        ).fetchall()

        if not active_rows:
            continue

        spec_names = {r[2] for r in active_rows}

        # 96-REQ-5.1: must span 3+ distinct spec_names
        if len(spec_names) < 3:
            continue

        candidates_found += 1
        active_ids = [str(r[0]) for r in active_rows]

        # 96-REQ-5.E1: skip if any fact already linked to a pattern fact
        already_linked = False
        for fid in active_ids:
            pattern_effect = conn.execute(
                """
                SELECT 1 FROM fact_causes fc
                JOIN memory_facts mf ON CAST(fc.effect_id AS VARCHAR) = CAST(mf.id AS VARCHAR)
                WHERE CAST(fc.cause_id AS VARCHAR) = ? AND mf.category = 'pattern'
                LIMIT 1
                """,
                [fid],
            ).fetchone()
            if pattern_effect is not None:
                already_linked = True
                break

        if already_linked:
            continue

        facts_info = [{"id": str(r[0]), "content": r[1], "spec_name": r[2]} for r in active_rows]

        try:
            decision = await _call_llm_json(model, PATTERN_PROMPT, {"facts": facts_info})
        except Exception:
            logger.warning("Failed to confirm pattern (skipping)", exc_info=True)
            continue

        if not decision.get("is_pattern", False):
            continue

        patterns_confirmed += 1
        description = decision.get("description", "Recurring pattern")

        # 96-REQ-5.3: create pattern fact with category=pattern, confidence=0.9
        pattern_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES (?, ?, 'pattern', 'consolidated', 0.9, CURRENT_TIMESTAMP)
            """,
            [pattern_id, description],
        )

        # Generate and store embedding for the pattern fact (best-effort)
        if embedding_generator is not None:
            try:
                embedding = embedding_generator.embed_text(description)
                if embedding is not None:
                    dim = embedding_generator.embedding_dimensions
                    conn.execute(
                        f"INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{dim}])",
                        [pattern_id, embedding],
                    )
                else:
                    logger.warning(
                        "Embedding generation returned None for pattern fact %s",
                        pattern_id,
                    )
            except Exception:
                logger.warning(
                    "Embedding write failed for pattern fact %s",
                    pattern_id,
                    exc_info=True,
                )
        else:
            logger.warning(
                "No embedder configured; pattern fact %s stored without embedding",
                pattern_id,
            )

        # Add causal edges from each original fact to the pattern fact
        for fid in active_ids:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO fact_causes (cause_id, effect_id) VALUES (?::UUID, ?::UUID)",
                    [fid, pattern_id],
                )
            except Exception:
                pass

        pattern_facts_created += 1

    return PromotionResult(
        candidates_found=candidates_found,
        patterns_confirmed=patterns_confirmed,
        pattern_facts_created=pattern_facts_created,
    )


async def _prune_redundant_chains(
    conn: duckdb.DuckDBPyConnection,
    model: str,
) -> PruneResult:
    """Find and prune redundant causal chains A→B→C where A→C exists.

    Requirements: 96-REQ-6.1, 96-REQ-6.2, 96-REQ-6.3, 96-REQ-6.E1
    """
    # 96-REQ-6.1: find all redundant chains
    try:
        chain_rows = conn.execute(
            """
            SELECT
                CAST(a.cause_id AS VARCHAR) AS a_id,
                CAST(a.effect_id AS VARCHAR) AS b_id,
                CAST(b.effect_id AS VARCHAR) AS c_id
            FROM fact_causes a
            JOIN fact_causes b ON a.effect_id = b.cause_id
            JOIN fact_causes direct
                ON a.cause_id = direct.cause_id
                AND b.effect_id = direct.effect_id
            """
        ).fetchall()
    except Exception:
        logger.warning("Failed to query redundant causal chains", exc_info=True)
        return PruneResult(0, 0, 0)

    if not chain_rows:
        return PruneResult(0, 0, 0)

    chains_evaluated = 0
    intermediates_pruned = 0
    edges_removed = 0

    # Deduplicate chains (same triple may appear multiple times due to JOIN)
    seen_chains: set[tuple[str, str, str]] = set()

    for row in chain_rows:
        a_id, b_id, c_id = str(row[0]), str(row[1]), str(row[2])
        chain = (a_id, b_id, c_id)
        if chain in seen_chains:
            continue
        seen_chains.add(chain)

        chains_evaluated += 1

        # 96-REQ-6.2: ask LLM whether B is meaningful
        fact_rows = conn.execute(
            "SELECT CAST(id AS VARCHAR), content FROM memory_facts WHERE CAST(id AS VARCHAR) IN (?, ?, ?)",
            [a_id, b_id, c_id],
        ).fetchall()
        facts = {str(r[0]): r[1] for r in fact_rows}

        try:
            decision = await _call_llm_json(
                model,
                CHAIN_PROMPT,
                {
                    "A": {"id": a_id, "content": facts.get(a_id, "")},
                    "B": {"id": b_id, "content": facts.get(b_id, "")},
                    "C": {"id": c_id, "content": facts.get(c_id, "")},
                },
            )
        except Exception:
            # 96-REQ-6.E1: preserve all edges on LLM failure
            logger.warning(
                "LLM evaluation failed for chain %s→%s→%s (preserving edges)",
                a_id,
                b_id,
                c_id,
                exc_info=True,
            )
            continue

        if not decision.get("meaningful", True):
            # 96-REQ-6.3: remove A→B and B→C; preserve A→C
            try:
                conn.execute(
                    "DELETE FROM fact_causes WHERE cause_id = ?::UUID AND effect_id = ?::UUID",
                    [a_id, b_id],
                )
                conn.execute(
                    "DELETE FROM fact_causes WHERE cause_id = ?::UUID AND effect_id = ?::UUID",
                    [b_id, c_id],
                )
                intermediates_pruned += 1
                edges_removed += 2
            except Exception:
                logger.warning(
                    "Failed to remove edges for chain %s→%s→%s",
                    a_id,
                    b_id,
                    c_id,
                    exc_info=True,
                )

    return PruneResult(
        chains_evaluated=chains_evaluated,
        intermediates_pruned=intermediates_pruned,
        edges_removed=edges_removed,
    )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

# Forward declaration: populated immediately after run_consolidation is defined.
# Stores the *original* function object so the delegation guard inside
# run_consolidation can detect when the module attribute has been patched by
# tests, even though the name "run_consolidation" inside the function body
# also resolves through __globals__ (which patch modifies).
_run_consolidation_original: Any = None


async def run_consolidation(
    conn: duckdb.DuckDBPyConnection,
    repo_root: Path,
    completed_specs: set[str] | None,
    model: str,
    embedding_generator: EmbeddingGenerator | None = None,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str | None = None,
    change_ratio_threshold: float = 0.5,
    merge_similarity_threshold: float = _DEFAULT_MERGE_THRESHOLD,
    max_cost: float | None = None,
) -> ConsolidationResult:
    """Run the full knowledge consolidation pipeline.

    Executes six steps in order:
    1. Entity graph refresh (analyze_codebase)
    2. Fact-entity linking (link_facts)
    3. Git verification (supersede/decay stale facts)
    4. Cross-spec merging (LLM merge/link clusters)
    5. Pattern promotion (LLM pattern confirmation)
    6. Causal chain pruning (LLM intermediate evaluation)

    Each step is isolated — if it raises, a warning is logged, the step name
    is added to errors, and execution continues with the next step.

    Delegation: if the module-level ``run_consolidation`` attribute has been
    replaced (e.g. by test patches) and we are not already delegating,
    forward the call to the patched version. This allows tests to intercept
    calls made via the local function reference.

    Requirements: 96-REQ-1.1, 96-REQ-1.2, 96-REQ-1.3, 96-REQ-1.E1,
                  96-REQ-1.E2, 96-REQ-2.E1, 96-REQ-7.E1
    """
    # Delegation: allow test patches on the module attribute to intercept calls
    # made through the locally-imported reference (96-REQ-7.2 testability).
    #
    # Problem: inside this function, bare "run_consolidation" resolves through
    # __globals__ (== consolidation.__dict__), which patch() has already
    # modified to point at the mock.  Both sides of the comparison would be the
    # mock and the guard would never fire.
    #
    # Fix: compare the module attribute against _run_consolidation_original,
    # which is a separate module-level name that patch() does NOT touch.
    if not _is_delegating.get():
        import sys  # noqa: PLC0415

        _self_module = sys.modules[__name__]
        if _self_module.run_consolidation is not _run_consolidation_original:
            token = _is_delegating.set(True)
            try:
                return await _self_module.run_consolidation(
                    conn,
                    repo_root,
                    completed_specs,
                    model,
                    embedding_generator=embedding_generator,
                    sink_dispatcher=sink_dispatcher,
                    run_id=run_id,
                    change_ratio_threshold=change_ratio_threshold,
                    merge_similarity_threshold=merge_similarity_threshold,
                    max_cost=max_cost,
                )
            finally:
                _is_delegating.reset(token)

    errors: list[str] = []
    total_llm_cost = 0.0

    # Determine whether entity graph steps can run.
    # Check and log warnings BEFORE the zero-facts early exit so that
    # callers always see warnings about missing tables/invalid roots.
    entity_tables_ok = _entity_graph_tables_exist(conn)
    repo_root_ok = repo_root.exists()

    if not entity_tables_ok:
        logger.warning(
            "Entity graph tables not found (migration v8 not applied); "
            "skipping entity graph refresh and fact-entity linking"
        )
    if not repo_root_ok:
        logger.warning(
            "Repository root %s does not exist or is not accessible; skipping entity graph steps",
            repo_root,
        )

    # 96-REQ-1.E1: early exit when no active facts exist
    if _count_active_facts(conn) == 0:
        result = ConsolidationResult(
            entity_refresh=None,
            facts_linked=0,
            verification=VerificationResult(0, 0, 0, 0),
            merging=MergeResult(0, 0, 0, 0),
            promotion=PromotionResult(0, 0, 0),
            pruning=PruneResult(0, 0, 0),
            total_llm_cost=0.0,
            errors=[],
        )
        _emit_events(sink_dispatcher, result, run_id)
        return result

    # ------------------------------------------------------------------ #
    # Step 1: Entity graph refresh                                         #
    # ------------------------------------------------------------------ #
    entity_refresh: AnalysisResult | None = None
    if entity_tables_ok and repo_root_ok:
        try:
            entity_refresh = _refresh_entity_graph(conn, repo_root)
        except Exception:
            logger.warning("Entity graph refresh failed", exc_info=True)
            errors.append("entity_refresh")

    # ------------------------------------------------------------------ #
    # Step 2: Fact-entity linking                                          #
    # ------------------------------------------------------------------ #
    facts_linked = 0
    if entity_tables_ok and repo_root_ok:
        try:
            link_result = _link_unlinked_facts(conn, repo_root)
            facts_linked = link_result.links_created
        except Exception:
            logger.warning("Fact-entity linking failed", exc_info=True)
            errors.append("link_facts")

    # ------------------------------------------------------------------ #
    # Step 3: Git verification                                             #
    # ------------------------------------------------------------------ #
    verification: VerificationResult | None = None
    try:
        verification = _verify_against_git(conn, repo_root, change_ratio_threshold)
    except Exception:
        logger.warning("Git verification step failed", exc_info=True)
        errors.append("git_verification")

    # ------------------------------------------------------------------ #
    # Step 4: Cross-spec fact merging                                      #
    # ------------------------------------------------------------------ #
    merging: MergeResult | None = None
    if max_cost is not None and (total_llm_cost >= max_cost or max_cost < _MIN_LLM_STEP_COST):
        # 96-REQ-7.E1: budget too small to afford an LLM call — abort step.
        logger.warning(
            "Skipping cross-spec merging: budget %.4f is below minimum LLM step cost %.4f",
            max_cost,
            _MIN_LLM_STEP_COST,
        )
        errors.append("merging")
    else:
        try:
            merging = await _merge_related_facts(conn, model, merge_similarity_threshold, embedding_generator)
        except Exception:
            logger.warning("Cross-spec fact merging step failed", exc_info=True)
            errors.append("merging")

    # ------------------------------------------------------------------ #
    # Step 5: Pattern promotion                                            #
    # ------------------------------------------------------------------ #
    promotion: PromotionResult | None = None
    if max_cost is not None and (total_llm_cost >= max_cost or max_cost < _MIN_LLM_STEP_COST):
        # 96-REQ-7.E1: budget exhausted or too small — abort step.
        logger.warning(
            "Skipping pattern promotion: budget %.4f is below minimum LLM step cost %.4f",
            max_cost,
            _MIN_LLM_STEP_COST,
        )
        errors.append("promotion")
    else:
        try:
            promotion = await _promote_patterns(conn, model, merge_similarity_threshold, embedding_generator)
        except Exception:
            logger.warning("Pattern promotion step failed", exc_info=True)
            errors.append("promotion")

    # ------------------------------------------------------------------ #
    # Step 6: Causal chain pruning                                         #
    # ------------------------------------------------------------------ #
    pruning: PruneResult | None = None
    if max_cost is not None and (total_llm_cost >= max_cost or max_cost < _MIN_LLM_STEP_COST):
        # 96-REQ-7.E1: budget exhausted or too small — abort step.
        logger.warning(
            "Skipping causal chain pruning: budget %.4f is below minimum LLM step cost %.4f",
            max_cost,
            _MIN_LLM_STEP_COST,
        )
        errors.append("pruning")
    else:
        try:
            pruning = await _prune_redundant_chains(conn, model)
        except Exception:
            logger.warning("Causal chain pruning step failed", exc_info=True)
            errors.append("pruning")

    result = ConsolidationResult(
        entity_refresh=entity_refresh,
        facts_linked=facts_linked,
        verification=verification,
        merging=merging,
        promotion=promotion,
        pruning=pruning,
        total_llm_cost=total_llm_cost,
        errors=errors,
    )

    # 96-REQ-1.3: emit audit events
    _emit_events(sink_dispatcher, result, run_id)

    return result


def _emit_events(
    sink_dispatcher: Any | None,
    result: ConsolidationResult,
    run_id: str | None,
) -> None:
    """Emit consolidation.complete and consolidation.cost audit events."""
    if sink_dispatcher is None:
        return

    payload = {
        "entity_refresh": (
            {
                "entities_upserted": result.entity_refresh.entities_upserted,
                "edges_upserted": result.entity_refresh.edges_upserted,
                "entities_soft_deleted": result.entity_refresh.entities_soft_deleted,
            }
            if result.entity_refresh is not None
            else None
        ),
        "facts_linked": result.facts_linked,
        "verification": (
            {
                "facts_checked": result.verification.facts_checked,
                "superseded_count": result.verification.superseded_count,
                "decayed_count": result.verification.decayed_count,
                "unchanged_count": result.verification.unchanged_count,
            }
            if result.verification is not None
            else None
        ),
        "merging": (
            {
                "clusters_found": result.merging.clusters_found,
                "facts_merged": result.merging.facts_merged,
                "facts_linked": result.merging.facts_linked,
                "consolidated_created": result.merging.consolidated_created,
            }
            if result.merging is not None
            else None
        ),
        "promotion": (
            {
                "candidates_found": result.promotion.candidates_found,
                "patterns_confirmed": result.promotion.patterns_confirmed,
                "pattern_facts_created": result.promotion.pattern_facts_created,
            }
            if result.promotion is not None
            else None
        ),
        "pruning": (
            {
                "chains_evaluated": result.pruning.chains_evaluated,
                "intermediates_pruned": result.pruning.intermediates_pruned,
                "edges_removed": result.pruning.edges_removed,
            }
            if result.pruning is not None
            else None
        ),
        "errors": result.errors,
        "total_llm_cost": result.total_llm_cost,
    }

    from agent_fox.knowledge.audit import AuditEvent, AuditEventType

    try:
        sink_dispatcher.emit_audit_event(
            AuditEvent(
                run_id=run_id or "",
                event_type=AuditEventType.CONSOLIDATION_COMPLETE,
                payload=payload,
            )
        )
    except Exception:
        logger.warning("Failed to dispatch consolidation.complete event", exc_info=True)

    try:
        sink_dispatcher.emit_audit_event(
            AuditEvent(
                run_id=run_id or "",
                event_type=AuditEventType.CONSOLIDATION_COST,
                payload={"total_cost": result.total_llm_cost},
            )
        )
    except Exception:
        logger.warning("Failed to dispatch consolidation.cost event", exc_info=True)


# Capture the real function object so the delegation guard inside
# run_consolidation can distinguish "module attribute replaced by a test patch"
# from "this is the genuine function calling itself".  Must be set after the
# function is defined; patch() never touches this name.
_run_consolidation_original = run_consolidation
