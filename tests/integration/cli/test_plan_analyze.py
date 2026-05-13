"""Integration tests for plan --dry-run CLI flag.

Test Spec: TS-122-1, TS-122-2, TS-122-3 (persistence/exit codes)
           TS-122-12 through TS-122-15 (flag composability)
           TS-122-E1, TS-122-E2, TS-122-E7 (edge cases)
           TS-122-SMOKE-1 through TS-122-SMOKE-4 (smoke tests)
Requirements: 122-REQ-1.1, 122-REQ-1.2, 122-REQ-1.3,
              122-REQ-1.E1, 122-REQ-1.E2,
              122-REQ-5.1, 122-REQ-5.2, 122-REQ-5.3, 122-REQ-5.4,
              122-REQ-5.E1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.plan import plan_cmd
from agent_fox.core.errors import PlanError
from agent_fox.graph.planner import run_plan
from agent_fox.graph.types import TaskGraph
from agent_fox.nightshift.pid import PidStatus

# -- Helpers ----------------------------------------------------------------


def _mock_graph() -> MagicMock:
    """Return a minimal TaskGraph-like mock for tests that mock build_plan."""
    graph = MagicMock(spec=TaskGraph)
    graph.nodes = {
        "01_test:1": MagicMock(
            id="01_test:1",
            spec_name="01_test",
            group_number=1,
            title="Write tests",
            optional=False,
            archetype="coder",
            status="pending",
        ),
        "01_test:2": MagicMock(
            id="01_test:2",
            spec_name="01_test",
            group_number=2,
            title="Implement feature",
            optional=False,
            archetype="coder",
            status="pending",
        ),
    }
    graph.edges = [
        MagicMock(source="01_test:1", target="01_test:2", kind="intra_spec"),
    ]
    graph.order = ["01_test:1", "01_test:2"]
    meta = MagicMock()
    meta.created_at = "2026-01-01T00:00:00"
    meta.fast_mode = False
    meta.filtered_spec = None
    meta.version = "0.0.1"
    graph.metadata = meta
    return graph


def _setup_specs(base: Path, *spec_names: str) -> Path:
    """Create a specs directory with minimal spec(s).

    Each spec gets a tasks.md with two task groups.
    Returns the specs directory path.
    """
    specs_dir = base / ".specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    for name in spec_names:
        spec_dir = specs_dir / name
        spec_dir.mkdir(exist_ok=True)
        (spec_dir / "tasks.md").write_text(
            "# Tasks\n\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Unit tests\n"
            "\n"
            "- [ ] 2. Implement feature\n"
            "  - [ ] 2.1 Core logic\n"
        )

    return specs_dir


# Correct patch targets based on import analysis:
#
# cli/plan.py imports at module level:
#   build_plan, format_plan_summary, save_plan, discover_specs
#   -> patch at "agent_fox.cli.plan.<name>"
#
# cli/plan.py imports inline:
#   open_knowledge_store -> patch at "agent_fox.knowledge.db.open_knowledge_store"
#   check_pid_file -> patch at "agent_fox.nightshift.pid.check_pid_file"
_P_BUILD = "agent_fox.cli.plan.build_plan"
_P_FORMAT_SUMMARY = "agent_fox.cli.plan.format_plan_summary"
_P_DISCOVER = "agent_fox.cli.plan.discover_specs"
_P_SAVE = "agent_fox.cli.plan.save_plan"
_P_OPEN_DB = "agent_fox.knowledge.db.open_knowledge_store"
_P_CHECK_PID = "agent_fox.nightshift.pid.check_pid_file"


@pytest.fixture(autouse=True)
def _no_daemon() -> None:  # noqa: PT004
    """Prevent daemon PID check from blocking tests."""
    with patch(_P_CHECK_PID, return_value=(PidStatus.ABSENT, None)):
        yield  # type: ignore[misc]


# ===========================================================================
# Core Persistence Tests
# ===========================================================================


class TestAnalyzeSkipsPersistence:
    """TS-122-1: plan --dry-run does not call save_plan.

    Requirement: 122-REQ-1.1
    """

    def test_dry_run_skips_save_and_db(self, tmp_path: Path) -> None:
        """--dry-run does not call save_plan or open_knowledge_store."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB) as mock_db,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0, f"output: {result.output}"
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0


class TestNormalPlanPersists:
    """TS-122-2: plan without --dry-run still calls save_plan.

    Requirement: 122-REQ-1.2
    """

    def test_normal_plan_calls_save(self, tmp_path: Path) -> None:
        """plan (no --dry-run) calls save_plan exactly once."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()
        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_FORMAT_SUMMARY, return_value="Plan summary"),
            patch(_P_DISCOVER, return_value=[]),
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB, return_value=mock_kb),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0, f"output: {result.output}"
            assert mock_save.call_count == 1


class TestAnalyzeExitCodes:
    """TS-122-3: Correct exit codes for --dry-run mode.

    Requirement: 122-REQ-1.3
    """

    def test_success_exits_zero(self, tmp_path: Path) -> None:
        """--dry-run with valid specs exits with code 0."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0

    def test_plan_error_exits_one(self) -> None:
        """--dry-run with plan error (cycle) exits with code 1."""
        with patch(_P_BUILD, side_effect=PlanError("Dependency cycle detected")):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", "/nonexistent"],
                obj={"json": False},
            )
            assert result.exit_code == 1


