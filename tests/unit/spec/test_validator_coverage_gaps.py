"""Unit tests for the 8 new lint-spec rules closing the af-spec coverage gap.

Issue #335: lint-specs is missing 8 rules referenced by af-spec completeness checklist.

Test Spec: AC-1 through AC-20 (from issue #335 triage acceptance criteria)
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import SubtaskDef, TaskGroupDef
from agent_fox.spec.validators import (
    check_first_group_title,
    check_last_group_title,
    check_non_bracket_req_id_format,
    check_section_schema,
    check_too_many_requirements,
    check_untraced_edge_cases,
    validate_specs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SPEC_NAME = "05_test_spec"


def _make_group(title: str, number: int = 1, completed: bool = False) -> TaskGroupDef:
    """Create a minimal TaskGroupDef with one subtask."""
    return TaskGroupDef(
        number=number,
        title=title,
        optional=False,
        completed=completed,
        subtasks=(
            SubtaskDef(id=f"{number}.1", title="Do something", completed=False),
            SubtaskDef(id=f"{number}.V", title="Verify", completed=False),
        ),
        body=f"- [ ] {number}. {title}\n  - [ ] {number}.1 Do something\n  - [ ] {number}.V Verify\n",
    )


def _write_design(path: Path, *, with_execution_paths: bool) -> None:
    """Write a minimal design.md."""
    sections = [
        "## Overview\n\nSome overview.\n",
        "## Architecture\n\nSome architecture.\n",
        "## Correctness Properties\n\n### Property 1: Data integrity\n\n",
        "## Error Handling\n\n| Error | Code | Req |\n|---|---|---|\n| Boom | E1 | [05-REQ-1.1] |\n",
        "## Definition of Done\n\n- All tests pass.\n",
    ]
    if with_execution_paths:
        sections.append("## Execution Paths\n\nHappy path described here.\n")
    (path / "design.md").write_text("\n".join(sections), encoding="utf-8")


def _write_test_spec(path: Path, *, with_smoke_tests: bool) -> None:
    """Write a minimal test_spec.md."""
    sections = [
        "## Test Cases\n\nTS-05-1: Something works.\n",
        "## Coverage Matrix\n\n| Req | Test |\n|---|---|\n| [05-REQ-1.1] | TS-05-1 |\n",
    ]
    if with_smoke_tests:
        sections.append("## Integration Smoke Tests\n\nSmoke test here.\n")
    (path / "test_spec.md").write_text("\n".join(sections), encoding="utf-8")


def _write_requirements(path: Path, content: str) -> None:
    (path / "requirements.md").write_text(content, encoding="utf-8")


def _write_tasks(path: Path, content: str) -> None:
    (path / "tasks.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-1: Missing Execution Paths in design.md → WARNING
# ---------------------------------------------------------------------------


class TestExecutionPathsMissing:
    """AC-1: Missing Execution Paths section in design.md produces a WARNING."""

    def test_produces_one_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_design(spec_path, with_execution_paths=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        ep_findings = [f for f in findings if "Execution Paths" in f.message]
        assert len(ep_findings) == 1

    def test_severity_is_warning(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_design(spec_path, with_execution_paths=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        ep_findings = [f for f in findings if "Execution Paths" in f.message]
        assert ep_findings[0].severity == "warning"

    def test_rule_is_missing_section(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_design(spec_path, with_execution_paths=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        ep_findings = [f for f in findings if "Execution Paths" in f.message]
        assert ep_findings[0].rule == "missing-section"

    def test_file_is_design_md(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_design(spec_path, with_execution_paths=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        ep_findings = [f for f in findings if "Execution Paths" in f.message]
        assert ep_findings[0].file == "design.md"


# ---------------------------------------------------------------------------
# AC-2: Present Execution Paths section → no finding
# ---------------------------------------------------------------------------


class TestExecutionPathsPresent:
    """AC-2: Present Execution Paths section produces no Execution Paths finding."""

    def test_no_execution_paths_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_design(spec_path, with_execution_paths=True)
        findings = check_section_schema(SPEC_NAME, spec_path)
        ep_findings = [f for f in findings if "Execution Paths" in f.message]
        assert len(ep_findings) == 0


# ---------------------------------------------------------------------------
# AC-3: Missing Integration Smoke Tests in test_spec.md → WARNING
# ---------------------------------------------------------------------------


class TestIntegrationSmokeTestsMissing:
    """AC-3: Missing Integration Smoke Tests section in test_spec.md → WARNING."""

    def test_produces_one_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_test_spec(spec_path, with_smoke_tests=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
        assert len(smoke_findings) == 1

    def test_severity_is_warning(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_test_spec(spec_path, with_smoke_tests=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
        assert smoke_findings[0].severity == "warning"

    def test_rule_is_missing_section(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_test_spec(spec_path, with_smoke_tests=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
        assert smoke_findings[0].rule == "missing-section"

    def test_file_is_test_spec_md(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_test_spec(spec_path, with_smoke_tests=False)
        findings = check_section_schema(SPEC_NAME, spec_path)
        smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
        assert smoke_findings[0].file == "test_spec.md"


# ---------------------------------------------------------------------------
# AC-4: Present Integration Smoke Tests → no finding
# ---------------------------------------------------------------------------


class TestIntegrationSmokeTestsPresent:
    """AC-4: Present Integration Smoke Tests section produces no finding."""

    def test_no_smoke_test_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_test_spec(spec_path, with_smoke_tests=True)
        findings = check_section_schema(SPEC_NAME, spec_path)
        smoke_findings = [f for f in findings if "Integration Smoke Tests" in f.message]
        assert len(smoke_findings) == 0


# ---------------------------------------------------------------------------
# AC-5: More than 10 requirements → too-many-requirements WARNING
# ---------------------------------------------------------------------------


class TestTooManyRequirements:
    """AC-5: More than 10 requirements triggers too-many-requirements WARNING."""

    def _make_requirements(self, count: int) -> str:
        lines = ["## Requirements\n"]
        for i in range(1, count + 1):
            lines.append(
                f"### Requirement {i}: Req {i}\n\n"
                f"[05-REQ-{i}.1] The system SHALL do thing {i}.\n"
            )
        return "\n".join(lines)

    def test_eleven_requirements_produces_one_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert len(findings) == 1

    def test_rule_is_too_many_requirements(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert findings[0].rule == "too-many-requirements"

    def test_severity_is_warning(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert findings[0].severity == "warning"

    def test_message_contains_count(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert "11" in findings[0].message

    def test_message_contains_limit(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert "10" in findings[0].message

    def test_file_is_requirements_md(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(11))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert findings[0].file == "requirements.md"


# ---------------------------------------------------------------------------
# AC-6: Exactly 10 requirements → no finding
# ---------------------------------------------------------------------------


class TestExactlyTenRequirements:
    """AC-6: Exactly 10 requirements produces no too-many-requirements finding."""

    def _make_requirements(self, count: int) -> str:
        lines = ["## Requirements\n"]
        for i in range(1, count + 1):
            lines.append(
                f"### Requirement {i}: Req {i}\n\n"
                f"[05-REQ-{i}.1] The system SHALL do thing {i}.\n"
            )
        return "\n".join(lines)

    def test_ten_requirements_produces_no_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        _write_requirements(spec_path, self._make_requirements(10))
        findings = check_too_many_requirements(SPEC_NAME, spec_path)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-7: First group title missing 'fail'/'test' → wrong-first-group WARNING
# ---------------------------------------------------------------------------


class TestWrongFirstGroupTitle:
    """AC-7: First task group without 'fail' and 'test' keywords triggers WARNING."""

    def test_produces_one_finding(self) -> None:
        groups = [_make_group("Implement core module", number=1)]
        findings = check_first_group_title(SPEC_NAME, groups)
        assert len(findings) == 1

    def test_rule_is_wrong_first_group(self) -> None:
        groups = [_make_group("Implement core module", number=1)]
        findings = check_first_group_title(SPEC_NAME, groups)
        assert findings[0].rule == "wrong-first-group"

    def test_severity_is_warning(self) -> None:
        groups = [_make_group("Implement core module", number=1)]
        findings = check_first_group_title(SPEC_NAME, groups)
        assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# AC-8: First group title contains 'fail' and 'test' → no finding
# ---------------------------------------------------------------------------


class TestCorrectFirstGroupTitle:
    """AC-8: First task group with 'fail' and 'test' keywords produces no finding."""

    def test_no_finding_for_correct_title(self) -> None:
        groups = [_make_group("Write failing spec tests", number=1)]
        findings = check_first_group_title(SPEC_NAME, groups)
        assert len(findings) == 0

    def test_case_insensitive_matching(self) -> None:
        groups = [_make_group("Write FAILING TESTS for spec", number=1)]
        findings = check_first_group_title(SPEC_NAME, groups)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-9: Last group title missing 'wiring'/'verification' → wrong-last-group WARNING
# ---------------------------------------------------------------------------


class TestWrongLastGroupTitle:
    """AC-9: Last task group without required keywords triggers WARNING."""

    def test_produces_one_finding(self) -> None:
        groups = [
            _make_group("Write failing tests", number=1),
            _make_group("Final cleanup", number=2),
        ]
        findings = check_last_group_title(SPEC_NAME, groups)
        assert len(findings) == 1

    def test_rule_is_wrong_last_group(self) -> None:
        groups = [
            _make_group("Write failing tests", number=1),
            _make_group("Final cleanup", number=2),
        ]
        findings = check_last_group_title(SPEC_NAME, groups)
        assert findings[0].rule == "wrong-last-group"

    def test_severity_is_warning(self) -> None:
        groups = [
            _make_group("Write failing tests", number=1),
            _make_group("Final cleanup", number=2),
        ]
        findings = check_last_group_title(SPEC_NAME, groups)
        assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# AC-10: Last group title contains 'wiring' and 'verification' → no finding
# ---------------------------------------------------------------------------


class TestCorrectLastGroupTitle:
    """AC-10: Last task group with 'wiring' and 'verification' produces no finding."""

    def test_no_finding_for_correct_title(self) -> None:
        groups = [
            _make_group("Write failing tests", number=1),
            _make_group("Wiring verification", number=2),
        ]
        findings = check_last_group_title(SPEC_NAME, groups)
        assert len(findings) == 0

    def test_case_insensitive_matching(self) -> None:
        groups = [
            _make_group("Write failing tests", number=1),
            _make_group("WIRING AND VERIFICATION complete", number=2),
        ]
        findings = check_last_group_title(SPEC_NAME, groups)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-11: Edge case req not in Edge Case Tests section → untraced-edge-case WARNING
# ---------------------------------------------------------------------------


class TestUntracedEdgeCase:
    """AC-11: Edge case requirement not in Edge Case Tests triggers WARNING."""

    def _setup(self, tmp_path: Path, *, edge_case_in_test_spec: bool) -> Path:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        req_content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "[05-REQ-1.1] The system SHALL handle normal cases.\n\n"
            "[05-REQ-1.E1] The system SHALL handle edge case 1.\n"
        )
        _write_requirements(spec_path, req_content)

        if edge_case_in_test_spec:
            ts_content = (
                "## Test Cases\n\nTS-05-1: Normal test.\n\n"
                "## Edge Case Tests\n\n"
                "TS-05-E1: Tests [05-REQ-1.E1] edge case.\n\n"
                "## Coverage Matrix\n\n| Req | Test |\n|---|---|\n| [05-REQ-1.1] | TS-05-1 |\n"
            )
        else:
            ts_content = (
                "## Test Cases\n\nTS-05-1: Normal test.\n\n"
                "## Edge Case Tests\n\n"
                "TS-05-E1: Tests some other edge case (no reference here).\n\n"
                "## Coverage Matrix\n\n| Req | Test |\n|---|---|\n| [05-REQ-1.1] | TS-05-1 |\n"
            )
        (spec_path / "test_spec.md").write_text(ts_content, encoding="utf-8")
        return spec_path

    def test_produces_one_finding(self, tmp_path: Path) -> None:
        spec_path = self._setup(tmp_path, edge_case_in_test_spec=False)
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert len(findings) == 1

    def test_rule_is_untraced_edge_case(self, tmp_path: Path) -> None:
        spec_path = self._setup(tmp_path, edge_case_in_test_spec=False)
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert findings[0].rule == "untraced-edge-case"

    def test_severity_is_warning(self, tmp_path: Path) -> None:
        spec_path = self._setup(tmp_path, edge_case_in_test_spec=False)
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert findings[0].severity == "warning"

    def test_message_names_edge_case_id(self, tmp_path: Path) -> None:
        spec_path = self._setup(tmp_path, edge_case_in_test_spec=False)
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert "05-REQ-1.E1" in findings[0].message


# ---------------------------------------------------------------------------
# AC-12: All edge case reqs traced → no finding
# ---------------------------------------------------------------------------


class TestTracedEdgeCases:
    """AC-12: All edge case requirements traced produces no finding."""

    def test_no_finding_when_traced(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        req_content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "[05-REQ-1.E1] The system SHALL handle edge case 1.\n"
        )
        _write_requirements(spec_path, req_content)
        ts_content = (
            "## Test Cases\n\nTS-05-1: Normal test.\n\n"
            "## Edge Case Tests\n\n"
            "[05-REQ-1.E1] is covered here.\n\n"
            "## Coverage Matrix\n\n| Req | Test |\n|---|---|\n"
        )
        (spec_path / "test_spec.md").write_text(ts_content, encoding="utf-8")
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-13: Missing Introduction in requirements.md → WARNING (not HINT)
# ---------------------------------------------------------------------------


class TestIntroductionSectionRequired:
    """AC-13: Missing Introduction in requirements.md produces WARNING."""

    def test_produces_warning_not_hint(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        # requirements.md without Introduction section
        content = (
            "## Glossary\n\n| Term | Definition |\n|---|---|\n| Foo | Bar |\n\n"
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n[05-REQ-1.1] The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_section_schema(SPEC_NAME, spec_path)
        intro_findings = [
            f for f in findings if f.file == "requirements.md" and "Introduction" in f.message
        ]
        assert len(intro_findings) == 1
        assert intro_findings[0].severity == "warning"

    def test_rule_is_missing_section(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n[05-REQ-1.1] The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_section_schema(SPEC_NAME, spec_path)
        intro_findings = [
            f for f in findings if f.file == "requirements.md" and "Introduction" in f.message
        ]
        assert intro_findings[0].rule == "missing-section"


# ---------------------------------------------------------------------------
# AC-14: Missing Glossary in requirements.md → WARNING (not HINT)
# ---------------------------------------------------------------------------


class TestGlossarySectionRequired:
    """AC-14: Missing Glossary in requirements.md produces WARNING."""

    def test_produces_warning_not_hint(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        # requirements.md without Glossary section
        content = (
            "## Introduction\n\nThis spec covers X.\n\n"
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n[05-REQ-1.1] The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_section_schema(SPEC_NAME, spec_path)
        glossary_findings = [
            f for f in findings if f.file == "requirements.md" and "Glossary" in f.message
        ]
        assert len(glossary_findings) == 1
        assert glossary_findings[0].severity == "warning"

    def test_rule_is_missing_section(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        content = (
            "## Introduction\n\nThis spec covers X.\n\n"
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n[05-REQ-1.1] The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_section_schema(SPEC_NAME, spec_path)
        glossary_findings = [
            f for f in findings if f.file == "requirements.md" and "Glossary" in f.message
        ]
        assert glossary_findings[0].rule == "missing-section"


# ---------------------------------------------------------------------------
# AC-15: Bold-only requirement IDs → non-bracket-req-id-format WARNING
# ---------------------------------------------------------------------------


class TestNonBracketReqIdFormat:
    """AC-15: Bold-only requirement IDs trigger a WARNING."""

    def test_bold_only_produces_warning(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "**05-REQ-1.1:** The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_non_bracket_req_id_format(SPEC_NAME, spec_path)
        assert len(findings) >= 1
        assert findings[0].severity == "warning"

    def test_rule_is_non_bracket_req_id_format(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "**05-REQ-1.1:** The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_non_bracket_req_id_format(SPEC_NAME, spec_path)
        assert findings[0].rule == "non-bracket-req-id-format"

    def test_bracket_format_produces_no_finding(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "[05-REQ-1.1] The system SHALL work.\n"
        )
        _write_requirements(spec_path, content)
        findings = check_non_bracket_req_id_format(SPEC_NAME, spec_path)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-16: Empty task groups list → no first-group or last-group findings
# ---------------------------------------------------------------------------


class TestEmptyTaskGroupsProduceNoFindings:
    """AC-16: Empty task groups list produces no first-group or last-group findings."""

    def test_first_group_empty_list(self) -> None:
        findings = check_first_group_title(SPEC_NAME, [])
        assert findings == []

    def test_last_group_empty_list(self) -> None:
        findings = check_last_group_title(SPEC_NAME, [])
        assert findings == []


# ---------------------------------------------------------------------------
# AC-17: No edge case requirements → no untraced-edge-case findings
# ---------------------------------------------------------------------------


class TestNoEdgeCaseRequirementsProducesNoFindings:
    """AC-17: No edge case requirements produces no untraced-edge-case findings."""

    def test_no_findings_when_no_edge_cases(self, tmp_path: Path) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        req_content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "[05-REQ-1.1] The system SHALL do something.\n"
        )
        _write_requirements(spec_path, req_content)
        ts_content = "## Test Cases\n\nTS-05-1: Test something.\n"
        (spec_path / "test_spec.md").write_text(ts_content, encoding="utf-8")
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# AC-18: No Edge Case Tests section → all edge case reqs reported as untraced
# ---------------------------------------------------------------------------


class TestNoEdgeCaseTestsSectionReportsAllUntraced:
    """AC-18: No Edge Case Tests section means all edge case reqs are untraced."""

    def test_two_edge_cases_without_section_produces_two_findings(
        self, tmp_path: Path
    ) -> None:
        spec_path = tmp_path / SPEC_NAME
        spec_path.mkdir()
        req_content = (
            "## Requirements\n\n"
            "### Requirement 1: Core\n\n"
            "[05-REQ-1.E1] The system SHALL handle edge 1.\n"
            "[05-REQ-2.E1] The system SHALL handle edge 2.\n"
        )
        _write_requirements(spec_path, req_content)
        # test_spec.md with no Edge Case Tests section
        ts_content = "## Test Cases\n\nTS-05-1: Normal test.\n"
        (spec_path / "test_spec.md").write_text(ts_content, encoding="utf-8")
        findings = check_untraced_edge_cases(SPEC_NAME, spec_path)
        assert len(findings) == 2
        assert all(f.rule == "untraced-edge-case" for f in findings)


# ---------------------------------------------------------------------------
# AC-19: New validators are wired into validate_specs()
# ---------------------------------------------------------------------------


class TestNewValidatorsWiredIntoRunner:
    """AC-19: New validator functions are wired into validate_specs()."""

    def _build_violating_spec(self, tmp_path: Path) -> tuple[Path, SpecInfo]:
        """Create a spec that violates all new rules."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_path = specs_dir / "05_test_spec"
        spec_path.mkdir()

        # requirements.md: 11 requirements, edge case req, no Introduction/Glossary
        req_lines = ["## Requirements\n"]
        for i in range(1, 12):
            req_lines.append(
                f"### Requirement {i}: Thing {i}\n\n"
                f"[05-REQ-{i}.1] The system SHALL do thing {i}.\n"
            )
        req_lines.append("[05-REQ-1.E1] The system SHALL handle edge 1.\n")
        _write_requirements(spec_path, "\n".join(req_lines))

        # design.md: missing Execution Paths
        _write_design(spec_path, with_execution_paths=False)

        # test_spec.md: missing Integration Smoke Tests, edge case not traced
        ts_content = (
            "## Test Cases\n\nTS-05-1: Test thing.\n\n"
            "## Edge Case Tests\n\n(placeholder, no real tests here)\n\n"
            "## Coverage Matrix\n\n| Req | Test |\n|---|---|\n| [05-REQ-1.1] | TS-05-1 |\n"
        )
        (spec_path / "test_spec.md").write_text(ts_content, encoding="utf-8")

        # tasks.md: wrong first and last group titles
        tasks_content = (
            "## Tasks\n\n"
            "- [ ] 1. Implement core module\n"
            "  - [ ] 1.1 Build the thing\n"
            "  - [ ] 1.V Verify group 1\n"
            "- [ ] 2. Final cleanup\n"
            "  - [ ] 2.1 Clean things up\n"
            "  - [ ] 2.V Verify group 2\n"
            "\n## Traceability\n\n"
            "| Req | Task |\n|---|---|\n| [05-REQ-1.1] | 1.1 |\n"
        )
        _write_tasks(spec_path, tasks_content)

        # prd.md (needed to avoid missing-file finding noise)
        (spec_path / "prd.md").write_text("# PRD\n\nSpec description.\n", encoding="utf-8")

        spec_info = SpecInfo(
            name="05_test_spec",
            prefix=5,
            path=spec_path,
            has_tasks=True,
            has_prd=True,
        )
        return specs_dir, spec_info

    def test_too_many_requirements_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        rules = {f.rule for f in findings}
        assert "too-many-requirements" in rules

    def test_wrong_first_group_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        rules = {f.rule for f in findings}
        assert "wrong-first-group" in rules

    def test_wrong_last_group_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        rules = {f.rule for f in findings}
        assert "wrong-last-group" in rules

    def test_untraced_edge_case_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        rules = {f.rule for f in findings}
        assert "untraced-edge-case" in rules

    def test_execution_paths_finding_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        messages = [f.message for f in findings]
        assert any("Execution Paths" in m for m in messages)

    def test_integration_smoke_tests_finding_in_runner(self, tmp_path: Path) -> None:
        specs_dir, spec_info = self._build_violating_spec(tmp_path)
        findings = validate_specs(specs_dir, [spec_info])
        messages = [f.message for f in findings]
        assert any("Integration Smoke Tests" in m for m in messages)


# ---------------------------------------------------------------------------
# AC-20: New public functions are exported from validators __init__.py
# ---------------------------------------------------------------------------


class TestNewFunctionsAreExported:
    """AC-20: New public functions are importable from agent_fox.spec.validators."""

    def test_check_too_many_requirements_importable(self) -> None:
        from agent_fox.spec.validators import check_too_many_requirements  # noqa: F401

    def test_check_first_group_title_importable(self) -> None:
        from agent_fox.spec.validators import check_first_group_title  # noqa: F401

    def test_check_last_group_title_importable(self) -> None:
        from agent_fox.spec.validators import check_last_group_title  # noqa: F401

    def test_check_untraced_edge_cases_importable(self) -> None:
        from agent_fox.spec.validators import check_untraced_edge_cases  # noqa: F401

    def test_check_non_bracket_req_id_format_importable(self) -> None:
        from agent_fox.spec.validators import check_non_bracket_req_id_format  # noqa: F401
