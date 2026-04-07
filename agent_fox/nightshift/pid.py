"""PID file management for daemon locking.

Provides utilities to check, write, and remove the daemon PID file,
enabling mutual exclusion between daemon, code, and plan commands.

Requirements: 85-REQ-2.1, 85-REQ-2.4, 85-REQ-2.E1, 85-REQ-2.E2,
              85-REQ-2.E3, 85-REQ-3.1, 85-REQ-3.2
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class PidStatus(Enum):
    """Status of a PID file check.

    ALIVE — the recorded process is running.
    STALE — the recorded process is dead (previous daemon crash).
    ABSENT — no PID file exists.
    """

    ALIVE = "alive"
    STALE = "stale"
    ABSENT = "absent"


def check_pid_file(pid_path: Path) -> tuple[PidStatus, int | None]:
    """Check the daemon PID file and determine process liveness.

    Returns a tuple of (status, pid). If the file does not exist,
    returns (ABSENT, None). If the file exists, reads the PID and
    checks whether the process is alive.

    Requirements: 85-REQ-2.E1, 85-REQ-2.E2, 85-REQ-3.E1, 85-REQ-3.E2
    """
    if not pid_path.exists():
        return PidStatus.ABSENT, None

    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError) as exc:
        logger.warning("Could not read PID file %s: %s", pid_path, exc)
        return PidStatus.STALE, None

    # Check if the process is alive using os.kill with signal 0.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        # Process does not exist — stale PID file.
        logger.info("PID %d is not alive (stale PID file)", pid)
        return PidStatus.STALE, pid
    except PermissionError:
        # Process exists but we lack permission to signal it — treat as alive.
        logger.info("PID %d is alive (permission denied on signal)", pid)
        return PidStatus.ALIVE, pid
    except (OverflowError, OSError):
        # PID out of valid range or other OS error — treat as stale.
        logger.info("PID %d is invalid or unreachable (stale PID file)", pid)
        return PidStatus.STALE, pid
    else:
        return PidStatus.ALIVE, pid


def write_pid_file(pid_path: Path) -> None:
    """Write the current process PID to the PID file.

    Creates parent directories if needed. Raises OSError if the
    file cannot be written (e.g., read-only directory).

    Requirements: 85-REQ-2.1, 85-REQ-2.E3
    """
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))
    logger.info("Wrote PID %d to %s", os.getpid(), pid_path)


def remove_pid_file(pid_path: Path) -> None:
    """Remove the daemon PID file if it exists.

    Does not raise if the file is already absent.

    Requirements: 85-REQ-2.4
    """
    try:
        pid_path.unlink(missing_ok=True)
        logger.info("Removed PID file %s", pid_path)
    except OSError as exc:
        logger.warning("Could not remove PID file %s: %s", pid_path, exc)
