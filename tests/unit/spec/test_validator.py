"""Unit tests for static validation rules.

Test Spec: TS-09-1 through TS-09-12
Requirements: 09-REQ-2.1, 09-REQ-2.2, 09-REQ-3.1, 09-REQ-3.2,
              09-REQ-4.1, 09-REQ-4.2, 09-REQ-5.1, 09-REQ-5.2,
              09-REQ-6.1, 09-REQ-6.2, 09-REQ-6.3, 09-REQ-7.1, 09-REQ-7.2,
              09-REQ-1.3
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.parser import SubtaskDef, TaskGroupDef
from agent_fox.spec.validator import (
    Finding,
    check_broken_dependencies,
    check_missing_acceptance_criteria,
    check_missing_files,
    check_missing_verification,
    check_oversized_groups,
    check_untraced_requirements,
    sort_findings,
)

# -- Fixtures path helper -----------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "specs"


def _make_subtasks(count: int, group_number: int = 1) -> list[SubtaskDef]:
    """Create a list of N non-verification subtasks for a given group."""
    return [
        SubtaskDef(
            id=f"{group_number}.{i}",
            title=f"Subtask {i}",
            completed=False,
        )
        for i in range(1, count + 1)
    ]


def _make_verification_subtask(group_number: int) -> SubtaskDef:
    """Create a verification subtask (N.V pattern) for a given group."""
    return SubtaskDef(
        id=f"{group_number}.V",
        title=f"Verify task group {group_number}",
        completed=False,
    )


# -- TS-09-1: Missing files detected ------------------------------------------


class TestMissingFilesDetected:
    """TS-09-1: Missing files detected.

    Requirements: 09-REQ-2.1, 09-REQ-2.2
    Verify check_missing_files produces an Error finding for each missing
    expected file.
    """

    def test_detects_three_missing_files(self) -> None:
        """Incomplete spec (only prd.md and tasks.md) produces 3 findings."""
        fixture_path = FIXTURES_DIR / "incomplete_spec"
        findings = check_missing_files("incomplete_spec", fixture_path)

        assert len(findings) == 3

    def test_all_findings_are_error_severity(self) -> None:
        """All findings for missing files have severity 'error'."""
        fixture_path = FIXTURES_DIR / "incomplete_spec"
        findings = check_missing_files("incomplete_spec", fixture_path)

        for f in findings:
            assert f.severity == "error"

    def test_all_findings_have_missing_file_rule(self) -> None:
        """All findings have rule 'missing-file'."""
        fixture_path = FIXTURES_DIR / "incomplete_spec"
        findings = check_missing_files("incomplete_spec", fixture_path)

        for f in findings:
            assert f.rule == "missing-file"

    def test_missing_filenames_identified(self) -> None:
        """Finding file fields identify the missing filenames."""
        fixture_path = FIXTURES_DIR / "incomplete_spec"
        findings = check_missing_files("incomplete_spec", fixture_path)

        missing_files = {f.file for f in findings}
        assert missing_files == {"requirements.md", "design.md", "test_spec.md"}


# -- TS-09-2: All files present produces no findings --------------------------


class TestAllFilesPresentNoFindings:
    """TS-09-2: All files present produces no findings.

    Requirements: 09-REQ-2.1
    Verify check_missing_files returns empty list when all files present.
    """

    def test_complete_spec_no_findings(self) -> None:
        """Complete spec folder (all 5 files) produces no findings."""
        fixture_path = FIXTURES_DIR / "complete_spec"
        findings = check_missing_files("complete_spec", fixture_path)

        assert len(findings) == 0


# -- TS-09-3: Oversized task group detected ------------------------------------


class TestOversizedGroupDetected:
    """TS-09-3: Oversized task group detected.

    Requirements: 09-REQ-3.1, 09-REQ-3.2
    Verify check_oversized_groups flags a task group with >6 subtasks.
    """

    def test_eight_subtasks_produces_warning(self) -> None:
        """Task group with 8 subtasks produces exactly 1 finding."""
        group = TaskGroupDef(
            number=1,
            title="Big group",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(8)),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert len(findings) == 1

    def test_finding_is_warning_severity(self) -> None:
        """Oversized group finding has severity 'warning'."""
        group = TaskGroupDef(
            number=1,
            title="Big group",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(8)),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert findings[0].severity == "warning"

    def test_finding_has_oversized_group_rule(self) -> None:
        """Oversized group finding has rule 'oversized-group'."""
        group = TaskGroupDef(
            number=1,
            title="Big group",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(8)),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert findings[0].rule == "oversized-group"

    def test_finding_message_mentions_count(self) -> None:
        """Oversized group finding message mentions the subtask count."""
        group = TaskGroupDef(
            number=1,
            title="Big group",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(8)),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert "8" in findings[0].message


# -- TS-09-4: Task group with 6 subtasks is acceptable ------------------------


class TestSixSubtasksAcceptable:
    """TS-09-4: Task group with 6 subtasks is acceptable.

    Requirements: 09-REQ-3.1, 09-REQ-3.2
    Verify check_oversized_groups does not flag a group with exactly 6 subtasks.
    """

    def test_six_subtasks_no_finding(self) -> None:
        """Task group with exactly 6 subtasks produces no findings."""
        group = TaskGroupDef(
            number=1,
            title="Okay group",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(6)),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert len(findings) == 0


# -- TS-09-5: Verification step excluded from subtask count --------------------


class TestVerificationExcludedFromCount:
    """TS-09-5: Verification step excluded from subtask count.

    Requirements: 09-REQ-3.1
    Verify that N.V verification steps are excluded from the oversized check.
    """

    def test_seven_with_verify_is_acceptable(self) -> None:
        """7 subtasks (6 normal + 1 verification) produces no findings."""
        subtasks = _make_subtasks(6) + [_make_verification_subtask(1)]
        group = TaskGroupDef(
            number=1,
            title="With verify",
            optional=False,
            completed=False,
            subtasks=tuple(subtasks),
            body="",
        )
        findings = check_oversized_groups("test_spec", [group])

        assert len(findings) == 0


# -- TS-09-6: Missing verification step detected ------------------------------


class TestMissingVerificationDetected:
    """TS-09-6: Missing verification step detected.

    Requirements: 09-REQ-4.1, 09-REQ-4.2
    Verify check_missing_verification flags groups without N.V step.
    """

    def test_no_verify_produces_warning(self) -> None:
        """Task group without verification step produces 1 finding."""
        group = TaskGroupDef(
            number=2,
            title="No verify",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(3, group_number=2)),
            body="",
        )
        findings = check_missing_verification("test_spec", [group])

        assert len(findings) == 1

    def test_finding_is_warning_severity(self) -> None:
        """Missing verification finding has severity 'warning'."""
        group = TaskGroupDef(
            number=2,
            title="No verify",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(3, group_number=2)),
            body="",
        )
        findings = check_missing_verification("test_spec", [group])

        assert findings[0].severity == "warning"

    def test_finding_has_missing_verification_rule(self) -> None:
        """Missing verification finding has rule 'missing-verification'."""
        group = TaskGroupDef(
            number=2,
            title="No verify",
            optional=False,
            completed=False,
            subtasks=tuple(_make_subtasks(3, group_number=2)),
            body="",
        )
        findings = check_missing_verification("test_spec", [group])

        assert findings[0].rule == "missing-verification"


# -- TS-09-7: Present verification step produces no finding --------------------


class TestVerificationPresentNoFinding:
    """TS-09-7: Present verification step produces no finding.

    Requirements: 09-REQ-4.1
    Verify check_missing_verification returns empty when N.V step exists.
    """

    def test_with_verify_no_finding(self) -> None:
        """Task group with verification step produces no findings."""
        subtasks = _make_subtasks(3, group_number=2) + [_make_verification_subtask(2)]
        group = TaskGroupDef(
            number=2,
            title="With verify",
            optional=False,
            completed=False,
            subtasks=tuple(subtasks),
            body="",
        )
        findings = check_missing_verification("test_spec", [group])

        assert len(findings) == 0


# -- TS-09-8: Missing acceptance criteria detected -----------------------------


class TestMissingAcceptanceCriteria:
    """TS-09-8: Missing acceptance criteria detected.

    Requirements: 09-REQ-5.1, 09-REQ-5.2
    Verify check_missing_acceptance_criteria flags requirement sections
    without acceptance criteria.
    """

    def test_empty_req_produces_finding(self) -> None:
        """Requirement section without criteria produces at least 1 finding."""
        fixture_path = FIXTURES_DIR / "missing_criteria_spec"
        findings = check_missing_acceptance_criteria("test_spec", fixture_path)

        empty_req_findings = [f for f in findings if "Requirement 3" in f.message]
        assert len(empty_req_findings) == 1

    def test_finding_is_error_severity(self) -> None:
        """Missing criteria finding has severity 'error'."""
        fixture_path = FIXTURES_DIR / "missing_criteria_spec"
        findings = check_missing_acceptance_criteria("test_spec", fixture_path)

        empty_req_findings = [f for f in findings if "Requirement 3" in f.message]
        assert empty_req_findings[0].severity == "error"

    def test_finding_has_correct_rule(self) -> None:
        """Missing criteria finding has rule 'missing-acceptance-criteria'."""
        fixture_path = FIXTURES_DIR / "missing_criteria_spec"
        findings = check_missing_acceptance_criteria("test_spec", fixture_path)

        empty_req_findings = [f for f in findings if "Requirement 3" in f.message]
        assert empty_req_findings[0].rule == "missing-acceptance-criteria"


# -- TS-09-9: Broken dependency to non-existent spec --------------------------


class TestBrokenDependencyNonExistentSpec:
    """TS-09-9: Broken dependency to non-existent spec.

    Requirements: 09-REQ-6.1, 09-REQ-6.2
    Verify check_broken_dependencies flags references to missing specs.
    """

    def test_missing_spec_produces_error(self) -> None:
        """Reference to non-existent spec produces at least 1 error finding."""
        fixture_path = FIXTURES_DIR / "broken_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        broken = [f for f in findings if f.rule == "broken-dependency"]
        assert len(broken) >= 1

    def test_finding_is_error_severity(self) -> None:
        """Broken dependency finding has severity 'error'."""
        fixture_path = FIXTURES_DIR / "broken_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        broken = [f for f in findings if f.rule == "broken-dependency"]
        assert broken[0].severity == "error"

    def test_finding_mentions_missing_spec(self) -> None:
        """Broken dependency finding message mentions the missing spec name."""
        fixture_path = FIXTURES_DIR / "broken_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        broken = [f for f in findings if "99_nonexistent" in f.message]
        assert len(broken) >= 1


# -- TS-09-10: Broken dependency to non-existent task group --------------------


class TestBrokenDependencyNonExistentGroup:
    """TS-09-10: Broken dependency to non-existent task group.

    Requirements: 09-REQ-6.3
    Verify check_broken_dependencies flags references to missing groups.
    """

    def test_missing_group_produces_error(self) -> None:
        """Reference to non-existent group produces at least 1 error."""
        fixture_path = FIXTURES_DIR / "broken_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        group_findings = [f for f in findings if "99" in f.message]
        assert len(group_findings) >= 1

    def test_finding_is_error_severity(self) -> None:
        """Missing group finding has severity 'error'."""
        fixture_path = FIXTURES_DIR / "broken_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3, 4, 5]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        group_findings = [f for f in findings if "99" in f.message]
        assert group_findings[0].severity == "error"


# -- TS-09-11: Untraced requirement detected ----------------------------------


class TestUntracedRequirement:
    """TS-09-11: Untraced requirement detected.

    Requirements: 09-REQ-7.1, 09-REQ-7.2
    Verify check_untraced_requirements flags requirements not referenced
    in test_spec.md.
    """

    def test_untraced_req_produces_warning(self) -> None:
        """Requirement not in test_spec produces exactly 1 warning."""
        fixture_path = FIXTURES_DIR / "untraced_spec"
        findings = check_untraced_requirements("test_spec", fixture_path)

        assert len(findings) == 1

    def test_finding_is_warning_severity(self) -> None:
        """Untraced requirement finding has severity 'warning'."""
        fixture_path = FIXTURES_DIR / "untraced_spec"
        findings = check_untraced_requirements("test_spec", fixture_path)

        assert findings[0].severity == "warning"

    def test_finding_has_correct_rule(self) -> None:
        """Untraced requirement finding has rule 'untraced-requirement'."""
        fixture_path = FIXTURES_DIR / "untraced_spec"
        findings = check_untraced_requirements("test_spec", fixture_path)

        assert findings[0].rule == "untraced-requirement"

    def test_finding_identifies_missing_req(self) -> None:
        """Untraced requirement finding message mentions the missing ID."""
        fixture_path = FIXTURES_DIR / "untraced_spec"
        findings = check_untraced_requirements("test_spec", fixture_path)

        assert "09-REQ-1.2" in findings[0].message


# -- TS-09-12: Findings sorted correctly --------------------------------------


class TestFindingsSortedCorrectly:
    """TS-09-12: Findings sorted correctly.

    Requirements: 09-REQ-1.3
    Verify findings are sorted by spec_name, file, severity
    (error < warning < hint).
    """

    def test_sort_by_spec_name_file_severity(self) -> None:
        """Findings are sorted by spec_name, then file, then severity."""
        findings = [
            Finding("b_spec", "tasks.md", "rule", "hint", "msg", None),
            Finding("a_spec", "tasks.md", "rule", "warning", "msg", None),
            Finding("a_spec", "prd.md", "rule", "error", "msg", None),
            Finding("a_spec", "tasks.md", "rule", "error", "msg", None),
        ]
        sorted_findings = sort_findings(findings)

        assert sorted_findings[0].spec_name == "a_spec"
        assert sorted_findings[0].file == "prd.md"
        assert sorted_findings[1].spec_name == "a_spec"
        assert sorted_findings[1].file == "tasks.md"
        assert sorted_findings[1].severity == "error"
        assert sorted_findings[2].severity == "warning"
        assert sorted_findings[3].spec_name == "b_spec"


# -- TS-09-E8: Valid dependencies produce no findings --------------------------


class TestValidDependenciesNoFindings:
    """TS-09-E8: Valid dependencies produce no findings.

    Requirements: 09-REQ-6.1
    Verify check_broken_dependencies returns empty for valid references.
    """

    def test_valid_deps_no_findings(self) -> None:
        """Valid dependency reference produces no findings."""
        fixture_path = FIXTURES_DIR / "valid_deps_spec"
        known_specs = {"01_core_foundation": [1, 2, 3]}
        findings = check_broken_dependencies("test_spec", fixture_path, known_specs)

        assert len(findings) == 0
