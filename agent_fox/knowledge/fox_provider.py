"""Concrete KnowledgeProvider: gotchas + review carry-forward + errata.

Implements the KnowledgeProvider protocol (spec 114) with three knowledge
categories: gotchas (surprising findings), review carry-forward (unresolved
critical/major findings), and errata (spec divergence pointers).

Requirements: 115-REQ-1.1, 115-REQ-1.2, 115-REQ-1.3, 115-REQ-1.E1,
              115-REQ-4.1, 115-REQ-4.2, 115-REQ-4.3, 115-REQ-4.E1, 115-REQ-4.E2,
              115-REQ-6.1, 115-REQ-6.2, 115-REQ-6.3, 115-REQ-6.E1, 115-REQ-6.E2
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import KnowledgeDB

logger = logging.getLogger(__name__)

_MAX_GOTCHAS = 3


class FoxKnowledgeProvider:
    """Concrete KnowledgeProvider: gotchas + review carry-forward + errata.

    Orchestrates retrieval from three knowledge categories and ingestion
    of gotchas from completed sessions.  Satisfies the ``KnowledgeProvider``
    protocol defined in spec 114 (``@runtime_checkable``).
    """

    def __init__(
        self,
        knowledge_db: KnowledgeDB,
        config: KnowledgeProviderConfig,
    ) -> None:
        self._knowledge_db = knowledge_db
        self._config = config

    # ------------------------------------------------------------------
    # KnowledgeProvider protocol methods
    # ------------------------------------------------------------------

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        """Retrieve knowledge context for an upcoming session.

        Queries errata, review findings, and gotchas for the given spec,
        composes them in priority order (errata first, reviews second,
        gotchas last), and caps the total at ``max_items``.

        Args:
            spec_name: Name of the spec being worked on.
            task_description: Human-readable description of the task.

        Returns:
            List of formatted text blocks ready for prompt injection.

        Raises:
            KnowledgeStoreError: If the database connection is closed or
                a query fails unexpectedly.
        """
        try:
            conn = self._knowledge_db.connection
        except KnowledgeStoreError:
            raise

        try:
            errata = self._query_errata(conn, spec_name)
            reviews = self._query_reviews(conn, spec_name)
            gotchas = self._query_gotchas(conn, spec_name)
        except KnowledgeStoreError:
            raise
        except Exception as exc:
            raise KnowledgeStoreError(
                f"Failed to retrieve knowledge for {spec_name}: {exc}",
            ) from exc

        result = self._compose_results(errata, reviews, gotchas)

        logger.debug(
            "Retrieved %d items for %s: %d errata, %d reviews, %d gotchas",
            len(result),
            spec_name,
            len(errata),
            len(reviews),
            len([r for r in result if r.startswith("[GOTCHA]")]),
        )

        return result

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session.

        Extracts gotchas from the session context via LLM and stores them.
        Skips extraction if the session did not complete successfully
        (115-REQ-2.5).

        Args:
            session_id: Node ID of the completed session.
            spec_name: Name of the spec the session belongs to.
            context: Dict with ``session_status``, ``touched_files``,
                ``commit_sha``.
        """
        if context.get("session_status") != "completed":
            return

        from agent_fox.knowledge.gotcha_extraction import extract_gotchas

        try:
            candidates = extract_gotchas(context, self._config.model_tier)
        except Exception:
            logger.warning(
                "Gotcha extraction failed for %s",
                spec_name,
                exc_info=True,
            )
            return

        if not candidates:
            return

        # Defense-in-depth: cap at _MAX_GOTCHAS even if extraction
        # returned more (115-REQ-2.E3).
        candidates = candidates[:_MAX_GOTCHAS]

        from agent_fox.knowledge.gotcha_store import store_gotchas

        conn = self._knowledge_db.connection
        stored = store_gotchas(conn, spec_name, session_id, candidates)
        logger.info(
            "Ingested %d gotchas for %s (session %s)",
            stored,
            spec_name,
            session_id,
        )

    # ------------------------------------------------------------------
    # Internal query helpers
    # ------------------------------------------------------------------

    def _query_errata(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query errata entries for the given spec."""
        from agent_fox.knowledge.errata_store import query_errata

        return query_errata(conn, spec_name)

    def _query_reviews(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query unresolved critical/major review findings for the spec.

        Handles missing ``review_findings`` table gracefully by returning
        an empty list (115-REQ-4.E2).  Filters to ``critical`` and
        ``major`` severity only (115-REQ-4.1).
        """
        try:
            from agent_fox.knowledge.review_store import query_active_findings

            findings = query_active_findings(conn, spec_name)
        except Exception:
            # Table may not exist in a fresh database (115-REQ-4.E2).
            logger.debug(
                "Could not query review findings for %s",
                spec_name,
            )
            return []

        result: list[str] = []
        for f in findings:
            if f.severity in ("critical", "major"):
                parts = [f"[{f.severity}]"]
                if f.category:
                    parts.append(f"{f.category}:")
                parts.append(f.description)
                result.append(f"[REVIEW] {' '.join(parts)}")
        return result

    def _query_gotchas(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query non-expired gotchas for the given spec."""
        from agent_fox.knowledge.gotcha_store import query_gotchas

        return query_gotchas(conn, spec_name, self._config.gotcha_ttl_days)

    def _compose_results(
        self,
        errata: list[str],
        reviews: list[str],
        gotchas: list[str],
    ) -> list[str]:
        """Merge categories in priority order with cap.

        Priority order: errata first, reviews second, gotchas last.
        Reviews and errata are never trimmed — only gotchas are trimmed
        when the total would exceed ``max_items``.  If reviews + errata
        alone exceed ``max_items``, all reviews and errata are returned
        with no gotchas (115-REQ-6.E2).
        """
        priority_count = len(errata) + len(reviews)
        remaining = max(0, self._config.max_items - priority_count)
        trimmed_gotchas = gotchas[:remaining]

        return errata + reviews + trimmed_gotchas
