"""Context re-representation sleep task.

Clusters active facts by the parent directory of their entity-linked files,
synthesizes a structured narrative summary for each qualifying cluster via an
LLM call, and stores the result as a sleep artifact.

A cluster qualifies when it contains 3 or more facts linked to files under the
same directory.  The artifact is regenerated only when the content hash of the
cluster changes (staleness detection).

Requirements: 112-REQ-3.1 through 112-REQ-3.6, 112-REQ-3.E1, 112-REQ-3.E2,
              112-REQ-3.E3
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict

import duckdb

from agent_fox.knowledge.sleep_compute import (
    SleepContext,
    SleepTaskResult,
    compute_content_hash,
    upsert_artifact,
)

logger = logging.getLogger(__name__)

# Minimum number of facts in a directory cluster to trigger synthesis.
_MIN_CLUSTER_SIZE = 3

# Maximum characters for a stored context block.
_MAX_BLOCK_CHARS = 2000

_TASK_NAME = "context_rewriter"

_PROMPT_TEMPLATE = """\
You are a knowledge system. Given a set of facts about code in the directory \
"{directory_path}", write a structured narrative summary (max 2000 chars) that \
explains how these facts relate to each other and what a developer should know \
when working in this area.

Format:
### {directory_path}
{{narrative summary}}

