# Implementation Plan: lint-specs Coverage Gaps

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds 6 new validation rules to the existing `lint-specs`
infrastructure. Two rules are pure schema additions (entries in
`_SECTION_SCHEMAS`), and four are new functions in existing modules. All are
wired into `runner.py` and re-exported from `__init__.py`.

Task group 1 writes failing tests. Task group 2 implements the section schema
additions. Task group 3 implements the 4 new validator functions and wires
them into the runner. Task group 4 is wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/spec/test_validator_coverage_rules.py tests/property/spec/test_validator_coverage_props.py tests/integration/spec/test_validator_coverage_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/spec/test_validator_coverage_rules.py`
- Property tests: `uv run pytest -q tests/property/spec/test_validator_coverage_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file `tests/unit/spec/test_validator_coverage_rules.py`
    - Import test helpers and validator functions
    - Write test classes for TS-83-1 through TS-83-12 and TS-83-E1 through TS-83-E6
    - Each test creates a minimal spec folder in `tmp_path` with the required files
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-83-1 through TS-83-12, TS-83-E1 through TS-83-E6_

  - [ ] 1.2 Create property test file `tests/property/spec/test_validator_coverage_props.py`
    - Write property tests for TS-83-P1 through TS-83-P4
    - Use Hypothesis strategies for input generation
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-83-P1 through TS-83-P4_

  - [ ] 1.3 Create integration smoke test `tests/integration/spec/test_validator_coverage_smoke.py`
    - Write smoke test for TS-83-SMOKE-1
    - Create a fixture spec that violates all 6 new rules
    - Test MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-83-SMOKE-1_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Implement section schema additions
  - [ ] 2.1 Add `("Execution Paths", True)` to `_SECTION_SCHEMAS["design.md"]` in `_helpers.py`
    - Insert after `("Architecture", True)` to match the document structure order
    - _Requirements: 83-REQ-1.1, 83-REQ-1.2, 83-REQ-1.E1_

  - [ ] 2.2 Add `("Integration Smoke Tests", True)` to `_SECTION_SCHEMAS["test_spec.md"]` in `_helpers.py`
    - Insert after `("Coverage Matrix", True)` to match the document structure order
    - _Requirements: 83-REQ-2.1, 83-REQ-2.2, 83-REQ-2.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for section schema pass: `uv run pytest -q tests/unit/spec/test_validator_coverage_rules.py -k "execution_paths or smoke_tests_section"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/`
    - [ ] Requirements 83-REQ-1.1, 83-REQ-1.2, 83-REQ-2.1, 83-REQ-2.2 acceptance criteria met

- [ ] 3. Implement new validator functions and wire into runner
  - [ ] 3.1 Add `MAX_REQUIREMENTS = 10` constant to `_helpers.py`
    - _Requirements: 83-REQ-3.1_

  - [ ] 3.2 Add `check_too_many_requirements()` to `requirements.py`
    - Count `### Requirement N:` headings using `_REQUIREMENT_HEADING` regex
    - Return finding if count > MAX_REQUIREMENTS
    - _Requirements: 83-REQ-3.1, 83-REQ-3.2, 83-REQ-3.E1, 83-REQ-3.E2_

  - [ ] 3.3 Add `check_first_group_title()` and `check_last_group_title()` to `tasks.py`
    - Check first group: title must contain "fail" and "test" (case-insensitive)
    - Check last group: title must contain "wiring" and "verification" (case-insensitive)
    - Skip if completed or empty groups list
    - _Requirements: 83-REQ-4.1, 83-REQ-4.2, 83-REQ-4.E1, 83-REQ-4.E2, 83-REQ-5.1, 83-REQ-5.2, 83-REQ-5.E1, 83-REQ-5.E2_

  - [ ] 3.4 Add `check_untraced_edge_cases()` to `traceability.py`
    - Extract edge case req IDs (`NN-REQ-X.EN`) from requirements.md
    - Extract `## Edge Case Tests` section text from test_spec.md
    - Report edge case reqs not referenced in that section
    - _Requirements: 83-REQ-6.1, 83-REQ-6.2, 83-REQ-6.E1, 83-REQ-6.E2, 83-REQ-6.E3_

  - [ ] 3.5 Wire new functions into `runner.py` `validate_specs()`
    - Add `check_too_many_requirements` after existing requirements checks
    - Add `check_first_group_title` and `check_last_group_title` after existing task checks
    - Add `check_untraced_edge_cases` after existing traceability checks
    - _Requirements: all_

  - [ ] 3.6 Re-export new functions from `__init__.py`
    - Add `check_too_many_requirements`, `check_first_group_title`,
      `check_last_group_title`, `check_untraced_edge_cases` to imports and `__all__`
    - _Requirements: all_

  - [ ] 3.V Verify task group 3
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/spec/test_validator_coverage_rules.py tests/property/spec/test_validator_coverage_props.py tests/integration/spec/test_validator_coverage_smoke.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 83-REQ-3.1 through 83-REQ-6.E3 acceptance criteria met

