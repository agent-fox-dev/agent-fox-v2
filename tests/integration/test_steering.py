"""Integration tests for steering document context assembly (Spec 64).

Verifies that assemble_context() includes steering content in the correct
position relative to spec files and memory facts.

Test Spec: TS-64-6
Requirements: 64-REQ-2.1, 64-REQ-2.2
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL


def _make_spec_dir(root: Path) -> Path:
    """Create a spec directory with minimal required files."""
    spec_dir = root / "specs" / "64_steering_test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text("# Requirements\n\nReq content.\n")
    (spec_dir / "design.md").write_text("# Design\n\nDesign content.\n")
    (spec_dir / "test_spec.md").write_text("# Test Spec\n\nTest content.\n")
    (spec_dir / "tasks.md").write_text("# Tasks\n\nTask content.\n")
    return spec_dir


def _make_steering_file(root: Path, content: str) -> Path:
    """Create .specs/steering.md with given content."""
    specs_dir = root / ".specs"
    specs_dir.mkdir(exist_ok=True)
    steering_path = specs_dir / "steering.md"
    steering_path.write_text(content)
    return steering_path


# ---------------------------------------------------------------------------
# TS-64-6: Steering placement in assembled context
# Requirements: 64-REQ-2.2
# ---------------------------------------------------------------------------


class TestSteeringPlacementInAssembledContext:
    """TS-64-6: Steering section appears after spec files and before memory facts."""

    def test_steering_section_present_in_context(self, tmp_path: Path) -> None:
        """assemble_context() includes ## Steering Directives when file has content."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = _make_spec_dir(tmp_path)
        _make_steering_file(tmp_path, "Always use type hints.\n")

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        context = assemble_context(
            spec_dir, 1, ["fact1"], conn=conn, project_root=tmp_path
        )
        conn.close()

        assert "## Steering Directives" in context

    def test_steering_after_requirements_before_memory(self, tmp_path: Path) -> None:
        """Steering section appears after Requirements and before Memory Facts."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = _make_spec_dir(tmp_path)
        _make_steering_file(tmp_path, "Always use type hints.\n")

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        context = assemble_context(
            spec_dir, 1, ["fact1"], conn=conn, project_root=tmp_path
        )
        conn.close()

        req_pos = context.index("## Requirements")
        steer_pos = context.index("## Steering Directives")
        mem_pos = context.index("## Memory Facts")
        assert req_pos < steer_pos < mem_pos, (
            f"Expected Requirements ({req_pos}) < Steering ({steer_pos})"
            f" < Memory Facts ({mem_pos})"
        )

    def test_no_steering_section_when_file_missing(self, tmp_path: Path) -> None:
        """assemble_context() omits steering section when file does not exist."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = _make_spec_dir(tmp_path)
        # No steering file created

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        context = assemble_context(
            spec_dir, 1, ["fact1"], conn=conn, project_root=tmp_path
        )
        conn.close()

        assert "## Steering Directives" not in context

    def test_no_steering_section_when_project_root_not_provided(
        self, tmp_path: Path
    ) -> None:
        """assemble_context() omits steering when project_root is None."""
        from agent_fox.session.prompt import assemble_context

        spec_dir = _make_spec_dir(tmp_path)
        _make_steering_file(tmp_path, "Always use type hints.\n")

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        # Calling without project_root (backward-compatible call)
        context = assemble_context(spec_dir, 1, ["fact1"], conn=conn)
        conn.close()

        assert "## Steering Directives" not in context

    def test_no_steering_section_for_placeholder_content(self, tmp_path: Path) -> None:
        """assemble_context() omits steering when file has only placeholder."""
        from agent_fox.cli.init import _ensure_steering_md
        from agent_fox.session.prompt import assemble_context

        spec_dir = _make_spec_dir(tmp_path)
        _ensure_steering_md(tmp_path)  # Creates placeholder-only file

        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        apply_pending_migrations(conn)

        context = assemble_context(
            spec_dir, 1, ["fact1"], conn=conn, project_root=tmp_path
        )
        conn.close()

        assert "## Steering Directives" not in context
