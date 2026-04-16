"""Hot-load gate pipeline tests: git-tracked, completeness, lint, tasks-complete gates.

Test Spec: TS-51-12 through TS-51-22, TS-444-1 through TS-444-5
Requirements: 51-REQ-4.1, 51-REQ-4.2, 51-REQ-4.E1,
              51-REQ-5.1, 51-REQ-5.2, 51-REQ-5.E1,
              51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1,
              51-REQ-7.1, 51-REQ-7.2, 51-REQ-7.3,
              444-AC-1, 444-AC-2, 444-AC-3, 444-AC-4
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.engine.hot_load import (
    _are_all_plan_nodes_done,
    are_all_tasks_done,
    discover_new_specs_gated,
    is_spec_complete,
    is_spec_tracked_on_develop,
    lint_spec_gate,
)

REQUIRED_FILES = ["prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"]


def _create_spec_files(
    spec_path: Path,
    files: list[str] | None = None,
    empty: list[str] | None = None,
) -> None:
    """Helper to create spec files. Files in `empty` are created with 0 bytes."""
    spec_path.mkdir(parents=True, exist_ok=True)
    if files is None:
        files = REQUIRED_FILES
    empty = empty or []
    for f in files:
        fp = spec_path / f
        if f in empty:
            fp.write_text("")
        else:
            fp.write_text(f"# {f}\nContent for {f}\n")


# ---------------------------------------------------------------------------
# TS-51-12: Git-tracked gate accepts tracked spec
# ---------------------------------------------------------------------------


class TestGitTrackedGateAccepts:
    """TS-51-12: Git-tracked gate accepts tracked spec.

    Requirements: 51-REQ-4.1
    """

    @pytest.mark.asyncio
    async def test_tracked_spec_returns_true(self, tmp_path: Path) -> None:
        """Spec tracked on develop returns True."""

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            return (0, "100644 blob abc123\tprd.md\n", "")

        with patch(
            "agent_fox.engine.hot_load.run_git",
            side_effect=mock_run_git,
        ):
            result = await is_spec_tracked_on_develop(tmp_path, "42_feature")

        assert result is True


# ---------------------------------------------------------------------------
# TS-51-13: Git-tracked gate rejects untracked spec
# ---------------------------------------------------------------------------


class TestGitTrackedGateRejects:
    """TS-51-13: Git-tracked gate rejects untracked spec.

    Requirements: 51-REQ-4.2
    """

    @pytest.mark.asyncio
    async def test_untracked_spec_returns_false(self, tmp_path: Path) -> None:
        """Spec not tracked on develop returns False."""

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            return (0, "", "")

        with patch(
            "agent_fox.engine.hot_load.run_git",
            side_effect=mock_run_git,
        ):
            result = await is_spec_tracked_on_develop(tmp_path, "42_feature")

        assert result is False


# ---------------------------------------------------------------------------
# TS-51-14: Git-tracked gate fallback on failure
# ---------------------------------------------------------------------------


class TestGitTrackedGateFallback:
    """TS-51-14: Git-tracked gate fallback on failure.

    Requirements: 51-REQ-4.E1
    """

    @pytest.mark.asyncio
    async def test_fallback_to_permissive_on_failure(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """git ls-tree failure returns True (permissive) and logs warning."""

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            raise Exception("git command failed")

        with (
            patch(
                "agent_fox.engine.hot_load.run_git",
                side_effect=mock_run_git,
            ),
            caplog.at_level(logging.WARNING, logger="agent_fox.engine.hot_load"),
        ):
            result = await is_spec_tracked_on_develop(tmp_path, "42_feature")

        assert result is True
        assert len(caplog.records) > 0


# ---------------------------------------------------------------------------
# TS-51-15: Completeness gate with all files
# ---------------------------------------------------------------------------


class TestCompletenessGateAllFiles:
    """TS-51-15: Completeness gate with all 5 non-empty files.

    Requirements: 51-REQ-5.1
    """

    def test_all_files_present_and_nonempty(self, tmp_path: Path) -> None:
        """Returns (True, []) when all 5 files exist and are non-empty."""
        spec_path = tmp_path / "42_feature"
        _create_spec_files(spec_path)

        passed, missing = is_spec_complete(spec_path)
        assert passed is True
        assert missing == []


# ---------------------------------------------------------------------------
# TS-51-16: Completeness gate with missing file
# ---------------------------------------------------------------------------


class TestCompletenessGateMissingFile:
    """TS-51-16: Completeness gate with missing file.

    Requirements: 51-REQ-5.2
    """

    def test_missing_design_md(self, tmp_path: Path) -> None:
        """Returns (False, ['design.md']) when design.md is missing."""
        spec_path = tmp_path / "42_feature"
        files = [f for f in REQUIRED_FILES if f != "design.md"]
        _create_spec_files(spec_path, files=files)

        passed, missing = is_spec_complete(spec_path)
        assert passed is False
        assert "design.md" in missing


# ---------------------------------------------------------------------------
# TS-51-17: Completeness gate with empty file
# ---------------------------------------------------------------------------


class TestCompletenessGateEmptyFile:
    """TS-51-17: Completeness gate with empty file.

    Requirements: 51-REQ-5.E1
    """

    def test_empty_requirements_md(self, tmp_path: Path) -> None:
        """Empty requirements.md is treated as incomplete."""
        spec_path = tmp_path / "42_feature"
        _create_spec_files(spec_path, empty=["requirements.md"])

        passed, missing = is_spec_complete(spec_path)
        assert passed is False
        assert "requirements.md" in missing


# ---------------------------------------------------------------------------
# TS-51-E2: Empty spec file treated as incomplete (tasks.md)
# ---------------------------------------------------------------------------


class TestCompletenessGateEmptyTasksMd:
    """TS-51-E2: Zero-byte tasks.md causes completeness gate to fail.

    Requirements: 51-REQ-5.E1
    """

    def test_empty_tasks_md(self, tmp_path: Path) -> None:
        """Empty tasks.md is treated as incomplete."""
        spec_path = tmp_path / "42_feature"
        _create_spec_files(spec_path, empty=["tasks.md"])

        passed, missing = is_spec_complete(spec_path)
        assert passed is False
        assert "tasks.md" in missing


# ---------------------------------------------------------------------------
# TS-51-18: Lint gate accepts clean spec
# ---------------------------------------------------------------------------


class TestLintGateAcceptsClean:
    """TS-51-18: Lint gate accepts clean spec (warnings only, no errors).

    Requirements: 51-REQ-6.1, 51-REQ-6.3
    """

    def test_warnings_only_passes(self, tmp_path: Path) -> None:
        """Spec with only warning-level findings passes."""
        from agent_fox.spec.validators import Finding

        mock_findings = [
            Finding(
                spec_name="42_feature",
                file="tasks.md",
                rule="oversized-group",
                severity="warning",
                message="Group too large",
                line=10,
            ),
            Finding(
                spec_name="42_feature",
                file="prd.md",
                rule="missing-heading",
                severity="warning",
                message="Missing heading",
                line=5,
            ),
        ]

        spec_path = tmp_path / "42_feature"
        spec_path.mkdir(parents=True)

        with patch(
            "agent_fox.engine.hot_load.validate_specs",
            return_value=mock_findings,
        ):
            passed, errors = lint_spec_gate("42_feature", spec_path)

        assert passed is True
        assert errors == []


# ---------------------------------------------------------------------------
# TS-51-19: Lint gate rejects spec with errors
# ---------------------------------------------------------------------------


class TestLintGateRejectsErrors:
    """TS-51-19: Lint gate rejects spec with error findings.

    Requirements: 51-REQ-6.2
    """

    def test_error_finding_fails_gate(self, tmp_path: Path) -> None:
        """Spec with error-severity finding is rejected."""
        from agent_fox.spec.validators import Finding

        mock_findings = [
            Finding(
                spec_name="42_feature",
                file="design.md",
                rule="missing-file",
                severity="error",
                message="Expected file 'design.md' is missing",
                line=None,
            ),
            Finding(
                spec_name="42_feature",
                file="tasks.md",
                rule="oversized-group",
                severity="warning",
                message="Group too large",
                line=10,
            ),
        ]

        spec_path = tmp_path / "42_feature"
        spec_path.mkdir(parents=True)

        with patch(
            "agent_fox.engine.hot_load.validate_specs",
            return_value=mock_findings,
        ):
            passed, errors = lint_spec_gate("42_feature", spec_path)

        assert passed is False
        assert len(errors) == 1
        assert "missing-file" in errors[0]


# ---------------------------------------------------------------------------
# TS-51-20 / TS-51-E3: Lint gate handles validator exception
# ---------------------------------------------------------------------------


class TestLintGateValidatorException:
    """TS-51-20: Lint gate handles validator crash gracefully.

    Requirements: 51-REQ-6.E1
    """

    def test_validator_exception_returns_false(self, tmp_path: Path) -> None:
        """Validator crash returns (False, [error desc]), no exception propagated."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir(parents=True)

        with patch(
            "agent_fox.engine.hot_load.validate_specs",
            side_effect=RuntimeError("boom"),
        ):
            passed, errors = lint_spec_gate("42_feature", spec_path)

        assert passed is False
        assert len(errors) == 1
        assert "boom" in errors[0]


