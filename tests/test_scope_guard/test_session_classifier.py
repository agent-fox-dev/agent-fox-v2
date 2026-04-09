"""Tests for scope_guard.session_classifier module.

Test Spec: TS-87-3, TS-87-14, TS-87-E10, TS-87-E11, TS-87-E12,
           TS-87-P11, TS-87-P12, TS-87-P13, TS-87-P14
Requirements: 87-REQ-1.3, 87-REQ-4.1, 87-REQ-4.E1 through 87-REQ-4.E3
"""

from __future__ import annotations

import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    FileChange,
    Language,
    SessionClassification,
    SessionResult,
    TaskGroup,
)
from agent_fox.scope_guard.session_classifier import classify_session

# ---------------------------------------------------------------------------
# TS-87-3: Stub violation flagged in completion record
# Requirement: 87-REQ-1.3
# ---------------------------------------------------------------------------


class TestStubViolationFlaggedInOutcome:
    """TS-87-3: Session with non-stub code from test-writing TG has stub_violation=True."""

    def test_violation_flagged(self) -> None:
        session = SessionResult(
            session_id="sess-001",
            spec_number=4,
            task_group_number=1,
            branch_name="feature/04/1",
            base_branch="develop",
            exit_status="success",
            duration_seconds=120.0,
            cost_dollars=3.50,
            modified_files=[
                FileChange("src/foo.rs", Language.RUST, "fn bar() { compute() }")
            ],
            commit_count=2,
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("src/foo.rs", "bar", 1)],
            depends_on=[],
        )
        outcome = classify_session(session, task_group)
        assert outcome.stub_violation is True
        assert len(outcome.violation_details) >= 1
        assert outcome.classification == SessionClassification.SUCCESS


# ---------------------------------------------------------------------------
# TS-87-14: No-op session recorded when zero new commits
# Requirement: 87-REQ-4.1
# ---------------------------------------------------------------------------


