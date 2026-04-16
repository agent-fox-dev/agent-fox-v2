"""Validation orchestrator -- runs all rules against discovered specs."""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo

# Re-export TaskGroupDef for backward compatibility (it was importable from
# the original validator module via the parser import).
from agent_fox.spec.parser import (
    TaskGroupDef,  # noqa: F401
    parse_tasks,
)
from agent_fox.spec.validators._helpers import SEVERITY_WARNING
from agent_fox.spec.validators.dependencies import (
    _check_circular_dependency,
    _check_coarse_dependency,
    check_broken_dependencies,
)
from agent_fox.spec.validators.files import check_missing_files
from agent_fox.spec.validators.finding import Finding, sort_findings
from agent_fox.spec.validators.requirements import (
    check_inconsistent_req_id_format,
    check_missing_acceptance_criteria,
    check_missing_ears_keyword,
    check_non_bracket_req_id_format,
    check_too_many_requirements,
)
from agent_fox.spec.validators.schema import (
    check_design_completeness,
    check_section_schema,
)
from agent_fox.spec.validators.tasks import (
    check_archetype_tags,
    check_checkbox_states,
    check_first_group_title,
    check_last_group_title,
    check_missing_verification,
    check_oversized_groups,
)
from agent_fox.spec.validators.traceability import (
    check_coverage_matrix_completeness,
    check_missing_coverage_matrix,
    check_missing_traceability_table,
    check_orphan_error_refs,
    check_traceability_table_completeness,
    check_untraced_edge_cases,
    check_untraced_properties,
    check_untraced_requirements,
    check_untraced_test_specs,
)