# ===========================================================================
# Flag Composability Tests
# ===========================================================================


class TestAnalyzeWithFast:
    """TS-122-12: --dry-run --fast applies fast-mode filtering.

    Requirement: 122-REQ-5.1
    """

    def test_fast_mode_reflected_in_output(self, tmp_path: Path) -> None:
        """--dry-run --fast output reflects fast mode status."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()
        mock_graph.metadata.fast_mode = True

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--fast", "--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Fast mode:" in result.output


class TestAnalyzeWithSpec:
    """TS-122-13: --dry-run --spec restricts to one spec.

    Requirement: 122-REQ-5.2
    """

    def test_spec_filter_restricts_plan(self, tmp_path: Path) -> None:
        """--dry-run --spec spec_a only includes spec_a nodes."""
        specs_dir = _setup_specs(tmp_path, "01_spec_a", "02_spec_b")

        # Mock graph with only spec_a nodes
        mock_graph = MagicMock(spec=TaskGraph)
        mock_graph.nodes = {
            "01_spec_a:1": MagicMock(
                id="01_spec_a:1",
                spec_name="01_spec_a",
                group_number=1,
                title="Spec A task",
                optional=False,
                archetype="coder",
                status="pending",
            ),
        }
        mock_graph.edges = []
        mock_graph.order = ["01_spec_a:1"]
        meta = MagicMock()
        meta.fast_mode = False
        meta.filtered_spec = "01_spec_a"
        meta.created_at = "2026-01-01T00:00:00"
        meta.version = "0.0.1"
        mock_graph.metadata = meta

        with (
            patch(_P_BUILD, return_value=mock_graph) as mock_build,
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--spec", "01_spec_a", "--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            # Verify build_plan was called with filter_spec
            called_filter = mock_build.call_args.args[1]
            assert called_filter == "01_spec_a"


class TestAnalyzeJSON:
    """TS-122-14: --dry-run --json produces structured JSON output.

    Requirement: 122-REQ-5.3
    """

    def test_json_output_has_analysis_keys(self, tmp_path: Path) -> None:
        """--dry-run --json output contains phases, critical_path, grouped_edges."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", str(specs_dir)],
                obj={"json": True},
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "phases" in data
            assert "critical_path" in data
            assert "grouped_edges" in data
            assert "nodes" in data
            assert "edges" in data
            assert "order" in data
            assert "metadata" in data


class TestAnalyzeAllFlags:
    """TS-122-15: All flags combined.

    Requirement: 122-REQ-5.4
    """

    def test_all_flags_combined(self, tmp_path: Path) -> None:
        """--dry-run --fast --spec NAME --json all work together."""
        specs_dir = _setup_specs(tmp_path, "01_spec_a", "02_spec_b")

        mock_graph = MagicMock(spec=TaskGraph)
        mock_graph.nodes = {
            "01_spec_a:1": MagicMock(
                id="01_spec_a:1",
                spec_name="01_spec_a",
                group_number=1,
                title="Spec A task",
                optional=False,
                archetype="coder",
                status="pending",
            ),
        }
        mock_graph.edges = []
        mock_graph.order = ["01_spec_a:1"]
        meta = MagicMock()
        meta.fast_mode = True
        meta.filtered_spec = "01_spec_a"
        meta.created_at = "2026-01-01T00:00:00"
        meta.version = "0.0.1"
        mock_graph.metadata = meta

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                [
                    "--dry-run",
                    "--fast",
                    "--spec",
                    "01_spec_a",
                    "--specs-dir",
                    str(specs_dir),
                ],
                obj={"json": True},
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "phases" in data
            assert "critical_path" in data
            assert "grouped_edges" in data


# ===========================================================================
# Edge Case Tests
# ===========================================================================


class TestAnalyzeEmptySpecs:
    """TS-122-E1: Empty specs directory with --dry-run.

    Requirement: 122-REQ-1.E1
    """

    def test_empty_specs_exits_one(self, tmp_path: Path) -> None:
        """--dry-run with empty specs dir exits with code 1."""
        empty_dir = tmp_path / "empty_specs"
        empty_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            plan_cmd,
            ["--dry-run", "--specs-dir", str(empty_dir)],
            obj={"json": False},
        )
        assert result.exit_code == 1