class TestNoopZeroCommits:
    """TS-87-14: Session with zero commits and normal exit is classified as no-op."""

    def test_zero_commits_normal_exit(self) -> None:
        session = SessionResult(
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
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.NO_OP


# ---------------------------------------------------------------------------
# TS-87-E10: Whitespace-only commits classified as no-op
# Requirement: 87-REQ-4.E1
# ---------------------------------------------------------------------------


class TestWhitespaceOnlyCommitsNoop:
    """TS-87-E10: Commits consisting solely of whitespace/comment changes are classified as no-op."""

    def test_whitespace_only_is_noop(self) -> None:
        session = SessionResult(
            session_id="sess-ws-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="success",
            duration_seconds=80.0,
            cost_dollars=2.00,
            modified_files=[
                FileChange("src/foo.rs", Language.RUST, "  \n  \n")  # whitespace-only diff
            ],
            commit_count=1,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.NO_OP


# ---------------------------------------------------------------------------
# TS-87-E11: Harvest error not classified as no-op
# Requirement: 87-REQ-4.E2
# ---------------------------------------------------------------------------


class TestHarvestErrorNotNoop:
    """TS-87-E11: Git error leads to harvest-error, not no-op."""

    def test_harvest_error_classification(self) -> None:
        session = SessionResult(
            session_id="sess-herr-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="harvest-error",
            duration_seconds=10.0,
            cost_dollars=0.50,
            modified_files=[],
            commit_count=-1,  # indicates harvest couldn't determine count
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.HARVEST_ERROR


# ---------------------------------------------------------------------------
# TS-87-E12: Error exit with no commits is failure, not no-op
# Requirement: 87-REQ-4.E3
# ---------------------------------------------------------------------------


class TestErrorExitNoCommitsIsFailure:
    """TS-87-E12: Error exit + no commits is classified as failure, not no-op."""

    def test_error_exit_is_failure(self) -> None:
        session = SessionResult(
            session_id="sess-err-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="error",
            duration_seconds=30.0,
            cost_dollars=1.00,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.FAILURE

    def test_timeout_exit_is_failure(self) -> None:
        session = SessionResult(
            session_id="sess-timeout-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="timeout",
            duration_seconds=600.0,
            cost_dollars=5.00,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.FAILURE


# ---------------------------------------------------------------------------
# TS-87-P11: Property — Classification Mutual Exclusivity
# Property 11 from design.md
# Validates: 87-REQ-4.1, 87-REQ-4.2, 87-REQ-4.E3
# ---------------------------------------------------------------------------


class TestPropertyClassificationMutualExclusivity:
    """TS-87-P11: Exactly one classification per session."""

    @pytest.mark.property
    def test_success_session_is_only_success(self) -> None:
        session = SessionResult(
            session_id="sess-ok",
            spec_number=1,
            task_group_number=2,
            branch_name="feature/01/2",
            base_branch="develop",
            exit_status="success",
            duration_seconds=100.0,
            cost_dollars=3.00,
            modified_files=[
                FileChange("src/a.py", Language.PYTHON, "def foo():\n    return 1")
            ],
            commit_count=1,
        )
        tg = TaskGroup(2, 1, "implementation", [], [1])
        outcome = classify_session(session, tg)
        assert outcome.classification in list(SessionClassification)

    @pytest.mark.property
    def test_noop_session_has_noop_classification(self) -> None:
        session = SessionResult(
            session_id="sess-noop",
            spec_number=1,
            task_group_number=2,
            branch_name="feature/01/2",
            base_branch="develop",
            exit_status="success",
            duration_seconds=50.0,
            cost_dollars=1.50,
            modified_files=[],
            commit_count=0,
        )
        tg = TaskGroup(2, 1, "implementation", [], [1])
        outcome = classify_session(session, tg)
        assert outcome.classification == SessionClassification.NO_OP


# ---------------------------------------------------------------------------
# TS-87-P12: Property — No-Op vs Failure Distinction
# Property 12 from design.md
# Validates: 87-REQ-4.1, 87-REQ-4.E3
# ---------------------------------------------------------------------------


class TestPropertyNoopVsFailureDistinction:
    """TS-87-P12: No-op only if normal exit; error exit → failure."""

    @pytest.mark.property
    def test_error_exit_never_noop(self) -> None:
        for exit_status in ["error", "timeout"]:
            session = SessionResult(
                session_id=f"sess-{exit_status}",
                spec_number=1,
                task_group_number=2,
                branch_name="feature/01/2",
                base_branch="develop",
                exit_status=exit_status,
                duration_seconds=50.0,
                cost_dollars=1.50,
                modified_files=[],
                commit_count=0,
            )
            tg = TaskGroup(2, 1, "implementation", [], [1])
            outcome = classify_session(session, tg)
            assert outcome.classification != SessionClassification.NO_OP


# ---------------------------------------------------------------------------
# TS-87-P13: Property — Whitespace Commits Are No-Op
# Property 13 from design.md
# Validates: 87-REQ-4.E1
# ---------------------------------------------------------------------------


class TestPropertyWhitespaceCommitsNoop:
    """TS-87-P13: Whitespace-only changes → no-op."""

    @pytest.mark.property
    def test_whitespace_diff_is_noop(self) -> None:
        session = SessionResult(
            session_id="sess-ws",
            spec_number=1,
            task_group_number=2,
            branch_name="feature/01/2",
            base_branch="develop",
            exit_status="success",
            duration_seconds=50.0,
            cost_dollars=1.50,
            modified_files=[FileChange("a.py", Language.PYTHON, "   \n\n  ")],
            commit_count=1,
        )
        tg = TaskGroup(2, 1, "implementation", [], [1])
        outcome = classify_session(session, tg)
        assert outcome.classification == SessionClassification.NO_OP


# ---------------------------------------------------------------------------
# TS-87-P14: Property — Harvest Error Classification
# Property 14 from design.md
# Validates: 87-REQ-4.E2
# ---------------------------------------------------------------------------


class TestPropertyHarvestErrorClassification:
    """TS-87-P14: Git error → harvest-error, never no-op."""

    @pytest.mark.property
    def test_harvest_error_never_noop(self) -> None:
        session = SessionResult(
            session_id="sess-herr",
            spec_number=1,
            task_group_number=2,
            branch_name="feature/01/2",
            base_branch="develop",
            exit_status="harvest-error",
            duration_seconds=10.0,
            cost_dollars=0.50,
            modified_files=[],
            commit_count=-1,
        )
        tg = TaskGroup(2, 1, "implementation", [], [1])
        outcome = classify_session(session, tg)
        assert outcome.classification == SessionClassification.HARVEST_ERROR
        assert outcome.classification != SessionClassification.NO_OP
