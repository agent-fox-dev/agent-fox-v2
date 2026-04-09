"""Scan post-session file diffs to verify test-writing sessions produced only stubs.

Requirements: 87-REQ-1.2, 87-REQ-1.3, 87-REQ-1.E1, 87-REQ-1.E2, 87-REQ-1.E3
"""

from __future__ import annotations

from agent_fox.scope_guard.models import FileChange, StubValidationResult, TaskGroup


def validate_stubs(
    modified_files: list[FileChange], task_group: TaskGroup
) -> StubValidationResult:
    """Validate that all non-test functions in modified files are stubs."""
    raise NotImplementedError
