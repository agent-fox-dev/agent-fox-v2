"""Integration tests for Claude-only commitment (spec 55).

Test Spec: TS-55-1, TS-55-9
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# TS-55-1: ADR file exists
# ---------------------------------------------------------------------------


def test_adr_exists() -> None:
    """Exactly one ADR file matches *use-claude-exclusively*."""
    matches = list(_PROJECT_ROOT.glob("docs/adr/*use-claude-exclusively*"))
    assert len(matches) == 1, f"Expected 1 ADR *use-claude-exclusively*, found {len(matches)}: {matches}"


# ---------------------------------------------------------------------------
# TS-55-9: README mentions Claude
# ---------------------------------------------------------------------------


def test_readme_claude() -> None:
    """README.md states agent-fox is built for Claude."""
    readme = (_PROJECT_ROOT / "README.md").read_text()
    readme_lower = readme.lower()
    assert "claude" in readme_lower
    assert "built" in readme_lower or "exclusively" in readme_lower or "powered by" in readme_lower, (
        "README must indicate Claude exclusivity"
    )
