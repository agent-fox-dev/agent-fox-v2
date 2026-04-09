"""Compare task group deliverables against codebase state.

Requirements: 87-REQ-2.1 through 87-REQ-2.5, 87-REQ-2.E1 through 87-REQ-2.E3
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agent_fox.scope_guard.models import (
    DeliverableCheckResult,
    DeliverableStatus,
    ScopeCheckResult,
    TaskGroup,
)
from agent_fox.scope_guard.source_parser import extract_function_body
from agent_fox.scope_guard.stub_patterns import detect_language, is_stub_body

logger = logging.getLogger(__name__)


def check_scope(task_group: TaskGroup, codebase_root: Path) -> ScopeCheckResult:
    """Check which deliverables are already implemented in the codebase.

    For each deliverable:
    - If the file/function doesn't exist → PENDING (87-REQ-2.E1)
    - If the file can't be parsed → INDETERMINATE (87-REQ-2.E2)
    - If the function body is a stub → PENDING
    - If the function body has real logic → ALREADY_IMPLEMENTED
    - If no deliverables → overall "indeterminate" (87-REQ-2.E3)
    """
    start_ns = time.monotonic_ns()

    # Edge case: no deliverables → indeterminate with warning (87-REQ-2.E3)
    if not task_group.deliverables:
        logger.warning(
            "Task group %d has no enumerated deliverables; "
            "scope check is inconclusive",
            task_group.number,
        )
        elapsed_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        return ScopeCheckResult(
            task_group_number=task_group.number,
            deliverable_results=[],
            overall="indeterminate",
            check_duration_ms=elapsed_ms,
            deliverable_count=0,
        )

    results: list[DeliverableCheckResult] = []

    for deliverable in task_group.deliverables:
        file_path = codebase_root / deliverable.file_path

        # File doesn't exist → PENDING (87-REQ-2.E1)
        if not file_path.exists():
            results.append(
                DeliverableCheckResult(
                    deliverable=deliverable,
                    status=DeliverableStatus.PENDING,
                    reason="file does not exist",
                )
            )
            continue

        # Check language support
        language = detect_language(deliverable.file_path)
        from agent_fox.scope_guard.models import Language

        if language == Language.UNKNOWN:
            # Unsupported or binary → INDETERMINATE (87-REQ-2.E2)
            results.append(
                DeliverableCheckResult(
                    deliverable=deliverable,
                    status=DeliverableStatus.INDETERMINATE,
                    reason="unsupported language or file type",
                )
            )
            continue

        # Try to extract the function body
        func_body = extract_function_body(file_path, deliverable.function_id)

        if func_body is None:
            # Function not found → PENDING (could be not yet created)
            # But if the file exists and we couldn't parse it, check if
            # we can read it at all.
            try:
                file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # Can't read → INDETERMINATE (87-REQ-2.E2)
                results.append(
                    DeliverableCheckResult(
                        deliverable=deliverable,
                        status=DeliverableStatus.INDETERMINATE,
                        reason="file could not be parsed",
                    )
                )
                continue

            # File readable but function not found → PENDING (87-REQ-2.E1)
            results.append(
                DeliverableCheckResult(
                    deliverable=deliverable,
                    status=DeliverableStatus.PENDING,
                    reason="function not found in file",
                )
            )
            continue

        # Function found — check if it's a stub (87-REQ-2.4)
        if is_stub_body(func_body.body_text, func_body.language):
            results.append(
                DeliverableCheckResult(
                    deliverable=deliverable,
                    status=DeliverableStatus.PENDING,
                    reason="stub body",
                )
            )
        else:
            results.append(
                DeliverableCheckResult(
                    deliverable=deliverable,
                    status=DeliverableStatus.ALREADY_IMPLEMENTED,
                    reason="has implementation",
                )
            )

    # Derive overall status
    overall = _derive_overall(results)
    elapsed_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    return ScopeCheckResult(
        task_group_number=task_group.number,
        deliverable_results=results,
        overall=overall,
        check_duration_ms=elapsed_ms,
        deliverable_count=len(results),
    )


def _derive_overall(results: list[DeliverableCheckResult]) -> str:
    """Derive the overall scope check status from individual results."""
    if not results:
        return "indeterminate"

    statuses = {r.status for r in results}

    # If any indeterminate, the overall is indeterminate
    if DeliverableStatus.INDETERMINATE in statuses:
        if len(statuses) == 1:
            return "indeterminate"
        # Mixed with indeterminate — still indeterminate
        return "indeterminate"

    has_pending = DeliverableStatus.PENDING in statuses
    has_implemented = DeliverableStatus.ALREADY_IMPLEMENTED in statuses

    if has_pending and has_implemented:
        return "partially-implemented"
    if has_pending:
        return "all-pending"
    if has_implemented:
        return "all-implemented"

    return "indeterminate"
