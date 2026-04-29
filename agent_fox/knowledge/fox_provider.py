"""KnowledgeProvider protocol and concrete implementation.

Defines the KnowledgeProvider protocol (the clean boundary between the
engine and any knowledge implementation) and the concrete
FoxKnowledgeProvider (review carry-forward + ADR retrieval).

Requirements: 116-REQ-1.3, 116-REQ-1.4, 116-REQ-2.2,
              116-REQ-6.1, 116-REQ-6.2, 116-REQ-6.3, 116-REQ-6.E1,
              117-REQ-1.1, 117-REQ-6.1, 117-REQ-6.3, 117-REQ-7.4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_fox.core.config import KnowledgeProviderConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import KnowledgeDB

logger = logging.getLogger(__name__)


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Protocol defining the interface between the engine and a knowledge implementation.

    Any class that implements both ``ingest`` and ``retrieve`` with the
    correct signatures satisfies this protocol at runtime (``isinstance``
    check) thanks to the ``@runtime_checkable`` decorator.
    """

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session."""
        ...

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
        task_group: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        """Retrieve knowledge context for an upcoming session."""
        ...


class NoOpKnowledgeProvider:
    """Knowledge provider that does nothing.

    Default implementation used when no knowledge system is configured.
    ``ingest()`` is a no-op and ``retrieve()`` always returns an empty list.
    """

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Accept and discard session knowledge context."""
        return None

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
        task_group: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        """Return an empty list --- no knowledge is available."""
        return []


# Severity ordering for sorting — lower value = higher priority.
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "major": 1, "minor": 2, "observation": 3}


def _extract_keywords(task_description: str) -> frozenset[str]:
    """Extract lowercase words from *task_description* for relevance scoring.

    Returns an empty frozenset when *task_description* is blank, which
    causes ``_score_relevance`` to return 0 for every item and preserves
    the existing severity/description sort order (AC-3).
    """
    return frozenset(word.lower() for word in task_description.split() if word)


