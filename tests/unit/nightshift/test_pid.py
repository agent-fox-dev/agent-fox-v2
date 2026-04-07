"""Unit tests for PID file management.

Test Spec: TS-85-5, TS-85-10, TS-85-11, TS-85-E3, TS-85-E4, TS-85-E5, TS-85-E6, TS-85-E7
Requirements: 85-REQ-2.1, 85-REQ-2.E1, 85-REQ-2.E2, 85-REQ-2.E3,
              85-REQ-3.1, 85-REQ-3.2, 85-REQ-3.E1, 85-REQ-3.E2
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-85-5: PID file written on startup
# Requirement: 85-REQ-2.1
# ---------------------------------------------------------------------------


class TestPidFileWrite:
    """Verify that write_pid_file writes current PID as plain integer."""

    def test_write_pid_file_creates_file(self, tmp_path: Path) -> None:
        """PID file exists and contains current process PID."""
        from agent_fox.nightshift.pid import write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        content = pid_path.read_text().strip()
        assert content == str(os.getpid())


# ---------------------------------------------------------------------------
# TS-85-10: code command blocked by live daemon
# Requirement: 85-REQ-3.1
# ---------------------------------------------------------------------------


class TestCodeCommandBlocked:
    """Verify code command detects live daemon via PID file."""

    def test_check_pid_file_returns_alive_for_current_pid(self, tmp_path: Path) -> None:
        """check_pid_file returns ALIVE when PID is current process."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file, write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.ALIVE
        assert pid == os.getpid()


# ---------------------------------------------------------------------------
# TS-85-11: plan command blocked by live daemon
# Requirement: 85-REQ-3.2
# ---------------------------------------------------------------------------


class TestPlanCommandBlocked:
    """Verify plan command detects live daemon via PID file."""

    def test_check_pid_file_returns_alive(self, tmp_path: Path) -> None:
        """check_pid_file returns ALIVE for a live process."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file, write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.ALIVE


# ---------------------------------------------------------------------------
# TS-85-E3: Live PID blocks daemon startup
# Requirement: 85-REQ-2.E1
# ---------------------------------------------------------------------------


class TestLivePidBlocksStartup:
    """Verify daemon refuses to start when PID file has a live process."""

    def test_check_pid_file_alive(self, tmp_path: Path) -> None:
        """PID file with current PID returns ALIVE status."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file

        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text(str(os.getpid()))
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.ALIVE
        assert pid == os.getpid()


# ---------------------------------------------------------------------------
# TS-85-E4: Stale PID is cleaned up on daemon startup
# Requirement: 85-REQ-2.E2
# ---------------------------------------------------------------------------


class TestStalePidDetection:
    """Verify stale PID file is detected."""

    def test_check_pid_file_stale(self, tmp_path: Path) -> None:
        """PID file with dead process PID returns STALE status."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file

        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text("99999999")
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.STALE
        assert pid == 99999999


# ---------------------------------------------------------------------------
# TS-85-E5: PID file write failure
# Requirement: 85-REQ-2.E3
# ---------------------------------------------------------------------------


class TestPidFileWriteFailure:
    """Verify error on PID file write failure."""

    def test_write_pid_file_readonly_dir(self, tmp_path: Path) -> None:
        """write_pid_file raises OSError for read-only directory."""
        from agent_fox.nightshift.pid import write_pid_file

        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir(mode=0o444)
        with pytest.raises(OSError):
            write_pid_file(readonly_dir / "daemon.pid")


# ---------------------------------------------------------------------------
# TS-85-E6: No PID file allows code/plan to proceed
# Requirement: 85-REQ-3.E1
# ---------------------------------------------------------------------------


class TestNoPidFile:
    """Verify code/plan proceed when no PID file exists."""

    def test_check_pid_file_absent(self, tmp_path: Path) -> None:
        """check_pid_file returns ABSENT when file does not exist."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file

        status, pid = check_pid_file(tmp_path / "daemon.pid")
        assert status == PidStatus.ABSENT
        assert pid is None


# ---------------------------------------------------------------------------
# TS-85-E7: Stale PID does not block code/plan
# Requirement: 85-REQ-3.E2
# ---------------------------------------------------------------------------


class TestStalePidNoBlock:
    """Verify code/plan proceed when PID file has stale PID."""

    def test_stale_pid_returns_stale_status(self, tmp_path: Path) -> None:
        """STALE status means code/plan should proceed."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file

        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text("99999999")
        status, _ = check_pid_file(pid_path)
        assert status == PidStatus.STALE


# ---------------------------------------------------------------------------
# PID file remove
# Requirement: 85-REQ-2.4
# ---------------------------------------------------------------------------


class TestPidFileRemove:
    """Verify remove_pid_file deletes the PID file."""

    def test_remove_existing_pid_file(self, tmp_path: Path) -> None:
        """remove_pid_file deletes an existing PID file."""
        from agent_fox.nightshift.pid import remove_pid_file, write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        assert pid_path.exists()
        remove_pid_file(pid_path)
        assert not pid_path.exists()

    def test_remove_nonexistent_pid_file_no_error(self, tmp_path: Path) -> None:
        """remove_pid_file does not raise for missing file."""
        from agent_fox.nightshift.pid import remove_pid_file

        pid_path = tmp_path / "daemon.pid"
        remove_pid_file(pid_path)  # should not raise
