"""Property tests for Claude-only commitment (spec 55).

Test Spec: TS-55-P1, TS-55-P2, TS-55-P3
"""

from __future__ import annotations

import inspect
from typing import Protocol

from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# TS-55-P1: Factory always returns AgentBackend
# ---------------------------------------------------------------------------


@given(n=st.integers(min_value=1, max_value=20))
@settings(max_examples=20)
def test_factory_always_returns_agent_backend(n: int) -> None:
    """get_backend() always returns ClaudeBackend satisfying AgentBackend."""
    from agent_fox.session.backends import AgentBackend, get_backend
    from agent_fox.session.backends.claude import ClaudeBackend

    result = get_backend()
    assert isinstance(result, ClaudeBackend)
    assert isinstance(result, AgentBackend)


# ---------------------------------------------------------------------------
# TS-55-P2: Factory has no parameters
# ---------------------------------------------------------------------------


def test_factory_has_no_parameters() -> None:
    """get_backend signature has exactly zero parameters."""
    from agent_fox.session.backends import get_backend

    sig = inspect.signature(get_backend)
    assert len(sig.parameters) == 0


# ---------------------------------------------------------------------------
# TS-55-P3: Protocol is runtime-checkable
# ---------------------------------------------------------------------------


def test_protocol_is_runtime_checkable() -> None:
    """AgentBackend is a runtime-checkable Protocol subclass."""
    from agent_fox.session.backends import AgentBackend

    assert issubclass(AgentBackend, Protocol)  # type: ignore[arg-type]
    assert getattr(AgentBackend, "_is_runtime_protocol", False)
