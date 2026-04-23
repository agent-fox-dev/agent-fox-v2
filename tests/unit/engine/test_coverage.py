"""Tests for the test coverage regression gate.

Verifies that the coverage module correctly detects coverage tools,
measures per-file coverage, and identifies regressions on modified files.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.engine.coverage import (
    CoverageRegression,
    CoverageResult,
    CoverageTool,
    FileCoverage,
    detect_coverage_tool,
    find_regressions,
    measure_coverage,
)


class TestDetectCoverageTool:
    def test_detects_pytest_cov(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        tool = detect_coverage_tool(tmp_path)
        assert tool is not None
        assert tool.name == "pytest-cov"
        assert "--cov" in tool.command

    def test_detects_cargo_tarpaulin(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"foo\"\n")
        tool = detect_coverage_tool(tmp_path)
        assert tool is not None
        assert tool.name == "cargo-tarpaulin"

    def test_detects_go_cover(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/foo\n")
        tool = detect_coverage_tool(tmp_path)
        assert tool is not None
        assert tool.name == "go-cover"

    def test_returns_none_for_unknown_project(self, tmp_path: Path) -> None:
        assert detect_coverage_tool(tmp_path) is None

    def test_python_takes_precedence_over_makefile(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        (tmp_path / "Makefile").write_text("test:\n\techo hi\n")
        tool = detect_coverage_tool(tmp_path)
        assert tool is not None
        assert tool.name == "pytest-cov"

    def test_handles_unparseable_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("{{invalid toml}}")
        assert detect_coverage_tool(tmp_path) is None

    def test_pyproject_without_pytest_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88\n")
        assert detect_coverage_tool(tmp_path) is None


class TestFileCoverage:
    def test_percentage_calculation(self) -> None:
        fc = FileCoverage(file_path="a.py", covered_lines=75, total_lines=100)
        assert fc.percentage == 75.0

    def test_zero_total_lines_returns_100(self) -> None:
        fc = FileCoverage(file_path="empty.py", covered_lines=0, total_lines=0)
        assert fc.percentage == 100.0

    def test_full_coverage(self) -> None:
        fc = FileCoverage(file_path="a.py", covered_lines=50, total_lines=50)
        assert fc.percentage == 100.0


class TestCoverageResult:
    def test_coverage_for_existing_file(self) -> None:
        fc = FileCoverage(file_path="a.py", covered_lines=10, total_lines=20)
        result = CoverageResult(files={"a.py": fc})
        assert result.coverage_for("a.py") is fc

    def test_coverage_for_missing_file(self) -> None:
        result = CoverageResult(files={})
        assert result.coverage_for("missing.py") is None


class TestFindRegressions:
    def test_no_regression_when_coverage_increases(self) -> None:
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 50, 100)}
        )
        current = CoverageResult(
            files={"a.py": FileCoverage("a.py", 60, 100)}
        )
        assert find_regressions(baseline, current, ["a.py"]) == []

    def test_no_regression_when_coverage_unchanged(self) -> None:
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 50, 100)}
        )
        current = CoverageResult(
            files={"a.py": FileCoverage("a.py", 50, 100)}
        )
        assert find_regressions(baseline, current, ["a.py"]) == []

    def test_detects_regression(self) -> None:
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 80, 100)}
        )
        current = CoverageResult(
            files={"a.py": FileCoverage("a.py", 60, 100)}
        )
        regressions = find_regressions(baseline, current, ["a.py"])
        assert len(regressions) == 1
        assert regressions[0].file_path == "a.py"
        assert regressions[0].baseline_pct == 80.0
        assert regressions[0].current_pct == 60.0
        assert regressions[0].delta == -20.0

    def test_ignores_unmodified_files(self) -> None:
        baseline = CoverageResult(
            files={
                "a.py": FileCoverage("a.py", 80, 100),
                "b.py": FileCoverage("b.py", 90, 100),
            }
        )
        current = CoverageResult(
            files={
                "a.py": FileCoverage("a.py", 80, 100),
                "b.py": FileCoverage("b.py", 50, 100),
            }
        )
        regressions = find_regressions(baseline, current, ["a.py"])
        assert len(regressions) == 0

    def test_skips_files_missing_from_baseline(self) -> None:
        baseline = CoverageResult(files={})
        current = CoverageResult(
            files={"new.py": FileCoverage("new.py", 50, 100)}
        )
        assert find_regressions(baseline, current, ["new.py"]) == []

    def test_skips_files_missing_from_current(self) -> None:
        baseline = CoverageResult(
            files={"deleted.py": FileCoverage("deleted.py", 80, 100)}
        )
        current = CoverageResult(files={})
        assert find_regressions(baseline, current, ["deleted.py"]) == []

    def test_skips_files_with_zero_baseline_lines(self) -> None:
        baseline = CoverageResult(
            files={"empty.py": FileCoverage("empty.py", 0, 0)}
        )
        current = CoverageResult(
            files={"empty.py": FileCoverage("empty.py", 0, 0)}
        )
        assert find_regressions(baseline, current, ["empty.py"]) == []

    def test_multiple_regressions(self) -> None:
        baseline = CoverageResult(
            files={
                "a.py": FileCoverage("a.py", 80, 100),
                "b.py": FileCoverage("b.py", 70, 100),
            }
        )
        current = CoverageResult(
            files={
                "a.py": FileCoverage("a.py", 60, 100),
                "b.py": FileCoverage("b.py", 50, 100),
            }
        )
        regressions = find_regressions(baseline, current, ["a.py", "b.py"])
        assert len(regressions) == 2


class TestMeasureCoverage:
    def test_returns_none_on_timeout(self, tmp_path: Path) -> None:
        import subprocess

        tool = CoverageTool(
            name="pytest-cov",
            command=["sleep", "999"],
            result_path="coverage.json",
        )
        with patch("agent_fox.engine.coverage._COVERAGE_TIMEOUT", 0):
            with patch(
                "agent_fox.engine.coverage.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="sleep", timeout=0),
            ):
                result = measure_coverage(tmp_path, tool)
        assert result is None

    def test_returns_none_when_result_file_missing(self, tmp_path: Path) -> None:
        tool = CoverageTool(
            name="pytest-cov",
            command=["echo", "no-op"],
            result_path="coverage.json",
        )
        with patch("agent_fox.engine.coverage.subprocess.run"):
            result = measure_coverage(tmp_path, tool)
        assert result is None

    def test_parses_pytest_cov_output(self, tmp_path: Path) -> None:
        cov_data = {
            "files": {
                "agent_fox/foo.py": {
                    "summary": {
                        "covered_lines": 80,
                        "num_statements": 100,
                    }
                },
                "agent_fox/bar.py": {
                    "summary": {
                        "covered_lines": 45,
                        "num_statements": 50,
                    }
                },
            }
        }
        result_path = tmp_path / "coverage.json"
        result_path.write_text(json.dumps(cov_data))

        tool = CoverageTool(
            name="pytest-cov",
            command=["echo", "done"],
            result_path="coverage.json",
        )
        with patch("agent_fox.engine.coverage.subprocess.run"):
            result = measure_coverage(tmp_path, tool)

        assert result is not None
        assert len(result.files) == 2
        foo = result.coverage_for("agent_fox/foo.py")
        assert foo is not None
        assert foo.covered_lines == 80
        assert foo.total_lines == 100
        assert foo.percentage == 80.0

    def test_parses_go_cover_output(self, tmp_path: Path) -> None:
        go_cov = textwrap.dedent("""\
            mode: count
            example.com/foo/main.go:10.1,12.1 3 1
            example.com/foo/main.go:14.1,16.1 3 0
        """)
        result_path = tmp_path / "coverage.out"
        result_path.write_text(go_cov)

        tool = CoverageTool(
            name="go-cover",
            command=["echo", "done"],
            result_path="coverage.out",
        )
        with patch("agent_fox.engine.coverage.subprocess.run"):
            result = measure_coverage(tmp_path, tool)

        assert result is not None
        fc = result.coverage_for("example.com/foo/main.go")
        assert fc is not None
        assert fc.covered_lines == 3
        assert fc.total_lines == 6
        assert fc.percentage == 50.0

    def test_parses_tarpaulin_output(self, tmp_path: Path) -> None:
        tarp_data = {
            "files": [
                {
                    "path": "src/main.rs",
                    "traces": [
                        {"stats": {"Line": 1}},
                        {"stats": {"Line": 0}},
                        {"stats": {"Line": 1}},
                    ],
                }
            ]
        }
        result_path = tmp_path / "tarpaulin-report.json"
        result_path.write_text(json.dumps(tarp_data))

        tool = CoverageTool(
            name="cargo-tarpaulin",
            command=["echo", "done"],
            result_path="tarpaulin-report.json",
        )
        with patch("agent_fox.engine.coverage.subprocess.run"):
            result = measure_coverage(tmp_path, tool)

        assert result is not None
        fc = result.coverage_for("src/main.rs")
        assert fc is not None
        assert fc.covered_lines == 2
        assert fc.total_lines == 3

    def test_cleans_up_result_file(self, tmp_path: Path) -> None:
        cov_data = {"files": {}}
        result_path = tmp_path / "coverage.json"
        result_path.write_text(json.dumps(cov_data))

        tool = CoverageTool(
            name="pytest-cov",
            command=["echo", "done"],
            result_path="coverage.json",
        )
        with patch("agent_fox.engine.coverage.subprocess.run"):
            measure_coverage(tmp_path, tool)

        assert not result_path.exists()


class TestCoverageResultSerialization:
    def test_to_json_and_back(self) -> None:
        result = CoverageResult(
            files={
                "a.py": FileCoverage("a.py", 80, 100),
                "b.py": FileCoverage("b.py", 45, 50),
            }
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert "a.py" in parsed
        assert parsed["a.py"]["covered_lines"] == 80
        assert parsed["a.py"]["total_lines"] == 100

    def test_from_json(self) -> None:
        data = {
            "a.py": {"covered_lines": 80, "total_lines": 100},
        }
        result = CoverageResult.from_json(json.dumps(data))
        assert result is not None
        fc = result.coverage_for("a.py")
        assert fc is not None
        assert fc.percentage == 80.0

    def test_from_json_returns_none_on_invalid(self) -> None:
        assert CoverageResult.from_json("not json") is None
        assert CoverageResult.from_json("") is None


class TestResultHandlerCoverageIntegration:
    """Test coverage capture and regression check via SessionResultHandler."""

    def _make_handler(self) -> "SessionResultHandler":
        from agent_fox.engine.result_handler import SessionResultHandler

        mock_graph_sync = MagicMock()
        mock_graph_sync.node_states = {}
        mock_graph_sync.predecessors.return_value = []

        return SessionResultHandler(
            graph_sync=mock_graph_sync,
            routing_ladders={},
            retries_before_escalation=1,
            max_retries=2,
            task_callback=None,
            sink=None,
            run_id="test-run",
            graph=None,
            archetypes_config=None,
            knowledge_db_conn=None,
            block_task_fn=MagicMock(),
            check_block_budget_fn=MagicMock(),
        )

    def test_capture_baseline_stores_result(self, tmp_path: Path) -> None:
        handler = self._make_handler()
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 80, 100)}
        )
        with patch(
            "agent_fox.engine.coverage.detect_coverage_tool",
            return_value=CoverageTool("pytest-cov", ["echo"], "coverage.json"),
        ), patch(
            "agent_fox.engine.coverage.measure_coverage",
            return_value=baseline,
        ):
            handler.capture_coverage_baseline("spec:1", tmp_path)

        assert "spec:1" in handler._coverage_baselines
        assert handler._coverage_baselines["spec:1"] is baseline

    def test_capture_baseline_skips_when_no_tool(self, tmp_path: Path) -> None:
        handler = self._make_handler()
        with patch(
            "agent_fox.engine.coverage.detect_coverage_tool",
            return_value=None,
        ):
            handler.capture_coverage_baseline("spec:1", tmp_path)
        assert "spec:1" not in handler._coverage_baselines

    def test_check_regression_returns_json_on_no_regression(
        self, tmp_path: Path
    ) -> None:
        from agent_fox.engine.state import SessionRecord

        handler = self._make_handler()
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 80, 100)}
        )
        handler._coverage_baselines["spec:1"] = baseline
        handler._coverage_tool = CoverageTool("pytest-cov", ["echo"], "coverage.json")

        current = CoverageResult(
            files={"a.py": FileCoverage("a.py", 90, 100)}
        )
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="",
            files_touched=["a.py"],
        )
        state = MagicMock()
        with patch(
            "agent_fox.engine.coverage.measure_coverage",
            return_value=current,
        ):
            result = handler.check_coverage_regression(record, state, tmp_path)

        assert result is not None
        parsed = json.loads(result)
        assert "a.py" in parsed

    def test_check_regression_blocks_on_decrease(self, tmp_path: Path) -> None:
        from agent_fox.engine.state import SessionRecord

        handler = self._make_handler()
        baseline = CoverageResult(
            files={"a.py": FileCoverage("a.py", 80, 100)}
        )
        handler._coverage_baselines["spec:1"] = baseline
        handler._coverage_tool = CoverageTool("pytest-cov", ["echo"], "coverage.json")

        current = CoverageResult(
            files={"a.py": FileCoverage("a.py", 60, 100)}
        )
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="",
            files_touched=["a.py"],
        )
        state = MagicMock()
        state.blocked_reasons = {}
        with patch(
            "agent_fox.engine.coverage.measure_coverage",
            return_value=current,
        ):
            handler.check_coverage_regression(record, state, tmp_path)

        handler._block_task.assert_called_once()
        call_args = handler._block_task.call_args
        assert "spec:1" == call_args[0][0]
        assert "Coverage regression" in call_args[0][2]

    def test_check_regression_returns_none_without_baseline(
        self, tmp_path: Path
    ) -> None:
        from agent_fox.engine.state import SessionRecord

        handler = self._make_handler()
        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="",
            files_touched=["a.py"],
        )
        state = MagicMock()
        result = handler.check_coverage_regression(record, state, tmp_path)
        assert result is None


class TestMigrationV20:
    def test_adds_coverage_data_column(self) -> None:
        import duckdb

        from agent_fox.knowledge.migrations import run_migrations

        conn = duckdb.connect(":memory:")
        run_migrations(conn)
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'session_outcomes' AND column_name = 'coverage_data'"
        ).fetchall()
        assert len(cols) == 1
        conn.close()
