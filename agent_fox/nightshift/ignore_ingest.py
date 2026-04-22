"""Knowledge ingestion of af:ignore signals for the hunt scan pipeline.

When a user marks a hunt issue with af:ignore, it indicates a false-positive
pattern that should be persisted into the knowledge store so future scans
can avoid reporting similar findings.

Requirements: 110-REQ-5.1 through 110-REQ-5.E3

Note: The Fact-based and _write_fact-based storage mechanism has been removed
as part of the knowledge decoupling (spec 114). This module's
``ingest_ignore_signals()`` function is now a no-op that returns 0
immediately. The helper functions are retained for potential future use.

Requirements updated by: 114-REQ-6.5
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


async def ingest_ignore_signals(
    platform: PlatformProtocol,
    conn: object | None,
    embedder: object | None = None,
    *,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> int:
    """No-op: previously ingested af:ignore issues into the knowledge store.

    The Fact-based storage mechanism was removed as part of the knowledge
    decoupling (spec 114, REQ-6.5). This function now returns 0 immediately
    without performing any action.

    Args:
        platform: Platform API implementation (unused).
        conn: DuckDB connection (unused).
        embedder: Embedding generator (unused).
        sink: Optional SinkDispatcher (unused).
        run_id: Run identifier string (unused).

    Returns:
        Always returns 0.
    """
    return 0
