"""Fixtures for spec discovery and parser tests.

Creates temporary .specs/ directories with sample tasks.md and prd.md files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# -- Sample tasks.md content ------------------------------------------------

TASKS_MD_STANDARD = """\
# Implementation Plan: Test Spec

## Tasks

- [ ] 1. Write failing tests
  - [ ] 1.1 Create test fixtures
  - [ ] 1.2 Write unit tests
  - [ ] 1.3 Write integration tests

- [ ] 2. Implement core module
  - [ ] 2.1 Create data models
  - [ ] 2.2 Add validation
"""

TASKS_MD_WITH_OPTIONAL = """\
# Implementation Plan: Test Spec

## Tasks

- [ ] 1. Write failing tests
  - [ ] 1.1 Create test fixtures

- [ ] 2. Implement core module
  - [ ] 2.1 Create data models

- [ ] * 3. Polish and cleanup
  - [ ] 3.1 Add docstrings
  - [ ] 3.2 Refactor utilities

- [ ] 4. Final integration
"""

TASKS_MD_NON_CONTIGUOUS = """\
# Implementation Plan: Test Spec

## Tasks

- [ ] 1. First task
  - [ ] 1.1 Subtask A

- [ ] 3. Third task
  - [ ] 3.1 Subtask B

- [ ] 5. Fifth task
  - [ ] 5.1 Subtask C
"""

TASKS_MD_EMPTY = """\
# Tasks

No items here.
"""

TASKS_MD_COMPLETED = """\
# Implementation Plan: Test Spec

## Tasks

- [x] 1. Completed task
  - [x] 1.1 Done subtask

- [ ] 2. Pending task
"""

# -- Sample prd.md content --------------------------------------------------

PRD_MD_WITH_DEPS = """\
# Product Requirements: Beta Spec

## Dependencies

| This Spec | Depends On | What It Uses |
|-----------|-----------|--------------|
| 02_beta | 01_alpha | Core foundation types |
"""

PRD_MD_NO_DEPS = """\
# Product Requirements: Alpha Spec

## Overview

This is the first specification with no dependencies.
"""

PRD_MD_ALT_FORMAT = """\
# PRD: CLI Banner Enhancement

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 4 | 1 | Imports CLI framework, theme system |
| 03_session | 3 | 2 | Uses session context for banner data |
"""

PRD_MD_ALT_FORMAT_SINGLE = """\
# PRD: Init Settings

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 3 | 1 | Extends the init command implemented in group 3 |
"""


# -- Fixture: specs directory with multiple specs, all with tasks.md --------

@pytest.fixture
def specs_dir_sorted(tmp_path: Path) -> Path:
    """Create .specs/ with 03_foo, 01_bar, 02_baz, each with tasks.md.

    Used by TS-02-1 (sorted discovery).
    """
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir()

    for name in ["03_foo", "01_bar", "02_baz"]:
        spec = specs_dir / name
        spec.mkdir()
        (spec / "tasks.md").write_text(TASKS_MD_STANDARD)

    return specs_dir


@pytest.fixture
def specs_dir_two_specs(tmp_path: Path) -> Path:
    """Create .specs/ with 01_alpha and 02_beta, each with tasks.md.

    Used by TS-02-2 (filter) and TS-02-E2 (filter miss).
    """
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir()

    for name in ["01_alpha", "02_beta"]:
        spec = specs_dir / name
        spec.mkdir()
        (spec / "tasks.md").write_text(TASKS_MD_STANDARD)

    return specs_dir


@pytest.fixture
def specs_dir_missing_tasks(tmp_path: Path) -> Path:
    """Create .specs/ with 01_alpha (no tasks.md) and 02_beta (with tasks.md).

    Used by TS-02-E3 (spec folder without tasks.md).
    """
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir()

    # 01_alpha: no tasks.md
    (specs_dir / "01_alpha").mkdir()

    # 02_beta: has tasks.md
    beta = specs_dir / "02_beta"
    beta.mkdir()
    (beta / "tasks.md").write_text(TASKS_MD_STANDARD)

    return specs_dir


# -- Fixture: tasks.md files for parser tests --------------------------------

@pytest.fixture
def tasks_md_standard(tmp_path: Path) -> Path:
    """Create a standard tasks.md with 2 groups and subtasks.

    Used by TS-02-3.
    """
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(TASKS_MD_STANDARD)
    return tasks_path


@pytest.fixture
def tasks_md_with_optional(tmp_path: Path) -> Path:
    """Create a tasks.md with an optional marker (* on group 3).

    Used by TS-02-4.
    """
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(TASKS_MD_WITH_OPTIONAL)
    return tasks_path


@pytest.fixture
def tasks_md_non_contiguous(tmp_path: Path) -> Path:
    """Create a tasks.md with non-contiguous group numbers (1, 3, 5).

    Used by TS-02-E8.
    """
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(TASKS_MD_NON_CONTIGUOUS)
    return tasks_path


@pytest.fixture
def tasks_md_empty(tmp_path: Path) -> Path:
    """Create a tasks.md with no parseable task groups.

    Used by TS-02-E7.
    """
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(TASKS_MD_EMPTY)
    return tasks_path


@pytest.fixture
def prd_md_standard_deps(tmp_path: Path) -> Path:
    """Create a prd.md with standard dependency table format."""
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(PRD_MD_WITH_DEPS)
    return prd_path


@pytest.fixture
def prd_md_alt_format(tmp_path: Path) -> Path:
    """Create a prd.md with alternative dependency table format."""
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(PRD_MD_ALT_FORMAT)
    return prd_path


@pytest.fixture
def prd_md_alt_format_single(tmp_path: Path) -> Path:
    """Create a prd.md with alternative format, single dependency."""
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(PRD_MD_ALT_FORMAT_SINGLE)
    return prd_path


@pytest.fixture
def prd_md_no_deps(tmp_path: Path) -> Path:
    """Create a prd.md with no dependency table."""
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(PRD_MD_NO_DEPS)
    return prd_path
