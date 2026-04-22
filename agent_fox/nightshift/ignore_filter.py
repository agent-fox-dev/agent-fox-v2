"""Ignore filter gate for the hunt scan pipeline.

Filters FindingGroups that are semantically similar to af:ignore issues,
preventing false-positive findings from being re-reported after users
have marked them as not-an-issue.

Requirements: 110-REQ-4.1, 110-REQ-4.2, 110-REQ-4.3, 110-REQ-4.4,
              110-REQ-4.E1, 110-REQ-4.E2, 110-REQ-4.E3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.nightshift.finding import FindingGroup
    from agent_fox.platform.protocol import PlatformProtocol

from agent_fox.nightshift.dedup import (
    EmbedderProtocol,
    build_finding_group_text,
    build_issue_text,
    cosine_similarity,
)
from agent_fox.platform.labels import LABEL_IGNORE

logger = logging.getLogger(__name__)


async def filter_ignored(
    groups: list[FindingGroup],
    platform: PlatformProtocol,
    *,
    similarity_threshold: float = 0.85,
    embedder: EmbedderProtocol | None = None,
) -> list[FindingGroup]:
    """Fetch af:ignore issues (open + closed), return novel FindingGroups.

    Groups with embedding similarity strictly greater than `similarity_threshold`
    to any af:ignore issue are suppressed.

    If no embedder is provided, all groups are returned unfiltered (fail-open),
    since semantic comparison is not possible without embeddings.

    On platform failure: logs warning, returns all groups (fail-open).
    On embedding failure: logs warning, returns all groups (fail-open).

    Requirements: 110-REQ-4.1, 110-REQ-4.2, 110-REQ-4.3, 110-REQ-4.4,
                  110-REQ-4.E1, 110-REQ-4.E2, 110-REQ-4.E3
    """
    if not groups:
        return []

    # Fetch all af:ignore issues (open AND closed) in a single API call.
    # 110-REQ-4.2: state="all" covers both open and closed issues.
    try:
        ignore_issues = await platform.list_issues_by_label(
            LABEL_IGNORE,
            state="all",
        )
    except Exception:
        logger.warning(
            "Failed to fetch af:ignore issues; returning all groups unfiltered (fail-open)",
            exc_info=True,
        )
        return list(groups)

    # 110-REQ-4.E1: no ignore issues → return all groups unfiltered.
    if not ignore_issues:
        return list(groups)

    # 110-REQ-4.E3: no embedder → fail-open (semantic comparison not possible).
    if embedder is None:
        return list(groups)

    # Build text representations and batch-embed groups + issues together.
    group_texts = [build_finding_group_text(g) for g in groups]
    issue_texts = [build_issue_text(issue) for issue in ignore_issues]
    all_texts = group_texts + issue_texts

    try:
        all_embeddings = embedder.embed_batch(all_texts)
    except Exception:
        logger.warning(
            "Embedding computation failed during ignore filtering; returning all groups unfiltered (fail-open)",
            exc_info=True,
        )
        return list(groups)

    group_embeddings = all_embeddings[: len(group_texts)]
    issue_embeddings = all_embeddings[len(group_texts) :]

    novel: list[FindingGroup] = []
    for group, group_emb in zip(groups, group_embeddings):
        suppressed = False
        for issue, issue_emb in zip(ignore_issues, issue_embeddings):
            sim = cosine_similarity(group_emb, issue_emb)
            # Strict > comparison: 110-REQ-4.3 says "exceeds threshold".
            # At threshold=0.0, any positive similarity (> 0.0) is a match.
            if sim > similarity_threshold:
                logger.info(
                    "Skipping FindingGroup '%s' — matches af:ignore issue #%d "
                    "(embedding similarity %.3f > threshold %.3f; "
                    "finding matches an ignored issue)",
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
