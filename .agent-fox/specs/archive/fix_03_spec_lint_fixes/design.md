# Design Document: Spec Lint Fixes

## Overview

Three targeted fixes to existing modules plus a skill document update. No new
modules or architectural changes.

## Components and Changes

### 1. Parser subtask regex (`agent_fox/spec/parser.py`)

Current regex:
```python
_SUBTASK_PATTERN = re.compile(r"^\s+- \[([ x\-])\] (\d+\.\d+) (.+)$")
```

Updated regex — accept `N.V` in addition to `N.N`:
```python
_SUBTASK_PATTERN = re.compile(r"^\s+- \[([ x\-])\] (\d+\.(?:\d+|V)) (.+)$")
```

The change: `\d+` after the dot becomes `(?:\d+|V)` — either digits or
literal `V`.

### 2. Validator completed-group skip (`agent_fox/spec/validator.py`)

Add an early-continue in `check_oversized_groups` and
`check_missing_verification`:

```python
for group in task_groups:
    if group.completed:
        continue
    # ... existing check logic
```

### 3. Alternative dependency table validation (`agent_fox/spec/validator.py`)

Add a second header pattern:
```python
_DEP_TABLE_HEADER_ALT = re.compile(
    r"\|\s*Spec\s*\|\s*From Group\s*\|\s*To Group\s*\|", re.IGNORECASE
)
```

Extend `check_broken_dependencies` to detect and parse both table formats.
For the alternative format, extract explicit group numbers from the
`From Group` and `To Group` columns and validate them against `known_specs`.

Also validate the `To Group` column against the current spec's own task
groups (passed as a new parameter).

### 4. Skill document update (`SKILL.md`)

Add a validation checkpoint in the Cross-Spec Dependencies section of Step 2:

> **Validation checkpoint:** After writing the dependency table, verify:
> 1. Every spec name in the `Spec` column exists as a folder in `.specs/`.
> 2. Every `From Group` number exists in the referenced spec's `tasks.md`.
> 3. Every `To Group` number exists in the current spec's `tasks.md`.

## Correctness Properties

### Property 1: Verification step parsing

*For any* tasks.md containing subtask lines with ID `N.V`, the parser SHALL
include a `SubtaskDef` with `id == "N.V"` in the corresponding group's
subtask list.

**Validates: F3-REQ-1.1**

### Property 2: Completed group exemption

*For any* task group with `completed == True`, `check_oversized_groups` and
`check_missing_verification` SHALL return zero findings for that group.

**Validates: F3-REQ-2.1, F3-REQ-2.2**

### Property 3: Alternative table dangling reference detection

*For any* alternative-format dependency table row referencing a spec name not
in `known_specs`, the validator SHALL produce an ERROR finding.

**Validates: F3-REQ-3.2**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| Unknown subtask ID format (e.g., `1.X`) | Silently skip line | F3-REQ-1.E1 |
| Both table formats in one prd.md | Validate both | F3-REQ-3.E1 |

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests for the task group pass
3. All previously passing tests still pass (no regressions)
4. No linter warnings or errors introduced
5. Code is committed on a feature branch and pushed to remote
6. Feature branch is merged back to `develop`
7. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- Unit tests for parser regex changes (new and regression)
- Unit tests for validator skip-on-completed behavior
- Unit tests for alternative table format validation
- Existing tests must continue to pass (no regressions)
- Skill document change verified by reading the file
