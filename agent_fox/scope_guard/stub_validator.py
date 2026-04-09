"""Scan post-session file diffs to verify test-writing sessions produced only stubs.

Requirements: 87-REQ-1.2, 87-REQ-1.3, 87-REQ-1.E1, 87-REQ-1.E2, 87-REQ-1.E3
"""

from __future__ import annotations

import logging

from agent_fox.scope_guard.models import (
    FileChange,
    Language,
    StubValidationResult,
    TaskGroup,
    ViolationRecord,
)
from agent_fox.scope_guard.source_parser import extract_modified_functions
from agent_fox.scope_guard.stub_patterns import is_stub_body

logger = logging.getLogger(__name__)


def validate_stubs(
    modified_files: list[FileChange], task_group: TaskGroup
) -> StubValidationResult:
    """Validate that all non-test functions in modified files are stubs.

    Scans each non-test source file modified by the session.  For every
    function/method body that is *not* a recognized stub placeholder and
    is *not* inside a test-attributed block, a ``ViolationRecord`` is
    created.

    Files whose language is ``UNKNOWN`` are skipped and listed in
    ``skipped_files`` (87-REQ-1.E3).
    """
    violations: list[ViolationRecord] = []
    skipped_files: list[str] = []

    for fc in modified_files:
        # Skip unsupported languages
        if fc.language == Language.UNKNOWN:
            logger.warning(
                "Stub enforcement skipped for unsupported language: %s",
                fc.file_path,
            )
            skipped_files.append(fc.file_path)
            continue

        # Extract function bodies from the diff text
        functions = extract_modified_functions(fc)

        for func in functions:
            # Skip functions inside test blocks (87-REQ-1.E1)
            if func.inside_test_block:
                continue

            # Check if the body is a stub
            if not is_stub_body(func.body_text, func.language):
                violations.append(
                    ViolationRecord(
                        file_path=func.file_path,
                        function_id=func.function_id,
                        body_preview=func.body_text[:200],
                        prompt_directive_present=None,
                    )
                )

    return StubValidationResult(
        passed=len(violations) == 0,
        violations=violations,
        skipped_files=skipped_files,
    )
