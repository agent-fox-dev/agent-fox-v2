"""Rollback tests.

Test Spec: TS-31-17, TS-31-18
Requirements: 31-REQ-7.1, 31-REQ-7.3, 31-REQ-7.E1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.fix.improve import rollback_improvement_pass


class TestRollback:
    """TS-31-17, TS-31-18: Rollback logic."""

    def test_rollback_executes_git_reset(self, tmp_path: Path) -> None:
        """TS-31-17: Rollback runs git reset --hard HEAD~1."""
        with patch("agent_fox.fix.improve.run_git_sync") as mock_run:
            mock_run.return_value = (0, "", "")

            rollback_improvement_pass(tmp_path)

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["reset", "--hard", "HEAD~1"]

    def test_rollback_failure_raises_error(self, tmp_path: Path) -> None:
        """TS-31-18: Rollback raises error when git reset fails."""
        with patch("agent_fox.fix.improve.run_git_sync") as mock_run:
            mock_run.return_value = (128, "", "fatal: error")

            with pytest.raises(Exception):
                rollback_improvement_pass(tmp_path)
