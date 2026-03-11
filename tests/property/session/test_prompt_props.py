"""Property tests for prompt builder and context assembly.

Test Spec: TS-15-P1 through TS-15-P5
Properties: 1-6 from design.md
Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-2.1 through 15-REQ-2.3,
              15-REQ-3.1, 15-REQ-3.E1, 15-REQ-4.1, 15-REQ-4.2,
              15-REQ-5.1 through 15-REQ-5.3

Uses lazy imports inside test methods for functions that may not exist
yet (``build_system_prompt`` with ``role`` parameter) so property tests
are syntactically valid and individually fail at runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.session.prompt import (
    assemble_context,
    build_system_prompt,
    build_task_prompt,
)
from tests.unit.knowledge.conftest import SCHEMA_DDL

# Strategies for spec names: alphanumeric + underscores, common for spec folders
_spec_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=30,
)

# Strategy for fuzzed spec names with broader character set (including punctuation)
_fuzz_spec_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
)

# Strategy for valid roles
_role_strategy = st.sampled_from(["coding", "coordinator"])


def _make_spec_dir(tmp: Path) -> Path:
    """Create a temporary spec directory with all four spec files."""
    spec_dir = tmp / "specs" / "prop_test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text("# Requirements\nProp REQ\n")
    (spec_dir / "design.md").write_text("# Design\nProp design\n")
    (spec_dir / "test_spec.md").write_text("# Test Spec\nProp test spec\n")
    (spec_dir / "tasks.md").write_text("# Tasks\nProp tasks\n")
    return spec_dir


# ---------------------------------------------------------------------------
# TS-15-P1: Context always includes test spec when present
# Property 1: test_spec.md in context between design and tasks
# Requirements: 15-REQ-1.1, 15-REQ-1.2
# ---------------------------------------------------------------------------


class TestContextAlwaysIncludesTestSpec:
    """TS-15-P1: When test_spec.md exists, it appears in context
    between design and tasks for any task group.
    """

    @given(task_group=st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    def test_test_spec_between_design_and_tasks(
        self,
        task_group: int,
    ) -> None:
        """## Test Specification always between ## Design and ## Tasks."""
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = _make_spec_dir(Path(tmp))
            conn = duckdb.connect(":memory:")
            conn.execute(SCHEMA_DDL)
            apply_pending_migrations(conn)
            ctx = assemble_context(spec_dir, task_group, conn=conn)
            conn.close()

            design_pos = ctx.index("## Design")
            test_spec_pos = ctx.index("## Test Specification")
            tasks_pos = ctx.index("## Tasks")
            assert design_pos < test_spec_pos < tasks_pos


# ---------------------------------------------------------------------------
# TS-15-P2: Template content always present for valid roles
# Property 2: System prompt contains role-specific keywords
# Requirements: 15-REQ-2.1, 15-REQ-2.2, 15-REQ-2.3
# ---------------------------------------------------------------------------


class TestTemplateContentPresent:
    """TS-15-P2: For any valid role, the system prompt contains
    recognizable template content.
    """

    @given(
        role=_role_strategy,
        spec_name=_spec_name_strategy,
    )
    @settings(max_examples=50)
    def test_role_specific_content_present(
        self,
        role: str,
        spec_name: str,
    ) -> None:
        """System prompt contains role-specific keywords."""
        result = build_system_prompt("ctx", 1, spec_name, role=role)
        assert len(result) > 100
        if role == "coding":
            assert "CODER ARCHETYPE" in result
        else:
            assert "COORDINATOR AGENT" in result


# ---------------------------------------------------------------------------
# TS-15-P3: Interpolation never crashes
# Property 3, 4: No crash on any spec name or task group; literal braces OK
# Requirements: 15-REQ-3.1, 15-REQ-3.E1
# ---------------------------------------------------------------------------


class TestInterpolationNeverCrashes:
    """TS-15-P3: build_system_prompt never raises on any spec_name
    or task_group combination.
    """

    @given(
        spec_name=_fuzz_spec_name_strategy,
        task_group=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_no_exception_and_spec_name_present(
        self,
        spec_name: str,
        task_group: int,
    ) -> None:
        """No exception raised and result contains spec_name."""
        result = build_system_prompt("ctx", task_group, spec_name)
        assert spec_name in result


# ---------------------------------------------------------------------------
# TS-15-P4: Frontmatter never leaks
# Property 5: No frontmatter content in final prompt
# Requirements: 15-REQ-4.1, 15-REQ-4.2
# ---------------------------------------------------------------------------


class TestFrontmatterNeverLeaks:
    """TS-15-P4: Frontmatter content never appears in the final prompt."""

    @given(spec_name=_spec_name_strategy)
    @settings(max_examples=20)
    def test_frontmatter_not_in_coder_output(self, spec_name: str) -> None:
        """Coder prompt does not contain frontmatter delimiters."""
        result = build_system_prompt("ctx", 1, spec_name, role="coding")
        assert not result.startswith("---")

    def test_frontmatter_stripped_from_skeptic(self) -> None:
        """Skeptic template has frontmatter; verify it's stripped."""
        result = build_system_prompt("ctx", 1, "test_spec", archetype="skeptic")
        assert "role: skeptic" not in result
        assert not result.startswith("---")


# ---------------------------------------------------------------------------
# TS-15-P5: Task prompt completeness
# Property 6: Task prompt always contains required elements
# Requirements: 15-REQ-5.1, 15-REQ-5.2, 15-REQ-5.3
# ---------------------------------------------------------------------------


class TestTaskPromptCompleteness:
    """TS-15-P5: Task prompt always contains spec name, task group,
    and instruction keywords.
    """

    @given(
        task_group=st.integers(min_value=1, max_value=50),
        spec_name=_spec_name_strategy,
    )
    @settings(max_examples=50)
    def test_task_prompt_has_required_elements(
        self,
        task_group: int,
        spec_name: str,
    ) -> None:
        """Task prompt contains spec name, task group, and 'commit'."""
        result = build_task_prompt(task_group, spec_name)
        assert spec_name in result
        assert str(task_group) in result
        assert "commit" in result.lower()
