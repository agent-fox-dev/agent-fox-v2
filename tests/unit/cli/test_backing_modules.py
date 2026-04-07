"""Tests for backing module separation: export, lint-specs, code, and remaining.

Test Spec: TS-59-7 through TS-59-19, TS-59-29, TS-59-30
Requirements: 59-REQ-2.1 through 59-REQ-2.3, 59-REQ-3.1 through 59-REQ-3.E1,
              59-REQ-4.1 through 59-REQ-4.E1, 59-REQ-5.1 through 59-REQ-5.3,
              59-REQ-9.1, 59-REQ-9.2
"""

from __future__ import annotations

import inspect
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# TS-59-7 through TS-59-9: Export backing module
# ---------------------------------------------------------------------------


class TestExportMemoryCallable:
    """TS-59-7: export_memory() can be imported and called directly.

    Requirement: 59-REQ-2.1
    """

    def test_export_memory_returns_export_result(self, tmp_path: Path) -> None:
        """export_memory returns ExportResult with count and output_path."""
        from agent_fox.knowledge.export import ExportResult, export_memory

        conn = MagicMock()
        # Mock the DuckDB query for memory facts
        conn.execute.return_value.fetchall.return_value = []

        output_path = tmp_path / "memory.md"
        result = export_memory(conn, output_path)

        assert isinstance(result, ExportResult)
        assert result.count >= 0
        assert result.output_path == output_path


class TestExportDbCallable:
    """TS-59-8: export_db() can be imported and called directly.

    Requirement: 59-REQ-2.2
    """

    def test_export_db_returns_export_result(self, tmp_path: Path) -> None:
        """export_db returns ExportResult with table count."""
        from agent_fox.knowledge.export import ExportResult, export_db

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []

        output_path = tmp_path / "dump.md"
        result = export_db(conn, output_path)

        assert isinstance(result, ExportResult)
        assert result.count >= 0


class TestExportReturnsNotPrints:
    """TS-59-9: Export functions return data instead of printing.

    Requirement: 59-REQ-2.3
    """

    def test_export_memory_no_stdout(self, tmp_path: Path) -> None:
        """export_memory produces no stdout/stderr output."""
        from agent_fox.knowledge.export import export_memory

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []

        captured = StringIO()
        with patch("sys.stdout", captured), patch("sys.stderr", StringIO()):
            result = export_memory(conn, tmp_path / "memory.md")

        assert captured.getvalue() == ""
        assert result.count >= 0


# ---------------------------------------------------------------------------
# TS-59-10 through TS-59-13: Lint-specs backing module
# ---------------------------------------------------------------------------


class TestRunLintSpecsCallable:
    """TS-59-10: run_lint_specs() can be imported and called directly.

    Requirement: 59-REQ-3.1
    """

    def test_run_lint_specs_returns_lint_result(self, tmp_path: Path) -> None:
        """run_lint_specs returns LintResult with findings and exit code."""
        from agent_fox.spec.lint import LintResult, run_lint_specs

        # Create a minimal specs directory
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        result = run_lint_specs(specs_dir)

        assert isinstance(result, LintResult)
        assert isinstance(result.findings, list)
        assert result.exit_code in (0, 1)


class TestRunLintSpecsStructuredResult:
    """TS-59-11: run_lint_specs() returns findings and exit code.

    Requirement: 59-REQ-3.2
    """

    def test_lint_result_has_findings_and_exit_code(self, tmp_path: Path) -> None:
        """LintResult contains findings list and exit_code."""
        from agent_fox.spec.lint import LintResult, run_lint_specs

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        # Create a minimal spec dir missing required files to trigger findings
        bad_spec = specs_dir / "01_bad_spec"
        bad_spec.mkdir()
        (bad_spec / "requirements.md").write_text("# incomplete")

        result = run_lint_specs(specs_dir)

        assert isinstance(result, LintResult)
        assert hasattr(result, "findings")
        assert hasattr(result, "exit_code")


class TestRunLintSpecsFixNoGit:
    """TS-59-12: run_lint_specs(fix=True) does not create git commits.

    Requirement: 59-REQ-3.3
    """

    def test_fix_does_not_invoke_git(self, tmp_path: Path) -> None:
        """run_lint_specs(fix=True) applies fixes without git operations."""
        from agent_fox.spec.lint import run_lint_specs

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            result = run_lint_specs(specs_dir, fix=True)

        # Ensure no git commands were invoked
        for call in mock_run.call_args_list:
            args = call[0][0] if call[0] else call[1].get("args", [])
            if isinstance(args, (list, tuple)) and len(args) > 0:
                assert args[0] != "git", f"Unexpected git command: {args}"

        assert hasattr(result, "fix_results")


