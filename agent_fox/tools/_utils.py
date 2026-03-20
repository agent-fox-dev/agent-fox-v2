"""Shared utilities for fox tools: file validation, lossy reading, content hashing.

Consolidates the helpers used by fox_read, fox_search, and fox_edit into
a single module.

Requirements: 29-REQ-5.1, 29-REQ-5.2, 29-REQ-5.3, 29-REQ-5.E1
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content hashing (xxh3_64 with blake2b fallback)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# File validation and lossy reading
# ---------------------------------------------------------------------------


def validate_file(path: Path, *, writable: bool = False) -> str | None:
    """Check that *path* exists and is a regular file.

    When *writable* is True also checks write permission.

    Returns an error string on failure, or ``None`` on success.
    """
    if not path.exists():
        return f"Error: file not found: {path}"
    if not path.is_file():
        return f"Error: not a file: {path}"
    if writable:
        import os

        if not os.access(path, os.W_OK):
            return f"Error: file not writable: {path}"
    return None


def read_text_lossy(path: Path) -> tuple[str, str | None]:
    """Read a text file with UTF-8, falling back to latin-1.

    Returns ``(text, error)``.  On success *error* is ``None``.
    On failure *text* is empty and *error* contains the message.
    """
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1"), None
        except Exception as e:
            return "", f"Error: cannot read {path}: {e}"
    except OSError as e:
        return "", f"Error: cannot read {path}: {e}"