class TestAnalyzeCycleError:
    """TS-122-E2: Cycle detected during --dry-run.

    Requirement: 122-REQ-1.E2
    """

    def test_cycle_error_exits_one(self) -> None:
        """--dry-run with cycle error exits with code 1 and no DB persistence."""
        with (
            patch(_P_BUILD, side_effect=PlanError("Dependency cycle detected")),
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB) as mock_db,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", "/nonexistent"],
                obj={"json": False},
            )
            assert result.exit_code == 1
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0


class TestAnalyzeNonexistentSpec:
    """TS-122-E7: --dry-run --spec with nonexistent spec.

    Requirement: 122-REQ-5.E1
    """

    def test_nonexistent_spec_exits_one(self, tmp_path: Path) -> None:
        """--dry-run --spec nonexistent_spec exits with code 1."""
        specs_dir = _setup_specs(tmp_path, "01_test")

        with (
            patch(_P_BUILD, side_effect=PlanError("Spec 'nonexistent_spec' not found")),
            patch(_P_SAVE),
            patch(_P_OPEN_DB),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                [
                    "--dry-run",
                    "--spec",
                    "nonexistent_spec",
                    "--specs-dir",
                    str(specs_dir),
                ],
                obj={"json": False},
            )
            assert result.exit_code == 1


# ===========================================================================
# Smoke Tests (end-to-end, no mocking of core pipeline)
# ===========================================================================


class TestSmoke1HumanReadable:
    """TS-122-SMOKE-1: Analyze human-readable end-to-end.

    Execution Path: Path 1 from design.md.
    Does NOT mock build_plan, compute_phases, critical_path, or group_edges.
    """

    def test_full_pipeline_human_output(self, tmp_path: Path) -> None:
        """Full --dry-run invocation produces human-readable analysis."""
        specs_dir = _setup_specs(tmp_path, "01_spec_a", "02_spec_b")

        with (
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB) as mock_db,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0, f"output: {result.output}"
            assert "Plan Analysis" in result.output
            assert "Parallelism Phases" in result.output
            assert "Critical Path" in result.output
            assert "Dependency Edges" in result.output
            # No DB interaction
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0


class TestSmoke2JSON:
    """TS-122-SMOKE-2: Analyze JSON end-to-end.

    Execution Path: Path 2 from design.md.
    Does NOT mock build_plan, compute_phases, critical_path, or group_edges.
    """

    def test_full_pipeline_json_output(self, tmp_path: Path) -> None:
        """Full --dry-run --json invocation produces valid JSON with all keys."""
        specs_dir = _setup_specs(tmp_path, "01_spec_a", "02_spec_b")

        with (
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB) as mock_db,
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--dry-run", "--specs-dir", str(specs_dir)],
                obj={"json": True},
                catch_exceptions=False,
            )
            assert result.exit_code == 0, f"output: {result.output}"
            data = json.loads(result.output)
            for key in [
                "nodes",
                "edges",
                "order",
                "metadata",
                "phases",
                "critical_path",
                "grouped_edges",
            ]:
                assert key in data, f"Missing key: {key}"
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0


class TestSmoke3NormalPersists:
    """TS-122-SMOKE-3: Normal plan persists (regression).

    Execution Path: Path 3 from design.md.
    Mocks open_knowledge_store (avoid real DB) but patches save_plan
    at module level to verify it is called.

    Note: The test spec prose says "do NOT mock save_plan" but the pseudocode
    patches it. We follow the pseudocode pattern: patch save_plan at the CLI
    module to verify it is called (the mock intercepts the call but confirms
    it happens).
    """

    def test_normal_plan_persists_regression(self, tmp_path: Path) -> None:
        """plan (no --dry-run) calls save_plan exactly once."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        mock_graph = _mock_graph()
        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()

        with (
            patch(_P_BUILD, return_value=mock_graph),
            patch(_P_FORMAT_SUMMARY, return_value="Plan summary"),
            patch(_P_DISCOVER, return_value=[]),
            patch(_P_SAVE) as mock_save,
            patch(_P_OPEN_DB, return_value=mock_kb),
        ):
            runner = CliRunner()
            result = runner.invoke(
                plan_cmd,
                ["--specs-dir", str(specs_dir)],
                obj={"json": False},
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert mock_save.call_count == 1


class TestSmoke4RunPlanAPI:
    """TS-122-SMOKE-4: run_plan API dry-run mode.

    Execution Path: Path 4 from design.md.
    Does NOT mock build_plan -- uses real planning pipeline.
    """

    def test_run_plan_dry_run_returns_graph(self, tmp_path: Path) -> None:
        """run_plan(dry_run=True) returns TaskGraph without DB interaction."""
        specs_dir = _setup_specs(tmp_path, "01_test")
        config = MagicMock()
        config.archetypes = {}

        with (
            patch("agent_fox.graph.persistence.save_plan") as mock_save,
            patch("agent_fox.knowledge.db.open_knowledge_store") as mock_db,
        ):
            graph = run_plan(config, dry_run=True, specs_dir=specs_dir)
            assert isinstance(graph, TaskGraph)
            assert len(graph.nodes) > 0
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0