def validate_specs(
    specs_dir: Path,
    discovered_specs: list[SpecInfo],
) -> list[Finding]:
    """Run all static validation rules against all discovered specs.

    1. For each spec, run check_missing_files.
    2. For specs with tasks.md, parse task groups and run:
       - check_oversized_groups
       - check_missing_verification
    3. For specs with requirements.md, run:
       - check_missing_acceptance_criteria
    4. For specs with requirements.md and test_spec.md, run:
       - check_untraced_requirements
    5. Build known_specs map, then for each spec with prd.md, run:
       - check_broken_dependencies
    6. Sort all findings by spec_name, file, severity order.
    7. Return the complete findings list.

    Requirements: 09-REQ-1.1, 09-REQ-1.2, 09-REQ-1.3
    """
    findings: list[Finding] = []

    # Build known_specs map from ALL specs in the directory, not just the
    # filtered subset.  Dependency validation needs to resolve references to
    # specs that may have been filtered out (e.g. already-implemented specs).
    # Also include archived specs (in specs_dir/archive/) so that references
    # to fully-implemented, archived dependencies are not flagged as broken.
    known_specs: dict[str, list[int]] = {}
    _spec_dir_pattern = re.compile(r"^\d+_.+$")
    scan_dirs = [specs_dir]
    archive_dir = specs_dir / "archive"
    if archive_dir.is_dir():
        scan_dirs.append(archive_dir)
    for scan_dir in scan_dirs:
        for entry in sorted(scan_dir.iterdir()):
            if not entry.is_dir() or not _spec_dir_pattern.match(entry.name):
                continue
            # Don't overwrite active specs with archived copies of the same name
            if entry.name in known_specs:
                continue
            tasks_path = entry / "tasks.md"
            if tasks_path.is_file():
                try:
                    groups = parse_tasks(tasks_path)
                    known_specs[entry.name] = [g.number for g in groups]
                except Exception:
                    known_specs[entry.name] = []
            else:
                known_specs[entry.name] = []

    # Parse task groups for the specs being linted
    parsed_groups: dict[str, list[TaskGroupDef]] = {}
    for spec in discovered_specs:
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            try:
                groups = parse_tasks(tasks_path)
                parsed_groups[spec.name] = groups
            except Exception:
                findings.append(
                    Finding(
                        spec_name=spec.name,
                        file="tasks.md",
                        rule="parse-error",
                        severity=SEVERITY_WARNING,
                        message="Failed to parse tasks.md",
                        line=None,
                    )
                )

    # Run all rules against each spec
    for spec in discovered_specs:
        # 1. Missing files check
        findings.extend(check_missing_files(spec.name, spec.path))

        # 2. Task-based checks (oversized groups, missing verification, group titles)
        if spec.name in parsed_groups:
            groups = parsed_groups[spec.name]
            findings.extend(check_oversized_groups(spec.name, groups))
            findings.extend(check_missing_verification(spec.name, groups))
            findings.extend(check_first_group_title(spec.name, groups))
            findings.extend(check_last_group_title(spec.name, groups))

        # 2b. Archetype tag and checkbox state checks
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            findings.extend(check_archetype_tags(spec.name, tasks_path))
            findings.extend(check_checkbox_states(spec.name, tasks_path))

        # 3. Acceptance criteria check
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_missing_acceptance_criteria(spec.name, spec.path))

        # 4. Traceability check
        if (spec.path / "requirements.md").is_file() and (spec.path / "test_spec.md").is_file():
            findings.extend(check_untraced_requirements(spec.name, spec.path))

        # 5. Dependency check
        if (spec.path / "prd.md").is_file():
            findings.extend(check_broken_dependencies(spec.name, spec.path, known_specs))

        # 6. Coarse dependency check
        if (spec.path / "prd.md").is_file():
            findings.extend(_check_coarse_dependency(spec.name, spec.path / "prd.md"))

        # -- Phase 1: Completeness checks --
        # 7. EARS keyword check
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_missing_ears_keyword(spec.name, spec.path))

        # 8. Design completeness (correctness properties, error table, DoD)
        if (spec.path / "design.md").is_file():
            findings.extend(check_design_completeness(spec.name, spec.path))

        # 9. Coverage matrix check
        if (spec.path / "test_spec.md").is_file():
            findings.extend(check_missing_coverage_matrix(spec.name, spec.path))

        # 10. Traceability table check
        if (spec.path / "tasks.md").is_file():
            findings.extend(check_missing_traceability_table(spec.name, spec.path))

        # 11. Requirement ID format consistency
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_inconsistent_req_id_format(spec.name, spec.path))
            findings.extend(check_non_bracket_req_id_format(spec.name, spec.path))
            findings.extend(check_too_many_requirements(spec.name, spec.path))

        # -- Phase 3: Traceability chain checks --
        # 12. Test spec -> tasks traceability
        if (spec.path / "test_spec.md").is_file() and (spec.path / "tasks.md").is_file():
            findings.extend(check_untraced_test_specs(spec.name, spec.path))

        # 13. Property -> test spec traceability
        if (spec.path / "design.md").is_file() and (spec.path / "test_spec.md").is_file():
            findings.extend(check_untraced_properties(spec.name, spec.path))

        # 14. Error table -> requirements cross-reference
        if (spec.path / "design.md").is_file() and (spec.path / "requirements.md").is_file():
            findings.extend(check_orphan_error_refs(spec.name, spec.path))

        # 15. Coverage matrix completeness
        if (spec.path / "requirements.md").is_file() and (spec.path / "test_spec.md").is_file():
            findings.extend(check_coverage_matrix_completeness(spec.name, spec.path))

        # 16. Traceability table completeness
        if (spec.path / "requirements.md").is_file() and (spec.path / "tasks.md").is_file():
            findings.extend(check_traceability_table_completeness(spec.name, spec.path))

        # 16b. Edge case traceability
        if (spec.path / "requirements.md").is_file() and (spec.path / "test_spec.md").is_file():
            findings.extend(check_untraced_edge_cases(spec.name, spec.path))

        # -- Phase 4: Section schema validation --
        # 17. Section schema checks
        findings.extend(check_section_schema(spec.name, spec.path))

    # 18. Circular dependency check (cross-spec, runs once for all specs)
    findings.extend(_check_circular_dependency(discovered_specs))

    # 19. Sort findings
    return sort_findings(findings)
