"""Cross-iteration deduplication for the hunt scan pipeline.

Provides fingerprint computation, embedding, extraction, and duplicate
filtering so that the same maintenance problem is not reported twice
across consecutive scan iterations.

Requirements: 79-REQ-1.*, 79-REQ-2.*, 79-REQ-3.1, 79-REQ-4.*, 79-REQ-5.*
"""

from __future__ import annotations

import hashlib
import logging
import re

from agent_fox.nightshift.finding import FindingGroup

logger = logging.getLogger(__name__)

# Label applied to every issue created by the hunt scan pipeline.
# Used to efficiently query only night-shift-created issues during dedup.
FINGERPRINT_LABEL: str = "af:hunt"

# Regex pattern for extracting fingerprint markers from issue bodies.
_FINGERPRINT_PATTERN: re.Pattern[str] = re.compile(r"<!-- af:fingerprint:([0-9a-f]{16}) -->")


def compute_fingerprint(group: FindingGroup) -> str:
    """Compute a 16-char hex fingerprint for a FindingGroup.

    Hash input: category + NUL + sorted(deduplicated(affected_files)) joined by NUL.
    Returns first 16 hex characters of SHA-256 digest.

    If affected_files is empty, hashes only the category field.

    Requirements: 79-REQ-1.1, 79-REQ-1.2, 79-REQ-1.3, 79-REQ-1.E1, 79-REQ-1.E2,
                  79-REQ-5.1, 79-REQ-5.2, 79-REQ-5.E1
    """
    # Deduplicate and sort files lexicographically for determinism.
    unique_sorted_files = sorted(set(group.affected_files))

    if unique_sorted_files:
        # Null-byte separator between all fields prevents ambiguity:
        # category="ab" + file="c" differs from category="a" + file="bc".
        raw = group.category + "\0" + "\0".join(unique_sorted_files)
    else:
        raw = group.category

    digest = hashlib.sha256(raw.encode()).hexdigest()
    return digest[:16]


def embed_fingerprint(body: str, fingerprint: str) -> str:
    """Append fingerprint marker to issue body.

    Returns body + newline + '<!-- af:fingerprint:{fp} -->'.

    Requirements: 79-REQ-2.1
    """
    return body + f"\n<!-- af:fingerprint:{fingerprint} -->"


def extract_fingerprint(body: str) -> str | None:
    """Extract fingerprint from issue body.

    Returns 16-char hex string or None if no marker found.
    Matches first occurrence if multiple markers are present.

    Requirements: 79-REQ-2.2, 79-REQ-2.E1, 79-REQ-2.E2
    """
    match = _FINGERPRINT_PATTERN.search(body)
    if match is None:
        return None
    return match.group(1)


async def filter_known_duplicates(
    groups: list[FindingGroup],
    platform: object,
) -> list[FindingGroup]:
    """Fetch open af:hunt issues, extract fingerprints, return novel groups.

    On platform failure: logs warning, returns all groups (fail-open).
    For each skipped group: logs INFO with group title and matching issue number.

    Requirements: 79-REQ-4.1, 79-REQ-4.2, 79-REQ-4.3, 79-REQ-4.4,
                  79-REQ-4.E1, 79-REQ-4.E2, 79-REQ-4.E3
    """
    # Fetch all open af:hunt issues in a single API call (79-REQ-4.1).
    try:
        existing_issues = await platform.list_issues_by_label(  # type: ignore[union-attr]
            FINGERPRINT_LABEL,
            state="open",
        )
    except Exception:
        logger.warning(
            "Failed to fetch existing af:hunt issues for dedup check; proceeding without filtering (fail-open)",
            exc_info=True,
        )
        return list(groups)

    # Build a mapping from fingerprint -> issue number for known issues.
    known: dict[str, int] = {}
    for issue in existing_issues:
        fp = extract_fingerprint(issue.body)  # type: ignore[union-attr]
        if fp is not None:
            known[fp] = issue.number  # type: ignore[union-attr]

    # Filter out groups whose fingerprint matches a known issue.
    novel: list[FindingGroup] = []
    for group in groups:
        fp = compute_fingerprint(group)
        if fp in known:
            logger.info(
                "Skipping duplicate FindingGroup '%s' — matches existing issue #%d",
                group.title,
                known[fp],
            )
        else:
            novel.append(group)

    return novel
