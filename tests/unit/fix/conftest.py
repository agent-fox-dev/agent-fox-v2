"""Fixtures for error auto-fix tests.

Provides shared fixtures for check descriptors, failure records, failure
clusters, and mock configuration used across all fix test files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.clusterer import FailureCluster
from agent_fox.fix.collector import FailureRecord
from agent_fox.fix.detector import CheckCategory, CheckDescriptor

# -- Check descriptor fixtures ------------------------------------------------


@pytest.fixture
def check_descriptor_pytest() -> CheckDescriptor:
    """A pytest check descriptor."""
    return CheckDescriptor(
        name="pytest",
        command=["uv", "run", "pytest"],
        category=CheckCategory.TEST,
    )


@pytest.fixture
def ruff_check_descriptor() -> CheckDescriptor:
    """A ruff check descriptor."""
    return CheckDescriptor(
        name="ruff",
        command=["uv", "run", "ruff", "check", "."],
        category=CheckCategory.LINT,
    )


@pytest.fixture
def mypy_check_descriptor() -> CheckDescriptor:
    """A mypy check descriptor."""
    return CheckDescriptor(
        name="mypy",
        command=["uv", "run", "mypy", "."],
        category=CheckCategory.TYPE,
    )


# -- Failure record fixtures --------------------------------------------------


def make_failure_record(
    check: CheckDescriptor | None = None,
    output: str = "FAILED test_example.py::test_one",
    exit_code: int = 1,
) -> FailureRecord:
    """Create a FailureRecord with sensible defaults."""
    if check is None:
        check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
    return FailureRecord(check=check, output=output, exit_code=exit_code)


@pytest.fixture
def sample_failure_record(check_descriptor_pytest: CheckDescriptor) -> FailureRecord:
    """A sample failure record from pytest."""
    return make_failure_record(check=check_descriptor_pytest)


@pytest.fixture
def ruff_failure_record(ruff_check_descriptor: CheckDescriptor) -> FailureRecord:
    """A sample failure record from ruff."""
    return make_failure_record(
        check=ruff_check_descriptor,
        output="error: unused import `os`",
        exit_code=1,
    )


# -- Failure cluster fixtures -------------------------------------------------


@pytest.fixture
def sample_failure_cluster(
    sample_failure_record: FailureRecord,
) -> FailureCluster:
    """A sample failure cluster with one pytest failure."""
    return FailureCluster(
        label="Missing return types",
        failures=[sample_failure_record],
        suggested_approach="Add return type annotations to affected functions.",
    )


# -- Config fixtures -----------------------------------------------------------


@pytest.fixture
def mock_config() -> AgentFoxConfig:
    """An AgentFoxConfig with defaults for testing."""
    return AgentFoxConfig()


# -- Temp project helpers ------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A temporary project directory for detector tests."""
    return tmp_path
