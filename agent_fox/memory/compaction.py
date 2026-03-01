"""Knowledge base compaction: dedup and supersession resolution.

Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.3, 05-REQ-5.E1,
              05-REQ-5.E2
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from agent_fox.memory.store import DEFAULT_MEMORY_PATH
from agent_fox.memory.types import Fact

logger = logging.getLogger("agent_fox.memory.compaction")


def compact(path: Path = DEFAULT_MEMORY_PATH) -> tuple[int, int]:
    """Compact the knowledge base by removing duplicates and superseded facts.

    Steps:
    1. Load all facts.
    2. Deduplicate by content hash (SHA-256 of content string), keeping the
       earliest instance.
    3. Resolve supersession chains: if B supersedes A and C supersedes B,
       only C survives.
    4. Rewrite the JSONL file with surviving facts.

    Args:
        path: Path to the JSONL file.

    Returns:
        A tuple of (original_count, surviving_count).
    """
    raise NotImplementedError


def _content_hash(content: str) -> str:
    """Compute SHA-256 hash of a fact's content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _deduplicate_by_content(facts: list[Fact]) -> list[Fact]:
    """Remove duplicate facts with the same content hash.

    Keeps the earliest instance (by created_at) for each unique hash.
    """
    raise NotImplementedError


def _resolve_supersession(facts: list[Fact]) -> list[Fact]:
    """Remove facts that have been superseded by newer facts.

    A fact is superseded if another fact references its ID in the
    `supersedes` field. Chains are resolved transitively.
    """
    raise NotImplementedError
