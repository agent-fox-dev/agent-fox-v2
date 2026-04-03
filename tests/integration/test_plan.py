"""Plan command integration tests.

Test Spec: TS-02-10 (plan persist/load), TS-02-11 (CLI end-to-end),
           TS-02-E6 (corrupted plan.json)
Requirements: 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3, 02-REQ-6.4, 02-REQ-6.E1,
              02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.types import (
    Edge,
    Node,
    PlanMetadata,
    TaskGraph,
)

# -- Helpers -----------------------------------------------------------------


def _make_sample_graph() -> TaskGraph:
    """Create a small sample graph for persistence tests."""
    nodes = {
        "test_spec:1": Node(
            id="test_spec:1",
            spec_name="test_spec",
            group_number=1,
            title="First task",
            optional=False,
            subtask_count=2,
        ),
        "test_spec:2": Node(
            id="test_spec:2",
            spec_name="test_spec",
            group_number=2,
            title="Second task",
            optional=False,
            subtask_count=1,
        ),
    }
    edges = [
        Edge(source="test_spec:1", target="test_spec:2", kind="intra_spec"),
    ]
    metadata = PlanMetadata(
        created_at="2026-03-01T12:00:00",
        fast_mode=False,
        filtered_spec=None,
        version="0.1.0",
    )
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["test_spec:1", "test_spec:2"],
        metadata=metadata,
    )


def _setup_project(project_dir: Path) -> None:
    """Create a minimal project structure for CLI tests."""
    # Create .agent-fox/config.toml
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    # Create .specs/01_test/tasks.md
    spec_dir = project_dir / ".specs" / "01_test"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Write tests\n"
        "  - [ ] 1.1 Unit tests\n"
        "\n"
        "- [ ] 2. Implement feature\n"
        "  - [ ] 2.1 Core logic\n"
    )


class TestPlanPersistAndLoad:
    """TS-02-10: Plan persisted and loaded."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Saving and loading a plan produces equivalent graph."""
        plan_path = tmp_path / "plan.json"
        graph = _make_sample_graph()

        save_plan(graph, plan_path)
        loaded = load_plan(plan_path)

        assert loaded is not None
        assert loaded.nodes.keys() == graph.nodes.keys()

    def test_loaded_edges_count(self, tmp_path: Path) -> None:
        """Loaded graph has same number of edges."""
        plan_path = tmp_path / "plan.json"
        graph = _make_sample_graph()

        save_plan(graph, plan_path)
        loaded = load_plan(plan_path)

        assert loaded is not None
        assert len(loaded.edges) == len(graph.edges)

    def test_loaded_order_preserved(self, tmp_path: Path) -> None:
        """Loaded graph has same execution order."""
        plan_path = tmp_path / "plan.json"
        graph = _make_sample_graph()

        save_plan(graph, plan_path)
        loaded = load_plan(plan_path)

        assert loaded is not None
        assert loaded.order == graph.order

    def test_loaded_metadata(self, tmp_path: Path) -> None:
        """Loaded graph metadata contains created_at and version."""
        plan_path = tmp_path / "plan.json"
        graph = _make_sample_graph()

        save_plan(graph, plan_path)
        loaded = load_plan(plan_path)

        assert loaded is not None
        assert loaded.metadata.created_at != ""
        assert loaded.metadata.version == "0.1.0"

    def test_plan_file_created(self, tmp_path: Path) -> None:
        """save_plan creates the plan.json file on disk."""
        plan_path = tmp_path / "plan.json"
        graph = _make_sample_graph()

        save_plan(graph, plan_path)

        assert plan_path.exists()


class TestCorruptedPlanJson:
    """TS-02-E6: Corrupted plan.json triggers rebuild."""

    def test_corrupted_returns_none(self, tmp_path: Path) -> None:
        """Invalid JSON in plan.json returns None."""
        plan_path = tmp_path / "plan.json"
        plan_path.write_text("{invalid json")

        result = load_plan(plan_path)

        assert result is None

    def test_missing_plan_returns_none(self, tmp_path: Path) -> None:
        """Non-existent plan.json returns None."""
        plan_path = tmp_path / "nonexistent.json"

        result = load_plan(plan_path)

        assert result is None


