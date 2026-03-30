"""Prompt safety utilities for sanitizing untrusted content.

Provides boundary marking, control character stripping, and truncation
for content interpolated into LLM prompts. Mitigates prompt injection
by delimiting untrusted regions with unique nonce-tagged boundaries.

Requirements: Issue #185 — F4 prompt injection chain mitigation.
"""

from __future__ import annotations

import re
import secrets

# Matches ANSI escape sequences (SGR and other CSI sequences).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]?")

# Matches C0 control characters except tab (0x09), newline (0x0a),
# and carriage return (0x0d).
_CONTROL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
)

# Default maximum characters for untrusted content in prompts.
DEFAULT_MAX_PROMPT_CHARS = 100_000


def strip_control_chars(text: str) -> str:
    """Strip ANSI escapes and C0 control characters from text.

    Preserves tabs, newlines, and carriage returns.
    """
    text = _ANSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


def truncate_content(text: str, *, max_chars: int) -> str:
    """Truncate text to max_chars, appending a truncation notice."""
    if len(text) <= max_chars:
        return text
    notice = f"\n[truncated: {len(text) - max_chars} chars omitted]"
    return text[:max_chars] + notice


def sanitize_prompt_content(
    content: str,
    *,
    label: str,
    max_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    """Sanitize untrusted content for safe inclusion in LLM prompts.

    1. Strips ANSI escapes and C0 control characters.
    2. Truncates to ``max_chars``.
    3. Wraps in XML boundary tags with a random hex nonce, making it
       difficult for injected content to close the boundary early.

    Args:
        content: The untrusted text to sanitize.
        label: A descriptive label for the boundary tag (e.g.
            "transcript", "diff", "facts").
        max_chars: Maximum character length before truncation.

    Returns:
        The sanitized content wrapped in boundary tags.
    """
    cleaned = strip_control_chars(content)
    cleaned = truncate_content(cleaned, max_chars=max_chars)
    nonce = secrets.token_hex(8)
    tag = f"untrusted-{label}-{nonce}"
    return f"<{tag}>\n{cleaned}\n</{tag}>"
