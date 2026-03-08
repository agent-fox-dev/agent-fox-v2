"""Collector tests.

Test Spec: TS-08-6 (failure capture), TS-08-7 (all passing)
Edge Cases: TS-08-E3 (timeout)
Requirements: 08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3, 08-REQ-2.E1
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from agent_fox.fix.checks import run_checks
from agent_fox.fix.checks import CheckDescriptor


class TestCollectorCapturesFailures:
    """TS-08-6: Collector captures failures from failing checks.

    Requirement: 08-REQ-2.1, 08-REQ-2.2
    """

    def test_failing_check_produces_failure_record(
        self,
        tmp_project: Path,
        check_descriptor_pytest: CheckDescriptor,
    ) -> None:
        """A check exiting non-zero creates a FailureRecord."""
        mock_result = subprocess.CompletedProcess(
            args=check_descriptor_pytest.command,
            returncode=1,
            stdout="",
            stderr="FAILED test_foo.py",
        )

        with patch("agent_fox.fix.checks.subprocess.run", return_value=mock_result):
            failures, passed = run_checks([check_descriptor_pytest], tmp_project)

        assert len(failures) == 1
        assert len(passed) == 0
        assert failures[0].exit_code == 1
        assert "FAILED" in failures[0].output

    def test_failure_record_contains_check_descriptor(
        self,
        tmp_project: Path,
        check_descriptor_pytest: CheckDescriptor,
    ) -> None:
        """FailureRecord references the correct check descriptor."""
        mock_result = subprocess.CompletedProcess(
            args=check_descriptor_pytest.command,
            returncode=1,
            stdout="error output",
            stderr="",
        )

        with patch("agent_fox.fix.checks.subprocess.run", return_value=mock_result):
            failures, _ = run_checks([check_descriptor_pytest], tmp_project)

        assert failures[0].check == check_descriptor_pytest


class TestCollectorReportsPassingChecks:
    """TS-08-7: Collector reports passing checks.

    Requirement: 08-REQ-2.3
    """

    def test_all_passing_returns_no_failures(
        self,
        tmp_project: Path,
        check_descriptor_pytest: CheckDescriptor,
        ruff_check_descriptor: CheckDescriptor,
    ) -> None:
        """When all checks pass, failures is empty and all checks are in passed."""
        mock_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="all good",
            stderr="",
        )

        with patch("agent_fox.fix.checks.subprocess.run", return_value=mock_result):
            failures, passed = run_checks(
                [check_descriptor_pytest, ruff_check_descriptor],
                tmp_project,
            )

        assert len(failures) == 0
        assert len(passed) == 2


# -- Edge case tests ---------------------------------------------------------


class TestCollectorTimeout:
    """TS-08-E3: Check command timeout.

    Requirement: 08-REQ-2.E1
    """

    def test_timeout_recorded_as_failure(
        self,
        tmp_project: Path,
        check_descriptor_pytest: CheckDescriptor,
    ) -> None:
        """A timed-out check is recorded as a failure with timeout message."""
        with patch(
            "agent_fox.fix.checks.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=300),
        ):
            failures, passed = run_checks([check_descriptor_pytest], tmp_project)

        assert len(failures) == 1
        assert "timeout" in failures[0].output.lower()
        assert len(passed) == 0

    def test_timeout_does_not_raise(
        self,
        tmp_project: Path,
        check_descriptor_pytest: CheckDescriptor,
    ) -> None:
        """Timeout is handled gracefully, not propagated as an exception."""
        with patch(
            "agent_fox.fix.checks.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=300),
        ):
            # Should not raise
            failures, passed = run_checks([check_descriptor_pytest], tmp_project)

        assert len(failures) == 1
