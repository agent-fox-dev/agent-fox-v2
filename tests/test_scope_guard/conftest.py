"""Shared fixtures for scope_guard tests.

Provides common TaskGroup, SessionResult, and DuckDB setup fixtures.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    SessionResult,
    TaskGroup,
)
from agent_fox.scope_guard.telemetry import init_schema

# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "smoke: marks smoke tests")
    config.addinivalue_line("markers", "property: marks property-based tests")


# ---------------------------------------------------------------------------
# DuckDB fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sg_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Provide a fresh in-memory DuckDB with scope_guard schema."""
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Common TaskGroup fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_writing_tg() -> TaskGroup:
    """A test-writing task group with one deliverable."""
    return TaskGroup(
        number=1,
        spec_number=4,
        archetype="test-writing",
        deliverables=[Deliverable("src/foo.rs", "foo::validate", 1)],
        depends_on=[],
    )


@pytest.fixture
def implementation_tg() -> TaskGroup:
    """An implementation task group with two deliverables."""
    return TaskGroup(
        number=2,
        spec_number=4,
        archetype="implementation",
        deliverables=[
            Deliverable("src/foo.rs", "validate", 2),
            Deliverable("src/bar.rs", "process", 2),
        ],
        depends_on=[1],
    )


# ---------------------------------------------------------------------------
# Common SessionResult fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def noop_session() -> SessionResult:
    """A session with zero commits and normal exit."""
    return SessionResult(
        session_id="sess-noop-1",
        spec_number=4,
        task_group_number=3,
        branch_name="feature/04/3",
        base_branch="develop",
        exit_status="success",
        duration_seconds=106.0,
        cost_dollars=3.50,
        modified_files=[],
        commit_count=0,
    )


# ---------------------------------------------------------------------------
# Temp codebase helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def rust_stub_codebase(tmp_path: Path) -> Path:
    """Create a temp codebase with a Rust stub function."""
    src = tmp_path / "src"
    src.mkdir()
    foo = src / "foo.rs"
    foo.write_text("fn validate() -> bool {\n    todo!()\n}\n")
    return tmp_path


@pytest.fixture
def rust_impl_codebase(tmp_path: Path) -> Path:
    """Create a temp codebase with a fully implemented Rust function."""
    src = tmp_path / "src"
    src.mkdir()
    bar = src / "bar.rs"
    bar.write_text("fn process() -> i32 {\n    let result = compute();\n    result\n}\n")
    return tmp_path


@pytest.fixture
def mixed_codebase(tmp_path: Path) -> Path:
    """Create a temp codebase with one stub and one implemented function."""
    src = tmp_path / "src"
    src.mkdir()
    foo = src / "foo.rs"
    foo.write_text("fn validate() -> bool {\n    todo!()\n}\n")
    bar = src / "bar.rs"
    bar.write_text("fn process() -> i32 {\n    let result = compute();\n    result\n}\n")
    return tmp_path


@pytest.fixture
def python_stub_codebase(tmp_path: Path) -> Path:
    """Create a temp codebase with Python stub and implemented functions."""
    src = tmp_path / "src"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text(
        "def connect():\n    raise NotImplementedError\n\n"
        "def disconnect():\n    socket.close()\n"
    )
    return tmp_path
