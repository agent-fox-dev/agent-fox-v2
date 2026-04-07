# Design Document: lint-specs Coverage Gaps

## Overview

This spec adds 6 new validation rules to the existing `lint-specs` validator
infrastructure. Two rules extend the section schema, two validate task group
structure, one enforces a requirement count limit, and one adds edge case
traceability. All rules integrate into the existing `validate_specs` runner
and produce `Finding` objects at `warning` severity.

## Architecture

The existing validator architecture is modular:

```
runner.py (orchestrator)
  ├── _helpers.py (constants, schemas, regex)
  ├── files.py (missing file checks)
  ├── requirements.py (EARS, acceptance criteria, ID format)
  ├── schema.py (section schema, design completeness)
  ├── tasks.py (group sizing, verification, archetypes, checkboxes)
  ├── traceability.py (req↔test↔task traceability)
  └── dependencies.py (broken, coarse, circular deps)
```

New rules slot into existing modules — no new modules are needed.

### Module Responsibilities

1. **`_helpers.py`** — Add `("Execution Paths", True)` to `design.md` schema
   and `("Integration Smoke Tests", True)` to `test_spec.md` schema.
2. **`requirements.py`** — Add `check_too_many_requirements()` function.
3. **`tasks.py`** — Add `check_first_group_title()` and
   `check_last_group_title()` functions.
4. **`traceability.py`** — Add `check_untraced_edge_cases()` function.
5. **`runner.py`** — Wire the 4 new functions into `validate_specs()`.
6. **`__init__.py`** — Re-export the 3 new public functions.

## Execution Paths

### Path 1: Section schema rules (Execution Paths, Integration Smoke Tests)

1. `cli/lint_specs.py: lint_specs_cmd` — CLI entry point
2. `spec/lint.py: run_lint_specs()` — orchestrates validation
3. `spec/validators/runner.py: validate_specs()` — iterates specs
4. `spec/validators/schema.py: check_section_schema()` — reads `_SECTION_SCHEMAS`
5. `spec/validators/_helpers.py: _SECTION_SCHEMAS` — dict lookup returns
   `("Execution Paths", True)` / `("Integration Smoke Tests", True)` entries
6. Side effect: `Finding` appended to findings list with rule `missing-section`

### Path 2: Requirement count limit

1. `cli/lint_specs.py: lint_specs_cmd` — CLI entry point
2. `spec/lint.py: run_lint_specs()` — orchestrates validation
3. `spec/validators/runner.py: validate_specs()` — iterates specs
4. `spec/validators/requirements.py: check_too_many_requirements()` → `list[Finding]`
5. Side effect: `Finding` with rule `too-many-requirements` if count > 10

### Path 3: Task group title checks (first and last)

1. `cli/lint_specs.py: lint_specs_cmd` — CLI entry point
2. `spec/lint.py: run_lint_specs()` — orchestrates validation
3. `spec/validators/runner.py: validate_specs()` — iterates specs, passes
   parsed `task_groups` list
4. `spec/validators/tasks.py: check_first_group_title(spec_name, task_groups)` → `list[Finding]`
5. `spec/validators/tasks.py: check_last_group_title(spec_name, task_groups)` → `list[Finding]`
6. Side effect: `Finding` with rule `wrong-first-group` / `wrong-last-group`

### Path 4: Edge case traceability

1. `cli/lint_specs.py: lint_specs_cmd` — CLI entry point
2. `spec/lint.py: run_lint_specs()` — orchestrates validation
3. `spec/validators/runner.py: validate_specs()` — iterates specs
4. `spec/validators/traceability.py: check_untraced_edge_cases(spec_name, spec_path)` → `list[Finding]`
5. Side effect: `Finding` with rule `untraced-edge-case` for each untraced
   edge case requirement

## Components and Interfaces

### New Functions

