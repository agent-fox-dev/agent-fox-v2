"""Fixtures for workspace tests: git repos with develop branch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_worktree_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with a develop branch.

    Sets up a repo suitable for worktree and harvester tests:
    - Initialized with git init
    - Has user.email and user.name config
    - Has an initial commit on the default branch
    - Has a 'develop' branch created from the initial commit
    - Develop is checked out

    Returns the path to the repo directory.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init"], cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )

    # Initial commit
    readme = repo / "README.md"
    readme.write_text("# Test repo\n")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo, check=True, capture_output=True,
    )

    # Create and checkout develop branch
    subprocess.run(
        ["git", "checkout", "-b", "develop"],
        cwd=repo, check=True, capture_output=True,
    )

    return repo


def add_commit_to_branch(
    repo: Path,
    filename: str,
    content: str = "content\n",
    message: str | None = None,
) -> str:
    """Add a file and commit it on the current branch.

    Returns the commit SHA.
    """
    filepath = repo / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    subprocess.run(
        ["git", "add", filename], cwd=repo, check=True, capture_output=True,
    )
    commit_msg = message or f"add {filename}"
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=repo, check=True, capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def get_branch_tip(repo: Path, branch: str) -> str:
    """Get the commit SHA at the tip of a branch."""
    result = subprocess.run(
        ["git", "rev-parse", branch],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def list_branches(repo: Path) -> list[str]:
    """List all local branch names in the repo."""
    result = subprocess.run(
        ["git", "branch", "--list", "--format=%(refname:short)"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