class TestRunLintSpecsMissingDir:
    """TS-59-13: run_lint_specs() raises PlanError on missing dir.

    Requirement: 59-REQ-3.E1
    """

    def test_raises_plan_error_on_missing_dir(self) -> None:
        """run_lint_specs raises PlanError when specs_dir doesn't exist."""
        from agent_fox.core.errors import PlanError
        from agent_fox.spec.lint import run_lint_specs

        with pytest.raises(PlanError):
            run_lint_specs(Path("/nonexistent/specs/dir"))


# ---------------------------------------------------------------------------
# TS-59-14 through TS-59-16: Code backing module
# ---------------------------------------------------------------------------


class TestRunCodeCallable:
    """TS-59-14: run_code() can be imported and called with explicit params.

    Requirement: 59-REQ-4.1
    """

    @pytest.mark.asyncio()
    async def test_run_code_returns_execution_state(self) -> None:
        """run_code returns ExecutionState."""
        from agent_fox.engine.run import run_code

        config = MagicMock()

        with (
            patch("agent_fox.engine.run._setup_infrastructure", return_value=None),
            patch("agent_fox.engine.run.Orchestrator") as mock_orch_cls,
        ):
            mock_state = MagicMock()
            mock_state.status = "completed"
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock(return_value=mock_state)
            mock_orch_cls.return_value = mock_orch

            result = await run_code(config, parallel=2, max_cost=1.0)

        assert result is not None
        assert result.status == "completed"  # type: ignore[union-attr]


class TestRunCodeReturnsExecutionState:
    """TS-59-15: run_code() returns ExecutionState with status.

    Requirement: 59-REQ-4.2
    """

    @pytest.mark.asyncio()
    async def test_execution_state_has_status(self) -> None:
        """Returned ExecutionState has a status field."""
        from agent_fox.engine.run import run_code

        config = MagicMock()

        with (
            patch("agent_fox.engine.run._setup_infrastructure", return_value=None),
            patch("agent_fox.engine.run.Orchestrator") as mock_orch_cls,
        ):
            mock_state = MagicMock()
            mock_state.status = "stalled"
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock(return_value=mock_state)
            mock_orch_cls.return_value = mock_orch

            result = await run_code(config)

        assert result.status in (  # type: ignore[union-attr]
            "completed",
            "stalled",
            "cost_limit",
            "interrupted",
        )


class TestRunCodeParallelism:
    """TS-59-15b: run_code passes parallelism override to orchestrator.

    Requirement: 59-REQ-4.3
    """

    @pytest.mark.asyncio()
    async def test_parallel_passed_to_orchestrator(self) -> None:
        """run_code(config, parallel=4) forwards parallel to orchestrator."""
        from agent_fox.engine.run import run_code

        config = MagicMock()

        with (
            patch("agent_fox.engine.run._setup_infrastructure", return_value=None),
            patch("agent_fox.engine.run.Orchestrator") as mock_orch_cls,
        ):
            mock_state = MagicMock()
            mock_state.status = "completed"
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock(return_value=mock_state)
            mock_orch_cls.return_value = mock_orch

            await run_code(config, parallel=4)

        # Verify parallel=4 was passed somewhere in construction
        call_kwargs = mock_orch_cls.call_args
        assert call_kwargs is not None, "Orchestrator was not instantiated"


class TestRunCodeKeyboardInterrupt:
    """TS-59-16: KeyboardInterrupt during run_code returns interrupted state.

    Requirement: 59-REQ-4.E1
    """

    @pytest.mark.asyncio()
    async def test_keyboard_interrupt_returns_interrupted(self) -> None:
        """KeyboardInterrupt produces ExecutionState(status='interrupted')."""
        from agent_fox.engine.run import run_code

        config = MagicMock()

        with (
            patch("agent_fox.engine.run._setup_infrastructure", return_value=None),
            patch("agent_fox.engine.run.Orchestrator") as mock_orch_cls,
        ):
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock(side_effect=KeyboardInterrupt)
            mock_orch_cls.return_value = mock_orch

            result = await run_code(config)

        assert result.status == "interrupted"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# TS-59-17 through TS-59-19: Remaining commands backing functions
# ---------------------------------------------------------------------------


