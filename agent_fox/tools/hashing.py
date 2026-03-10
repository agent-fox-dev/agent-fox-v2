"""Content hashing for fox tools.

Uses xxh3_64 for fast, deterministic line hashing. Falls back to
blake2b (stdlib) if xxhash is not installed.

Requirements: 29-REQ-5.1, 29-REQ-5.2, 29-REQ-5.3, 29-REQ-5.E1
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

try:
    import xxhash

    _USE_XXHASH = True
except ImportError:
    _USE_XXHASH = False
    logger.warning("xxhash not available, falling back to blake2b for content hashing")


def hash_line(content: bytes) -> str:
    """Return 16-char lowercase hex hash of content.

    Uses xxh3_64 when available, blake2b (8-byte digest) otherwise.
    """
    if _USE_XXHASH:
        return xxhash.xxh3_64(content).hexdigest()
    return hashlib.blake2b(content, digest_size=8).hexdigest()
