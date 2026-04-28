"""Concrete KnowledgeProvider: review carry-forward + ADR retrieval.

Implements the KnowledgeProvider protocol (spec 114) with review-only
retrieval and ADR ingestion/retrieval. Gotcha extraction, errata indexing,
and blocking history have been removed (spec 116).

Requirements: 116-REQ-1.3, 116-REQ-1.4, 116-REQ-2.2,
              116-REQ-6.1, 116-REQ-6.2, 116-REQ-6.3, 116-REQ-6.E1,
              117-REQ-1.1, 117-REQ-6.1, 117-REQ-6.3, 117-REQ-7.4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import KnowledgeDB

logger = logging.getLogger(__name__)


class FoxKnowledgeProvider:
    """Concrete KnowledgeProvider: review carry-forward + ADR retrieval.

    Retrieves active critical/major review findings, errata, and ADR
    summaries for a spec.  Ingests ADR files detected in session
    ``touched_files``.  Satisfies the ``KnowledgeProvider`` protocol
    defined in spec 114 (``@runtime_checkable``).
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
        task_group: str | None = None,
    ) -> list[str]:
        """Retrieve knowledge context for an upcoming session.

        Queries active critical/major review findings, errata, and ADR
        summaries for the given spec and returns them as prefixed strings,
        capped at ``max_items``.

        Args:
            spec_name: Name of the spec being worked on.
            task_description: Human-readable description of the task.
            task_group: Optional task group identifier to restrict review
                findings to those tagged for this group.  When ``None``,
                findings from all task groups are returned.

        Returns:
            List of formatted text blocks ready for prompt injection.

        Raises:
            KnowledgeStoreError: If the database connection is closed or
                a query fails unexpectedly.

        Requirements: 117-REQ-6.1, 117-REQ-6.3
        """
        try:
            conn = self._knowledge_db.connection
        except KnowledgeStoreError:
            raise

        reviews = self._query_reviews(conn, spec_name, task_group=task_group)
        errata = self._query_errata(conn, spec_name)
        adrs = self._query_adrs(conn, spec_name, task_description)
        verdicts = self._query_verdicts(conn, spec_name, task_group=task_group)

        combined = reviews + errata + adrs + verdicts

        logger.debug(
            "Retrieved %d review + %d errata + %d ADR + %d verdict items for %s",
            len(reviews),
            len(errata),
            len(adrs),
            len(verdicts),
            spec_name,
        )

        return combined[: self._config.max_items]

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session.

        Detects ADR files in ``touched_files`` and ingests them into
        the knowledge database.  Gotcha extraction was removed in
        spec 116.

        Args:
            session_id: Node ID of the completed session.
            spec_name: Name of the spec the session belongs to.
            context: Dict with ``session_status``, ``touched_files``,
                ``commit_sha``, and ``project_root``.

        Requirements: 117-REQ-1.1, 117-REQ-7.4
        """
        from agent_fox.knowledge.adr import detect_adr_changes, ingest_adr

        touched_files = context.get("touched_files") or []
        project_root_str = context.get("project_root", "")
        if not project_root_str:
            return

        project_root = Path(str(project_root_str))
        adr_paths = detect_adr_changes(touched_files)
        if not adr_paths:
            return

        try:
            conn = self._knowledge_db.connection
        except KnowledgeStoreError:
            logger.warning(
                "Knowledge DB unavailable for ADR ingestion in session %s",
                session_id,
            )
            return

        # Extract sink and run_id from context if available
        sink = context.get("sink")
        run_id = str(context.get("run_id", ""))

        for adr_path in adr_paths:
            try:
                ingest_adr(
                    conn,
                    adr_path,
                    project_root,
                    sink=sink,
                    run_id=run_id,
                )
            except Exception:
                logger.warning(
                    "Failed to ingest ADR %s in session %s",
                    adr_path,
                    session_id,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Internal query helpers
    # ------------------------------------------------------------------

    def _query_reviews(
        self,
        conn: Any,
        spec_name: str,
        task_group: str | None = None,
    ) -> list[str]:
        """Query unresolved critical/major review findings for the spec.

        Handles missing ``review_findings`` table gracefully by returning
        an empty list (116-REQ-6.E1).  Filters to ``critical`` and
        ``major`` severity only (116-REQ-6.1).

        When ``task_group`` is provided, only findings tagged for that group
        are returned, reducing noise for sessions focused on a specific
        task group.  When ``None``, all active findings for the spec are
        returned (backward-compatible behaviour).

        ``query_active_findings`` already excludes non-actionable severities;
        the ``if f.severity in (...)`` guard below is defense-in-depth and
        kept consistent with that filter (issue #553).
        """
        try:
            from agent_fox.knowledge.review_store import query_active_findings

            findings = query_active_findings(conn, spec_name, task_group=task_group)
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

    def _query_errata(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query errata for the spec and format as prompt-ready strings.

        Handles missing ``errata`` table gracefully by returning an
        empty list.
        """
        try:
            from agent_fox.knowledge.errata import format_errata_for_prompt, query_errata

            errata = query_errata(conn, spec_name)
            return format_errata_for_prompt(errata)
        except Exception:
            logger.debug(
                "Could not query errata for %s",
                spec_name,
            )
            return []

    def _query_adrs(
        self,
        conn: Any,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        """Query ADRs matching the spec or task and format for prompt injection.

        Handles missing ``adr_entries`` table gracefully by returning
        an empty list (117-REQ-6.E1).

        Requirements: 117-REQ-6.1, 117-REQ-6.3
        """
        try:
            from agent_fox.knowledge.adr import format_adrs_for_prompt, query_adrs

            adrs = query_adrs(conn, spec_name, task_description)
            return format_adrs_for_prompt(adrs)
        except Exception:
            logger.debug(
                "Could not query ADRs for %s",
                spec_name,
            )
            return []

    def _query_verdicts(
        self,
        conn: Any,
        spec_name: str,
        task_group: str | None = None,
    ) -> list[str]:
        """Query active FAIL verdicts and format as prompt-ready strings.

        Only FAIL verdicts are returned — PASS verdicts indicate the
        requirement was satisfied and need not be re-injected.  Handles
        a missing ``verification_results`` table gracefully by returning
        an empty list (AC-3).

        When ``task_group`` is provided, only verdicts tagged for that
        group are returned (AC-4).

        Requirements: 555-AC-1, 555-AC-2, 555-AC-3, 555-AC-4
        """
        try:
            from agent_fox.knowledge.review_store import query_active_verdicts

            verdicts = query_active_verdicts(conn, spec_name, task_group=task_group)
        except Exception:
            logger.debug(
                "Could not query verification verdicts for %s",
                spec_name,
            )
            return []

        result: list[str] = []
        for v in verdicts:
            if v.verdict == "FAIL":
                parts = [f"[FAIL] {v.requirement_id}"]
                if v.evidence:
                    parts.append(v.evidence)
                result.append(f"[VERIFY] {' '.join(parts)}")
        return result
