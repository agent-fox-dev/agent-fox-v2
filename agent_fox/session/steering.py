"""Steering document loading.

Loads project-level steering directives from .specs/steering.md and
detects placeholder-only content.

Requirements: 64-REQ-2.1 through 64-REQ-2.E1, 64-REQ-5.1, 64-REQ-5.2
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Sentinel string that marks placeholder-only content (64-REQ-5.1)
STEERING_PLACEHOLDER_SENTINEL: str = "<!-- steering:placeholder -->"

# Path relative to project root
_STEERING_PATH: str = ".specs/steering.md"

# HTML comment pattern for placeholder detection
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def load_steering(project_root: Path) -> str | None:
    """Load steering content from .specs/steering.md.

    Returns:
        The file content (stripped) if it contains real directives.
        None if the file does not exist, cannot be read, or contains
        only placeholder content.

    Requirements: 64-REQ-2.1, 64-REQ-2.3, 64-REQ-2.4, 64-REQ-2.E1,
                  64-REQ-5.1, 64-REQ-5.2
    """
    steering_path = project_root / _STEERING_PATH

    # Security: reject symlinks to prevent path traversal (CWE-59)
    if steering_path.is_symlink():
        logger.warning("Steering file is a symlink; skipping for security")
        return None

    # 64-REQ-2.3: Skip silently when file is absent
    if not steering_path.exists():
        logger.debug("Steering file not found at %s, skipping", steering_path)
        return None

    # 64-REQ-2.E1: Handle unreadable files gracefully
    try:
        content = steering_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Cannot read steering file %s: %s — skipping steering inclusion",
            steering_path,
            exc,
        )
        return None

    # 64-REQ-2.4, 64-REQ-5.2: Detect placeholder-only content
    # A file is placeholder-only when it contains the sentinel and after
    # removing all HTML comments and the sentinel, nothing non-whitespace remains.
    if STEERING_PLACEHOLDER_SENTINEL in content:
        # Strip the sentinel marker itself
        stripped = content.replace(STEERING_PLACEHOLDER_SENTINEL, "")
        # Strip all HTML comments
        stripped = _HTML_COMMENT_RE.sub("", stripped)
        if not stripped.strip():
            logger.debug("Steering file contains only placeholder content, skipping")
            return None

    result = content.strip()
    if not result:
        logger.debug("Steering file is empty after stripping, skipping")
        return None

    logger.debug("Loaded steering directives from %s", steering_path)
    return result
