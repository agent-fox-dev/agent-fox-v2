"""Integration smoke tests for git stack hardening.

Test Spec: TS-118-SMOKE-1, TS-118-SMOKE-2, TS-118-SMOKE-3, TS-118-SMOKE-4
Requirements: 118-REQ-1.1, 118-REQ-1.2, 118-REQ-2.1, 118-REQ-2.3,
              118-REQ-3.1, 118-REQ-3.E1, 118-REQ-6.1, 118-REQ-6.2
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.engine.state import (
    cleanup_stale_runs,
    run_cleanup_handler,
)
from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.workspace.harvest import _clean_conflicting_untracked, harvest
from agent_fox.workspace.health import (
    check_workspace_health,
    force_clean_workspace,
    format_health_diagnostic,
)
from agent_fox.workspace.worktree import WorkspaceInfo
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Create a git repo with develop branch for smoke tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "develop"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _in_memory_db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with full schema."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-118-SMOKE-1: Pre-run health gate blocks dirty repo
# ---------------------------------------------------------------------------


class TestPreRunHealthGateBlocksDirtyRepo:
    """TS-118-SMOKE-1: Full path from health check through diagnostic output.

    Uses real git repos and real health check (no mocking of
    check_workspace_health, run_git, or file I/O).
    """

    @pytest.mark.asyncio
    async def test_health_gate_detects_untracked_files(self, tmp_path: Path) -> None:
        """Health gate detects untracked files and reports them."""
        repo = _make_repo(tmp_path)

        # Create untracked files
        (repo / "src").mkdir()
        (repo / "src" / "foo.py").write_text("# foo\n")
        (repo / "src" / "bar.py").write_text("# bar\n")

        report = await check_workspace_health(repo)

        assert report.has_issues is True
        assert set(report.untracked_files) == {"src/foo.py", "src/bar.py"}

        # Diagnostic message includes remediation hints
        msg = format_health_diagnostic(report)
        assert "git clean" in msg
        assert "--force-clean" in msg
        assert "src/foo.py" in msg
        assert "src/bar.py" in msg

    @pytest.mark.asyncio
    async def test_force_clean_removes_untracked_files(self, tmp_path: Path) -> None:
        """Force-clean removes all detected untracked files."""
        repo = _make_repo(tmp_path)

        # Create untracked files
        (repo / "a.py").write_text("# a\n")
        (repo / "b.py").write_text("# b\n")
        (repo / "c.py").write_text("# c\n")

        initial = await check_workspace_health(repo)
        assert len(initial.untracked_files) == 3

        result = await force_clean_workspace(repo, initial)
        assert result.has_issues is False

        # All files removed
        for f in initial.untracked_files:
            assert not (repo / f).exists()


# ---------------------------------------------------------------------------
# TS-118-SMOKE-2: Force-clean enables successful harvest
# ---------------------------------------------------------------------------


class TestForceCleanEnablesHarvest:
    """TS-118-SMOKE-2: harvest(force_clean=True) removes divergent files.

    Uses real git repos and real harvest (no mocking of
    _clean_conflicting_untracked or harvest).
    """

    @pytest.mark.asyncio
    async def test_force_clean_harvest_removes_divergent_files(
        self, tmp_path: Path
    ) -> None:
        """Harvest with force_clean=True removes divergent untracked files."""
        repo = _make_repo(tmp_path)

        # Create a feature branch with a new file
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "new_file.py").write_text("# feature version\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add new file"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Switch back to develop and create divergent untracked file
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "new_file.py").write_text("# divergent local version\n")

        workspace = WorkspaceInfo(
            path=repo,
            branch="feature/test",
            spec_name="test",
            task_group=1,
        )

        # With force_clean=True, harvest should succeed
        changed = await harvest(repo, workspace, force_clean=True)
        assert len(changed) > 0

        # File should match the feature branch version (merged)
        content = (repo / "src" / "new_file.py").read_text()
        assert content == "# feature version\n"


# ---------------------------------------------------------------------------
# TS-118-SMOKE-3: Non-retryable error skips escalation ladder
# ---------------------------------------------------------------------------


class TestNonRetryableErrorSkipsEscalation:
    """TS-118-SMOKE-3: Divergent files produce IntegrationError(retryable=False).

    Uses real git repos and real _clean_conflicting_untracked.
    """

    @pytest.mark.asyncio
    async def test_divergent_files_raise_nonretryable_error(
        self, tmp_path: Path
    ) -> None:
        """_clean_conflicting_untracked raises IntegrationError(retryable=False)."""
        repo = _make_repo(tmp_path)

        # Create feature branch with a file
        subprocess.run(
            ["git", "checkout", "-b", "feature/diverge"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "foo.py").write_text("# branch version\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add foo"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Switch to develop, create divergent untracked file
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "foo.py").write_text("# different local version\n")

        with pytest.raises(IntegrationError) as exc_info:
            await _clean_conflicting_untracked(repo, "feature/diverge")

        assert exc_info.value.retryable is False
        msg = str(exc_info.value)
        assert "git clean" in msg
        assert "--force-clean" in msg

    @pytest.mark.asyncio
    async def test_merge_conflict_remains_retryable(self, tmp_path: Path) -> None:
        """Merge conflicts (not divergent files) produce retryable errors."""
        repo = _make_repo(tmp_path)

        # Create conflicting changes on develop and feature branch
        # First modify README on develop
        (repo / "README.md").write_text("# develop changes\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "develop edit"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Create feature branch from before the develop edit
        subprocess.run(
            ["git", "checkout", "-b", "feature/conflict", "HEAD~1"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "README.md").write_text("# feature changes\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feature edit"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Go back to develop for harvest
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        workspace = WorkspaceInfo(
            path=repo,
            branch="feature/conflict",
            spec_name="test",
            task_group=1,
        )

        # Mock only the merge agent to return False (failed to resolve)
        with patch(
            "agent_fox.workspace.harvest.run_merge_agent",
            return_value=False,
        ):
            with pytest.raises(IntegrationError) as exc_info:
                await harvest(repo, workspace)

        # Merge conflict errors default to retryable=True
        assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# TS-118-SMOKE-4: Stale run cleanup on startup
# ---------------------------------------------------------------------------


class TestStaleRunCleanupOnStartup:
    """TS-118-SMOKE-4: Stale runs are detected and transitioned to stalled.

    Uses real DuckDB (in-memory). Does NOT mock cleanup_stale_runs or the
    database connection.
    """

    def test_stale_run_detection_and_cleanup(self) -> None:
        """Stale 'running' runs are transitioned to 'stalled'."""
        conn = _in_memory_db()
        now = datetime.now(UTC).isoformat()

        # Insert a stale run (from a prior process)
        conn.execute(
            """
            INSERT INTO runs (id, plan_content_hash, started_at, status,
                              total_input_tokens, total_output_tokens,
                              total_cost, total_sessions)
            VALUES (?, ?, ?, 'running', 0, 0, 0.0, 0)
            """,
            ["stale_run_1", "hash1", now],
        )

        # Insert a completed run (should not be touched)
        conn.execute(
            """
            INSERT INTO runs (id, plan_content_hash, started_at, completed_at,
                              status, total_input_tokens, total_output_tokens,
                              total_cost, total_sessions)
            VALUES (?, ?, ?, ?, 'completed', 0, 0, 0.0, 0)
            """,
            ["completed_run", "hash2", now, now],
        )

        # Current run id (should be excluded from cleanup)
        current_run_id = "current_run_id"

        count = cleanup_stale_runs(conn, current_run_id)
        assert count == 1

        # Stale run is now 'stalled'
        row = conn.execute(
            "SELECT status FROM runs WHERE id = 'stale_run_1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "stalled"

        # Completed run is unchanged
        row = conn.execute(
            "SELECT status FROM runs WHERE id = 'completed_run'"
        ).fetchone()
        assert row is not None
        assert row[0] == "completed"

        conn.close()

    def test_cleanup_handler_transitions_to_stalled(self) -> None:
        """The cleanup handler transitions the current run to 'stalled'."""
        conn = _in_memory_db()
        now = datetime.now(UTC).isoformat()

        # Insert a running run
        conn.execute(
            """
            INSERT INTO runs (id, plan_content_hash, started_at, status,
                              total_input_tokens, total_output_tokens,
                              total_cost, total_sessions)
            VALUES (?, ?, ?, 'running', 0, 0, 0.0, 0)
            """,
            ["test_run", "hash", now],
        )

        # Invoke cleanup handler
        run_cleanup_handler("test_run", conn)

        row = conn.execute(
            "SELECT status FROM runs WHERE id = 'test_run'"
        ).fetchone()
        assert row is not None
        assert row[0] == "stalled"

        conn.close()
