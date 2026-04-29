"""Property tests for workspace health checks and force-clean.

Test Spec: TS-118-P1 (health check completeness),
           TS-118-P2 (force-clean safety),
           TS-118-P6 (error message completeness),
           TS-118-P7 (pre-session monotonicity)
Properties: Property 1, Property 2, Property 6, Property 7 from design.md
Requirements: 118-REQ-1.1, 118-REQ-2.1, 118-REQ-4.1, 118-REQ-4.3,
              118-REQ-8.1, 118-REQ-8.2
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from agent_fox.workspace.health import (
    HealthReport,
    check_workspace_health,
    force_clean_workspace,
    format_health_diagnostic,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid file paths: alphanumeric + /. patterns, no leading dots (git-ignored)
_file_name_strategy = st.from_regex(
    r"[a-z][a-z0-9_]{0,10}\.py",
    fullmatch=True,
)

_file_path_strategy = st.one_of(
    _file_name_strategy,
    st.builds(
        lambda d, f: f"{d}/{f}",
        st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True),
        _file_name_strategy,
    ),
)

# Sets of unique file paths
_file_set_strategy = st.lists(
    _file_path_strategy,
    min_size=0,
    max_size=20,
    unique=True,
)


def _setup_clean_repo(tmp_dir: Path, committed_files: list[str]) -> Path:
    """Create a git repo with only committed files."""
    repo = tmp_dir / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )

    # Create initial commit
    readme = repo / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo, check=True, capture_output=True,
    )

    # Add committed files
    for f in committed_files:
        p = repo / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"content of {f}\n")
    if committed_files:
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add files"],
            cwd=repo, check=True, capture_output=True,
        )

    return repo


# ---------------------------------------------------------------------------
# TS-118-P1: Health Check Completeness
# Property 1: For any set of untracked files, the health check reports all
# ---------------------------------------------------------------------------


class TestHealthCheckCompleteness:
    """TS-118-P1: health check reports all untracked files.

    Property 1 from design.md.
    Requirements: 118-REQ-1.1
    """

    @pytest.mark.asyncio
    @pytest.mark.property
    @given(
        files=st.lists(
            _file_name_strategy,
            min_size=0,
            max_size=10,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=30000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_completeness(
        self,
        files: list[str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """For any set of untracked files, check_workspace_health reports all."""
        tmp_dir = tmp_path_factory.mktemp("completeness")
        repo = _setup_clean_repo(tmp_dir, [])

        # Create untracked files
        for f in files:
            p = repo / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"content of {f}\n")

        report = await check_workspace_health(repo)
        assert set(report.untracked_files) == set(files)


# ---------------------------------------------------------------------------
# TS-118-P2: Force-Clean Safety
# Property 2: Force-clean only removes files listed in the health report
# ---------------------------------------------------------------------------


class TestForceCleanSafety:
    """TS-118-P2: force-clean only removes files listed in the report.

    Property 2 from design.md.
    Requirements: 118-REQ-2.1
    """

    @pytest.mark.asyncio
    @pytest.mark.property
    @given(
        untracked=st.lists(
            _file_name_strategy,
            min_size=1,
            max_size=5,
            unique=True,
        ),
        tracked=st.lists(
            st.from_regex(r"tracked_[a-z0-9]{1,5}\.py", fullmatch=True),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=30000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_safety(
        self,
        untracked: list[str],
        tracked: list[str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """After force-clean, all tracked files still exist. Only files from
        the report are removed."""
        tmp_dir = tmp_path_factory.mktemp("safety")
        repo = _setup_clean_repo(tmp_dir, tracked)

        # Create untracked files
        for f in untracked:
            (repo / f).write_text(f"untracked {f}\n")

        report = await check_workspace_health(repo)
        await force_clean_workspace(repo, report)

        # All tracked files must still exist
        for f in tracked:
            assert (repo / f).exists(), f"Tracked file {f} was wrongly deleted"

        # All untracked files must be gone
        for f in untracked:
            assert not (repo / f).exists(), f"Untracked file {f} was not removed"


# ---------------------------------------------------------------------------
# TS-118-P6: Error Message Completeness
# Property 6: Error messages always contain remediation hints
# ---------------------------------------------------------------------------


class TestErrorMessageCompleteness:
    """TS-118-P6: error messages always contain remediation hints.

    Property 6 from design.md.
    Requirements: 118-REQ-8.1, 118-REQ-8.2
    """

    @pytest.mark.property
    @given(
        files=st.lists(
            _file_name_strategy,
            min_size=1,
            max_size=30,
            unique=True,
        ),
    )
    @settings(max_examples=20, deadline=5000)
    def test_message_completeness(self, files: list[str]) -> None:
        """For any non-empty HealthReport, formatted message contains
        'git clean' and '--force-clean'."""
        report = HealthReport(untracked_files=files, dirty_index_files=[])
        msg = format_health_diagnostic(report)
        assert "git clean" in msg
        assert "--force-clean" in msg


# ---------------------------------------------------------------------------
# TS-118-P7: Pre-Session Monotonicity
# Property 7: A clean health check remains clean on re-check
# ---------------------------------------------------------------------------


class TestPreSessionMonotonicity:
    """TS-118-P7: a clean health check remains clean on re-check.

    Property 7 from design.md.
    Requirements: 118-REQ-4.1, 118-REQ-4.3
    """

    @pytest.mark.asyncio
    @pytest.mark.property
    @given(
        committed_files=st.lists(
            st.from_regex(r"committed_[a-z0-9]{1,5}\.py", fullmatch=True),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=30000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_monotonicity(
        self,
        committed_files: list[str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Two consecutive calls to check_workspace_health on a clean repo
        both return has_issues=False."""
        tmp_dir = tmp_path_factory.mktemp("monotonicity")
        repo = _setup_clean_repo(tmp_dir, committed_files)

        r1 = await check_workspace_health(repo)
        r2 = await check_workspace_health(repo)

        assert r1.has_issues is False
        assert r2.has_issues is False