Facts:
{fact_list}
"""


def _truncate_to_sentence(text: str, max_len: int) -> str:
    """Truncate text to at most max_len characters at the last complete sentence.

    A "complete sentence" ends with '.', '!', or '?'.  If no sentence boundary
    is found within the limit the text is hard-truncated.

    Requirements: 112-REQ-3.4
    """
    if len(text) <= max_len:
        return text

    # Find the last sentence-ending punctuation within the limit
    truncated = text[:max_len]
    last_pos = -1
    for punct in (".", "!", "?"):
        pos = truncated.rfind(punct)
        if pos > last_pos:
            last_pos = pos

    if last_pos > 0:
        return truncated[: last_pos + 1]

    # No sentence boundary found — hard truncate
    return truncated


class ContextRewriter:
    """Sleep task that synthesizes per-directory narrative context blocks.

    Requirements: 112-REQ-3.1 through 112-REQ-3.6
    """

    @property
    def name(self) -> str:
        """Unique identifier for this task.

        Requirements: 112-REQ-1.1
        """
        return _TASK_NAME

    @property
    def cost_estimate(self) -> float:
        """Estimated LLM cost per run (heuristic based on typical cluster count)."""
        return 0.5

    def stale_scopes(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        """Return scope keys for directory clusters whose content hash has changed.

        Requirements: 112-REQ-1.3, 112-REQ-3.2, 112-REQ-3.5
        """
        clusters = self._build_clusters(conn)
        stale: list[str] = []
        for directory, facts in clusters.items():
            if len(facts) < _MIN_CLUSTER_SIZE:
                continue
            scope_key = f"dir:{directory}"
            current_hash = compute_content_hash(
                [(f["id"], f["confidence"]) for f in facts]
            )
            stored_hash = self._get_stored_hash(conn, scope_key)
            if stored_hash != current_hash:
                stale.append(scope_key)
        return stale

    async def run(self, ctx: SleepContext) -> SleepTaskResult:
        """Synthesize context blocks for all stale directory clusters.

        Requirements: 112-REQ-3.1, 112-REQ-3.3, 112-REQ-3.5
        """
        clusters = self._build_clusters(ctx.conn)

        created = 0
        refreshed = 0
        unchanged = 0

        for directory, facts in clusters.items():
            if len(facts) < _MIN_CLUSTER_SIZE:
                continue

            scope_key = f"dir:{directory}"
            current_hash = compute_content_hash(
                [(f["id"], f["confidence"]) for f in facts]
            )
            stored_hash = self._get_stored_hash(ctx.conn, scope_key)

            if stored_hash == current_hash:
                unchanged += 1
                continue

            # Generate narrative via LLM
            try:
                content = await self._call_llm(directory, facts, ctx)
            except Exception as exc:
                logger.warning(
                    "Context rewriter: LLM call failed for directory %r: %s",
                    directory,
                    exc,
                )
                continue

            # Truncate if necessary (REQ-3.4)
            content = _truncate_to_sentence(content, _MAX_BLOCK_CHARS)

            # Determine whether this is a create or refresh
            is_refresh = stored_hash is not None
            metadata = json.dumps(
                {
                    "directory": directory,
                    "fact_count": len(facts),
                    "fact_ids": [f["id"] for f in facts],
                }
            )

            upsert_artifact(
                ctx.conn,
                task_name=_TASK_NAME,
                scope_key=scope_key,
                content=content,
                metadata_json=metadata,
                content_hash=current_hash,
            )

            if is_refresh:
                refreshed += 1
            else:
                created += 1

        return SleepTaskResult(
            created=created,
            refreshed=refreshed,
            unchanged=unchanged,
            llm_cost=0.0,  # Actual cost tracked by LLM caller; placeholder here
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self, directory: str, facts: list[dict], ctx: SleepContext
    ) -> str:
        """Call the LLM to synthesize a narrative summary for the cluster.

        This method is the primary LLM call site and can be patched in tests.

        Requirements: 112-REQ-3.3
        """
        from agent_fox.core.client import ai_call

        fact_list = "\n".join(
            f"{i + 1}. {f['content']}" for i, f in enumerate(facts)
        )
        prompt = _PROMPT_TEMPLATE.format(
            directory_path=directory,
            fact_list=fact_list,
        )

        text, _response = await ai_call(
            model_tier="STANDARD",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            context="context_rewriter",
        )
        return text or ""

    def _build_clusters(
        self, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, list[dict]]:
        """Group active entity-linked facts by parent directory of linked files.

        Requirements: 112-REQ-3.1, 112-REQ-3.E1
        """
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    mf.id,
                    mf.content,
                    mf.confidence,
                    fe.entity_id
                FROM memory_facts mf
                JOIN fact_entities fe ON fe.fact_id = mf.id
                WHERE mf.superseded_by IS NULL
                """
            ).fetchall()
        except duckdb.CatalogException:
            # fact_entities table may not exist in minimal test setups
            return {}

        if not rows:
            return {}

        # Get file paths for entity IDs
        entity_ids = list({str(row[3]) for row in rows})
        if not entity_ids:
            return {}

        try:
            placeholders = ", ".join("?" * len(entity_ids))
            entity_rows = conn.execute(
                f"SELECT id, entity_path FROM entity_graph WHERE id IN ({placeholders})",
                entity_ids,
            ).fetchall()
        except duckdb.CatalogException:
            return {}

        entity_to_path: dict[str, str] = {str(r[0]): r[1] for r in entity_rows}

        # Build fact → directories mapping
        fact_map: dict[str, dict] = {}
        for fact_id, content, confidence, entity_id in rows:
            if str(fact_id) not in fact_map:
                fact_map[str(fact_id)] = {
                    "id": str(fact_id),
                    "content": content,
                    "confidence": float(confidence),
                    "directories": set(),
                }
            path = entity_to_path.get(str(entity_id), "")
            if path:
                # Parent directory of the file
                directory = os.path.dirname(path) or "."
                fact_map[str(fact_id)]["directories"].add(directory)

        # Group by directory (a fact appears in all its directories)
        clusters: dict[str, list[dict]] = defaultdict(list)
        for fact in fact_map.values():
            for directory in fact["directories"]:
                clusters[directory].append(
                    {
                        "id": fact["id"],
                        "content": fact["content"],
                        "confidence": fact["confidence"],
                    }
                )

        return dict(clusters)

    def _get_stored_hash(
        self, conn: duckdb.DuckDBPyConnection, scope_key: str
    ) -> str | None:
        """Return the content_hash of the active artifact for this scope key, or None."""
        try:
            row = conn.execute(
                """
                SELECT content_hash
                FROM sleep_artifacts
                WHERE task_name = ?
                  AND scope_key = ?
                  AND superseded_at IS NULL
                """,
                [_TASK_NAME, scope_key],
            ).fetchone()
        except duckdb.CatalogException:
            return None
        return row[0] if row else None
