"""Fixtures for error auto-fix tests.

Provides shared fixtures for check descriptors, failure records, failure
clusters, and mock configuration used across all fix test files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import AnalyzerResult, Improvement
from agent_fox.fix.checks import CheckCategory, CheckDescriptor, FailureRecord
from agent_fox.fix.clusterer import FailureCluster
from agent_fox.fix.improve import ImproveResult, ImproveTermination

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
def sample_failure_record(
    check_descriptor_pytest: CheckDescriptor,
) -> FailureRecord:
    """A sample failure record from pytest."""
    return make_failure_record(check=check_descriptor_pytest)


@pytest.fixture
def ruff_failure_record(
    ruff_check_descriptor: CheckDescriptor,
) -> FailureRecord:
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
        suggested_approach="Add return type annotations.",
    )


# -- Config fixtures -----------------------------------------------------------


@pytest.fixture
def mock_config() -> AgentFoxConfig:
    """An AgentFoxConfig with defaults for testing."""
    return AgentFoxConfig()


# -- Auto-improve fixtures -----------------------------------------------------


def make_improvement(
    id: str = "IMP-1",
    tier: str = "quick_win",
    title: str = "Remove dead import",
    description: str = "Remove unused import os from foo.py",
    files: list[str] | None = None,
    impact: str = "low",
    confidence: float = 0.9,
) -> Improvement:
    """Create an Improvement with sensible defaults."""
    return Improvement(
        id=id,
        tier=tier,
        title=title,
        description=description,
        files=files or ["foo.py"],
        impact=impact,
        confidence=confidence,
    )


@pytest.fixture
def sample_improvement() -> Improvement:
    """A sample Improvement dataclass with defaults."""
    return make_improvement()


@pytest.fixture
def sample_analyzer_result() -> AnalyzerResult:
    """An AnalyzerResult with 2 improvements."""
    return AnalyzerResult(
        improvements=[
            make_improvement(id="IMP-1", tier="quick_win", confidence=0.9),
            make_improvement(
                id="IMP-2",
                tier="structural",
                title="Consolidate validators",
                description="Merge a.py and b.py validators",
                files=["a.py", "b.py"],
                impact="medium",
                confidence=0.6,
            ),
        ],
        summary="Found 2 improvements.",
        diminishing_returns=False,
        raw_response="{}",
    )


@pytest.fixture
def sample_improve_result() -> ImproveResult:
    """An ImproveResult with defaults for testing."""
    return ImproveResult(
        passes_completed=2,
        max_passes=3,
        total_improvements=5,
        improvements_by_tier={"quick_win": 3, "structural": 2},
        verifier_pass_count=2,
        verifier_fail_count=0,
        sessions_consumed=6,
        total_cost=2.50,
        termination_reason=ImproveTermination.CONVERGED,
        pass_results=[],
    )


@pytest.fixture
def valid_analyzer_json() -> str:
    """Valid JSON string for analyzer response."""
    return json.dumps(
        {
            "improvements": [
                {
                    "id": "IMP-1",
                    "tier": "quick_win",
                    "title": "Remove dead import",
                    "description": "Remove unused import",
                    "files": ["foo.py"],
                    "impact": "low",
                    "confidence": "high",
                },
                {
                    "id": "IMP-2",
                    "tier": "structural",
                    "title": "Consolidate validators",
                    "description": "Merge validators",
                    "files": ["a.py", "b.py"],
                    "impact": "medium",
                    "confidence": "medium",
                },
            ],
            "summary": "Found 2 improvements.",
            "diminishing_returns": False,
        }
    )


@pytest.fixture
def valid_verifier_json() -> str:
    """Valid JSON string for verifier verdict (PASS)."""
    return json.dumps(
        {
            "quality_gates": "PASS",
            "improvement_valid": True,
            "verdict": "PASS",
            "evidence": "All tests pass. 3 files simplified.",
        }
    )


@pytest.fixture
def mock_improve_session_runner():
    """Async callable returning (cost, status)."""

    async def _runner(
        system_prompt: str,
        task_prompt: str,
        model_tier: str,
    ) -> tuple[float, str]:
        return (0.10, "completed")

    return _runner


# -- Temp project helpers ------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A temporary project directory for detector tests."""
    return tmp_path
