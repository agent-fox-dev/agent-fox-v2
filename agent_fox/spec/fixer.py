"""Spec fixer: auto-fix functions for mechanically fixable lint findings.

Stub module -- implementation pending (task group 4).

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.validator import Finding


@dataclass(frozen=True)
class FixResult:
    """Result of applying a single fix."""

    rule: str
    spec_name: str
    file: str
    description: str


FIXABLE_RULES = {"coarse-dependency", "missing-verification"}


def fix_coarse_dependency(
    spec_name: str,
    prd_path: Path,
    known_specs: dict[str, list[int]],
    current_spec_groups: list[int],
) -> list[FixResult]:
    """Rewrite a standard-format dependency table to group-level format.

    Stub -- raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("fix_coarse_dependency not yet implemented")


def fix_missing_verification(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Append a verification step to task groups that lack one.

    Stub -- raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("fix_missing_verification not yet implemented")


def apply_fixes(
    findings: list[Finding],
    discovered_specs: list[SpecInfo],
    specs_dir: Path,
    known_specs: dict[str, list[int]],
) -> list[FixResult]:
    """Apply all available auto-fixes for the given findings.

    Stub -- raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("apply_fixes not yet implemented")
