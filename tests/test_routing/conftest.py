"""Shared fixtures for adaptive model routing tests.

Provides temp spec directories, in-memory DuckDB instances, and
helper factories used across test modules.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import duckdb
import pytest


@pytest.fixture
def spec_dir(tmp_path: Path) -> Path:
    """Create a temp spec directory with realistic spec content.

    Contains:
    - tasks.md with 4 subtasks across 2 task groups
    - requirements.md with 2 edge cases and ~150 words
    - design.md referencing 2 dependencies
    - test_spec.md with property test references
    """
    sd = tmp_path / ".specs" / "test_spec"
    sd.mkdir(parents=True)

    tasks_md = textwrap.dedent("""\
    # Tasks

    ## Task Group 1

    - [ ] 1.1 First subtask
    - [ ] 1.2 Second subtask

    ## Task Group 2

    - [ ] 2.1 Implement feature A
    - [ ] 2.2 Implement feature B
    - [ ] 2.3 Write tests for feature A
    - [ ] 2.4 Write tests for feature B
    """)
    (sd / "tasks.md").write_text(tasks_md)

    # ~150 words with 2 edge cases
    requirements_md = textwrap.dedent("""\
    # Requirements

    ## Requirement 1

    Some requirement text here describing the feature that needs to be
    implemented. This is a detailed description of what the system should
    do when certain conditions are met. The system shall validate input
    and produce correct output. Additional context about the requirement
    and how it relates to other parts of the system. More words to reach
    the target word count for testing purposes. The implementation should
    handle various scenarios gracefully and provide meaningful feedback
    to the user when errors occur. Testing should cover both happy path
    and error scenarios to ensure robustness of the implementation.

    ### Edge Cases

    1. [REQ-1.E1] IF input is empty THEN return default.
    2. [REQ-1.E2] IF connection fails THEN retry with backoff.

    ## Requirement 2

    Another requirement with more details about expected behavior
    and acceptance criteria for the feature implementation. This
    requirement covers the data persistence layer and ensures that
    all records are properly stored and retrievable. Additional
    words here to pad the document for word count testing purposes.
    """)
    (sd / "requirements.md").write_text(requirements_md)

    design_md = textwrap.dedent("""\
    # Design

    ## Dependencies

    - **duckdb** - embedded database for persistence
    - **scikit-learn** - statistical model training

    ## Architecture

    Component A talks to Component B through an interface.
    """)
    (sd / "design.md").write_text(design_md)

    test_spec_md = textwrap.dedent("""\
    # Test Specification

    ## Property Test Cases

    ### TS-P1: Some Property Test

    **Type:** property
    **Description:** Verify invariant holds.
    """)
    (sd / "test_spec.md").write_text(test_spec_md)

    return sd


@pytest.fixture
def empty_spec_dir(tmp_path: Path) -> Path:
    """Create an empty spec directory (no files)."""
    sd = tmp_path / ".specs" / "empty_spec"
    sd.mkdir(parents=True)
    return sd


@pytest.fixture
def routing_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with routing tables.

    Creates both complexity_assessments and execution_outcomes tables
    matching the schema from design.md.
    """
    conn = duckdb.connect(":memory:")

    # Bootstrap schema_version table (mirrors KnowledgeDB.open())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create the routing tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complexity_assessments (
            id              VARCHAR PRIMARY KEY,
            node_id         VARCHAR NOT NULL,
            spec_name       VARCHAR NOT NULL,
            task_group      INTEGER NOT NULL,
            predicted_tier  VARCHAR NOT NULL,
            confidence      FLOAT NOT NULL,
            assessment_method VARCHAR NOT NULL,
            feature_vector  JSON NOT NULL,
            tier_ceiling    VARCHAR NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_outcomes (
            id                  VARCHAR PRIMARY KEY,
            assessment_id       VARCHAR NOT NULL REFERENCES complexity_assessments(id),
            actual_tier         VARCHAR NOT NULL,
            total_tokens        INTEGER NOT NULL,
            total_cost          FLOAT NOT NULL,
            duration_ms         INTEGER NOT NULL,
            attempt_count       INTEGER NOT NULL,
            escalation_count    INTEGER NOT NULL,
            outcome             VARCHAR NOT NULL,
            files_touched_count INTEGER NOT NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
    """)

    # Also create the base facts table so migration tests work
    conn.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id          VARCHAR PRIMARY KEY,
            content     TEXT NOT NULL,
            spec_name   TEXT,
            source      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    yield conn
    conn.close()


@pytest.fixture
def minimal_config_toml(tmp_path: Path) -> Path:
    """Create a minimal config.toml with no [routing] section."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [orchestrator]
    parallel = 1
    """)
    )
    return p


@pytest.fixture
def routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with [routing] section."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [orchestrator]
    parallel = 1

    [routing]
    retries_before_escalation = 2
    training_threshold = 30
    accuracy_threshold = 0.80
    retrain_interval = 15
    """)
    )
    return p


@pytest.fixture
def extreme_routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with out-of-range [routing] values."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [routing]
    retries_before_escalation = 10
    training_threshold = 2
    accuracy_threshold = 0.1
    retrain_interval = 200
    """)
    )
    return p


@pytest.fixture
def bad_type_routing_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with invalid type in [routing]."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [routing]
    retries_before_escalation = "high"
    """)
    )
    return p


@pytest.fixture
def archetype_ceiling_config_toml(tmp_path: Path) -> Path:
    """Create a config.toml with archetype model override."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""\
    [archetypes]
    models = { coder = "STANDARD" }
    """)
    )
    return p
