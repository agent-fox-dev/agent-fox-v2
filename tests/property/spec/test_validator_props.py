"""Property tests for specification validation.

Test Spec: TS-09-P1 through TS-09-P5
Properties: 1, 3, 4, 5, 6 from design.md
Requirements: 09-REQ-9.4, 09-REQ-9.5, 09-REQ-2.1, 09-REQ-2.2,
              09-REQ-3.1, 09-REQ-3.2
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.spec.parser import SubtaskDef, TaskGroupDef
from agent_fox.spec.validator import (
    EXPECTED_FILES,
    SEVERITY_ERROR,
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
    check_missing_files,
    check_oversized_groups,
    compute_exit_code,
)

# -- Strategies ----------------------------------------------------------------

severity_strategy = st.sampled_from([SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_HINT])

finding_strategy = st.builds(
    Finding,
    spec_name=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz_0123456789",
        min_size=1,
        max_size=20,
    ),
    file=st.sampled_from(EXPECTED_FILES),
    rule=st.sampled_from([
        "missing-file",
        "oversized-group",
        "missing-verification",
        "missing-acceptance-criteria",
        "broken-dependency",
        "untraced-requirement",
    ]),
    severity=severity_strategy,
    message=st.text(min_size=1, max_size=100),
    line=st.one_of(st.none(), st.integers(min_value=1, max_value=1000)),
)


def _make_subtasks(count: int, group_number: int = 1) -> tuple[SubtaskDef, ...]:
    """Create N non-verification subtasks for a given group."""
    return tuple(
        SubtaskDef(
            id=f"{group_number}.{i}",
            title=f"Subtask {i}",
            completed=False,
        )
        for i in range(1, count + 1)
    )


# -- TS-09-P1: Error findings imply non-zero exit -----------------------------


class TestErrorFindingsImplyNonZeroExit:
    """TS-09-P1: Error findings imply non-zero exit.

    Property 3 from design.md.
    Requirements: 09-REQ-9.4
    For any findings list with at least one Error, exit code is 1.
    """

    @given(
        findings=st.lists(finding_strategy, min_size=1, max_size=10).filter(
            lambda fs: any(f.severity == SEVERITY_ERROR for f in fs)
        )
    )
    @settings(max_examples=50)
    def test_error_findings_produce_exit_code_one(
        self, findings: list[Finding]
    ) -> None:
        """Any findings list with at least one error produces exit code 1."""
        exit_code = compute_exit_code(findings)
        assert exit_code == 1


# -- TS-09-P2: No errors implies zero exit ------------------------------------


class TestNoErrorsImplyZeroExit:
    """TS-09-P2: No errors implies zero exit.

    Property 4 from design.md.
    Requirements: 09-REQ-9.5
    For any findings list with no errors, exit code is 0.
    """

    @given(
        findings=st.lists(
            finding_strategy.filter(
                lambda f: f.severity != SEVERITY_ERROR
            ),
            min_size=0,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_no_errors_produce_exit_code_zero(
        self, findings: list[Finding]
    ) -> None:
        """Findings list with no errors produces exit code 0."""
        exit_code = compute_exit_code(findings)
        assert exit_code == 0


# -- TS-09-P3: Missing files count matches reality ----------------------------


class TestMissingFilesCountMatchesReality:
    """TS-09-P3: Missing files count matches reality.

    Property 5 from design.md.
    Requirements: 09-REQ-2.1, 09-REQ-2.2
    For any subset of expected files present, findings count == 5 - len(subset).
    """

    @given(
        present_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=50)
    def test_findings_count_equals_missing_count(
        self,
        present_indices: list[int],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Number of findings equals number of missing files."""
        tmp_dir = tmp_path_factory.mktemp("spec")

        # Create only the selected files
        present_files = [EXPECTED_FILES[i] for i in present_indices]
        for filename in present_files:
            (tmp_dir / filename).write_text(f"# {filename}\n")

        findings = check_missing_files("test", tmp_dir)

        expected_missing = 5 - len(present_files)
        assert len(findings) == expected_missing


# -- TS-09-P4: Oversized group threshold is exact -----------------------------


class TestOversizedGroupThresholdExact:
    """TS-09-P4: Oversized group threshold is exact.

    Property 6 from design.md.
    Requirements: 09-REQ-3.1, 09-REQ-3.2
    A task group produces a warning iff non-verification subtask count > 6.
    """

    @given(n=st.integers(min_value=0, max_value=20))
    @settings(max_examples=50)
    def test_threshold_is_exactly_six(self, n: int) -> None:
        """Warning iff subtask count exceeds 6."""
        group = TaskGroupDef(
            number=1,
            title="Test group",
            optional=False,
            completed=False,
            subtasks=_make_subtasks(n),
            body="",
        )
        findings = check_oversized_groups("test", [group])

        if n > 6:
            assert len(findings) == 1, (
                f"Expected 1 finding for {n} subtasks, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for {n} subtasks, got {len(findings)}"
            )


# -- TS-09-P5: Finding immutability -------------------------------------------


class TestFindingImmutability:
    """TS-09-P5: Finding immutability.

    Property 1 from design.md.
    Finding instances are frozen and cannot be mutated.
    """

    @given(finding=finding_strategy)
    @settings(max_examples=50)
    def test_cannot_mutate_severity(self, finding: Finding) -> None:
        """Attempting to set severity raises FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            finding.severity = "error"  # type: ignore[misc]

    @given(finding=finding_strategy)
    @settings(max_examples=50)
    def test_cannot_mutate_message(self, finding: Finding) -> None:
        """Attempting to set message raises FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            finding.message = "changed"  # type: ignore[misc]

    @given(finding=finding_strategy)
    @settings(max_examples=50)
    def test_cannot_mutate_spec_name(self, finding: Finding) -> None:
        """Attempting to set spec_name raises FrozenInstanceError."""
        with pytest.raises(FrozenInstanceError):
            finding.spec_name = "changed"  # type: ignore[misc]