# ---------------------------------------------------------------------------
# TS-51-21: Full gate pipeline filters correctly
# ---------------------------------------------------------------------------


class TestFullGatePipeline:
    """TS-51-21: Full gate pipeline filters specs through all gates.

    Requirements: 51-REQ-7.1
    """

    @pytest.mark.asyncio
    async def test_pipeline_filters_correctly(self, tmp_path: Path) -> None:
        """Only spec passing all gates is returned.

        spec_a: tracked, complete, lint-clean -> accepted
        spec_b: tracked, complete, has lint errors -> rejected at lint
        spec_c: not tracked on develop -> rejected at git gate
        """
        specs_dir = tmp_path / ".specs"

        # Create spec_a (valid)
        _create_spec_files(specs_dir / "42_spec_a")
        # Create spec_b (lint errors)
        _create_spec_files(specs_dir / "43_spec_b")
        # Create spec_c (untracked)
        _create_spec_files(specs_dir / "44_spec_c")

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return spec_name != "44_spec_c"

        def mock_is_complete(spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            if spec_name == "43_spec_b":
                return (False, ["missing-file: design.md"])
            return (True, [])

        from agent_fox.spec.discovery import SpecInfo

        mock_new_specs = [
            SpecInfo(
                name="42_spec_a",
                prefix=42,
                path=specs_dir / "42_spec_a",
                has_tasks=True,
                has_prd=True,
            ),
            SpecInfo(
                name="43_spec_b",
                prefix=43,
                path=specs_dir / "43_spec_b",
                has_tasks=True,
                has_prd=True,
            ),
            SpecInfo(
                name="44_spec_c",
                prefix=44,
                path=specs_dir / "44_spec_c",
                has_tasks=True,
                has_prd=True,
            ),
        ]

        with (
            patch(
                "agent_fox.engine.hot_load.discover_new_specs",
                return_value=mock_new_specs,
            ),
            patch(
                "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                side_effect=mock_is_tracked,
            ),
            patch(
                "agent_fox.engine.hot_load.is_spec_complete",
                side_effect=mock_is_complete,
            ),
            patch(
                "agent_fox.engine.hot_load.lint_spec_gate",
                side_effect=mock_lint_gate,
            ),
        ):
            result = await discover_new_specs_gated(specs_dir, known_specs=set(), repo_root=tmp_path)

        assert len(result) == 1
        assert result[0].name == "42_spec_a"


# ---------------------------------------------------------------------------
# TS-51-22: Previously skipped spec accepted after fix
# ---------------------------------------------------------------------------


class TestSkippedSpecReEvaluation:
    """TS-51-22: Previously skipped spec accepted after fix.

    Requirements: 51-REQ-7.2, 51-REQ-7.3
    """

    @pytest.mark.asyncio
    async def test_spec_accepted_after_fix(self, tmp_path: Path) -> None:
        """Spec skipped at barrier N passes at barrier N+1 after being fixed."""
        specs_dir = tmp_path / ".specs"
        spec_path = specs_dir / "42_feature"
        # First: create incomplete spec (missing design.md)
        files_without_design = [f for f in REQUIRED_FILES if f != "design.md"]
        _create_spec_files(spec_path, files=files_without_design)

        from agent_fox.spec.discovery import SpecInfo

        mock_spec = SpecInfo(
            name="42_feature",
            prefix=42,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return True

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        with (
            patch(
                "agent_fox.engine.hot_load.discover_new_specs",
                return_value=[mock_spec],
            ),
            patch(
                "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                side_effect=mock_is_tracked,
            ),
            patch(
                "agent_fox.engine.hot_load.lint_spec_gate",
                side_effect=mock_lint_gate,
            ),
        ):
            # Barrier N: spec is incomplete
            result_1 = await discover_new_specs_gated(specs_dir, known_specs=set(), repo_root=tmp_path)
            assert result_1 == []

            # Fix spec: add design.md
            (spec_path / "design.md").write_text("# Design\nContent\n")

            # Barrier N+1: spec now passes
            result_2 = await discover_new_specs_gated(specs_dir, known_specs=set(), repo_root=tmp_path)
            assert len(result_2) == 1
            assert result_2[0].name == "42_feature"


# ---------------------------------------------------------------------------
# TS-444-1: are_all_tasks_done
# ---------------------------------------------------------------------------

_COMPLETED_TASKS_MD = """\
# Tasks

- [x] 1. First task group
  - [x] 1.1 Subtask one
  - [x] 1.2 Subtask two
- [x] 2. Second task group
  - [x] 2.1 Subtask one
"""

_INCOMPLETE_TASKS_MD = """\
# Tasks

- [x] 1. First task group
  - [x] 1.1 Subtask one
- [ ] 2. Second task group
  - [ ] 2.1 Subtask one
"""

_ALL_INCOMPLETE_TASKS_MD = """\
# Tasks

- [ ] 1. First task group
  - [ ] 1.1 Subtask one
- [ ] 2. Second task group
  - [ ] 2.1 Subtask one
"""


class TestAreAllTasksDone:
    """TS-444-1: tasks.md checkbox gate for completed specs.

    Requirements: 444-AC-1
    """

    def test_all_groups_completed(self, tmp_path: Path) -> None:
        """Returns True when all task groups are marked [x]."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()
        (spec_path / "tasks.md").write_text(_COMPLETED_TASKS_MD)

        assert are_all_tasks_done(spec_path) is True

    def test_some_groups_incomplete(self, tmp_path: Path) -> None:
        """Returns False when some groups are not completed."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()
        (spec_path / "tasks.md").write_text(_INCOMPLETE_TASKS_MD)

        assert are_all_tasks_done(spec_path) is False

    def test_no_groups_found(self, tmp_path: Path) -> None:
        """Returns False when tasks.md has no parseable groups."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()
        (spec_path / "tasks.md").write_text("# Tasks\n\nNo task groups here.\n")

        assert are_all_tasks_done(spec_path) is False

    def test_tasks_md_missing(self, tmp_path: Path) -> None:
        """Returns False when tasks.md does not exist."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()

        assert are_all_tasks_done(spec_path) is False

    def test_parse_error(self, tmp_path: Path) -> None:
        """Returns False when parse_tasks raises an exception."""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()
        (spec_path / "tasks.md").write_text(_COMPLETED_TASKS_MD)

        with patch(
            "agent_fox.engine.hot_load.parse_tasks",
            side_effect=RuntimeError("parse error"),
        ):
            assert are_all_tasks_done(spec_path) is False

    def test_new_unchecked_tasks_added(self, tmp_path: Path) -> None:
        """Returns False when previously complete spec has new unchecked tasks.

        Acceptance criterion: 444-AC-4
        """
        tasks_with_new = """\
# Tasks

- [x] 1. First task group
  - [x] 1.1 Subtask one
- [x] 2. Second task group
  - [x] 2.1 Subtask one
- [ ] 3. New task group added later
  - [ ] 3.1 New subtask
"""
        spec_path = tmp_path / "42_feature"
        spec_path.mkdir()
        (spec_path / "tasks.md").write_text(tasks_with_new)

        assert are_all_tasks_done(spec_path) is False


# ---------------------------------------------------------------------------
# TS-444-2: _are_all_plan_nodes_done
# ---------------------------------------------------------------------------


class TestAreAllPlanNodesDone:
    """TS-444-2: plan node state gate for completed specs (queries plan_nodes DB table).

    Requirements: 444-AC-2
    """

    def test_all_nodes_completed(self) -> None:
        """Returns True when all nodes for spec have 'completed' status."""
        import duckdb

        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:0', '42_feature', 'completed')")
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:1', '42_feature', 'completed')")

        assert _are_all_plan_nodes_done("42_feature", conn) is True
        conn.close()

    def test_some_nodes_not_completed(self) -> None:
        """Returns False when some nodes are pending."""
        import duckdb

        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:0', '42_feature', 'completed')")
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:1', '42_feature', 'pending')")

        assert _are_all_plan_nodes_done("42_feature", conn) is False
        conn.close()

    def test_no_nodes_for_spec(self) -> None:
        """Returns False when plan has no nodes for this spec."""
        import duckdb

        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('99_other:0', '99_other', 'completed')")

        assert _are_all_plan_nodes_done("42_feature", conn) is False
        conn.close()

    def test_conn_is_none(self) -> None:
        """Returns False when no DB connection is available."""
        assert _are_all_plan_nodes_done("42_feature", None) is False

    def test_missing_table(self) -> None:
        """Returns False when plan_nodes table does not exist."""
        import duckdb

        conn = duckdb.connect(":memory:")
        assert _are_all_plan_nodes_done("42_feature", conn) is False
        conn.close()


# ---------------------------------------------------------------------------
# TS-444-3: Gate 4 integration in discover_new_specs_gated pipeline
# ---------------------------------------------------------------------------


class TestTasksCompleteGatePipeline:
    """TS-444-3: Tasks-complete gate filters fully implemented specs.

    Requirements: 444-AC-1, 444-AC-2, 444-AC-3, 444-AC-4
    """

    @pytest.mark.asyncio
    async def test_both_signals_done_skips_spec(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Spec skipped when tasks.md all [x] AND plan nodes all completed in DB."""
        import duckdb

        from agent_fox.spec.discovery import SpecInfo

        specs_dir = tmp_path / ".specs"
        spec_path = specs_dir / "42_feature"
        _create_spec_files(spec_path)
        (spec_path / "tasks.md").write_text(_COMPLETED_TASKS_MD)

        # Create in-memory DuckDB with completed plan nodes
        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:1', '42_feature', 'completed')")
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:2', '42_feature', 'completed')")

        mock_spec = SpecInfo(
            name="42_feature",
            prefix=42,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return True

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        with (
            patch("agent_fox.engine.hot_load.discover_new_specs", return_value=[mock_spec]),
            patch("agent_fox.engine.hot_load.is_spec_tracked_on_develop", side_effect=mock_is_tracked),
            patch("agent_fox.engine.hot_load.is_spec_complete", return_value=(True, [])),
            patch("agent_fox.engine.hot_load.lint_spec_gate", side_effect=mock_lint_gate),
            caplog.at_level(logging.INFO, logger="agent_fox.engine.hot_load"),
        ):
            result = await discover_new_specs_gated(
                specs_dir, known_specs=set(), repo_root=tmp_path, db_conn=conn
            )

        assert result == []
        assert any("fully implemented" in r.message for r in caplog.records)
        conn.close()

    @pytest.mark.asyncio
    async def test_tasks_done_but_nodes_not_done(self, tmp_path: Path) -> None:
        """Spec NOT skipped when tasks.md all [x] but plan nodes are pending."""
        import duckdb

        from agent_fox.spec.discovery import SpecInfo

        specs_dir = tmp_path / ".specs"
        spec_path = specs_dir / "42_feature"
        _create_spec_files(spec_path)
        (spec_path / "tasks.md").write_text(_COMPLETED_TASKS_MD)

        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:1', '42_feature', 'pending')")

        mock_spec = SpecInfo(
            name="42_feature",
            prefix=42,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return True

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        with (
            patch("agent_fox.engine.hot_load.discover_new_specs", return_value=[mock_spec]),
            patch("agent_fox.engine.hot_load.is_spec_tracked_on_develop", side_effect=mock_is_tracked),
            patch("agent_fox.engine.hot_load.is_spec_complete", return_value=(True, [])),
            patch("agent_fox.engine.hot_load.lint_spec_gate", side_effect=mock_lint_gate),
        ):
            result = await discover_new_specs_gated(
                specs_dir, known_specs=set(), repo_root=tmp_path, db_conn=conn
            )

        assert len(result) == 1
        assert result[0].name == "42_feature"
        conn.close()

    @pytest.mark.asyncio
    async def test_nodes_done_but_tasks_not_done(self, tmp_path: Path) -> None:
        """Spec NOT skipped when plan nodes completed but tasks.md has unchecked boxes."""
        import duckdb

        from agent_fox.spec.discovery import SpecInfo

        specs_dir = tmp_path / ".specs"
        spec_path = specs_dir / "42_feature"
        _create_spec_files(spec_path)
        (spec_path / "tasks.md").write_text(_INCOMPLETE_TASKS_MD)

        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE plan_nodes (id VARCHAR PRIMARY KEY, spec_name VARCHAR, status VARCHAR)"
        )
        conn.execute("INSERT INTO plan_nodes VALUES ('42_feature:1', '42_feature', 'completed')")

        mock_spec = SpecInfo(
            name="42_feature",
            prefix=42,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return True

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        with (
            patch("agent_fox.engine.hot_load.discover_new_specs", return_value=[mock_spec]),
            patch("agent_fox.engine.hot_load.is_spec_tracked_on_develop", side_effect=mock_is_tracked),
            patch("agent_fox.engine.hot_load.is_spec_complete", return_value=(True, [])),
            patch("agent_fox.engine.hot_load.lint_spec_gate", side_effect=mock_lint_gate),
        ):
            result = await discover_new_specs_gated(
                specs_dir, known_specs=set(), repo_root=tmp_path, db_conn=conn
            )

        assert len(result) == 1
        conn.close()

    @pytest.mark.asyncio
    async def test_no_db_conn_does_not_skip(self, tmp_path: Path) -> None:
        """Spec NOT skipped when db_conn is None (even if tasks all done)."""
        from agent_fox.spec.discovery import SpecInfo

        specs_dir = tmp_path / ".specs"
        spec_path = specs_dir / "42_feature"
        _create_spec_files(spec_path)
        (spec_path / "tasks.md").write_text(_COMPLETED_TASKS_MD)

        mock_spec = SpecInfo(
            name="42_feature",
            prefix=42,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )

        async def mock_is_tracked(repo_root: Path, spec_name: str, **kwargs: object) -> bool:
            return True

        def mock_lint_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
            return (True, [])

        with (
            patch("agent_fox.engine.hot_load.discover_new_specs", return_value=[mock_spec]),
            patch("agent_fox.engine.hot_load.is_spec_tracked_on_develop", side_effect=mock_is_tracked),
            patch("agent_fox.engine.hot_load.is_spec_complete", return_value=(True, [])),
            patch("agent_fox.engine.hot_load.lint_spec_gate", side_effect=mock_lint_gate),
        ):
            # No db_conn argument — backward compatible
            result = await discover_new_specs_gated(
                specs_dir, known_specs=set(), repo_root=tmp_path
            )

        assert len(result) == 1
