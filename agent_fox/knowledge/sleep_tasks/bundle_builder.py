"""Retrieval bundle builder sleep task.

Pre-computes keyword and causal retrieval signals for each spec that has active
facts, serialises the ScoredFact lists to JSON, and stores the result as a
sleep artifact.  The retriever can later load these cached signals instead of
recomputing them at query time.

No LLM calls are required — this task reports llm_cost = 0.0.

Requirements: 112-REQ-4.1 through 112-REQ-4.6, 112-REQ-4.E1, 112-REQ-4.E2
"""

from __future__ import annotations

import dataclasses
import json
import logging

import duckdb

from agent_fox.knowledge.retrieval import _causal_signal, _keyword_signal
from agent_fox.knowledge.sleep_compute import (
    SleepContext,
    SleepTaskResult,
    compute_content_hash,
    upsert_artifact,
)

logger = logging.getLogger(__name__)

_TASK_NAME = "bundle_builder"


def _scored_fact_to_dict(sf: object) -> dict:
    """Serialise a ScoredFact to a JSON-compatible dict."""
    return dataclasses.asdict(sf)  # type: ignore[arg-type]


class BundleBuilder:
    """Sleep task that pre-computes keyword and causal retrieval signals per spec.

    Requirements: 112-REQ-4.1 through 112-REQ-4.6
    """

    @property
    def name(self) -> str:
        """Unique identifier for this task.

        Requirements: 112-REQ-1.1
        """
        return _TASK_NAME

    @property
    def cost_estimate(self) -> float:
        """No LLM calls required; budget cost is zero.

        Requirements: 112-REQ-4.6
        """
        return 0.0

    def stale_scopes(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        """Return scope keys for specs whose cached bundle content hash has changed.

        Requirements: 112-REQ-1.3, 112-REQ-4.2, 112-REQ-4.4
        """
        spec_facts = self._query_active_spec_facts(conn)
        stale: list[str] = []
        for spec_name, facts in spec_facts.items():
            if not facts:
                continue
            scope_key = f"spec:{spec_name}"
            current_hash = compute_content_hash(
                [(f["id"], f["confidence"]) for f in facts]
            )
            stored_hash = self._get_stored_hash(conn, scope_key)
            if stored_hash != current_hash:
                stale.append(scope_key)
        return stale

    async def run(self, ctx: SleepContext) -> SleepTaskResult:
        """Build retrieval bundles for all stale specs.

        Requirements: 112-REQ-4.1, 112-REQ-4.3, 112-REQ-4.5
        """
        spec_facts = self._query_active_spec_facts(ctx.conn)

        created = 0
        refreshed = 0
        unchanged = 0

        for spec_name, facts in spec_facts.items():
            if not facts:
                # REQ-4.E1: skip specs with zero active facts
                continue

            scope_key = f"spec:{spec_name}"
            current_hash = compute_content_hash(
                [(f["id"], f["confidence"]) for f in facts]
            )
            stored_hash = self._get_stored_hash(ctx.conn, scope_key)

            if stored_hash == current_hash:
                unchanged += 1
                continue

            # Compute keyword and causal signals (REQ-4.3)
            try:
                keyword_facts, causal_facts = self._compute_signals(
                    spec_name, ctx.conn
                )
            except Exception as exc:
                logger.warning(
                    "Bundle builder: signal computation failed for spec %r: %s",
                    spec_name,
                    exc,
                )
                continue

            # Serialize to JSON
            content = json.dumps(
                {
                    "keyword": [_scored_fact_to_dict(sf) for sf in keyword_facts],
                    "causal": [_scored_fact_to_dict(sf) for sf in causal_facts],
                }
            )

            metadata = json.dumps(
                {
                    "spec_name": spec_name,
                    "fact_count": len(facts),
                    "keyword_count": len(keyword_facts),
                    "causal_count": len(causal_facts),
                }
            )

            is_refresh = stored_hash is not None
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
            llm_cost=0.0,  # No LLM calls (REQ-4.6)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_active_spec_facts(
        self, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, list[dict]]:
        """Return a mapping of spec_name → list of active fact dicts.

        Requirements: 112-REQ-4.1
        """
        try:
            rows = conn.execute(
                """
                SELECT id::VARCHAR, spec_name, confidence
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND spec_name IS NOT NULL
                  AND spec_name != ''
                """
            ).fetchall()
        except duckdb.CatalogException:
            return {}

        if not rows:
            return {}

        result: dict[str, list[dict]] = {}
        for fact_id, spec_name, confidence in rows:
            if spec_name not in result:
                result[spec_name] = []
            result[spec_name].append(
                {"id": str(fact_id), "confidence": float(confidence)}
            )
        return result

    def _get_stored_hash(
        self, conn: duckdb.DuckDBPyConnection, scope_key: str
    ) -> str | None:
        """Return the content_hash of the active bundle for this scope key, or None."""
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

    def _compute_signals(
        self, spec_name: str, conn: duckdb.DuckDBPyConnection
    ) -> tuple[list, list]:
        """Compute keyword and causal signals for a spec.

        Uses empty keywords (only spec-name matching) so results are
        deterministic and independent of session context.

        Requirements: 112-REQ-4.3
        """
        keyword_facts = _keyword_signal(
            spec_name=spec_name,
            keywords=[],  # Only spec-name based matching
            conn=conn,
            confidence_threshold=0.0,
            top_k=100,
        )
        causal_facts = _causal_signal(
            spec_name=spec_name,
            conn=conn,
        )
        return keyword_facts, causal_facts
