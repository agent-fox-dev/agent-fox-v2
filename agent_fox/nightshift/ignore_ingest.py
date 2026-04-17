"""Knowledge ingestion of af:ignore signals for the hunt scan pipeline.

When a user marks a hunt issue with af:ignore, it indicates a false-positive
pattern that should be persisted into the knowledge store so future scans
can avoid reporting similar findings.

Requirements: 110-REQ-5.1 through 110-REQ-5.E3
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import duckdb

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.git_mining import _write_fact
from agent_fox.platform.labels import LABEL_IGNORE

if TYPE_CHECKING:
    from agent_fox.knowledge.embeddings import EmbeddingGenerator
    from agent_fox.knowledge.sink import SinkDispatcher
    from agent_fox.platform.protocol import IssueResult, PlatformProtocol

logger = logging.getLogger(__name__)

# HTML comment marker embedded in issue bodies after knowledge ingestion.
_KNOWLEDGE_INGESTED_MARKER: str = "<!-- af:knowledge-ingested -->"

# Regex to detect the ingestion marker in an issue body.
_INGESTED_RE: re.Pattern[str] = re.compile(re.escape(_KNOWLEDGE_INGESTED_MARKER))

# Regex to extract the hunt category from the **Category:** field.
_CATEGORY_RE: re.Pattern[str] = re.compile(r"\*\*Category:\*\*\s*(\S+)")

# Minimum word length for keyword extraction.
_MIN_KEYWORD_LEN: int = 3


def extract_category_from_body(body: str) -> str:
    """Extract the hunt category from an issue body.

    Parses the ``**Category:** value`` field present in all hunt-generated
    issue bodies.

    Args:
        body: The full issue body text.

    Returns:
        The category string (e.g. ``"dead_code"``), or ``"unknown"`` if the
        field is not found.

    Requirements: 110-REQ-5.4, 110-REQ-5.E10
    """
    match = _CATEGORY_RE.search(body)
    if match:
        return match.group(1).strip()
    return "unknown"


def _is_ingested(issue: IssueResult) -> bool:
    """Return True if the issue body already contains the ingestion marker.

    Requirements: 110-REQ-5.1, 110-REQ-5.E1
    """
    return bool(_INGESTED_RE.search(issue.body))


def _extract_keywords(title: str) -> list[str]:
    """Extract keywords from an issue title by simple word tokenization.

    Splits on non-word characters, lowercases, and filters short tokens.
    This mirrors the minor finding from the Skeptic review — an explicit
    but simple algorithm is used since no extraction library is available.

    Requirements: 110-REQ-5.2
    """
    return [word.lower() for word in re.split(r"\W+", title) if len(word) >= _MIN_KEYWORD_LEN]


def _build_fact_from_issue(issue: IssueResult) -> Fact:
    """Build an anti_pattern Fact from an af:ignore issue.

    Requirements: 110-REQ-5.2
    """
    category = extract_category_from_body(issue.body)
    keywords = _extract_keywords(issue.title)

    content = f"Hunt false positive: {issue.title}. Category: {category}. User marked as af:ignore."

    return Fact(
        id=str(uuid.uuid4()),
        content=content,
        category="anti_pattern",
        spec_name="nightshift:ignore",
        keywords=keywords,
        confidence=0.9,
        created_at=datetime.now(UTC).isoformat(),
        session_id=None,
        commit_sha=None,
    )


async def ingest_ignore_signals(
    platform: PlatformProtocol,
    conn: duckdb.DuckDBPyConnection | None,
    embedder: EmbeddingGenerator | None,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> int:
    """Ingest af:ignore issues into the knowledge store as anti_pattern facts.

    For each af:ignore issue (open or closed) that has not yet been ingested
    (i.e. lacks the ``<!-- af:knowledge-ingested -->`` marker in its body),
    this function:

    1. Creates an ``anti_pattern`` fact in the knowledge store.
    2. Appends the ingestion marker to the issue body via the platform API.

    Fail-open on all error conditions:
    - If ``conn`` is None, returns 0 and logs a warning.
    - If the platform API call to fetch issues fails, returns 0 and logs a
      warning.
    - If ``update_issue`` fails for a specific issue, logs a warning and
      continues (the fact is still stored; re-ingestion on next scan is
      acceptable per 110-REQ-5.E2).

    Args:
        platform: Platform API implementation (GitHub, etc.).
        conn: DuckDB connection to the knowledge store.  If None, ingestion
              is skipped entirely (110-REQ-5.E3).
        embedder: EmbeddingGenerator instance (accepted but unused; _write_fact
                  does not generate embeddings — kept in signature for API
                  consistency with other pipeline functions).
        sink: Optional SinkDispatcher for audit events (reserved for future use).
        run_id: Run identifier string (reserved for future use).

    Returns:
        The count of newly ingested facts (0 if none were ingested).

    Requirements: 110-REQ-5.1, 110-REQ-5.2, 110-REQ-5.3, 110-REQ-5.4,
                  110-REQ-5.E1, 110-REQ-5.E2, 110-REQ-5.E3
    """
    # 110-REQ-5.E3: knowledge store unavailable → skip ingestion entirely.
    if conn is None:
        logger.warning("Knowledge store unavailable (conn=None); skipping af:ignore ingestion")
        return 0

    # Fetch all af:ignore issues (open AND closed) in a single API call.
    try:
        ignore_issues = await platform.list_issues_by_label(
            LABEL_IGNORE,
            state="all",
        )
    except Exception:
        logger.warning(
            "Failed to fetch af:ignore issues from platform; skipping ingestion",
            exc_info=True,
        )
        return 0

    count = 0
    for issue in ignore_issues:
        # 110-REQ-5.E1: skip issues that already carry the ingestion marker.
        if _is_ingested(issue):
            continue

        # 110-REQ-5.2: build and persist the anti_pattern fact.
        fact = _build_fact_from_issue(issue)
        _write_fact(conn, fact)
        logger.info(
            "Ingested af:ignore issue #%d '%s' as anti_pattern fact (spec_name='nightshift:ignore', confidence=0.9)",
            issue.number,
            issue.title,
        )
        count += 1

        # 110-REQ-5.3: append the ingestion marker to the issue body.
        new_body = issue.body + f"\n{_KNOWLEDGE_INGESTED_MARKER}"
        try:
            await platform.update_issue(issue.number, new_body)
        except Exception:
            # 110-REQ-5.E2: marker update failure is non-fatal.
            logger.warning(
                "Failed to append ingestion marker to issue #%d; continuing (re-ingestion possible on next scan)",
                issue.number,
                exc_info=True,
            )

    return count
