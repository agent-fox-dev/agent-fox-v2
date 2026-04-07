"""Unit tests for post-session quality gate execution.

Test Spec: TS-54-1, TS-54-2, TS-54-3, TS-54-4, TS-54-5, TS-54-E1
Requirements: 54-REQ-1.1, 54-REQ-1.2, 54-REQ-1.3, 54-REQ-1.E1, 54-REQ-1.E2,
              54-REQ-2.1, 54-REQ-2.2, 54-REQ-2.E1
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from agent_fox.core.config import OrchestratorConfig

# ---------------------------------------------------------------------------
# TS-54-1: Quality gate runs after completed session
# ---------------------------------------------------------------------------


class TestQualityGateRuns:
    """TS-54-1: Quality gate command is executed after a completed session."""

    def test_gate_runs_configured_command(self) -> None:
        """TS-54-1: Verify quality gate runs the configured command.

        Requirement: 54-REQ-1.1
        """
        from agent_fox.engine.quality_gate import (
            QualityGateResult,
            run_quality_gate,
        )

        config = OrchestratorConfig(quality_gate="make check")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="make check",
                returncode=0,
                stdout="all good\n",
                stderr="",
            )
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        assert isinstance(result, QualityGateResult)
        assert result.passed is True
        assert result.exit_code == 0
        mock_run.assert_called_once()
        # AC-1, AC-6: subprocess.run receives a list and shell=False
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args.kwargs.get("args")
        assert cmd == ["make", "check"], f"Expected list ['make', 'check'], got {cmd!r}"
        assert call_args.kwargs.get("shell") is False


# ---------------------------------------------------------------------------
# TS-54-2: Quality gate skipped when not configured
# ---------------------------------------------------------------------------


class TestQualityGateSkipped:
    """TS-54-2: No subprocess spawned when quality_gate is empty."""

    def test_gate_skipped_empty_string(self) -> None:
        """TS-54-2: Empty quality_gate string means no subprocess.

        Requirement: 54-REQ-1.3
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is None
        mock_run.assert_not_called()

    def test_gate_skipped_default_config(self) -> None:
        """TS-54-2: Default config (no quality_gate) skips gate.

        Requirement: 54-REQ-1.3
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig()

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is None
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# TS-54-3: Quality gate timeout handling
# ---------------------------------------------------------------------------


class TestQualityGateTimeout:
    """TS-54-3: Timed-out command is killed and recorded as failure."""

    def test_gate_timeout_records_failure(self) -> None:
        """TS-54-3: TimeoutExpired results in exit_code=-1, passed=False.

        Requirement: 54-REQ-1.2
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(
            quality_gate="sleep 600",
            quality_gate_timeout=1,
        )

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 600", timeout=1)
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        assert result.exit_code == -1
        assert result.passed is False
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# TS-54-4: Quality gate result audit event
# ---------------------------------------------------------------------------


class TestQualityGateAuditEvent:
    """TS-54-4: quality_gate.result audit event is emitted."""

    def test_audit_event_emitted(self) -> None:
        """TS-54-4: Verify audit event with correct payload.

        Requirement: 54-REQ-2.1
        """
        from agent_fox.engine.quality_gate import (
            QualityGateResult,
            build_gate_audit_payload,
        )

        result = QualityGateResult(
            exit_code=0,
            stdout_tail="ok",
            stderr_tail="",
            duration_ms=500,
            passed=True,
        )

        payload = build_gate_audit_payload(result, command="make check")

        assert payload["exit_code"] == 0
        assert payload["passed"] is True
        assert payload["duration_ms"] == 500
        assert payload["stdout_tail"] == "ok"
        assert payload["stderr_tail"] == ""
        assert payload["command"] == "make check"

    def test_audit_event_type_exists(self) -> None:
        """TS-54-4: QUALITY_GATE_RESULT exists in AuditEventType.

        Requirement: 54-REQ-2.1
        """
        from agent_fox.knowledge.audit import AuditEventType

        assert hasattr(AuditEventType, "QUALITY_GATE_RESULT")
        assert AuditEventType.QUALITY_GATE_RESULT == "quality_gate.result"

    def test_null_sink_logs_only(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-54-4: When sink is None, result is logged but no audit event emitted.

        Requirement: 54-REQ-2.E1
        """
        from agent_fox.engine.quality_gate import (
            QualityGateResult,
            emit_gate_result,
        )

        result = QualityGateResult(
            exit_code=0,
            stdout_tail="ok",
            stderr_tail="",
            duration_ms=100,
            passed=True,
        )

        with caplog.at_level("INFO", logger="agent_fox.engine.quality_gate"):
            # Should not raise even when sink_dispatcher is None
            emit_gate_result(
                result=result,
                command="make check",
                sink_dispatcher=None,
                run_id="",
                node_id="test:1",
            )

        # Should have logged the result
        assert any("quality" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-54-5: Gate failure sets status
# ---------------------------------------------------------------------------


class TestQualityGateStatus:
    """TS-54-5: Failed gate sets status to completed_with_gate_failure."""

    def test_gate_failure_status(self) -> None:
        """TS-54-5: Non-zero exit code means passed=False.

        Requirement: 54-REQ-2.2
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="false")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="false",
                returncode=1,
                stdout="",
                stderr="error: tests failed\n",
            )
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        assert result.passed is False
        assert result.exit_code == 1

    def test_completed_with_gate_failure_status_string(self) -> None:
        """TS-54-5: Verify the status string constant exists.

        Requirement: 54-REQ-2.2
        """
        from agent_fox.engine.quality_gate import (
            QualityGateResult,
            gate_session_status,
        )

        passing = QualityGateResult(exit_code=0, stdout_tail="", stderr_tail="", duration_ms=0, passed=True)
        failing = QualityGateResult(exit_code=1, stdout_tail="", stderr_tail="", duration_ms=0, passed=False)

        assert gate_session_status(passing) == "completed"
        assert gate_session_status(failing) == "completed_with_gate_failure"


