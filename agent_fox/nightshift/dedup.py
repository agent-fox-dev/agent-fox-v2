"""Cross-iteration deduplication for the hunt scan pipeline.

Provides fingerprint computation, embedding, extraction, and duplicate
filtering so that the same maintenance problem is not reported twice
across consecutive scan iterations.

Supports two deduplication strategies:
1. Fingerprint matching (exact): SHA-256 of category + sorted files.
2. Embedding similarity (semantic): cosine similarity of text embeddings
   from an embedding model. Requires an embedder with ``embed_batch()``.

Requirements: 79-REQ-1.*, 79-REQ-2.*, 79-REQ-3.1, 79-REQ-4.*, 79-REQ-5.*,
              110-REQ-2.*, 110-REQ-3.*, 110-REQ-7.*
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.nightshift.finding import FindingGroup
    from agent_fox.platform.protocol import IssueResult, PlatformProtocol

from agent_fox.platform.labels import LABEL_HUNT

logger = logging.getLogger(__name__)

# Label applied to every issue created by the hunt scan pipeline.
# Used to efficiently query only night-shift-created issues during dedup.
FINGERPRINT_LABEL: str = LABEL_HUNT

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


def cosine_similarity(
    a: list[float] | None,
    b: list[float] | None,
) -> float:
    """Compute cosine similarity between two float vectors.

    Returns a float in [-1.0, 1.0]. Returns 0.0 if either vector
    is None or zero-length (or has zero magnitude).

    Requirements: 110-REQ-2.4, 110-REQ-2.E1
    """
    if not a or not b:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)


def build_finding_group_text(group: FindingGroup) -> str:
    """Build a text representation of a FindingGroup for embedding comparison.

    Format: '{category}: {title}\\nFiles: {file1}, {file2}, ...'

    Requirements: 110-REQ-2.2
    """
    files_str = ", ".join(group.affected_files)
    return f"{group.category}: {group.title}\nFiles: {files_str}"


def build_issue_text(issue: IssueResult) -> str:
    """Build a text representation of an IssueResult for embedding comparison.

    Format: '{title}\\n{body[:500]}'
    Body is truncated to the first 500 characters.

    Requirements: 110-REQ-2.3
    """
    body = issue.body or ""
    return f"{issue.title}\n{body[:500]}"


async def filter_known_duplicates(
    groups: list[FindingGroup],
    platform: PlatformProtocol,
    *,
    similarity_threshold: float = 0.85,
    embedder: object | None = None,
) -> list[FindingGroup]:
    """Fetch af:hunt issues (open + closed), return novel FindingGroups.

    Deduplication uses two strategies in order:

    1. **Fingerprint match** (exact): groups whose SHA-256 fingerprint matches
       any existing issue are skipped immediately (short-circuits embedding).
    2. **Embedding similarity** (semantic): for groups that pass fingerprint
       matching, cosine similarity is computed against all existing issues.
       Groups with similarity strictly greater than `similarity_threshold`
       are suppressed.

    On platform failure: logs warning, returns all groups (fail-open).
    On embedding failure: falls back to fingerprint-only mode (fail-open).

    Requirements: 110-REQ-3.1, 110-REQ-3.2, 110-REQ-3.3, 110-REQ-3.4,
                  110-REQ-3.5, 110-REQ-3.E1, 110-REQ-3.E2
    """
    # Fetch all af:hunt issues (open AND closed) in a single API call.
    # 110-REQ-3.1: state="all" covers both open and closed issues.
    try:
        existing_issues = await platform.list_issues_by_label(
            FINGERPRINT_LABEL,
            state="all",
        )
    except Exception:
        logger.warning(
            "Failed to fetch existing af:hunt issues for dedup check; proceeding without filtering (fail-open)",
            exc_info=True,
        )
        return list(groups)

    # Build a mapping from fingerprint -> issue number for known issues.
    known_fps: dict[str, int] = {}
    for issue in existing_issues:
        fp = extract_fingerprint(issue.body)  # type: ignore[union-attr]
        if fp is not None:
            known_fps[fp] = issue.number  # type: ignore[union-attr]

    # --- Pass 1: Fingerprint matching (short-circuit for 110-REQ-3.5) ---
    fp_novel: list[FindingGroup] = []
    for group in groups:
        fp = compute_fingerprint(group)
        if fp in known_fps:
            logger.info(
                "Skipping duplicate FindingGroup '%s' — matches existing issue #%d (fingerprint)",
                group.title,
                known_fps[fp],
            )
        else:
            fp_novel.append(group)

    # Early exit: no remaining groups or no embedder → fingerprint-only mode.
    # 110-REQ-2.E2: if embedder is None, fall back to fingerprint-only.
    if not fp_novel or embedder is None:
        return fp_novel

    # --- Pass 2: Embedding similarity matching (110-REQ-3.3) ---
    # Build text representations and batch-embed groups + issues together.
    group_texts = [build_finding_group_text(g) for g in fp_novel]
    issue_texts = [build_issue_text(issue) for issue in existing_issues]
    all_texts = group_texts + issue_texts

    if not issue_texts:
        # No existing issues to compare against.
        return fp_novel

    try:
        all_embeddings = embedder.embed_batch(all_texts)
    except Exception:
        logger.warning(
            "Embedding computation failed during dedup; falling back to fingerprint-only matching (fail-open)",
            exc_info=True,
        )
        return fp_novel

    group_embeddings = all_embeddings[: len(group_texts)]
    issue_embeddings = all_embeddings[len(group_texts) :]

    novel: list[FindingGroup] = []
    for group, group_emb in zip(fp_novel, group_embeddings):
        suppressed = False
        for issue, issue_emb in zip(existing_issues, issue_embeddings):
            sim = cosine_similarity(group_emb, issue_emb)
            # Strict > comparison: 110-REQ-3.3 says "exceeds threshold".
            # At threshold=0.0, any positive similarity (> 0.0) is a match.
            if sim > similarity_threshold:
                logger.info(
                    "Skipping similar FindingGroup '%s' — matches existing issue #%d "
                    "(embedding similarity %.3f > threshold %.3f)",
                    group.title,
                    issue.number,
                    sim,
                    similarity_threshold,
                )
                suppressed = True
                break
        if not suppressed:
            novel.append(group)

    return novel