def _score_relevance(text: str, keywords: frozenset[str]) -> int:
    """Count how many *keywords* appear as substrings in *text* (case-insensitive).

    Returns 0 when *keywords* is empty so that an absent or blank
    ``task_description`` has no effect on ordering (AC-3).
    """
    if not keywords:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def generate_archetype_summary(
    archetype: str,
    findings: list[Any] | None = None,
    verdicts: list[Any] | None = None,
) -> str:
    """Generate a summary string for reviewer or verifier sessions.

    For reviewer: counts findings by severity and includes descriptions of
    up to 3 top-severity findings.
    For verifier: counts pass/fail verdicts and lists the requirement IDs
    of all FAIL verdicts.

    Returns a non-empty string even when the input lists are empty
    (120-REQ-3.E1, 120-REQ-3.E2).

    Requirements: 120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.E1, 120-REQ-3.E2
    """
    if archetype == "reviewer":
        if not findings:
            return "Reviewer session completed with no findings."
        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = getattr(f, "severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        # Build count string ordered by severity rank
        count_parts: list[str] = []
        for sev in ["critical", "major", "minor", "observation"]:
            if sev in severity_counts:
                count_parts.append(f"{severity_counts[sev]} {sev}")
        count_str = ", ".join(count_parts) if count_parts else "0 findings"
        # Include up to 3 top-severity finding descriptions
        sorted_findings = sorted(
            findings,
            key=lambda f: _SEVERITY_RANK.get(getattr(f, "severity", ""), 99),
        )
        top_descriptions = [
            getattr(f, "description", "") for f in sorted_findings[:3]
        ]
        desc_str = "; ".join(top_descriptions)
        return f"Reviewer session completed with {count_str}. Top findings: {desc_str}"

    if archetype == "verifier":
        if not verdicts:
            return "Verifier session completed with no verdicts."
        pass_count = sum(1 for v in verdicts if getattr(v, "verdict", "") == "PASS")
        fail_count = sum(1 for v in verdicts if getattr(v, "verdict", "") == "FAIL")
        fail_req_ids = [
            getattr(v, "requirement_id", "")
            for v in verdicts
            if getattr(v, "verdict", "") == "FAIL"
        ]
        parts = [f"Verifier session completed with {pass_count} pass, {fail_count} fail."]
        if fail_req_ids:
            parts.append(f"Failed requirements: {', '.join(fail_req_ids)}")
        return " ".join(parts)

    return f"{archetype} session completed."


class FoxKnowledgeProvider:
    """Concrete KnowledgeProvider: review carry-forward + ADR retrieval.

    Retrieves active critical/major review findings, errata, ADR
    summaries, and session summaries for a spec.  Ingests ADR files
    detected in session ``touched_files`` and stores session summaries.
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
        self._run_id: str | None = None

    def set_run_id(self, run_id: str) -> None:
        """Set the current run ID for summary queries.

        Stores the run ID for use in ``_query_same_spec_summaries()`` and
        ``_query_cross_spec_summaries()``.  An empty string is treated as
        unset (``None``).

        Requirements: 120-REQ-1.1, 120-REQ-1.2
        """
        self._run_id = run_id if run_id else None

    # ------------------------------------------------------------------
    # KnowledgeProvider protocol methods
    # ------------------------------------------------------------------

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
        task_group: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        """Retrieve knowledge context for an upcoming session.

        Queries active critical/major review findings, errata, and ADR
        summaries for the given spec and returns them as prefixed strings,
        capped at ``max_items``.

        When *session_id* is provided, the IDs of every review finding and
        verification verdict that appears in the returned list are recorded in
        the ``finding_injections`` table.  A subsequent successful
        ``ingest()`` call for the same session then supersedes those findings
        so they are not re-injected into future sessions.

        Args:
            spec_name: Name of the spec being worked on.
            task_description: Human-readable description of the task.
            task_group: Optional task group identifier to restrict review
                findings to those tagged for this group.  When ``None``,
                findings from all task groups are returned.
            session_id: Optional node ID of the current session.  When
                provided, injected finding/verdict IDs are persisted for
                later deduplication.  Callers that omit this parameter
                get the same retrieval behaviour as before (backward-
                compatible default).

        Returns:
            List of formatted text blocks ready for prompt injection.

        Raises:
            KnowledgeStoreError: If the database connection is closed or
                a query fails unexpectedly.

        Requirements: 117-REQ-6.1, 117-REQ-6.3, 558-AC-1, 558-AC-4
        """
        try:
            conn = self._knowledge_db.connection
        except KnowledgeStoreError:
            raise

        reviews, review_ids = self._query_reviews(
            conn, spec_name, task_group=task_group, task_description=task_description
        )
        errata = self._query_errata(conn, spec_name)
        adrs = self._query_adrs(conn, spec_name, task_description)
        verdicts, verdict_ids = self._query_verdicts(
            conn, spec_name, task_group=task_group, task_description=task_description
        )

        # Build a parallel list of (text, optional_id) so we can track which
        # finding/verdict IDs survive the max_items cap.
        items_with_ids: list[tuple[str, str | None]] = []
        for text, id_ in zip(reviews, review_ids):
            items_with_ids.append((text, id_))
        for text in errata:
            items_with_ids.append((text, None))
        for text in adrs:
            items_with_ids.append((text, None))
        for text, id_ in zip(verdicts, verdict_ids):
            items_with_ids.append((text, id_))

        # Cross-group items: findings and FAIL verdicts from other task groups
        # in the same spec.  These are informational (not tracked for injection)
        # and have their own cap (issue #559).
        cross_group_items: list[str] = []
        if task_group is not None:
            cross_reviews = self._query_cross_group_reviews(conn, spec_name, task_group, task_description)
            cross_verdicts = self._query_cross_group_verdicts(conn, spec_name, task_group, task_description)
            cross_group_items = (cross_reviews + cross_verdicts)[: self._config.max_cross_group_items]

        capped = items_with_ids[: self._config.max_items]
        result = [text for text, _ in capped] + cross_group_items

        # Session summary injection (119-REQ-2.1, 119-REQ-3.1)
        same_spec_summaries = self._query_same_spec_summaries(conn, spec_name, task_group)
        cross_spec_summaries = self._query_cross_spec_summaries(conn, spec_name)
        result.extend(same_spec_summaries)
        result.extend(cross_spec_summaries)

        # Prior-run carry-forward (120-REQ-4.1, 120-REQ-4.2).
        # Informational context, NOT tracked in finding_injections (120-REQ-4.4).
        prior_run_items, prior_run_ids = self._query_prior_run_findings(conn, spec_name)
        result.extend(prior_run_items)

        logger.debug(
            "Retrieved %d review + %d errata + %d ADR + %d verdict + %d cross-group "
            "+ %d context + %d cross-spec + %d prior-run items for %s",
            len(reviews),
            len(errata),
            len(adrs),
            len(verdicts),
            len(cross_group_items),
            len(same_spec_summaries),
            len(cross_spec_summaries),
            len(prior_run_items),
            spec_name,
        )

        # Record which finding/verdict IDs were injected into this session so
        # that a successful ingest() can supersede them later (558-AC-1).
        # Cross-group items and prior-run items are NOT tracked — they are
        # informational context (120-REQ-4.4).
        if session_id:
            injected_ids = [
                id_ for _, id_ in capped
                if id_ is not None and id_ not in prior_run_ids
            ]
            if injected_ids:
                try:
                    from agent_fox.knowledge.review_store import record_finding_injections

                    record_finding_injections(conn, injected_ids, session_id)
                except Exception:
                    logger.warning(
                        "Failed to record injection log for session %s",
                        session_id,
                        exc_info=True,
                    )

        return result

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session.

        On successful completion (``context['session_status'] == 'completed'``),
        supersedes all review findings and verification verdicts that were
        previously injected into the session (recorded in the
        ``finding_injections`` table), preventing them from being re-injected
        into subsequent sessions for the same spec.

        Also detects ADR files in ``touched_files`` and ingests them into
        the knowledge database.  Gotcha extraction was removed in spec 116.

        Args:
            session_id: Node ID of the completed session.
            spec_name: Name of the spec the session belongs to.
            context: Dict with ``session_status``, ``touched_files``,
                ``commit_sha``, and ``project_root``.

        Requirements: 117-REQ-1.1, 117-REQ-7.4, 558-AC-2
        """
        session_status = context.get("session_status", "")

        # Acquire the DB connection once for both finding supersession and
        # ADR ingestion.  If unavailable, log and bail out early.
        try:
            conn = self._knowledge_db.connection
        except KnowledgeStoreError:
            logger.warning(
                "Knowledge DB unavailable for ingestion in session %s",
                session_id,
            )
            return

        # Supersede injected findings when the session completed successfully
        # (558-AC-2).  A failed or incomplete session must NOT supersede findings
        # so retry sessions still see them (558-AC-3).
        if session_status == "completed":
            try:
                from agent_fox.knowledge.review_store import supersede_injected_findings

                supersede_injected_findings(conn, session_id)
            except Exception:
                logger.warning(
                    "Failed to supersede injected findings for session %s",
                    session_id,
                    exc_info=True,
                )

        # Session summary storage (119-REQ-5.2).
        # Only store for completed sessions with a non-empty summary.
        summary_text = context.get("summary")
        if session_status == "completed" and summary_text:
            self._store_summary(conn, session_id, spec_name, context)

        # ADR ingestion (unchanged from spec 117).
        from agent_fox.knowledge.adr import detect_adr_changes, ingest_adr

        touched_files = context.get("touched_files") or []
        project_root_str = context.get("project_root", "")
        if not project_root_str:
            return

        project_root = Path(str(project_root_str))
        adr_paths = detect_adr_changes(touched_files)
        if not adr_paths:
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
        task_description: str = "",
    ) -> tuple[list[str], list[str]]:
        """Query unresolved critical/major review findings for the spec.

        Returns a tuple of ``(formatted_strings, finding_ids)`` so that
        ``retrieve()`` can record which finding IDs were injected.

        Handles missing ``review_findings`` table gracefully by returning
        empty lists (116-REQ-6.E1).  Filters to ``critical`` and
        ``major`` severity only (116-REQ-6.1).

        When ``task_group`` is provided, only findings tagged for that group
        are returned, reducing noise for sessions focused on a specific
        task group.  When ``None``, all active findings for the spec are
        returned (backward-compatible behaviour).

        Findings are sorted by:
          1. Severity (critical before major — primary key, always preserved).
          2. Relevance score — keyword overlap with ``task_description``
             (higher overlap ranks first within a severity tier).
          3. Description (alphabetical — stable tiebreaker).

        When ``task_description`` is blank, relevance scores are all zero and
        the sort reduces to the existing severity/description order (AC-3).

        ``query_active_findings`` already excludes non-actionable severities;
        the ``if f.severity in (...)`` guard below is defense-in-depth and
        kept consistent with that filter (issue #553).
        """
        try:
            from agent_fox.knowledge.review_store import query_active_findings

            # Elevate pre-review (group 0) findings into primary review results
            # when the session targets a non-zero task group so they are tracked
            # via finding_injections and can be superseded (120-REQ-2.1, 120-REQ-2.2).
            include_prereview = task_group is not None and task_group != "0"
            findings = query_active_findings(
                conn, spec_name, task_group=task_group, include_prereview=include_prereview
            )
        except Exception:
            # Table may not exist in a fresh database (116-REQ-6.E1).
            logger.debug(
                "Could not query review findings for %s",
                spec_name,
            )
            return [], []

        keywords = _extract_keywords(task_description)
        actionable = [f for f in findings if f.severity in ("critical", "major")]
        actionable.sort(
            key=lambda f: (
                _SEVERITY_RANK.get(f.severity, 99),
                -_score_relevance(f"{f.category or ''} {f.description}", keywords),
                f.description,
            )
        )

        result: list[str] = []
        ids: list[str] = []
        for f in actionable:
            parts = [f"[{f.severity}]"]
            if f.category:
                parts.append(f"{f.category}:")
            parts.append(f.description)
            result.append(f"[REVIEW] {' '.join(parts)}")
            ids.append(f.id)
        return result, ids

    def _query_cross_group_reviews(
        self,
        conn: Any,
        spec_name: str,
        task_group: str,
        task_description: str,
    ) -> list[str]:
        """Query active findings from *other* task groups in the same spec.

        Returns formatted strings with a ``[CROSS-GROUP]`` prefix that includes
        the source task group for context.  Uses the same relevance scoring as
        same-group retrieval so the most relevant cross-group findings surface
        first.

        These items are informational — they are NOT tracked in
        ``finding_injections`` and are not expected to be "fixed" by the
        current session.
        """
        try:
            from agent_fox.knowledge.review_store import query_cross_group_findings

            # Exclude pre-review (group 0) findings from cross-group results
            # when the caller is not group 0 itself, since those findings are
            # elevated into primary review results (120-REQ-2.3, 120-REQ-2.E2).
            exclude_prereview = task_group != "0"
            findings = query_cross_group_findings(
                conn, spec_name, task_group, exclude_prereview=exclude_prereview
            )
        except Exception:
            logger.debug(
                "Could not query cross-group findings for %s",
                spec_name,
            )
            return []

        keywords = _extract_keywords(task_description)
        actionable = [f for f in findings if f.severity in ("critical", "major")]
        actionable.sort(
            key=lambda f: (
                _SEVERITY_RANK.get(f.severity, 99),
                -_score_relevance(f"{f.category or ''} {f.description}", keywords),
                f.description,
            )
        )

        result: list[str] = []
        for f in actionable:
            parts = [f"[{f.severity}]"]
            if f.category:
                parts.append(f"{f.category}:")
            parts.append(f.description)
            result.append(f"[CROSS-GROUP] (group {f.task_group}) {' '.join(parts)}")
        return result

    def _query_cross_group_verdicts(
        self,
        conn: Any,
        spec_name: str,
        task_group: str,
        task_description: str,
    ) -> list[str]:
        """Query active FAIL verdicts from *other* task groups in the same spec.

        Returns formatted strings with a ``[CROSS-GROUP]`` prefix.  Only FAIL
        verdicts are returned — PASS verdicts are not actionable.
        """
        try:
            from agent_fox.knowledge.review_store import query_cross_group_verdicts

            verdicts = query_cross_group_verdicts(conn, spec_name, task_group)
        except Exception:
            logger.debug(
                "Could not query cross-group verdicts for %s",
                spec_name,
            )
            return []

        keywords = _extract_keywords(task_description)
        fail_verdicts = [v for v in verdicts if v.verdict == "FAIL"]
        fail_verdicts.sort(
            key=lambda v: (
                -_score_relevance(f"{v.requirement_id} {v.evidence or ''}", keywords),
                v.requirement_id,
            )
        )

        result: list[str] = []
        for v in fail_verdicts:
            parts = [f"[FAIL] {v.requirement_id}"]
            if v.evidence:
                parts.append(v.evidence)
            result.append(f"[CROSS-GROUP] (group {v.task_group}) {' '.join(parts)}")
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
        task_description: str = "",
    ) -> tuple[list[str], list[str]]:
        """Query active FAIL verdicts and format as prompt-ready strings.

        Returns a tuple of ``(formatted_strings, verdict_ids)`` so that
        ``retrieve()`` can record which verdict IDs were injected.

        Only FAIL verdicts are returned — PASS verdicts indicate the
        requirement was satisfied and need not be re-injected.  Handles
        a missing ``verification_results`` table gracefully by returning
        empty lists (AC-3).

        When ``task_group`` is provided, only verdicts tagged for that
        group are returned (AC-4).

        Verdicts are sorted by:
          1. Relevance score — keyword overlap with ``task_description``
             (higher overlap ranks first).
          2. Requirement ID (stable alphabetical tiebreaker).

        When ``task_description`` is blank, relevance scores are all zero
        and the sort reduces to requirement_id order.

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
            return [], []

        keywords = _extract_keywords(task_description)
        fail_verdicts = [v for v in verdicts if v.verdict == "FAIL"]
        fail_verdicts.sort(
            key=lambda v: (
                -_score_relevance(f"{v.requirement_id} {v.evidence or ''}", keywords),
                v.requirement_id,
            )
        )

        result: list[str] = []
        ids: list[str] = []
        for v in fail_verdicts:
            parts = [f"[FAIL] {v.requirement_id}"]
            if v.evidence:
                parts.append(v.evidence)
            result.append(f"[VERIFY] {' '.join(parts)}")
            ids.append(v.id)
        return result, ids

    # ------------------------------------------------------------------
    # Session summary helpers (spec 119)
    # ------------------------------------------------------------------

    def _query_same_spec_summaries(
        self,
        conn: Any,
        spec_name: str,
        task_group: str | None,
    ) -> list[str]:
        """Query and format same-spec summaries as [CONTEXT] items.

        Requirements: 119-REQ-2.1, 119-REQ-2.2
        """
        if task_group is None:
            return []

        run_id = self._run_id
        if not run_id:
            return []

        try:
            from agent_fox.knowledge.summary_store import query_same_spec_summaries

            records = query_same_spec_summaries(conn, spec_name, task_group, run_id)
        except Exception:
            logger.debug(
                "Could not query same-spec summaries for %s",
                spec_name,
            )
            return []

        return [
            f"[CONTEXT] ({r.archetype}, group {r.task_group}, attempt {r.attempt}) {r.summary}"
            for r in records
        ]

    def _query_cross_spec_summaries(
        self,
        conn: Any,
        spec_name: str,
    ) -> list[str]:
        """Query and format cross-spec summaries as [CROSS-SPEC] items.

        Requirements: 119-REQ-3.1, 119-REQ-3.2, 119-REQ-3.E2
        """
        run_id = self._run_id
        if not run_id:
            return []

        try:
            from agent_fox.knowledge.summary_store import query_cross_spec_summaries

            records = query_cross_spec_summaries(conn, spec_name, run_id)
        except Exception:
            logger.debug(
                "Could not query cross-spec summaries for %s",
                spec_name,
            )
            return []

        return [f"[CROSS-SPEC] ({r.spec_name}, group {r.task_group}) {r.summary}" for r in records]

    def _query_prior_run_findings(
        self,
        conn: Any,
        spec_name: str,
    ) -> tuple[list[str], set[str]]:
        """Query prior-run findings and verdicts, formatted as [PRIOR-RUN] items.

        Returns a tuple of ``(formatted_items, prior_run_ids)`` where
        ``prior_run_ids`` is the set of finding/verdict IDs from prior runs.
        The IDs are used by ``retrieve()`` to exclude prior-run items from
        ``finding_injections`` tracking (120-REQ-4.4).

        Returns unresolved critical/major findings and FAIL verdicts from
        prior runs (i.e. created before the current run started).  These
        are informational context — they are NOT tracked in
        ``finding_injections`` (120-REQ-4.4).

        When ``_run_id`` is not set, returns empty collections (no way to
        distinguish prior from current without a run reference).

        Requirements: 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.4, 120-REQ-4.5
        """
        if not self._run_id:
            return [], set()

        max_items = self._config.max_prior_run_items

        result: list[str] = []
        prior_ids: set[str] = set()

        try:
            from agent_fox.knowledge.review_store import query_prior_run_findings

            findings = query_prior_run_findings(conn, spec_name, self._run_id, max_items=max_items)
            for f in findings:
                parts = [f"[{f.severity}]"]
                if f.category:
                    parts.append(f"{f.category}:")
                parts.append(f.description)
                result.append(f"[PRIOR-RUN] (spec {spec_name}) {' '.join(parts)}")
                prior_ids.add(f.id)
        except Exception:
            logger.debug(
                "Could not query prior-run findings for %s",
                spec_name,
            )

        try:
            from agent_fox.knowledge.review_store import query_prior_run_verdicts

            verdicts = query_prior_run_verdicts(conn, spec_name, self._run_id, max_items=max_items)
            for v in verdicts:
                parts = [f"[FAIL] {v.requirement_id}"]
                if v.evidence:
                    parts.append(v.evidence)
                result.append(f"[PRIOR-RUN] (spec {spec_name}) {' '.join(parts)}")
                prior_ids.add(v.id)
        except Exception:
            logger.debug(
                "Could not query prior-run verdicts for %s",
                spec_name,
            )

        return result, prior_ids

    def _store_summary(
        self,
        conn: Any,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Store a session summary in the database.

        Extracts archetype, task_group, and attempt from the context dict
        and inserts a SummaryRecord.  Handles DB failures gracefully.

        Requirements: 119-REQ-5.2, 119-REQ-5.E1
        """
        import uuid

        try:
            from agent_fox.knowledge.summary_store import SummaryRecord, insert_summary

            summary_text = context.get("summary", "")
            archetype = context.get("archetype", "coder")
            task_group = str(context.get("task_group", "0"))
            attempt = int(context.get("attempt", 1))
            run_id = context.get("run_id", "") or (self._run_id or "")

            record = SummaryRecord(
                id=str(uuid.uuid4()),
                node_id=session_id,
                run_id=run_id,
                spec_name=spec_name,
                task_group=task_group,
                archetype=archetype,
                attempt=attempt,
                summary=summary_text,
                created_at=context.get("created_at", "")
                or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            )
            insert_summary(conn, record)
            logger.info(
                "Stored session summary for %s (group %s, attempt %d)",
                session_id,
                task_group,
                attempt,
            )
        except Exception:
            logger.warning(
                "Failed to store session summary for %s",
                session_id,
                exc_info=True,
            )
