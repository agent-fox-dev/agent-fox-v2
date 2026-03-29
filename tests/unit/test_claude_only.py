"""Unit tests for Claude-only commitment (spec 55).

Test Spec: TS-55-2, TS-55-3, TS-55-4, TS-55-5, TS-55-7, TS-55-8, TS-55-E1, TS-55-E2
"""

from __future__ import annotations

import inspect
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-55-4: get_backend returns ClaudeBackend without arguments
# ---------------------------------------------------------------------------


def test_get_backend_returns_claude_backend() -> None:
    """get_backend() returns a ClaudeBackend instance."""
    from agent_fox.session.backends import get_backend
    from agent_fox.session.backends.claude import ClaudeBackend

    result = get_backend()
    assert isinstance(result, ClaudeBackend)


# ---------------------------------------------------------------------------
# TS-55-5: get_backend accepts no name parameter
# ---------------------------------------------------------------------------


def test_get_backend_no_params() -> None:
    """get_backend() signature has zero parameters."""
    from agent_fox.session.backends import get_backend

    sig = inspect.signature(get_backend)
    params = [p for p in sig.parameters if p != "self"]
    assert len(params) == 0, f"Expected 0 params, got: {list(sig.parameters)}"


# ---------------------------------------------------------------------------
# TS-55-7: AgentBackend protocol still exported
# ---------------------------------------------------------------------------


def test_protocol_exported() -> None:
    """AgentBackend is importable from the backends package and is a Protocol."""
    from typing import Protocol

    from agent_fox.session.backends import AgentBackend

    assert issubclass(AgentBackend, Protocol)


def test_protocol_is_runtime_checkable() -> None:
    """AgentBackend supports isinstance() checks."""
    from agent_fox.session.backends import AgentBackend

    # runtime_checkable protocols have _is_runtime_protocol set
    assert getattr(AgentBackend, "_is_runtime_protocol", False)


# ---------------------------------------------------------------------------
# TS-55-8: AgentBackend docstring mentions Claude-only
# ---------------------------------------------------------------------------


def test_protocol_docstring() -> None:
    """AgentBackend docstring states ClaudeBackend is the only production impl."""
    from agent_fox.session.backends.protocol import AgentBackend

    doc = AgentBackend.__doc__
    assert doc is not None, "AgentBackend must have a docstring"
    assert "ClaudeBackend" in doc
    assert "production" in doc.lower() or "only" in doc.lower()


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
    assert (
        "multi-provider" in content.lower() or "multiple providers" in content.lower()
    ), "ADR must mention multi-provider or multiple providers"


# ---------------------------------------------------------------------------
# TS-55-3: ADR mentions future non-coding use
# ---------------------------------------------------------------------------


def test_adr_non_coding() -> None:
    """ADR acknowledges future non-coding provider use."""
    content = _find_adr().read_text().lower()
    assert "non-coding" in content or "embeddings" in content, (
        "ADR must mention non-coding tasks or embeddings"
    )


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


# ---------------------------------------------------------------------------
# TS-55-E2: Test mock satisfies protocol
# ---------------------------------------------------------------------------


def test_mock_satisfies_protocol() -> None:
    """A mock backend implementing AgentBackend methods passes isinstance check."""
    from agent_fox.session.backends.protocol import (
        AgentBackend,
        AgentMessage,
        PermissionCallback,
        ToolDefinition,
    )

    class MockBackend:
        @property
        def name(self) -> str:
            return "mock"

        async def execute(
            self,
            prompt: str,
            *,
            system_prompt: str,
            model: str,
            cwd: str,
            permission_callback: PermissionCallback | None = None,
            tools: list[ToolDefinition] | None = None,
        ) -> AsyncIterator[AgentMessage]:
            yield  # type: ignore[misc]

        async def close(self) -> None:
            pass

    mock = MockBackend()
    assert isinstance(mock, AgentBackend)
