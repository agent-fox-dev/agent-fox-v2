"""Property tests for Claude-only commitment (spec 55).

Test Spec: TS-55-P1
"""

from __future__ import annotations

from agent_fox.session.backends.claude import ClaudeBackend

# ---------------------------------------------------------------------------
# TS-55-P1: ClaudeBackend is directly importable and instantiable
# ---------------------------------------------------------------------------


def test_claude_backend_instantiable() -> None:
    """ClaudeBackend can be imported and instantiated."""
    backend = ClaudeBackend()
    assert backend.name == "claude"
