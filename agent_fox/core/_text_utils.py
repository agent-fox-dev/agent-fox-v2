"""Shared text-sanitisation helpers."""

from __future__ import annotations

import re

# Matches ANSI escape sequences (SGR and other CSI sequences).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]?")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)
