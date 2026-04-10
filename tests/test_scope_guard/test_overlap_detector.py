"""Tests for scope_guard.overlap_detector module.

Test Spec: TS-87-10, TS-87-11, TS-87-12, TS-87-13, TS-87-E7, TS-87-E8, TS-87-E9,
           TS-87-P8, TS-87-P9, TS-87-P10
Requirements: 87-REQ-3.1 through 87-REQ-3.4, 87-REQ-3.E1 through 87-REQ-3.E3
"""

from __future__ import annotations

import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    OverlapSeverity,
    SpecGraph,
    TaskGroup,
)
from agent_fox.scope_guard.overlap_detector import detect_overlaps

# ---------------------------------------------------------------------------
# TS-87-10: Overlap detection identifies shared deliverables
# Requirement: 87-REQ-3.1
# ---------------------------------------------------------------------------


class TestDetectSharedDeliverables:
    """TS-87-10: detect_overlaps identifies deliverables present in multiple task groups."""

    def test_finds_shared_deliverable(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/validator.rs", "validate", 1)], []),
                TaskGroup(2, 4, "implementation", [Deliverable("src/engine.rs", "run", 2)], [1]),
                TaskGroup(3, 4, "implementation", [Deliverable("src/validator.rs", "validate", 3)], [1]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 1
        assert set(result.overlaps[0].task_group_numbers) == {1, 3}
        assert "validate" in result.overlaps[0].deliverable_id


# ---------------------------------------------------------------------------
# TS-87-11: Overlap detection emits warning
# Requirement: 87-REQ-3.2
# ---------------------------------------------------------------------------


class TestOverlapEmitsWarning:
    """TS-87-11: Detected overlaps produce warnings."""

    def test_has_warnings_when_overlap_found(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/validator.rs", "validate", 1)], []),
                TaskGroup(3, 4, "implementation", [Deliverable("src/validator.rs", "validate", 3)], [1]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert result.has_warnings is True
        assert len(result.overlaps) >= 1
        for overlap in result.overlaps:
            assert len(overlap.task_group_numbers) >= 2


# ---------------------------------------------------------------------------
# TS-87-12: Overlap blocks execution when no dependency
# Requirement: 87-REQ-3.3
# ---------------------------------------------------------------------------


class TestOverlapErrorNoDependency:
    """TS-87-12: Overlap between unrelated task groups is classified as error."""

    def test_error_when_no_dependency(self) -> None:
        spec_graph = SpecGraph(
            spec_number=5,
            task_groups=[
                TaskGroup(1, 5, "test-writing", [Deliverable("src/a.rs", "init", 1)], []),
                TaskGroup(2, 5, "implementation", [Deliverable("src/shared.rs", "process", 2)], [1]),
                TaskGroup(3, 5, "implementation", [Deliverable("src/shared.rs", "process", 3)], [1]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert result.has_errors is True
        error_overlaps = [o for o in result.overlaps if o.severity == OverlapSeverity.ERROR]
        assert len(error_overlaps) == 1
        assert set(error_overlaps[0].task_group_numbers) == {2, 3}


# ---------------------------------------------------------------------------
# TS-87-13: Overlap warning when dependency exists
# Requirement: 87-REQ-3.4
# ---------------------------------------------------------------------------


class TestOverlapWarningWithDependency:
    """TS-87-13: Overlap between dependent task groups is classified as warning."""

    def test_warning_when_dependency_exists(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/validator.rs", "validate", 1)], []),
                TaskGroup(3, 4, "implementation", [Deliverable("src/validator.rs", "validate", 3)], [1]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert result.has_errors is False
        assert result.has_warnings is True
        assert result.overlaps[0].severity == OverlapSeverity.WARNING


# ---------------------------------------------------------------------------
# TS-87-E7: Empty deliverables excluded from overlap analysis
# Requirement: 87-REQ-3.E1
# ---------------------------------------------------------------------------


class TestEmptyDeliverablesExcluded:
    """TS-87-E7: Task groups with empty deliverable lists are excluded."""

    def test_empty_deliverable_list_excluded(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/a.rs", "init", 1)], []),
                TaskGroup(2, 4, "implementation", [], [1]),  # empty deliverables
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 0


# ---------------------------------------------------------------------------
# TS-87-E8: Same file different functions — no overlap
# Requirement: 87-REQ-3.E2
# ---------------------------------------------------------------------------


class TestSameFileDifferentFunctionsNoOverlap:
    """TS-87-E8: Same file, different functions should not flag as overlap."""

    def test_different_functions_no_overlap(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/shared.rs", "init", 1)], []),
                TaskGroup(2, 4, "implementation", [Deliverable("src/shared.rs", "cleanup", 2)], [1]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 0


# ---------------------------------------------------------------------------
# TS-87-E9: Single task group — empty overlap list
# Requirement: 87-REQ-3.E3
# ---------------------------------------------------------------------------


class TestSingleTaskGroupNoOverlap:
    """TS-87-E9: Single task group returns empty overlap list."""

    def test_single_task_group(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(1, 4, "test-writing", [Deliverable("src/a.rs", "init", 1)], []),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 0

    def test_zero_task_groups(self) -> None:
        spec_graph = SpecGraph(spec_number=4, task_groups=[])
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 0


# ---------------------------------------------------------------------------
# TS-87-P8: Property — Overlap Detection Precision
# Property 8 from design.md
# Validates: 87-REQ-3.1, 87-REQ-3.E2
# ---------------------------------------------------------------------------


class TestPropertyOverlapDetectionPrecision:
    """TS-87-P8: Overlap iff same (file_path, function_id) in multiple task groups."""

    @pytest.mark.property
    def test_overlap_only_on_matching_file_and_function(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(
                    1,
                    4,
                    "test-writing",
                    [
                        Deliverable("src/a.rs", "fn_a", 1),
                        Deliverable("src/b.rs", "fn_b", 1),
                    ],
                    [],
                ),
                TaskGroup(
                    2,
                    4,
                    "implementation",
                    [
                        Deliverable("src/a.rs", "fn_a", 2),  # overlap
                        Deliverable("src/b.rs", "fn_c", 2),  # same file, different function — no overlap
                    ],
                    [1],
                ),
            ],
        )
        result = detect_overlaps(spec_graph)
        # Only fn_a in src/a.rs should be an overlap
        assert len(result.overlaps) == 1
        assert "fn_a" in result.overlaps[0].deliverable_id


# ---------------------------------------------------------------------------
# TS-87-P9: Property — Overlap Severity Classification
# Property 9 from design.md
# Validates: 87-REQ-3.3, 87-REQ-3.4
# ---------------------------------------------------------------------------


class TestPropertyOverlapSeverityClassification:
    """TS-87-P9: Error if no dependency, warning if dependency exists."""

    @pytest.mark.property
    def test_no_dependency_is_error(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(2, 4, "implementation", [Deliverable("src/x.rs", "fn_x", 2)], []),
                TaskGroup(3, 4, "implementation", [Deliverable("src/x.rs", "fn_x", 3)], []),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 1
        assert result.overlaps[0].severity == OverlapSeverity.ERROR

    @pytest.mark.property
    def test_with_dependency_is_warning(self) -> None:
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(2, 4, "implementation", [Deliverable("src/x.rs", "fn_x", 2)], []),
                TaskGroup(3, 4, "implementation", [Deliverable("src/x.rs", "fn_x", 3)], [2]),
            ],
        )
        result = detect_overlaps(spec_graph)
        assert len(result.overlaps) == 1
        assert result.overlaps[0].severity == OverlapSeverity.WARNING


# ---------------------------------------------------------------------------
# TS-87-P10: Property — Overlap Edge Cases
# Property 10 from design.md
# Validates: 87-REQ-3.E1, 87-REQ-3.E3
# ---------------------------------------------------------------------------


class TestPropertyOverlapEdgeCases:
    """TS-87-P10: 0 or 1 task groups or empty deliverables → empty overlaps."""

    @pytest.mark.property
    def test_zero_task_groups_empty_overlaps(self) -> None:
        result = detect_overlaps(SpecGraph(spec_number=1, task_groups=[]))
        assert result.overlaps == []
        assert result.has_errors is False
        assert result.has_warnings is False

    @pytest.mark.property
    def test_single_task_group_empty_overlaps(self) -> None:
        result = detect_overlaps(
            SpecGraph(
                spec_number=1,
                task_groups=[TaskGroup(1, 1, "test-writing", [Deliverable("a.rs", "fn_a", 1)], [])],
            )
        )
        assert result.overlaps == []

    @pytest.mark.property
    def test_empty_deliverables_excluded(self) -> None:
        result = detect_overlaps(
            SpecGraph(
                spec_number=1,
                task_groups=[
                    TaskGroup(1, 1, "test-writing", [], []),
                    TaskGroup(2, 1, "implementation", [], [1]),
                ],
            )
        )
        assert result.overlaps == []
