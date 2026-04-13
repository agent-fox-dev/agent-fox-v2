"""Shared text-sanitisation helpers.

Strip ANSI escapes and escape markdown special characters in
database-sourced or user-supplied content.
"""

from __future__ import annotations

import re

# Matches ANSI escape sequences (SGR and other CSI sequences).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]?")

# Characters that have special meaning in CommonMark.
_MD_SPECIAL_RE = re.compile(r"([\\`*_\{\}\[\]()#+\-.!~|>])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)


def escape_markdown(text: str) -> str:
    """Backslash-escape markdown special characters.

    Prevents database-stored content from being interpreted as
    markdown formatting when output is piped to a markdown renderer.
    Issue #193.
    """
    return _MD_SPECIAL_RE.sub(r"\\\1", text)
