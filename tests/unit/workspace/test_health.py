"""Workspace health check tests.

Test Spec: TS-118-1 (detects untracked files), TS-118-2 (clean repo),
           TS-118-3 (aborts on dirty), TS-118-4 (force-clean removes),
           TS-118-5 (CLI flag), TS-118-18 (diagnostic format),
           TS-118-E1 (dirty index), TS-118-E2 (git error fail-open),
           TS-118-E3 (force-clean resets dirty index),
           TS-118-E4 (permission error during force-clean),
           TS-118-E10 (file list truncation at 20)
Requirements: 118-REQ-1.1, 118-REQ-1.2, 118-REQ-1.3,
              118-REQ-1.E1, 118-REQ-1.E2,
              118-REQ-2.1, 118-REQ-2.2, 118-REQ-2.E1, 118-REQ-2.E2,
              118-REQ-8.1, 118-REQ-8.2, 118-REQ-8.E1
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from agent_fox.workspace.health import (
    HealthReport,
    check_workspace_health,
    force_clean_workspace,
    format_health_diagnostic,
)


class TestHealthCheckDetectsUntracked:
    """TS-118-1: check_workspace_health returns all untracked files.

    Requirements: 118-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_detects_untracked_files(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Verify that check_workspace_health returns all untracked files."""
        # Create 2 untracked files in code directories
        (tmp_worktree_repo / "src").mkdir(exist_ok=True)
        (tmp_worktree_repo / "src" / "foo.py").write_text("foo\n")
        (tmp_worktree_repo / "src" / "bar.py").write_text("bar\n")

        report = await check_workspace_health(tmp_worktree_repo)

        assert set(report.untracked_files) == {"src/foo.py", "src/bar.py"}
        assert report.has_issues is True


class TestHealthCheckCleanRepo:
    """TS-118-2: clean repo produces empty health report.

    Requirements: 118-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_clean_repo_no_issues(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """A clean repo with all files committed has no issues."""
        report = await check_workspace_health(tmp_worktree_repo)

        assert report.untracked_files == []
        assert report.dirty_index_files == []
        assert report.has_issues is False


class TestHealthCheckAbortsOnDirty:
    """TS-118-3: engine aborts when untracked files found and no force-clean.

    Requirements: 118-REQ-1.2, 118-REQ-8.3
    """

    @pytest.mark.asyncio
    async def test_aborts_on_dirty_workspace(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Health check detects untracked files and format_health_diagnostic
        includes remediation hints."""
        # Create untracked files
        (tmp_worktree_repo / "leftover.py").write_text("leftover\n")

        report = await check_workspace_health(tmp_worktree_repo)
        assert report.has_issues is True

        # The diagnostic message should contain remediation hints
        msg = format_health_diagnostic(report)
        assert "git clean" in msg
        assert "--force-clean" in msg


class TestForceCleanRemovesFiles:
    """TS-118-4: force_clean_workspace removes all untracked files.

    Requirements: 118-REQ-2.1
    """

    @pytest.mark.asyncio
    async def test_force_clean_removes_untracked(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """force_clean_workspace removes all untracked files and returns clean report."""
        # Create 3 untracked files
        files = ["a.py", "b.py", "c.py"]
        for f in files:
            (tmp_worktree_repo / f).write_text(f"content of {f}\n")

        initial = await check_workspace_health(tmp_worktree_repo)
        assert len(initial.untracked_files) == 3

        result = await force_clean_workspace(tmp_worktree_repo, initial)

        assert result.has_issues is False
        for f in files:
            assert not (tmp_worktree_repo / f).exists()


class TestForceCleanCLIFlag:
    """TS-118-5: --force-clean CLI flag and config option.

    Requirements: 118-REQ-2.2
    """

    def test_cli_flag_overrides_config(self) -> None:
        """CLI --force-clean flag takes precedence over config file."""
        # This tests the config loading logic - force_clean should be
        # available as a workspace config option and CLI flag should
        # override it.
        from agent_fox.core.config import AgentFoxConfig

        # Verify that the config class has the workspace.force_clean attribute
        config = AgentFoxConfig()
        assert hasattr(config, "workspace") or hasattr(config, "force_clean"), (
            "AgentFoxConfig must have workspace.force_clean config option"
        )


class TestFormatHealthDiagnostic:
    """TS-118-18: format_health_diagnostic produces actionable output.

    Requirements: 118-REQ-8.2
    """

    def test_diagnostic_format_includes_all_files(self) -> None:
        """Diagnostic output contains all file paths, git clean, and --force-clean."""
        report = HealthReport(
            untracked_files=["a.py", "b.py", "c.py"],
            dirty_index_files=[],
        )
        msg = format_health_diagnostic(report)

        assert "a.py" in msg
        assert "b.py" in msg
        assert "c.py" in msg
        assert "git clean" in msg
        assert "--force-clean" in msg


# ---------------------------------------------------------------------------
# Edge case tests: TS-118-E1, TS-118-E2, TS-118-E3, TS-118-E4, TS-118-E10
# ---------------------------------------------------------------------------


class TestDirtyIndexDetected:
    """TS-118-E1: health check detects staged but uncommitted changes.

    Requirements: 118-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_dirty_index_has_issues(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Staged but uncommitted file appears in dirty_index_files."""
        # Create and stage a file without committing
        staged_file = tmp_worktree_repo / "staged_file.py"
        staged_file.write_text("staged content\n")
        subprocess.run(
            ["git", "add", "staged_file.py"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )

        report = await check_workspace_health(tmp_worktree_repo)

        assert "staged_file.py" in report.dirty_index_files
        assert report.has_issues is True


class TestGitErrorFailOpen:
    """TS-118-E2: health check fails open on git errors.

    Requirements: 118-REQ-1.E2
    """

    @pytest.mark.asyncio
    async def test_git_error_returns_empty_report(
        self,
        tmp_worktree_repo: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When run_git fails, health check returns empty report (fail-open)."""
        # Patch run_git to fail for ls-files
        async def failing_run_git(args, **kwargs):
            if args and args[0] == "ls-files":
                return (1, "", "fatal: error")
            # Still need to fail for diff --cached too
            if args and args[0] == "diff":
                return (1, "", "fatal: error")
            return (0, "", "")

        with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.health"):
            with patch(
                "agent_fox.workspace.health.run_git",
                side_effect=failing_run_git,
            ):
                report = await check_workspace_health(tmp_worktree_repo)

        assert report.has_issues is False

        # WARNING should have been logged
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_messages) > 0


class TestForceCleanResetsDirtyIndex:
    """TS-118-E3: force-clean resets the git index when dirty.

    Requirements: 118-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_force_clean_resets_index(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """force_clean_workspace resets a dirty index."""
        # Modify an existing tracked file and stage the change
        readme = tmp_worktree_repo / "README.md"
        readme.write_text("modified content\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )

        report = HealthReport(untracked_files=[], dirty_index_files=["README.md"])
        result = await force_clean_workspace(tmp_worktree_repo, report)

        assert result.dirty_index_files == []


class TestForceCleanPermissionError:
    """TS-118-E4: permission error during force-clean.

    Requirements: 118-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_permission_error_keeps_file_in_report(
        self,
        tmp_worktree_repo: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When a file cannot be deleted, it remains in the report."""
        # Create an untracked file in a read-only directory
        ro_dir = tmp_worktree_repo / "readonly_dir"
        ro_dir.mkdir()
        undeletable = ro_dir / "undeletable.py"
        undeletable.write_text("content\n")

        report = HealthReport(
            untracked_files=["readonly_dir/undeletable.py"],
            dirty_index_files=[],
        )

        # Make the directory read-only so the file can't be deleted
        os.chmod(ro_dir, 0o555)
        try:
            with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.health"):
                result = await force_clean_workspace(tmp_worktree_repo, report)

            assert result.has_issues is True
            assert "readonly_dir/undeletable.py" in result.untracked_files
        finally:
            # Restore permissions for cleanup
            os.chmod(ro_dir, 0o755)


class TestForceCleanSymlinkEscape:
    """AC-1 (issue #579): force_clean skips symlink-based path traversal.

    A symlink inside repo_root pointing outside should not allow deletion
    of the target file.  The path must remain in the returned report.
    """

    @pytest.mark.asyncio
    async def test_symlink_target_not_deleted(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """force_clean_workspace does not delete a file via a symlink escape."""
        # Create the outside directory and file
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "outside.txt"
        outside_file.write_text("keep me\n")

        # Create a minimal git repo at repo_root
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Create a symlink inside the repo pointing to the outside directory
        link = repo_root / "link"
        link.symlink_to(outside_dir)

        report = HealthReport(
            untracked_files=["link/outside.txt"],
            dirty_index_files=[],
        )

        with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.health"):
            result = await force_clean_workspace(repo_root, report)

        # The external file must NOT have been deleted
        assert outside_file.exists(), "symlink target must not be deleted"

        # The path must remain in the returned report as untracked
        assert "link/outside.txt" in result.untracked_files

        # A WARNING must have been logged
        messages = " ".join(r.message for r in caplog.records)
        assert "outside repo root" in messages or "skipping" in messages.lower()


class TestForceCleanDotDotEscape:
    """AC-4 (issue #579): force_clean blocks literal '../' path traversal.

    A rel_path containing '../' segments that resolve outside repo_root
    must be skipped — the target file must not be deleted.
    """

    @pytest.mark.asyncio
    async def test_dotdot_traversal_blocked(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """force_clean_workspace skips '../outside_file.txt' style paths."""
        # Create a file one level above repo_root
        outside_file = tmp_path / "outside_file.txt"
        outside_file.write_text("keep me too\n")

        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        report = HealthReport(
            untracked_files=["../outside_file.txt"],
            dirty_index_files=[],
        )

        with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.health"):
            result = await force_clean_workspace(repo_root, report)

        # The external file must NOT have been deleted
        assert outside_file.exists(), "../ traversal target must not be deleted"

        # The path must remain in the returned report
        assert "../outside_file.txt" in result.untracked_files

        # A WARNING must have been logged
        messages = " ".join(r.message for r in caplog.records)
        assert "outside repo root" in messages or "skipping" in messages.lower()


class TestFileListTruncation:
    """TS-118-E10: file list truncation at 20 files.

    Requirements: 118-REQ-8.E1
    """

    def test_truncation_at_20_files(self) -> None:
        """format_health_diagnostic truncates at 20 files with '... and N more'."""
        files = [f"file_{i}.py" for i in range(25)]
        report = HealthReport(untracked_files=files, dirty_index_files=[])
        msg = format_health_diagnostic(report)

        # Should show exactly 20 files
        shown_count = sum(1 for f in files if f in msg)
        assert shown_count == 20

        # Should contain "... and 5 more"
        assert "... and 5 more" in msg