class TestPlanCLIEndToEnd:
    """TS-02-11: Plan CLI command end-to-end."""

    def test_plan_command_exits_zero(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan command exits with code 0."""
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}, output:\n{result.output}"

    def test_plan_output_mentions_spec(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan command output mentions the spec name."""
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan"])

        assert "01_test" in result.output

    def test_plan_creates_json(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan command creates .agent-fox/plan.json."""
        _setup_project(tmp_git_repo)

        cli_runner.invoke(main, ["plan"])

        plan_path = tmp_git_repo / ".agent-fox" / "plan.json"
        assert plan_path.exists()

    def test_plan_with_fast_flag(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan --fast is accepted."""
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan", "--fast"])

        assert result.exit_code == 0

    def test_plan_fast_rebuilds_when_cached_plan_was_non_fast(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Running --fast after a cached normal plan rebuilds with fast metadata."""
        _setup_project(tmp_git_repo)

        first = cli_runner.invoke(main, ["plan"])
        assert first.exit_code == 0

        second = cli_runner.invoke(main, ["plan", "--fast"])
        assert second.exit_code == 0

        plan_path = tmp_git_repo / ".agent-fox" / "plan.json"
        loaded = load_plan(plan_path)
        assert loaded is not None
        assert loaded.metadata.fast_mode is True

    def test_plan_with_spec_filter(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan --spec NAME is accepted."""
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan", "--spec", "01_test"])

        assert result.exit_code == 0

    def test_plan_spec_rebuilds_when_cached_plan_is_unfiltered(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """Running --spec after cached unfiltered plan rebuilds and filters nodes."""
        _setup_project(tmp_git_repo)

        second_spec = tmp_git_repo / ".specs" / "02_other"
        second_spec.mkdir(parents=True)
        (second_spec / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Add second feature\n  - [ ] 1.1 Implement\n")

        first = cli_runner.invoke(main, ["plan"])
        assert first.exit_code == 0

        second = cli_runner.invoke(main, ["plan", "--spec", "01_test"])
        assert second.exit_code == 0

        plan_path = tmp_git_repo / ".agent-fox" / "plan.json"
        loaded = load_plan(plan_path)
        assert loaded is not None
        assert loaded.metadata.filtered_spec == "01_test"
        assert loaded.nodes
        assert {node.spec_name for node in loaded.nodes.values()} == {"01_test"}

    def test_plan_reanalyze_rejected(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan --reanalyze is no longer a valid option (63-REQ-2.1, 63-REQ-2.2).

        Test Spec: TS-63-4
        """
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan", "--reanalyze"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_plan_always_rebuilds_after_spec_change(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan rebuilds from .specs/ even when plan.json exists (63-REQ-1.1).

        Modifying a spec's tasks.md and re-running plan (without --reanalyze)
        must produce output that reflects the updated spec.

        Test Spec: TS-63-1
        """
        _setup_project(tmp_git_repo)

        # First run — creates plan.json
        first = cli_runner.invoke(main, ["plan"])
        assert first.exit_code == 0, f"First plan invocation failed:\n{first.output}"

        # Add a new task group to the spec
        tasks_path = tmp_git_repo / ".specs" / "01_test" / "tasks.md"
        tasks_path.write_text(
            "# Tasks\n\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Unit tests\n"
            "\n"
            "- [ ] 2. Implement feature\n"
            "  - [ ] 2.1 Core logic\n"
            "\n"
            "- [ ] 3. new_group: Deploy changes\n"
            "  - [ ] 3.1 Deploy to staging\n"
        )

        # Second run — must reflect the new task group
        second = cli_runner.invoke(main, ["plan"])
        assert second.exit_code == 0, f"Second plan invocation failed:\n{second.output}"
        assert "new_group" in second.output, (
            f"Expected 'new_group' in plan output after spec change; got:\n{second.output}"
        )

    def test_plan_verify_removed(self, cli_runner: CliRunner, tmp_git_repo: Path) -> None:
        """plan --verify is no longer a valid option (removed dead code)."""
        _setup_project(tmp_git_repo)

        result = cli_runner.invoke(main, ["plan", "--verify"])

        assert result.exit_code == 2
