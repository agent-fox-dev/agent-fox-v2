"""Property-based tests for AGENTS.md initialization (Spec 44).

Requirements: 44-REQ-2.1, 44-REQ-3.1, 44-REQ-3.E1, 44-REQ-4.1, 44-REQ-4.2
Design Properties: 1 (Idempotent Creation), 2 (Content Fidelity),
                   3 (Existing File Preservation), 4 (CLAUDE.md Independence),
                   5 (Return Value Correctness)
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

import agent_fox
from agent_fox.workspace.init_project import _ensure_agents_md

# The bundled template path (used to assert byte-identical content)
_AGENTS_MD_TEMPLATE = Path(agent_fox.__file__).parent / "_templates" / "agents_md.md"


# ---------------------------------------------------------------------------
# TS-44-P1: Idempotent creation
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(st.just(None))  # No meaningful variation needed — directory is fresh
def test_idempotent_creation(tmp_path_factory, _):
    """Property 1: Calling _ensure_agents_md twice yields same result as once.

    TS-44-P1 / 44-REQ-2.1, 44-REQ-3.1
    """
    tmp_path = tmp_path_factory.mktemp("idempotent")

    result1 = _ensure_agents_md(tmp_path)
    content1 = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    result2 = _ensure_agents_md(tmp_path)
    content2 = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    assert result1 == "created"
    assert result2 == "skipped"
    assert content1 == content2


# ---------------------------------------------------------------------------
# TS-44-P2: Content fidelity
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(st.just(None))
def test_content_fidelity(tmp_path_factory, _):
    """Property 2: Written file is byte-identical to bundled template.

    TS-44-P2 / 44-REQ-1.1, 44-REQ-2.1
    """
    tmp_path = tmp_path_factory.mktemp("fidelity")

    _ensure_agents_md(tmp_path)

    written = (tmp_path / "AGENTS.md").read_bytes()
    template = _AGENTS_MD_TEMPLATE.read_bytes()

    assert written == template


# ---------------------------------------------------------------------------
# TS-44-P3: Existing file preservation
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(content=st.text(min_size=0, max_size=10000))
def test_existing_file_preservation(content, tmp_path_factory):
    """Property 3: Existing AGENTS.md content is never modified.

    TS-44-P3 / 44-REQ-3.1, 44-REQ-3.E1

    Uses bytes-level comparison to avoid platform-specific newline
    normalization from Python text-mode I/O. Byte-identical preservation
    is stricter than text-identity, satisfying the spec contract.
    """
    tmp_path = tmp_path_factory.mktemp("preservation")

    agents_md = tmp_path / "AGENTS.md"
    content_bytes = content.encode("utf-8")
    agents_md.write_bytes(content_bytes)

    _ensure_agents_md(tmp_path)

    assert agents_md.read_bytes() == content_bytes


# ---------------------------------------------------------------------------
# TS-44-P4: CLAUDE.md independence
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(claude_present=st.booleans())
def test_claude_md_independence(claude_present, tmp_path_factory):
    """Property 4: Behavior is identical regardless of CLAUDE.md presence.

    TS-44-P4 / 44-REQ-4.1, 44-REQ-4.2
    """
    tmp1 = tmp_path_factory.mktemp("claude_with")
    tmp2 = tmp_path_factory.mktemp("claude_without")

    if claude_present:
        (tmp1 / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")

    result1 = _ensure_agents_md(tmp1)
    result2 = _ensure_agents_md(tmp2)

    assert result1 == result2
    assert (tmp1 / "AGENTS.md").read_text(encoding="utf-8") == (tmp2 / "AGENTS.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TS-44-P5: Return value correctness
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(exists_before=st.booleans())
def test_return_value_correctness(exists_before, tmp_path_factory):
    """Property 5: Return value accurately reflects file creation.

    TS-44-P5 / 44-REQ-2.3, 44-REQ-3.3
    """
    tmp_path = tmp_path_factory.mktemp("retval")

    if exists_before:
        (tmp_path / "AGENTS.md").write_text("existing content", encoding="utf-8")

    result = _ensure_agents_md(tmp_path)

    if exists_before:
        assert result == "skipped"
    else:
        assert result == "created"