```python
# requirements.py
def check_too_many_requirements(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that requirements.md has no more than 10 requirements."""

# tasks.py
def check_first_group_title(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check that the first task group title contains 'fail' and 'test'."""

def check_last_group_title(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check that the last task group title contains 'wiring' and 'verification'."""

# traceability.py
def check_untraced_edge_cases(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that edge case reqs appear in the Edge Case Tests section."""
```

### Modified Constants

```python
# _helpers.py — _SECTION_SCHEMAS additions
"design.md": [
    ...,
    ("Execution Paths", True),   # NEW
],
"test_spec.md": [
    ...,
    ("Integration Smoke Tests", True),  # NEW
],
```

### Constants

```python
MAX_REQUIREMENTS = 10  # in _helpers.py
```

## Data Models

No new data models. All new rules produce `Finding` objects using the existing
dataclass.

## Correctness Properties

### Property 1: Section Schema Completeness

*For any* spec with a `design.md` file, the validator SHALL produce a
`missing-section` finding for `Execution Paths` if and only if the file
lacks a `## Execution Paths` heading.

**Validates: Requirements 83-REQ-1.1, 83-REQ-1.2**

### Property 2: Smoke Tests Section Completeness

*For any* spec with a `test_spec.md` file, the validator SHALL produce a
`missing-section` finding for `Integration Smoke Tests` if and only if the
file lacks a `## Integration Smoke Tests` heading.

**Validates: Requirements 83-REQ-2.1, 83-REQ-2.2**

### Property 3: Requirement Count Monotonicity

*For any* `requirements.md` content with N `### Requirement` headings where
N > 10, the validator SHALL produce exactly one `too-many-requirements`
finding. For N <= 10, no such finding SHALL be produced.

**Validates: Requirements 83-REQ-3.1, 83-REQ-3.2**

### Property 4: First Group Keyword Invariant

*For any* parsed task groups list where the first group's title (lowercased)
contains both "fail" and "test", the validator SHALL produce zero
`wrong-first-group` findings. If either keyword is absent, exactly one
finding SHALL be produced.

**Validates: Requirements 83-REQ-4.1, 83-REQ-4.2**

### Property 5: Last Group Keyword Invariant

*For any* parsed task groups list where the last group's title (lowercased)
contains both "wiring" and "verification", the validator SHALL produce zero
`wrong-last-group` findings. If either keyword is absent, exactly one
finding SHALL be produced.

**Validates: Requirements 83-REQ-5.1, 83-REQ-5.2**

### Property 6: Edge Case Traceability Completeness

*For any* spec where `requirements.md` contains K edge case requirement IDs
and the `## Edge Case Tests` section of `test_spec.md` references M of them,
the validator SHALL produce exactly K - M `untraced-edge-case` findings.

**Validates: Requirements 83-REQ-6.1, 83-REQ-6.2**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| design.md missing | Skip Execution Paths check | 83-REQ-1.E1 |
| test_spec.md missing | Skip smoke tests / edge case checks | 83-REQ-2.E1, 83-REQ-6.E1 |
| requirements.md missing | Skip count / edge case checks | 83-REQ-3.E1, 83-REQ-6.E1 |
| tasks.md missing or unparseable | Skip group title checks | 83-REQ-4.E1, 83-REQ-5.E1 |
| Zero task groups | Skip group title checks | 83-REQ-4.E2, 83-REQ-5.E2 |
| Zero requirements | No too-many-requirements finding | 83-REQ-3.E2 |
| Zero edge case reqs | No untraced-edge-case findings | 83-REQ-6.E2 |
| No Edge Case Tests section | All edge case reqs reported as untraced | 83-REQ-6.E3 |

## Technology Stack

- Python 3.12+
- Existing validator infrastructure (no new dependencies)
- `re` module for regex patterns
- `pathlib.Path` for file access

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and merged into `develop`
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests** validate each new rule function in isolation using
  in-memory spec content written to `tmp_path` fixtures.
- **Property tests** use Hypothesis to generate random requirement counts,
  task group titles, and edge case ID sets to verify invariants.
- **Integration smoke test** runs `validate_specs()` on a fixture spec
  that triggers all 6 new rules and verifies findings are returned.
