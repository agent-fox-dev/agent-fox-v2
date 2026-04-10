"""Scope Guard: prevents wasted coder sessions via stub enforcement,
pre-flight scope checking, overlap detection, and no-op tracking.

Requirements: 87-REQ-1 through 87-REQ-5
"""

from __future__ import annotations

from agent_fox.scope_guard.models import (
    Deliverable,
    DeliverableCheckResult,
    DeliverableStatus,
    FileChange,
    FunctionBody,
    Language,
    OverlapRecord,
    OverlapResult,
    OverlapSeverity,
    PromptRecord,
    ScopeCheckResult,
    ScopeGuardSessionOutcome,
    SessionClassification,
    SessionResult,
    SpecGraph,
    SpecWasteSummary,
    StubValidationResult,
    TaskGroup,
    ViolationRecord,
    WasteReport,
)
from agent_fox.scope_guard.stub_patterns import (
    detect_language,
    get_stub_patterns,
    is_stub_body,
    is_test_block,
)

__all__ = [
    # Models — enums
    "Language",
    "DeliverableStatus",
    "SessionClassification",
    "OverlapSeverity",
    # Models — data classes
    "Deliverable",
    "FunctionBody",
    "DeliverableCheckResult",
    "ScopeCheckResult",
    "OverlapRecord",
    "OverlapResult",
    "ViolationRecord",
    "StubValidationResult",
    "ScopeGuardSessionOutcome",
    "PromptRecord",
    "SpecWasteSummary",
    "WasteReport",
    "TaskGroup",
    "SpecGraph",
    "FileChange",
    "SessionResult",
    # stub_patterns
    "is_stub_body",
    "detect_language",
    "get_stub_patterns",
    "is_test_block",
]
