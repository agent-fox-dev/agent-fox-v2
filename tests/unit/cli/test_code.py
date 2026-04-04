"""Tests for the CLI code command.

Test Spec: TS-16-1 through TS-16-8, TS-16-E1 through TS-16-E4
Requirements: 16-REQ-1.1 through 16-REQ-5.2
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.core.config import AgentFoxConfig, OrchestratorConfig
from agent_fox.engine.state import ExecutionState
from agent_fox.knowledge.db import KnowledgeDB

_MOCK_KB = MagicMock(spec=KnowledgeDB)


def _make_execution_state(
    *,
    run_status: str = "completed",
    node_states: dict[str, str] | None = None,
    total_input_tokens: int = 100_000,
    total_output_tokens: int = 50_000,
    total_cost: float = 2.50,
    total_sessions: int = 3,
) -> ExecutionState:
    """Build a mock ExecutionState for testing."""
    if node_states is None:
        node_states = {
            "spec_a:1": "completed",
            "spec_a:2": "completed",
            "spec_a:3": "completed",
        }
    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        run_status=run_status,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-02T00:00:00+00:00",
        updated_at="2026-03-02T01:00:00+00:00",
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_plan_file(tmp_path: Path) -> Path:
    """Create a temporary plan.json file."""
    plan_dir = tmp_path / ".agent-fox"
    plan_dir.mkdir(parents=True)
    plan_file = plan_dir / "plan.json"
    plan_file.write_text('{"nodes": {"a": {}}, "edges": []}')
    return plan_file


def _mock_run_code(state: ExecutionState | None = None) -> AsyncMock:
    """Create a mock for run_code that returns an ExecutionState."""
    if state is None:
        state = _make_execution_state()
    return AsyncMock(return_value=state)


class TestCommandRegistered:
    """TS-16-1: Command is registered.

    Requirement: 16-REQ-1.1
    """

    def test_code_help_accessible(self, cli_runner: CliRunner) -> None:
        """The code command is accessible via the main CLI group."""
        result = cli_runner.invoke(main, ["code", "--help"])
        assert result.exit_code == 0
        assert "Execute the task plan" in result.output


class TestSuccessfulExecution:
    """TS-16-2: Successful execution prints summary.

    Requirements: 16-REQ-1.2, 16-REQ-1.3, 16-REQ-1.4, 16-REQ-3.1,
                  16-REQ-3.2, 16-REQ-4.1, 16-REQ-5.1, 16-REQ-5.2
    """

    def test_completed_run_exits_zero(self, cli_runner: CliRunner) -> None:
        """A completed run exits with code 0."""
        state = _make_execution_state(run_status="completed")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 0

    def test_summary_contains_task_counts(self, cli_runner: CliRunner) -> None:
        """Output contains task counts in the summary."""
        state = _make_execution_state(run_status="completed")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "3/3 done" in result.output

    def test_summary_contains_cost(self, cli_runner: CliRunner) -> None:
        """Output contains cost in the summary."""
        state = _make_execution_state(run_status="completed", total_cost=2.50)
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "$2.50" in result.output

    def test_summary_contains_status(self, cli_runner: CliRunner) -> None:
        """Output contains run status."""
        state = _make_execution_state(run_status="completed")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "completed" in result.output


class TestParallelOverride:
    """TS-16-3: Parallel override applied.

    Requirements: 16-REQ-2.1, 16-REQ-2.5
    """

    def test_parallel_override_applied(self, cli_runner: CliRunner) -> None:
        """The --parallel option is passed to run_code."""
        state = _make_execution_state()
        mock_rc = _mock_run_code(state)

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            cli_runner.invoke(main, ["code", "--parallel", "4"])

        mock_rc.assert_called_once()
        call_kwargs = mock_rc.call_args
        assert call_kwargs.kwargs["parallel"] == 4

    def test_parallel_override_revalidates_config(self) -> None:
        """Out-of-range override values are revalidated/clamped."""
        from agent_fox.engine.run import _apply_overrides

        base = OrchestratorConfig(parallel=4)
        updated = _apply_overrides(base, parallel=0, max_cost=None, max_sessions=None)

        assert updated.parallel == 1


class TestStalledExitCode:
    """TS-16-6: Stalled execution exits with code 2.

    Requirement: 16-REQ-4.3
    """

    def test_stalled_exits_code_2(self, cli_runner: CliRunner) -> None:
        """A stalled run exits with code 2."""
        state = _make_execution_state(
            run_status="stalled",
            node_states={"a:1": "blocked"},
        )
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 2

    def test_stalled_output_contains_status(self, cli_runner: CliRunner) -> None:
        """Output mentions stalled status."""
        state = _make_execution_state(
            run_status="stalled",
            node_states={"a:1": "blocked"},
        )
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "stalled" in result.output


class TestCostLimitExitCode:
    """TS-16-7: Cost limit exits with code 3.

    Requirement: 16-REQ-4.4
    """

    def test_cost_limit_exits_code_3(self, cli_runner: CliRunner) -> None:
        """A cost-limited run exits with code 3."""
        state = _make_execution_state(run_status="cost_limit")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 3


class TestInterruptedExitCode:
    """TS-16-8: Interrupted execution exits with code 130.

    Requirement: 16-REQ-4.5
    """

    def test_interrupted_exits_code_130(self, cli_runner: CliRunner) -> None:
        """An interrupted run exits with code 130."""
        from agent_fox.engine.run import InterruptedResult

        mock_rc = AsyncMock(return_value=InterruptedResult())
        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 130


class TestMissingPlanFile:
    """TS-16-E1: Missing plan file.

    Requirement: 16-REQ-1.E1
    """

    def test_missing_plan_exits_code_1(self, cli_runner: CliRunner) -> None:
        """The command exits with code 1 when no plan exists."""
        with patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path:
            mock_plan_path.exists.return_value = False
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 1

    def test_missing_plan_mentions_plan(self, cli_runner: CliRunner) -> None:
        """Error message mentions the plan."""
        with patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path:
            mock_plan_path.exists.return_value = False
            result = cli_runner.invoke(main, ["code"])

        assert "plan" in result.output.lower()


class TestUnexpectedException:
    """TS-16-E2: Unexpected exception.

    Requirement: 16-REQ-1.E2
    """

    def test_exception_exits_code_1(self, cli_runner: CliRunner) -> None:
        """Unexpected exceptions exit with code 1."""
        mock_rc = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 1

    def test_exception_shows_error_message(self, cli_runner: CliRunner) -> None:
        """User-friendly error message is shown."""
        mock_rc = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "error" in result.output.lower()


class TestEmptyPlan:
    """TS-16-E3: Empty plan (zero tasks).

    Requirement: 16-REQ-3.E1
    """

    def test_empty_plan_exits_code_0(self, cli_runner: CliRunner) -> None:
        """An empty plan exits with code 0."""
        state = _make_execution_state(
            run_status="completed",
            node_states={},
            total_sessions=0,
        )
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 0

    def test_empty_plan_shows_message(self, cli_runner: CliRunner) -> None:
        """Output contains 'No tasks to execute.' message."""
        state = _make_execution_state(
            run_status="completed",
            node_states={},
            total_sessions=0,
        )
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert "No tasks to execute" in result.output


class TestUnknownRunStatus:
    """TS-16-E4: Unknown run status.

    Requirement: 16-REQ-4.E1
    """

    def test_unknown_status_exits_code_1(self, cli_runner: CliRunner) -> None:
        """An unrecognized run status exits with code 1."""
        state = _make_execution_state(
            run_status="unknown_status",
            node_states={"a:1": "completed"},
        )
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 1


class TestDebugFlag:
    """Tests for the --debug flag.

    Verifies that --debug is passed to run_code correctly.
    """

    def test_debug_flag_in_help(self, cli_runner: CliRunner) -> None:
        """The --debug option appears in the code command help."""
        result = cli_runner.invoke(main, ["code", "--help"])
        assert "--debug" in result.output

    def test_debug_passes_debug_true_to_run_code(self, cli_runner: CliRunner) -> None:
        """With --debug, run_code is called with debug=True."""
        state = _make_execution_state(run_status="completed")
        mock_rc = _mock_run_code(state)

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            cli_runner.invoke(main, ["code", "--debug"])

        mock_rc.assert_called_once()
        assert mock_rc.call_args.kwargs["debug"] is True

    def test_no_debug_passes_debug_false_to_run_code(self, cli_runner: CliRunner) -> None:
        """Without --debug, run_code is called with debug=False."""
        state = _make_execution_state(run_status="completed")
        mock_rc = _mock_run_code(state)

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            cli_runner.invoke(main, ["code"])

        mock_rc.assert_called_once()
        assert mock_rc.call_args.kwargs["debug"] is False

    def test_debug_attaches_jsonl_sink(self, cli_runner: CliRunner) -> None:
        """With --debug, debug=True is forwarded to run_code."""
        state = _make_execution_state(run_status="completed")
        mock_rc = _mock_run_code(state)

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            cli_runner.invoke(main, ["code", "--debug"])

        assert mock_rc.call_args.kwargs["debug"] is True

    def test_no_debug_skips_jsonl_sink(self, cli_runner: CliRunner) -> None:
        """Without --debug, debug=False is forwarded to run_code."""
        state = _make_execution_state(run_status="completed")
        mock_rc = _mock_run_code(state)

        with (
            patch("agent_fox.cli.code.run_code", mock_rc),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            cli_runner.invoke(main, ["code"])

        assert mock_rc.call_args.kwargs["debug"] is False


class TestNodeSessionRunnerHarvestError:
    """Verify harvest IntegrationError is caught and reported cleanly.

    When the coding session succeeds but harvest (merge to develop) fails,
    the session should be marked as failed with a clear integration error
    message rather than a generic exception.
    """

    @pytest.mark.asyncio
    async def test_harvest_error_returns_failed_record_with_context(
        self,
    ) -> None:
        """Integration error produces a failed record mentioning harvest."""
        from agent_fox.core.errors import IntegrationError
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        from agent_fox.knowledge.sink import SessionOutcome

        config = AgentFoxConfig()
        runner = NodeSessionRunner("test_spec:1", config, knowledge_db=_MOCK_KB)

        mock_outcome = SessionOutcome(
            spec_name="test_spec",
            task_group="1",
            node_id="test_spec:1",
            status="completed",
            input_tokens=100,
            output_tokens=200,
            duration_ms=5000,
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=mock_outcome,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.harvest",
                new_callable=AsyncMock,
                side_effect=IntegrationError(
                    "Merge conflict in foo.py",
                ),
            ),
        ):
            from agent_fox.workspace import WorkspaceInfo

            workspace = WorkspaceInfo(
                path=Path("/tmp/fake-worktree"),
                spec_name="test_spec",
                task_group=1,
                branch="feature/test_spec/1",
            )
            record = await runner._run_and_harvest(
                "test_spec:1",
                1,
                workspace,
                "system prompt",
                "task prompt",
                Path("/tmp/fake-repo"),
            )

        assert record.status == "failed"
        assert "harvest failed" in record.error_message.lower()
        assert record.input_tokens == 100  # Session metrics preserved
        assert record.output_tokens == 200

    @pytest.mark.asyncio
    async def test_harvest_error_records_failed_status_to_sink(
        self,
    ) -> None:
        """Sink receives failed status when harvest fails after completed session."""
        from agent_fox.core.errors import IntegrationError
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        from agent_fox.knowledge.sink import SessionOutcome

        config = AgentFoxConfig()
        sink = MagicMock()
        runner = NodeSessionRunner("test_spec:1", config, sink_dispatcher=sink, knowledge_db=_MOCK_KB)

        mock_outcome = SessionOutcome(
            spec_name="test_spec",
            task_group="1",
            node_id="test_spec:1",
            status="completed",
            input_tokens=100,
            output_tokens=200,
            duration_ms=5000,
        )

        with (
            patch(
                "agent_fox.engine.session_lifecycle.run_session",
                new_callable=AsyncMock,
                return_value=mock_outcome,
            ),
            patch(
                "agent_fox.engine.session_lifecycle.harvest",
                new_callable=AsyncMock,
                side_effect=IntegrationError(
                    "Merge conflict in foo.py",
                ),
            ),
        ):
            from agent_fox.workspace import WorkspaceInfo

            workspace = WorkspaceInfo(
                path=Path("/tmp/fake-worktree"),
                spec_name="test_spec",
                task_group=1,
                branch="feature/test_spec/1",
            )
            await runner._run_and_harvest(
                "test_spec:1",
                1,
                workspace,
                "system prompt",
                "task prompt",
                Path("/tmp/fake-repo"),
            )

        sink.record_session_outcome.assert_called_once()
        recorded = sink.record_session_outcome.call_args.args[0]
        assert recorded.status == "failed"
        assert recorded.error_message is not None
        assert "harvest failed" in recorded.error_message.lower()

    @pytest.mark.asyncio
    async def test_session_summary_read_before_cleanup(
        self,
        tmp_path: Path,
    ) -> None:
        """Session summary JSON is read from the worktree."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        from agent_fox.workspace import WorkspaceInfo

        summary_data = {
            "summary": "Implemented task group 1.",
            "tests_added_or_modified": [],
        }

        summary_path = tmp_path / ".session-summary.json"
        summary_path.write_text(json.dumps(summary_data))

        workspace = WorkspaceInfo(
            path=tmp_path,
            spec_name="test_spec",
            task_group=1,
            branch="feature/test_spec/1",
        )

        result = NodeSessionRunner._read_session_artifacts(workspace)

        assert result is not None
        assert result["summary"] == "Implemented task group 1."


class TestFinallyBlockCleanup:
    """Regression test for issue #194: cleanup steps must run independently.

    Each cleanup step in run_code's finally block should be guarded so
    that a failure in one step does not prevent subsequent steps from
    executing.
    """

    def test_cleanup_continues_after_export_failure(self, cli_runner: CliRunner) -> None:
        """Cleanup completes even when internal export fails."""
        state = _make_execution_state(run_status="completed")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 0

    def test_cleanup_continues_after_sink_close_failure(self, cli_runner: CliRunner) -> None:
        """Cleanup completes even when internal sink close fails."""
        state = _make_execution_state(run_status="completed")
        with (
            patch("agent_fox.cli.code.run_code", _mock_run_code(state)),
            patch("agent_fox.cli.code.PLAN_PATH") as mock_plan_path,
        ):
            mock_plan_path.exists.return_value = True
            result = cli_runner.invoke(main, ["code"])

        assert result.exit_code == 0
