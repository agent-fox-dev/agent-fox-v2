"""Tests for scope_guard.preflight_checker module.

Test Spec: TS-87-5, TS-87-6, TS-87-8, TS-87-E4, TS-87-E5, TS-87-E6, TS-87-P4, TS-87-P5
Requirements: 87-REQ-2.1 through 87-REQ-2.5, 87-REQ-2.E1 through 87-REQ-2.E3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    DeliverableStatus,
    TaskGroup,
)
from agent_fox.scope_guard.preflight_checker import check_scope

# ---------------------------------------------------------------------------
# TS-87-5: Pre-flight scope check returns per-deliverable status
# Requirement: 87-REQ-2.1
# ---------------------------------------------------------------------------


class TestPerDeliverableStatus:
    """TS-87-5: check_scope returns per-deliverable status reflecting codebase state."""

    def test_mixed_stub_and_impl(self, mixed_codebase: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[
                Deliverable("src/foo.rs", "validate", 2),
                Deliverable("src/bar.rs", "process", 2),
            ],
            depends_on=[1],
        )
        result = check_scope(task_group, mixed_codebase)
        assert len(result.deliverable_results) == 2
        statuses = {dr.deliverable.function_id: dr.status for dr in result.deliverable_results}
        assert statuses["validate"] == DeliverableStatus.PENDING
        assert statuses["process"] == DeliverableStatus.ALREADY_IMPLEMENTED
        assert result.overall == "partially-implemented"


# ---------------------------------------------------------------------------
# TS-87-6: Pre-flight skip when all deliverables are implemented
# Requirement: 87-REQ-2.2
# ---------------------------------------------------------------------------


class TestAllImplementedSkip:
    """TS-87-6: check_scope returns 'all-implemented' when all functions have non-stub bodies."""

    def test_all_implemented(self, rust_impl_codebase: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[
                Deliverable("src/bar.rs", "process", 2),
            ],
            depends_on=[1],
        )
        result = check_scope(task_group, rust_impl_codebase)
        assert result.overall == "all-implemented"
        for dr in result.deliverable_results:
            assert dr.status == DeliverableStatus.ALREADY_IMPLEMENTED


# ---------------------------------------------------------------------------
# TS-87-8: Deliverable status uses stub detection logic
# Requirement: 87-REQ-2.4
# ---------------------------------------------------------------------------


class TestStubDetectionForStatus:
    """TS-87-8: Pre-flight checker classifies stubs as pending and non-stubs as implemented."""

    def test_python_stub_and_impl(self, python_stub_codebase: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[
                Deliverable("src/mod.py", "connect", 2),
                Deliverable("src/mod.py", "disconnect", 2),
            ],
            depends_on=[1],
        )
        result = check_scope(task_group, python_stub_codebase)
        statuses = {dr.deliverable.function_id: dr.status for dr in result.deliverable_results}
        assert statuses["connect"] == DeliverableStatus.PENDING
        assert statuses["disconnect"] == DeliverableStatus.ALREADY_IMPLEMENTED


# ---------------------------------------------------------------------------
# TS-87-E4: Nonexistent file/function classified as pending
# Requirement: 87-REQ-2.E1
# ---------------------------------------------------------------------------


class TestNonexistentFileClassifiedPending:
    """TS-87-E4: Missing file or function is classified as pending."""

    def test_missing_file_is_pending(self, tmp_path: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/nonexistent.rs", "missing_fn", 2)],
            depends_on=[1],
        )
        result = check_scope(task_group, tmp_path)
        assert result.deliverable_results[0].status == DeliverableStatus.PENDING

    def test_missing_function_is_pending(self, rust_stub_codebase: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/foo.rs", "nonexistent_fn", 2)],
            depends_on=[1],
        )
        result = check_scope(task_group, rust_stub_codebase)
        assert result.deliverable_results[0].status == DeliverableStatus.PENDING


# ---------------------------------------------------------------------------
# TS-87-E5: Unparseable file classified as indeterminate
# Requirement: 87-REQ-2.E2
# ---------------------------------------------------------------------------


class TestUnparseableFileClassifiedIndeterminate:
    """TS-87-E5: Syntax errors or binary files lead to indeterminate status."""

    def test_binary_file_is_indeterminate(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        binary = src / "data.bin"
        binary.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/data.bin", "some_fn", 2)],
            depends_on=[1],
        )
        result = check_scope(task_group, tmp_path)
        assert result.deliverable_results[0].status == DeliverableStatus.INDETERMINATE


# ---------------------------------------------------------------------------
# TS-87-E6: No deliverables leads to indeterminate
# Requirement: 87-REQ-2.E3
# ---------------------------------------------------------------------------


class TestNoDeliverablesIndeterminate:
    """TS-87-E6: Task group with no enumerated deliverables is indeterminate."""

    def test_empty_deliverables(self, tmp_path: Path) -> None:
        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )
        result = check_scope(task_group, tmp_path)
        assert result.overall == "indeterminate"


# ---------------------------------------------------------------------------
# TS-87-P4: Property — Deliverable Status Correctness
# Property 4 from design.md
# Validates: 87-REQ-2.1, 87-REQ-2.4, 87-REQ-2.E2
# ---------------------------------------------------------------------------


class TestPropertyDeliverableStatusCorrectness:
    """TS-87-P4: pending/implemented/indeterminate classification is correct."""

    @pytest.mark.property
    def test_stub_classified_as_pending(self, rust_stub_codebase: Path) -> None:
        tg = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/foo.rs", "validate", 2)],
            depends_on=[1],
        )
        result = check_scope(tg, rust_stub_codebase)
        assert result.deliverable_results[0].status == DeliverableStatus.PENDING

    @pytest.mark.property
    def test_impl_classified_as_already_implemented(self, rust_impl_codebase: Path) -> None:
        tg = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/bar.rs", "process", 2)],
            depends_on=[1],
        )
        result = check_scope(tg, rust_impl_codebase)
        assert result.deliverable_results[0].status == DeliverableStatus.ALREADY_IMPLEMENTED


# ---------------------------------------------------------------------------
# TS-87-P5: Property — Nonexistent Deliverable is Pending
# Property 5 from design.md
# Validates: 87-REQ-2.E1
# ---------------------------------------------------------------------------


class TestPropertyNonexistentIsPending:
    """TS-87-P5: Missing function or file leads to PENDING status."""

    @pytest.mark.property
    def test_nonexistent_always_pending(self, tmp_path: Path) -> None:
        tg = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[Deliverable("src/ghost.rs", "phantom_fn", 2)],
            depends_on=[1],
        )
        result = check_scope(tg, tmp_path)
        assert result.deliverable_results[0].status == DeliverableStatus.PENDING