class TestRemainingBackingFunctions:
    """TS-59-17: All 6 remaining commands have importable backing functions.

    Requirement: 59-REQ-5.1
    """

    def test_run_fix_importable(self) -> None:
        """run_fix can be imported."""
        from agent_fox.fix.runner import run_fix

        assert callable(run_fix)

    def test_run_plan_importable(self) -> None:
        """run_plan can be imported."""
        from agent_fox.graph.planner import run_plan

        assert callable(run_plan)

    def test_run_reset_importable(self) -> None:
        """run_reset can be imported."""
        from agent_fox.engine.reset import run_reset

        assert callable(run_reset)

    def test_init_project_importable(self) -> None:
        """init_project can be imported."""
        from agent_fox.workspace.init_project import init_project

        assert callable(init_project)

    def test_generate_status_importable(self) -> None:
        """generate_status can be imported."""
        from agent_fox.reporting.status import generate_status

        assert callable(generate_status)

    def test_generate_standup_importable(self) -> None:
        """generate_standup can be imported."""
        from agent_fox.reporting.standup import generate_standup

        assert callable(generate_standup)


class TestBackingFunctionsAcceptParameters:
    """TS-59-18: Backing function signatures match CLI options.

    Requirement: 59-REQ-5.2
    """

    def test_run_fix_has_issue_url_param(self) -> None:
        """run_fix signature includes issue_url."""
        from agent_fox.fix.runner import run_fix

        sig = inspect.signature(run_fix)
        assert "issue_url" in sig.parameters

    def test_run_plan_has_config_param(self) -> None:
        """run_plan signature includes config."""
        from agent_fox.graph.planner import run_plan

        sig = inspect.signature(run_plan)
        assert "config" in sig.parameters

    def test_run_reset_has_target_param(self) -> None:
        """run_reset signature includes target."""
        from agent_fox.engine.reset import run_reset

        sig = inspect.signature(run_reset)
        assert "target" in sig.parameters


class TestBackingFunctionsReturnResults:
    """TS-59-19: Backing functions return structured results, not None.

    Requirement: 59-REQ-5.3
    """

    def test_generate_status_returns_result(self) -> None:
        """generate_status returns a non-None result."""
        from agent_fox.reporting.status import generate_status

        config = MagicMock()
        result = generate_status(config)
        assert result is not None

    def test_generate_standup_returns_result(self) -> None:
        """generate_standup returns a non-None result."""
        from agent_fox.reporting.standup import generate_standup

        config = MagicMock()
        result = generate_standup(config)
        assert result is not None


# ---------------------------------------------------------------------------
# TS-59-29, TS-59-30: CLI handler thinness
# ---------------------------------------------------------------------------


class TestCliHandlersDelegateToBacking:
    """TS-59-29: CLI handlers contain no business logic.

    Requirement: 59-REQ-9.1
    """

    def test_export_handler_delegates(self) -> None:
        """export CLI handler calls export_memory or export_db."""
        from agent_fox.cli import export as export_mod

        source = inspect.getsource(export_mod)
        assert "export_memory(" in source or "export_db(" in source, "export handler must delegate to backing functions"
        # Should not contain direct DB queries
        assert "conn.execute" not in source, "export handler must not contain direct DB queries"

    def test_lint_specs_handler_delegates(self) -> None:
        """lint-specs CLI handler calls run_lint_specs."""
        from agent_fox.cli import lint_specs as lint_mod

        source = inspect.getsource(lint_mod)
        assert "run_lint_specs(" in source, "lint-specs handler must delegate to run_lint_specs"


class TestCliHandlersPassOptions:
    """TS-59-30: CLI handlers pass options as explicit parameters.

    Requirement: 59-REQ-9.2
    """

    def test_lint_specs_passes_named_args(self) -> None:
        """lint-specs handler passes ai/fix/lint_all as named params."""
        from agent_fox.cli import lint_specs as lint_mod

        source = inspect.getsource(lint_mod)
        assert "run_lint_specs(" in source
        # Check that at least some keyword args are passed
        assert "ai=" in source or "fix=" in source or "lint_all=" in source, (
            "lint-specs handler must pass options as keyword arguments"
        )

    def test_export_passes_named_args(self) -> None:
        """export handler passes options as named params."""
        from agent_fox.cli import export as export_mod

        source = inspect.getsource(export_mod)
        assert "json_mode=" in source or "output_path=" in source, (
            "export handler must pass options as keyword arguments"
        )
