"""Validators package -- re-exports all public symbols for backward compatibility.

This package splits the monolithic ``agent_fox.spec.validator`` module into
domain-grouped sub-modules while preserving the original public API.
"""

from agent_fox.spec.discovery import SpecInfo  # noqa: F401
from agent_fox.spec.parser import (
    TaskGroupDef,  # noqa: F401
    parse_tasks,  # noqa: F401
)
from agent_fox.spec.validators._helpers import (
    EXPECTED_FILES,
    MAX_REQUIREMENTS,
    MAX_SUBTASKS_PER_GROUP,
    SEVERITY_ERROR,
    SEVERITY_HINT,
    SEVERITY_ORDER,
    SEVERITY_WARNING,
    _spec_prefix,
)
from agent_fox.spec.validators.dependencies import (  # noqa: F401
    _check_circular_dependency,
    _check_coarse_dependency,
    check_broken_dependencies,
)
from agent_fox.spec.validators.files import check_missing_files  # noqa: F401
from agent_fox.spec.validators.finding import (
    Finding,
    compute_exit_code,
    sort_findings,
)
from agent_fox.spec.validators.requirements import (  # noqa: F401
    check_inconsistent_req_id_format,
    check_missing_acceptance_criteria,
    check_missing_ears_keyword,
    check_non_bracket_req_id_format,
    check_too_many_requirements,
)
from agent_fox.spec.validators.runner import validate_specs  # noqa: F401
from agent_fox.spec.validators.schema import (  # noqa: F401
    _check_section_with_table,
    check_design_completeness,
    check_section_schema,
)
from agent_fox.spec.validators.tasks import (  # noqa: F401
    check_archetype_tags,
    check_checkbox_states,
    check_first_group_title,
    check_last_group_title,
    check_missing_verification,
    check_oversized_groups,
)
from agent_fox.spec.validators.traceability import (  # noqa: F401
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

__all__ = [
    # Constants
    "EXPECTED_FILES",
    "MAX_REQUIREMENTS",
    "MAX_SUBTASKS_PER_GROUP",
    "SEVERITY_ERROR",
    "SEVERITY_HINT",
    "SEVERITY_ORDER",
    "SEVERITY_WARNING",
    # Finding
    "Finding",
    "compute_exit_code",
    "sort_findings",
    # Re-exported types
    "SpecInfo",
    "TaskGroupDef",
    "parse_tasks",
    # Validation rules
    "check_missing_files",
    "check_oversized_groups",
    "check_missing_verification",
    "check_first_group_title",
    "check_last_group_title",
    "check_archetype_tags",
    "check_checkbox_states",
    "check_missing_acceptance_criteria",
    "check_missing_ears_keyword",
    "check_inconsistent_req_id_format",
    "check_non_bracket_req_id_format",
    "check_too_many_requirements",
    "check_broken_dependencies",
    "check_untraced_requirements",
    "check_untraced_test_specs",
    "check_untraced_properties",
    "check_untraced_edge_cases",
    "check_orphan_error_refs",
    "check_coverage_matrix_completeness",
    "check_traceability_table_completeness",
    "check_missing_coverage_matrix",
    "check_missing_traceability_table",
    "check_design_completeness",
    "check_section_schema",
    "validate_specs",
    # Private but used by tests
    "_check_coarse_dependency",
    "_check_circular_dependency",
    "_check_section_with_table",
    "_spec_prefix",
]
