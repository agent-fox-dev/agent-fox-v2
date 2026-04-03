"""Cross-process lock serialization integration test.

Test Spec: TS-45-4
Requirements: 45-REQ-1.4
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Script that a subprocess runs to acquire and hold a lock
_LOCK_HOLDER_SCRIPT = """\
import asyncio
import json
import sys
import time
from pathlib import Path

# Add the project to sys.path
sys.path.insert(0, "{project_root}")

from agent_fox.workspace.merge_lock import MergeLock

async def main():
    repo_root = Path(sys.argv[1])
    hold_seconds = float(sys.argv[2])
    result_file = Path(sys.argv[3])

    lock = MergeLock(repo_root, timeout=10.0, poll_interval=0.05)
    acquired_at = time.time()
    await lock.acquire()

    result = {{"acquired_at": time.time(), "pid": os.getpid()}}
    await asyncio.sleep(hold_seconds)

    released_at = time.time()
    result["released_at"] = released_at
    result_file.write_text(json.dumps(result))

    await lock.release()

import os
asyncio.run(main())
"""


class TestCrossProcessLockSerialization:
    """TS-45-4: Lock works across OS processes."""

    @pytest.mark.asyncio
    async def test_cross_process_serialization(self, tmp_path: Path) -> None:
        """Process B blocks until Process A releases the lock."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Find the project root for sys.path injection
        project_root = Path(__file__).resolve().parent.parent.parent
        script = _LOCK_HOLDER_SCRIPT.format(project_root=project_root)

        script_file = tmp_path / "lock_holder.py"
        script_file.write_text(script)

        result_a = tmp_path / "result_a.json"
        result_b = tmp_path / "result_b.json"

        # Start process A (holds lock for 0.5 seconds)
        proc_a = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_file),
            str(repo_root),
            "0.5",
            str(result_a),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Give A a moment to acquire the lock
        await asyncio.sleep(0.1)

        # Start process B (tries to acquire immediately)
        proc_b = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_file),
            str(repo_root),
            "0.0",
            str(result_b),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for both
        _, stderr_a = await proc_a.communicate()
        _, stderr_b = await proc_b.communicate()

        assert proc_a.returncode == 0, f"Process A failed: {stderr_a.decode()}"
        assert proc_b.returncode == 0, f"Process B failed: {stderr_b.decode()}"

        # Verify serialization: B acquired after A released
        data_a = json.loads(result_a.read_text())
        data_b = json.loads(result_b.read_text())

        assert data_b["acquired_at"] >= data_a["released_at"], (
            f"Process B acquired at {data_b['acquired_at']} before A released at {data_a['released_at']}"
        )
