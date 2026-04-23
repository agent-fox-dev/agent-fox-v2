"""Task-structure validation rules (groups, verification, archetypes, checkboxes)."""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec._patterns import (
    CHECKBOX_LINE as _CHECKBOX_LINE,
)
from agent_fox.spec._patterns import (
    MALFORMED_ARCHETYPE_TAG as _MALFORMED_ARCHETYPE_TAG,
)
from agent_fox.spec._patterns import (
    VALID_CHECKBOX_CHARS as _VALID_CHECKBOX_CHARS,
)
from agent_fox.spec.parser import (
    _ARCHETYPE_TAG,
    _KNOWN_ARCHETYPES,
    TaskGroupDef,
)
from agent_fox.spec.validators._helpers import (
    MAX_SUBTASKS_PER_GROUP,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Finding,
)


def check_oversized_groups(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups with more than MAX_SUBTASKS_PER_GROUP subtasks.

    Rule: oversized-group
    Severity: warning
    Excludes verification steps from the subtask count.
    """
    findings: list[Finding] = []
    for group in task_groups:
        if group.completed:
            continue
        # Count non-verification subtasks: exclude N.V pattern
        non_verify_count = sum(1 for st in group.subtasks if not re.match(rf"^{group.number}\.V$", st.id))
        if non_verify_count > MAX_SUBTASKS_PER_GROUP:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="tasks.md",
                    rule="oversized-group",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Task group {group.number} has {non_verify_count} subtasks (max {MAX_SUBTASKS_PER_GROUP})"
                    ),
                    line=None,
                )
            )
    return findings


def check_missing_verification(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups without a verification step.

    Rule: missing-verification
    Severity: warning
    A verification step matches the pattern N.V (e.g., "1.V Verify task group 1").
    """
    findings: list[Finding] = []
    for group in task_groups:
        if group.completed:
            continue
        # Checkpoint groups are themselves a final verification step
        if group.title.startswith("Checkpoint"):
            continue
        has_verify = any(re.match(rf"^{group.number}\.V$", st.id) for st in group.subtasks)
        if not has_verify:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="tasks.md",
                    rule="missing-verification",
                    severity=SEVERITY_WARNING,
                    message=(f"Task group {group.number} is missing a verification step ({group.number}.V)"),
                    line=None,
                )
            )
    return findings


def check_archetype_tags(
    spec_name: str,
    tasks_path: Path,
) -> list[Finding]:
    """Check archetype tags on task group titles for validity.

    Rules:
    - malformed-archetype-tag (error): tag syntax deviates from [archetype: X]
    - invalid-archetype-tag (warning): archetype name not in registry
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    for i, line in enumerate(lines, 1):
        # Only check top-level task group lines
        if not re.match(r"^- \[.\]", line):
            continue

        # Check for well-formed archetype tag
        good_match = _ARCHETYPE_TAG.search(line)
        if good_match:
            arch_name = good_match.group(1)
            if arch_name not in _KNOWN_ARCHETYPES:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="invalid-archetype-tag",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Unknown archetype '{arch_name}' in task group title "
                            f"(known: {', '.join(sorted(_KNOWN_ARCHETYPES))})"
                        ),
                        line=i,
                    )
                )
            # Check for duplicate tags on same line
            all_matches = _ARCHETYPE_TAG.findall(line)
            if len(all_matches) > 1:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="malformed-archetype-tag",
                        severity=SEVERITY_ERROR,
                        message=(f"Duplicate archetype tags on line {i}: {', '.join(all_matches)}"),
                        line=i,
                    )
                )
        else:
            # Check for malformed variants
            bad_match = _MALFORMED_ARCHETYPE_TAG.search(line)
            if bad_match:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="malformed-archetype-tag",
                        severity=SEVERITY_ERROR,
                        message=(
                            f"Malformed archetype tag "
                            f"'{bad_match.group()}' on line {i}; "
                            f"expected format: [archetype: name]"
                        ),
                        line=i,
                    )
                )

    return findings


def check_first_group_title(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check that the first task group title contains 'fail' and 'test'.

    Rule: wrong-first-group
    Severity: warning
    The first task group should write failing tests from test_spec.md.
    Returns no finding if the task_groups list is empty.
    """
    if not task_groups:
        return []
    first = task_groups[0]
    title_lower = first.title.lower()
    if "fail" in title_lower and "test" in title_lower:
        return []
    return [
        Finding(
            spec_name=spec_name,
            file="tasks.md",
            rule="wrong-first-group",
            severity=SEVERITY_WARNING,
            message=(
                f"First task group title '{first.title}' must contain 'fail' and 'test' "
                f"(group 1 should write failing tests from test_spec.md)"
            ),
            line=None,
        )
    ]


def check_last_group_title(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check that the last task group title contains 'wiring' and 'verification'.

    Rule: wrong-last-group
    Severity: warning
    The final task group should be the wiring/verification step.
    Returns no finding if the task_groups list is empty.
    """
    if not task_groups:
        return []
    last = task_groups[-1]
    title_lower = last.title.lower()
    if "wiring" in title_lower and "verification" in title_lower:
        return []
    return [
        Finding(
            spec_name=spec_name,
            file="tasks.md",
            rule="wrong-last-group",
            severity=SEVERITY_WARNING,
            message=(
                f"Last task group title '{last.title}' must contain 'wiring' and 'verification' "
                f"(final group should wire everything together and verify)"
            ),
            line=None,
        )
    ]


def check_checkbox_states(
    spec_name: str,
    tasks_path: Path,
) -> list[Finding]:
    """Check checkbox states in tasks.md for valid characters.

    Rule: invalid-checkbox-state (error)
    Valid characters: ' ' (space), 'x', '-', '~'
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    for i, line in enumerate(lines, 1):
        m = _CHECKBOX_LINE.match(line)
        if m:
            char = m.group(2)
            if char not in _VALID_CHECKBOX_CHARS:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="invalid-checkbox-state",
                        severity=SEVERITY_ERROR,
                        message=(f"Invalid checkbox state '[{char}]' on line {i}; valid states: [ ], [x], [-], [~]"),
                        line=i,
                    )
                )

    return findings
