"""Shared fixtures for agent-fox test suite."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner
from hypothesis import settings

# Disable Hypothesis deadline globally — property tests that spin up DuckDB or
# do I/O regularly exceed the default 200 ms on the first example (cold-start),
# then pass comfortably on reruns, producing flaky DeadlineExceeded failures.
settings.register_profile("ci", deadline=None)
settings.load_profile("ci")

from agent_fox.knowledge.db import KnowledgeDB  # noqa: E402
from agent_fox.knowledge.migrations import apply_pending_migrations  # noqa: E402
from tests.unit.knowledge.conftest import SCHEMA_DDL  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_agent_fox_logger() -> Generator[None, None, None]:
    """Reset the agent_fox logger after each test.

    Tests that invoke the CLI (e.g. with --quiet) call setup_logging()
    which sets the agent_fox logger level and adds handlers. Without
    cleanup, this state leaks to subsequent tests in the same xdist
    worker, causing caplog-based assertions to fail because WARNING-level
    records are filtered out by a stale ERROR-level logger.
    """
    yield
    agent_logger = logging.getLogger("agent_fox")
    agent_logger.setLevel(logging.NOTSET)
    agent_logger.handlers.clear()


@pytest.fixture
def knowledge_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Provide a fresh in-memory DuckDB with all migrations applied.

    Creates a new in-memory database per test (function-scoped) with the
    full schema and all migrations applied. No cross-test contamination.

    Requirements: 38-REQ-5.1, 38-REQ-5.2
    """
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def knowledge_db(
    knowledge_conn: duckdb.DuckDBPyConnection,
) -> Generator[KnowledgeDB, None, None]:
    """Provide a KnowledgeDB wrapper around in-memory DuckDB.

    Requirements: 38-REQ-5.1, 38-REQ-5.2
    """
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = knowledge_conn
    yield db


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for integration tests.

    Returns the path to the temporary repo directory with git initialized
    and an initial commit so branches can be created.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
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

    # Create initial commit so branches can be created
    readme = repo / "README.md"
    readme.write_text("# Test repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Change to repo directory for the test
    original_dir = os.getcwd()
    os.chdir(repo)
    yield repo
    os.chdir(original_dir)