# ---------------------------------------------------------------------------
# TS-54-E1: Command not found
# ---------------------------------------------------------------------------


class TestQualityGateCommandNotFound:
    """TS-54-E1: Missing command is recorded as failure with exit_code=-2."""

    def test_command_not_found(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-54-E1: FileNotFoundError produces exit_code=-2.

        Requirement: 54-REQ-1.E1
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="nonexistent_command_xyz")

        with caplog.at_level("WARNING", logger="agent_fox.engine.quality_gate"):
            with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError(
                    "[Errno 2] No such file or directory: 'nonexistent_command_xyz'"
                )
                result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        assert result.exit_code == -2
        assert result.passed is False
        # Warning should mention the command
        assert any("nonexistent_command_xyz" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-54-1.E2: Output truncation (last 50 lines)
# ---------------------------------------------------------------------------


class TestQualityGateOutputTruncation:
    """TS-54-E2 (implied): Verify stdout/stderr are truncated to 50 lines."""

    def test_output_truncated_to_50_lines(self) -> None:
        """Excessive output is truncated to last 50 lines.

        Requirement: 54-REQ-1.E2
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="noisy_command")
        long_stdout = "\n".join(f"line {i}" for i in range(200))
        long_stderr = "\n".join(f"err {i}" for i in range(200))

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="noisy_command",
                returncode=0,
                stdout=long_stdout,
                stderr=long_stderr,
            )
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        # Count lines in the captured output
        stdout_lines = result.stdout_tail.strip().split("\n")
        stderr_lines = result.stderr_tail.strip().split("\n")
        assert len(stdout_lines) <= 50
        assert len(stderr_lines) <= 50
        # Should have the LAST lines, not the first
        assert "line 199" in result.stdout_tail
        assert "err 199" in result.stderr_tail


# ---------------------------------------------------------------------------
# AC-2: shlex import
# ---------------------------------------------------------------------------


class TestShellFalseInvocation:
    """AC-2 through AC-4: subprocess is invoked with shell=False and shlex tokenisation."""

    def test_shlex_imported_in_quality_gate_module(self) -> None:
        """AC-2: shlex is importable from quality_gate at module level."""
        import importlib
        import inspect

        import agent_fox.engine.quality_gate as qg_mod

        source = inspect.getsource(qg_mod)
        assert "import shlex" in source, "shlex must be imported at module level in quality_gate.py"

    def test_quoted_args_tokenised_correctly(self) -> None:
        """AC-3: Commands with quoted arguments are correctly tokenised by shlex.split.

        e.g. 'pytest -k "test_foo bar"' → ['pytest', '-k', 'test_foo bar']
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate='pytest -k "test_foo bar"')

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["pytest", "-k", "test_foo bar"],
                returncode=0,
                stdout="",
                stderr="",
            )
            run_quality_gate(config, project_root="/tmp/project")

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args.kwargs.get("args")
        assert cmd == ["pytest", "-k", "test_foo bar"], f"Unexpected tokenisation: {cmd!r}"
        assert call_args.kwargs.get("shell") is False

    def test_shell_metacharacters_not_interpreted(self) -> None:
        """AC-4: Shell metacharacters are tokenised literally, not interpreted.

        'echo hello; rm -rf /' → ['echo', 'hello;', 'rm', '-rf', '/']
        """
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="echo hello; rm -rf /")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["echo", "hello;", "rm", "-rf", "/"],
                returncode=0,
                stdout="hello; rm -rf /\n",
                stderr="",
            )
            run_quality_gate(config, project_root="/tmp/project")

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args.kwargs.get("args")
        assert cmd == ["echo", "hello;", "rm", "-rf", "/"], f"Unexpected tokenisation: {cmd!r}"
        assert call_args.kwargs.get("shell") is False


# ---------------------------------------------------------------------------
# Config field tests
# ---------------------------------------------------------------------------


class TestQualityGateConfig:
    """Verify quality_gate and quality_gate_timeout config fields."""

    def test_quality_gate_field_exists(self) -> None:
        """Verify quality_gate field on OrchestratorConfig.

        Requirement: 54-REQ-1.1
        """
        config = OrchestratorConfig()
        assert hasattr(config, "quality_gate")
        assert config.quality_gate == ""

    def test_quality_gate_timeout_default(self) -> None:
        """Verify quality_gate_timeout defaults to 300.

        Requirement: 54-REQ-1.2
        """
        config = OrchestratorConfig()
        assert hasattr(config, "quality_gate_timeout")
        assert config.quality_gate_timeout == 300

    def test_quality_gate_timeout_custom(self) -> None:
        """Verify quality_gate_timeout can be set.

        Requirement: 54-REQ-1.2
        """
        config = OrchestratorConfig(quality_gate_timeout=60)
        assert config.quality_gate_timeout == 60
