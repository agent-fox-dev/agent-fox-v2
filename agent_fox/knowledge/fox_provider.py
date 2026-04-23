"""Concrete KnowledgeProvider: review carry-forward.

Implements the KnowledgeProvider protocol (spec 114) with review-only
retrieval. Gotcha extraction, errata indexing, and blocking history have
been removed (spec 116). Ingest is a no-op.

Requirements: 116-REQ-1.3, 116-REQ-1.4, 116-REQ-2.2,
              116-REQ-6.1, 116-REQ-6.2, 116-REQ-6.3, 116-REQ-6.E1
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import KnowledgeDB

logger = logging.getLogger(__name__)


class FoxKnowledgeProvider:
    """Concrete KnowledgeProvider: review carry-forward only.

    Retrieves active critical/major review findings for a spec.
    Ingest is a no-op (gotcha extraction removed in spec 116).
    Satisfies the ``KnowledgeProvider`` protocol defined in spec 114
    (``@runtime_checkable``).
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

        Queries active critical/major review findings for the given spec
        and returns them as ``[REVIEW]``-prefixed strings, capped at
        ``max_items``.

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

        reviews = self._query_reviews(conn, spec_name)

        logger.debug(
            "Retrieved %d review items for %s",
            len(reviews),
            spec_name,
        )

        return reviews[: self._config.max_items]

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session (no-op).

        Gotcha extraction was removed in spec 116. This method satisfies
        the ``KnowledgeProvider`` protocol but performs no work.

        Args:
            session_id: Node ID of the completed session.
            spec_name: Name of the spec the session belongs to.
            context: Dict with ``session_status``, ``touched_files``,
                ``commit_sha``.
        """
        return None

    # ------------------------------------------------------------------
    # Internal query helpers
    # ------------------------------------------------------------------

    def _query_reviews(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query unresolved critical/major review findings for the spec.

        Handles missing ``review_findings`` table gracefully by returning
        an empty list (116-REQ-6.E1).  Filters to ``critical`` and
        ``major`` severity only (116-REQ-6.1).
        """
        try:
            from agent_fox.knowledge.review_store import query_active_findings

            findings = query_active_findings(conn, spec_name)
        except Exception:
            # Table may not exist in a fresh database (116-REQ-6.E1).
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