- [ ] 4. Wiring verification

  - [ ] 4.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [ ] 4.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [ ] 4.3 Run the integration smoke tests
    - All `TS-83-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-83-SMOKE-1_

  - [ ] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 4.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 83-REQ-1.1 | TS-83-1 | 2.1 | test_validator_coverage_rules.py::TestMissingExecutionPaths::test_missing |
| 83-REQ-1.2 | TS-83-2 | 2.1 | test_validator_coverage_rules.py::TestMissingExecutionPaths::test_present |
| 83-REQ-1.E1 | TS-83-E1 | 2.1 | test_validator_coverage_rules.py::TestMissingExecutionPaths::test_no_design_md |
| 83-REQ-2.1 | TS-83-3 | 2.2 | test_validator_coverage_rules.py::TestMissingSmokeTestsSection::test_missing |
| 83-REQ-2.2 | TS-83-4 | 2.2 | test_validator_coverage_rules.py::TestMissingSmokeTestsSection::test_present |
| 83-REQ-2.E1 | TS-83-E2 | 2.2 | test_validator_coverage_rules.py::TestMissingSmokeTestsSection::test_no_test_spec_md |
| 83-REQ-3.1 | TS-83-5 | 3.1, 3.2 | test_validator_coverage_rules.py::TestTooManyRequirements::test_over_limit |
| 83-REQ-3.2 | TS-83-6 | 3.2 | test_validator_coverage_rules.py::TestTooManyRequirements::test_at_limit |
| 83-REQ-3.E1 | TS-83-E3 | 3.2 | test_validator_coverage_rules.py::TestTooManyRequirements::test_no_file |
| 83-REQ-3.E2 | TS-83-6 | 3.2 | test_validator_coverage_rules.py::TestTooManyRequirements::test_at_limit |
| 83-REQ-4.1 | TS-83-7 | 3.3 | test_validator_coverage_rules.py::TestWrongFirstGroup::test_wrong |
| 83-REQ-4.2 | TS-83-8 | 3.3 | test_validator_coverage_rules.py::TestWrongFirstGroup::test_correct |
| 83-REQ-4.E1 | TS-83-E4 | 3.3 | test_validator_coverage_rules.py::TestWrongFirstGroup::test_empty |
| 83-REQ-4.E2 | TS-83-E4 | 3.3 | test_validator_coverage_rules.py::TestWrongFirstGroup::test_empty |
| 83-REQ-5.1 | TS-83-9 | 3.3 | test_validator_coverage_rules.py::TestWrongLastGroup::test_wrong |
| 83-REQ-5.2 | TS-83-10 | 3.3 | test_validator_coverage_rules.py::TestWrongLastGroup::test_correct |
| 83-REQ-5.E1 | TS-83-E4 | 3.3 | test_validator_coverage_rules.py::TestWrongLastGroup::test_empty |
| 83-REQ-5.E2 | TS-83-E4 | 3.3 | test_validator_coverage_rules.py::TestWrongLastGroup::test_empty |
| 83-REQ-6.1 | TS-83-11 | 3.4 | test_validator_coverage_rules.py::TestUntracedEdgeCases::test_untraced |
| 83-REQ-6.2 | TS-83-12 | 3.4 | test_validator_coverage_rules.py::TestUntracedEdgeCases::test_all_traced |
| 83-REQ-6.E1 | TS-83-E5 | 3.4 | test_validator_coverage_rules.py::TestUntracedEdgeCases::test_no_edge_cases |
| 83-REQ-6.E2 | TS-83-E5 | 3.4 | test_validator_coverage_rules.py::TestUntracedEdgeCases::test_no_edge_cases |
| 83-REQ-6.E3 | TS-83-E6 | 3.4 | test_validator_coverage_rules.py::TestUntracedEdgeCases::test_no_section |

## Notes

- Section schema additions (rules 1-2) are trivial — just adding entries to the
  existing `_SECTION_SCHEMAS` dict. The `check_section_schema` function handles
  the rest automatically.
- Task group title checks (rules 4-5) operate on already-parsed `TaskGroupDef`
  objects, avoiding redundant file parsing.
- The edge case traceability check (rule 6) reuses existing regex patterns from
  `_helpers.py` and `_patterns.py`.
- All new rules follow the existing pattern: function takes `spec_name` +
  `spec_path` or `task_groups`, returns `list[Finding]`.
- Completed specs are automatically excluded by the existing filter in
  `run_lint_specs()` — no changes needed.
