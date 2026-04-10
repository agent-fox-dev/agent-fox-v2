"""Shared data models, enums, and typed structures for scope_guard.

Requirements: all (foundational types)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Language(Enum):
    RUST = "rust"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    UNKNOWN = "unknown"


class DeliverableStatus(Enum):
    PENDING = "pending"
    ALREADY_IMPLEMENTED = "already-implemented"
    INDETERMINATE = "indeterminate"


class SessionClassification(Enum):
    SUCCESS = "success"
    NO_OP = "no-op"
    PRE_FLIGHT_SKIP = "pre-flight-skip"
    FAILURE = "failure"
    HARVEST_ERROR = "harvest-error"


class OverlapSeverity(Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Deliverable:
    file_path: str
    function_id: str  # fully qualified: "module::function" or "Class.method"
    task_group_number: int


@dataclass(frozen=True)
class FunctionBody:
    function_id: str
    file_path: str
    body_text: str
    language: Language
    start_line: int
    end_line: int
    inside_test_block: bool


@dataclass(frozen=True)
class DeliverableCheckResult:
    deliverable: Deliverable
    status: DeliverableStatus
    reason: str


@dataclass(frozen=True)
class ScopeCheckResult:
    task_group_number: int
    deliverable_results: list[DeliverableCheckResult]
    overall: str  # "all-pending", "all-implemented", "partially-implemented", "indeterminate"
    check_duration_ms: int
    deliverable_count: int


@dataclass(frozen=True)
class OverlapRecord:
    deliverable_id: str
    task_group_numbers: list[int]
    severity: OverlapSeverity


@dataclass(frozen=True)
class OverlapResult:
    overlaps: list[OverlapRecord]
    has_errors: bool
    has_warnings: bool


@dataclass(frozen=True)
class ViolationRecord:
    file_path: str
    function_id: str
    body_preview: str  # first 200 chars of the offending body
    prompt_directive_present: bool | None  # None if not yet checked


@dataclass(frozen=True)
class StubValidationResult:
    passed: bool
    violations: list[ViolationRecord]
    skipped_files: list[str]  # files with unsupported languages


@dataclass(frozen=True)
class ScopeGuardSessionOutcome:
    """Session outcome for scope guard telemetry.

    Named ScopeGuardSessionOutcome to avoid collision with
    agent_fox.knowledge.sink.SessionOutcome.
    """

    session_id: str
    spec_number: int
    task_group_number: int
    classification: SessionClassification
    duration_seconds: float
    cost_dollars: float
    timestamp: datetime
    stub_violation: bool = False
    violation_details: list[ViolationRecord] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class PromptRecord:
    session_id: str
    prompt_text: str
    truncated: bool
    stub_directive_present: bool


@dataclass(frozen=True)
class SpecWasteSummary:
    spec_number: int
    no_op_count: int
    pre_flight_skip_count: int
    total_wasted_cost: float
    total_wasted_duration: float


@dataclass(frozen=True)
class WasteReport:
    per_spec: list[SpecWasteSummary]


@dataclass
class TaskGroup:
    """Task group for scope guard analysis.

    This is a scope-guard-specific representation, distinct from
    agent_fox.graph.types.Node which represents task groups in the
    execution graph.
    """

    number: int
    spec_number: int
    archetype: str  # e.g., "test-writing", "implementation", "integration"
    deliverables: list[Deliverable]
    depends_on: list[int]  # task group numbers this depends on


@dataclass
class SpecGraph:
    spec_number: int
    task_groups: list[TaskGroup]


@dataclass(frozen=True)
class FileChange:
    file_path: str
    language: Language
    diff_text: str


@dataclass
class SessionResult:
    session_id: str
    spec_number: int
    task_group_number: int
    branch_name: str
    base_branch: str
    exit_status: str  # "success", "error", "timeout"
    duration_seconds: float
    cost_dollars: float
    modified_files: list[FileChange]
    commit_count: int
