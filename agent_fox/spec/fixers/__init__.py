"""Spec fixers package: auto-fix functions for mechanically fixable lint findings.

Each fixer reads a file, applies a transformation, and writes back.
The package is separate from the validator to maintain single-responsibility:
validator detects, fixer corrects.

Requirements: 20-REQ-6.*
"""

from .ai import fix_ai_criteria, fix_ai_test_spec_entries
from .archetype import fix_invalid_archetype_tag, fix_malformed_archetype_tag
from .checkbox import fix_invalid_checkbox_state
from .runner import apply_fixes
from .sections import (
    fix_missing_correctness_properties,
    fix_missing_coverage_matrix,
    fix_missing_definition_of_done,
    fix_missing_error_table,
    fix_missing_traceability_table,
)
from .standard import (
    fix_coarse_dependency,
    fix_inconsistent_req_id_format,
    fix_missing_verification,
    fix_stale_dependency,
    parse_finding_criterion_id,
)
from .tables import fix_coverage_matrix_mismatch, fix_traceability_table_mismatch
from .types import AI_FIXABLE_RULES, FIXABLE_RULES, FixResult, IdentifierFix

__all__ = [
    "AI_FIXABLE_RULES",
    "FIXABLE_RULES",
    "FixResult",
    "IdentifierFix",
    "apply_fixes",
    "fix_ai_criteria",
    "fix_ai_test_spec_entries",
    "fix_coarse_dependency",
    "fix_coverage_matrix_mismatch",
    "fix_inconsistent_req_id_format",
    "fix_invalid_archetype_tag",
    "fix_invalid_checkbox_state",
    "fix_malformed_archetype_tag",
    "fix_missing_correctness_properties",
    "fix_missing_coverage_matrix",
    "fix_missing_definition_of_done",
    "fix_missing_error_table",
    "fix_missing_traceability_table",
    "fix_missing_verification",
    "fix_stale_dependency",
    "fix_traceability_table_mismatch",
    "parse_finding_criterion_id",
]
