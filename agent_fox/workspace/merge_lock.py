"""File-based merge lock for serializing develop-branch operations.

Provides ``MergeLock``, an async context manager that serializes merge
operations across asyncio tasks (via ``asyncio.Lock``) and OS processes
(via atomic lock file creation with ``O_CREAT | O_EXCL``).

Requirements: 45-REQ-1.1 through 45-REQ-1.E3,
              45-REQ-2.1, 45-REQ-2.2, 45-REQ-2.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)


class MergeLock:
    """File-based merge lock for serializing develop-branch operations.

    Works across asyncio tasks (via asyncio.Lock) and OS processes
    (via lock file with atomic creation).
    """

    def __init__(
        self,
        repo_root: Path,
        timeout: float = 300.0,
        stale_timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> None:
        self._repo_root = repo_root
        self._timeout = timeout
        self._stale_timeout = stale_timeout
        self._poll_interval = poll_interval
        self._async_lock = asyncio.Lock()
        self._lock_dir = repo_root / ".agent-fox"
        self._lock_file = self._lock_dir / "merge.lock"

    async def acquire(self) -> None:
        """Acquire the merge lock. Blocks until acquired or timeout.

        Raises:
            IntegrationError: If the lock cannot be acquired within timeout.
        """
        # Serialize within-process callers first
        await self._async_lock.acquire()
        try:
            await self._acquire_file_lock()
        except BaseException:
            self._async_lock.release()
            raise

    async def _acquire_file_lock(self) -> None:
        """Acquire the file-based lock, handling stale detection."""
        # Ensure .agent-fox/ directory exists (45-REQ-1.E2)
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        deadline = time.monotonic() + self._timeout

        while True:
            # Try atomic creation
            if self._try_create_lock_file():
                return

            # Lock file exists — check if stale (45-REQ-1.E1)
            if self._try_break_stale_lock():
                # Stale lock removed, retry creation immediately
                if self._try_create_lock_file():
                    return
                # Another process won the race (45-REQ-1.E3), fall through

            # Check timeout (45-REQ-1.3)
            if time.monotonic() >= deadline:
                raise IntegrationError(
                    f"Could not acquire merge lock within {self._timeout}s "
                    f"(lock timeout). Lock file: {self._lock_file}",
                )

            # Poll (45-REQ-1.2)
            await asyncio.sleep(self._poll_interval)

    def _try_create_lock_file(self) -> bool:
        """Attempt atomic lock file creation. Returns True if created."""
        try:
            fd = os.open(
                str(self._lock_file),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            return False
        except OSError:
            return False

        # Write diagnostic content
        try:
            content = json.dumps(
                {
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                    "acquired_at": datetime.now(UTC).isoformat(),
                }
            )
            os.write(fd, content.encode())
        finally:
            os.close(fd)

        logger.info("Acquired merge lock: %s (pid=%d)", self._lock_file, os.getpid())
        return True

    def _try_break_stale_lock(self) -> bool:
        """Check if lock is stale and remove it atomically.

        Uses rename-to-temp to avoid TOCTOU: the rename is atomic, so
        only one process can claim the stale file. After claiming, we
        check the age and delete the temp file if stale, or rename it
        back if it turns out to be fresh.

        Returns True if the stale lock was broken (or already gone).
        """
        # Atomically claim the lock file by renaming it
        tmp_path = self._lock_dir / f"merge.lock.breaking.{os.getpid()}"
        try:
            os.rename(str(self._lock_file), str(tmp_path))
        except FileNotFoundError:
            # Lock was already removed by someone else
            return True
        except OSError:
            # Rename failed (another process won the race)
            return False

        # We now own the renamed file — check its age
        try:
            stat = tmp_path.stat()
        except FileNotFoundError:
            return True

        age = time.time() - stat.st_mtime
        if age < self._stale_timeout:
            # Not actually stale — put it back
            try:
                os.rename(str(tmp_path), str(self._lock_file))
            except OSError:
                # Another process created a new lock; discard the old one
                tmp_path.unlink(missing_ok=True)
            return False

        # Lock is stale — remove the claimed temp file (45-REQ-1.E1)
        logger.info(
            "Breaking stale merge lock (age=%.1fs, stale_timeout=%.1fs): %s",
            age,
            self._stale_timeout,
            self._lock_file,
        )
        tmp_path.unlink(missing_ok=True)
        return True

    async def release(self) -> None:
        """Release the merge lock by removing the lock file.

        If the lock file has already been removed (e.g., broken by another
        process as stale), logs a warning and continues without error.
        """
        try:
            self._lock_file.unlink()
            logger.info("Released merge lock: %s", self._lock_file)
        except FileNotFoundError:
            # 45-REQ-2.E1: already removed
            logger.warning(
                "Merge lock file already removed on release: %s",
                self._lock_file,
            )
        finally:
            self._async_lock.release()

    async def __aenter__(self) -> MergeLock:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.release()
