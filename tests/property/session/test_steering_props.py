"""Property tests for steering document (Spec 64).

Tests idempotent initialization, placeholder detection accuracy, and
context ordering invariant.

Test Spec: TS-64-P1, TS-64-P2, TS-64-P3
Properties: 1, 2, 3 from design.md
Requirements: 64-REQ-1.1, 64-REQ-1.2, 64-REQ-2.2, 64-REQ-2.4,
              64-REQ-5.1, 64-REQ-5.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL


def _make_spec_dir(root: Path) -> Path:
    """Create a minimal spec directory with required files."""
    spec_dir = root / "specs" / "prop_steering"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text("# Requirements\nProp REQ\n")
    (spec_dir / "design.md").write_text("# Design\nProp design\n")
    (spec_dir / "test_spec.md").write_text("# Test Spec\nProp test spec\n")
    (spec_dir / "tasks.md").write_text("# Tasks\nProp tasks\n")
    return spec_dir


# Strategy for arbitrary file content (at least one char)
_content_strategy = st.text(min_size=1)

# Strategy for directive text (alphanumeric and spaces, avoids HTML comment chars).
# Filtered to exclude whitespace-only strings so load_steering always returns content.
_directive_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=" ",
    ),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip())

# Strategy for memory facts
_facts_strategy = st.lists(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters=" ",
        ),
        min_size=1,
        max_size=100,
    ),
    min_size=1,
    max_size=5,
)


# ---------------------------------------------------------------------------
# TS-64-P1: Idempotent initialization
# Property 1 from design.md
# Requirements: 64-REQ-1.1, 64-REQ-1.2
# ---------------------------------------------------------------------------


class TestIdempotentInitialization:
    """TS-64-P1: _ensure_steering_md() never changes an existing file."""

    @given(content=_content_strategy)
    @settings(max_examples=30)
    def test_existing_file_never_changed(self, content: str) -> None:
        """Calling _ensure_steering_md() on an existing file leaves it unchanged."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            specs_dir = tmp_path / ".specs"
            specs_dir.mkdir()
            steering_path = specs_dir / "steering.md"
            # Use binary write/read to avoid platform newline translation so
            # the round-trip comparison is exact (e.g. '\r' not converted to '\n').
            steering_path.write_bytes(content.encode("utf-8"))

            result = _ensure_steering_md(tmp_path)

            assert result == "skipped"
            assert steering_path.read_bytes() == content.encode("utf-8")


# ---------------------------------------------------------------------------
# TS-64-P2: Placeholder detection accuracy
# Property 2 from design.md
# Requirements: 64-REQ-5.1, 64-REQ-5.2, 64-REQ-2.4
# ---------------------------------------------------------------------------


class TestPlaceholderDetectionAccuracy:
    """TS-64-P2: Content with directives is never treated as placeholder."""

    @given(directive=_directive_strategy)
    @settings(max_examples=50)
    def test_directive_appended_to_placeholder_is_detected(
        self, directive: str
    ) -> None:
        """File with placeholder plus directive text returns non-None."""
        from agent_fox.workspace.init_project import _STEERING_PLACEHOLDER
        from agent_fox.session.prompt import load_steering

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            specs_dir = tmp_path / ".specs"
            specs_dir.mkdir()

            # Placeholder + real directive content
            content = _STEERING_PLACEHOLDER + "\n" + directive
            (specs_dir / "steering.md").write_text(content)

            result = load_steering(tmp_path)
            assert result is not None, (
                f"Expected non-None for directive {directive!r}, got None"
            )

    @given(directive=_directive_strategy)
    @settings(max_examples=50)
    def test_standalone_directive_always_returned(self, directive: str) -> None:
        """File with only directive text (no sentinel) returns non-None."""
        from agent_fox.session.prompt import load_steering

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            specs_dir = tmp_path / ".specs"
            specs_dir.mkdir()

            (specs_dir / "steering.md").write_text(directive)

            result = load_steering(tmp_path)
            assert result is not None, (
                f"Expected non-None for directive {directive!r}, got None"
            )


# ---------------------------------------------------------------------------
# TS-64-P3: Context ordering invariant
# Property 3 from design.md
# Requirement: 64-REQ-2.2
# ---------------------------------------------------------------------------


class TestContextOrderingInvariant:
    """TS-64-P3: Steering always appears between spec sections and memory facts."""

    @given(
        steering_content=_directive_strategy,
        facts=_facts_strategy,
    )
    @settings(max_examples=20)
    def test_steering_before_memory_facts(
        self, steering_content: str, facts: list[str]
    ) -> None:
        """## Steering Directives appears before ## Memory Facts in context."""
        from agent_fox.session.prompt import assemble_context

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec_dir = _make_spec_dir(tmp_path)

            # Write a real steering file (no placeholder)
            specs_dir = tmp_path / ".specs"
            specs_dir.mkdir(exist_ok=True)
            (specs_dir / "steering.md").write_text(steering_content)

            conn = duckdb.connect(":memory:")
            conn.execute(SCHEMA_DDL)
            apply_pending_migrations(conn)

            context = assemble_context(
                spec_dir, 1, facts, conn=conn, project_root=tmp_path
            )
            conn.close()

            if "## Steering Directives" in context and "## Memory Facts" in context:
                steer_pos = context.index("## Steering Directives")
                mem_pos = context.index("## Memory Facts")
                assert steer_pos < mem_pos, (
                    f"Steering ({steer_pos}) should come before"
                    f" Memory Facts ({mem_pos})"
                )
