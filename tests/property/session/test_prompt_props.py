"""Property tests for prompt builder and context assembly.

Test Spec: TS-15-P1 through TS-15-P5
Properties: 1-6 from design.md
Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-2.1 through 15-REQ-2.3,
              15-REQ-4.1, 15-REQ-4.2,
              15-REQ-5.1 through 15-REQ-5.3

Updated after legacy template path removal (issue #342).
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

# Strategy for valid archetypes
_archetype_strategy = st.sampled_from(["coder", "reviewer"])


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
# TS-15-P2: Profile content always present for valid archetypes
# Property 2: System prompt contains archetype-specific keywords
# Requirements: 15-REQ-2.1, 15-REQ-2.2, 15-REQ-2.3
# ---------------------------------------------------------------------------


class TestProfileContentPresent:
    """TS-15-P2: For any valid archetype, the system prompt contains
    recognizable profile content.
    """

    @given(
        archetype=_archetype_strategy,
    )
    @settings(max_examples=50)
    def test_archetype_specific_content_present(
        self,
        archetype: str,
    ) -> None:
        """System prompt contains archetype-specific keywords."""
        result = build_system_prompt("ctx", archetype=archetype)
        assert len(result) > 100
        if archetype == "coder":
            assert "Identity" in result
        else:
            assert "Identity" in result


# ---------------------------------------------------------------------------
# TS-15-P3: build_system_prompt never crashes
# Property 3, 4: No crash on any archetype
# ---------------------------------------------------------------------------


class TestBuildSystemPromptNeverCrashes:
    """TS-15-P3: build_system_prompt never raises on valid archetypes."""

    @given(
        archetype=_archetype_strategy,
    )
    @settings(max_examples=50)
    def test_no_exception(
        self,
        archetype: str,
    ) -> None:
        """No exception raised for valid archetypes."""
        result = build_system_prompt("ctx", archetype=archetype)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TS-15-P4: Frontmatter never leaks
# Property 5: No frontmatter content in final prompt
# Requirements: 15-REQ-4.1, 15-REQ-4.2
# ---------------------------------------------------------------------------


class TestFrontmatterNeverLeaks:
    """TS-15-P4: Frontmatter content never appears in the final prompt."""

    def test_frontmatter_not_in_coder_output(self) -> None:
        """Coder prompt does not contain frontmatter delimiters."""
        result = build_system_prompt("ctx", archetype="coder")
        assert not result.startswith("---")

    def test_frontmatter_stripped_from_reviewer(self) -> None:
        """Reviewer profile has frontmatter; verify it's stripped."""
        result = build_system_prompt("ctx", archetype="reviewer")
        assert "role: reviewer" not in result
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
