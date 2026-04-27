"""Unit tests for Claude-only commitment (spec 55).

Test Spec: TS-55-2, TS-55-3, TS-55-E1
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-55-2: ADR contains alternatives section
# ---------------------------------------------------------------------------

_ADR_GLOB = "docs/adr/*use-claude-exclusively*"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _find_adr() -> Path:
    matches = list(_PROJECT_ROOT.glob("docs/adr/*use-claude-exclusively*"))
    if not matches:
        pytest.fail("ADR file not found: docs/adr/*use-claude-exclusively*")
    return matches[0]


def test_adr_alternatives() -> None:
    """ADR mentions considered alternatives: OpenAI, Gemini, multi-provider."""
    content = _find_adr().read_text()
    assert "OpenAI" in content, "ADR must mention OpenAI"
    assert "Gemini" in content, "ADR must mention Gemini"
    assert "multi-provider" in content.lower() or "multiple providers" in content.lower(), (
        "ADR must mention multi-provider or multiple providers"
    )


# ---------------------------------------------------------------------------
# TS-55-3: ADR mentions future non-coding use
# ---------------------------------------------------------------------------


def test_adr_non_coding() -> None:
    """ADR acknowledges future non-coding provider use."""
    content = _find_adr().read_text().lower()
    assert "non-coding" in content or "embeddings" in content, "ADR must mention non-coding tasks or embeddings"


# ---------------------------------------------------------------------------
# TS-55-E1: ADR number non-collision
# ---------------------------------------------------------------------------


def test_adr_number_unique() -> None:
    """All ADR files have unique numeric prefixes."""
    adr_dir = _PROJECT_ROOT / "docs" / "adr"
    if not adr_dir.exists():
        pytest.skip("docs/adr/ does not exist yet")

    adrs = list(adr_dir.glob("[0-9]*.md"))
    if not adrs:
        pytest.skip("No ADR files found")

    numbers: list[str] = []
    for f in adrs:
        match = re.match(r"(\d+)", f.name)
        if match:
            numbers.append(match.group(1))

    assert len(numbers) == len(set(numbers)), f"Duplicate ADR numbers: {numbers}"
