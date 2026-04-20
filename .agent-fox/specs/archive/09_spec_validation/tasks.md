# Implementation Plan: Specification Validation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the `agent-fox lint-spec` command for validating
specification files. Task group 1 writes all tests (unit, property,
integration). Task groups 2-4 implement the static rules, AI analysis, and CLI
command to make those tests pass.

## Test Commands

- Unit tests: `uv run pytest tests/unit/spec/ -q`
- Property tests: `uv run pytest tests/property/spec/ -q`
- Integration tests: `uv run pytest tests/integration/test_lint_spec.py -q`
- All spec 09 tests: `uv run pytest tests/unit/spec/ tests/property/spec/ tests/integration/test_lint_spec.py -q`
- Linter: `uv run ruff check agent_fox/spec/ agent_fox/cli/lint_spec.py`
- Type check: `uv run mypy agent_fox/spec/ agent_fox/cli/lint_spec.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
    - Create `tests/fixtures/specs/complete_spec/` with all 5 expected files
      (minimal valid content)
    - Create `tests/fixtures/specs/incomplete_spec/` with only `prd.md` and
      `tasks.md` (missing 3 files)
    - Create `tests/fixtures/specs/oversized_spec/` with `tasks.md` containing
      a task group with 8 subtasks and another with 6 subtasks
    - Create `tests/fixtures/specs/no_verify_spec/` with `tasks.md` containing
      a task group without a verification step
    - Create `tests/fixtures/specs/missing_criteria_spec/` with
      `requirements.md` having a requirement section with no criteria
    - Create `tests/fixtures/specs/broken_deps_spec/` with `prd.md` referencing
      non-existent spec `99_nonexistent` and non-existent group 99 in
      `01_core_foundation`
    - Create `tests/fixtures/specs/untraced_spec/` with `requirements.md`
      containing IDs not referenced in `test_spec.md`
    - Create `tests/fixtures/specs/warnings_only_spec/` with all files present
      but oversized groups (warnings only, no errors)
    - Create `tests/fixtures/specs/valid_deps_spec/` with `prd.md` referencing
      `01_core_foundation` group 1 (valid reference)

  - [x] 1.2 Write static rule unit tests
    - `tests/unit/spec/test_validator.py`:
      - TS-09-1 (missing files detected)
      - TS-09-2 (all files present)
      - TS-09-3 (oversized group detected)
      - TS-09-4 (6 subtasks acceptable)
      - TS-09-5 (verification step excluded from count)
      - TS-09-6 (missing verification detected)
      - TS-09-7 (verification present)
      - TS-09-8 (missing acceptance criteria)
      - TS-09-9 (broken dep to non-existent spec)
      - TS-09-10 (broken dep to non-existent group)
      - TS-09-11 (untraced requirement)
      - TS-09-12 (findings sorted correctly)
    - _Test Spec: TS-09-1 through TS-09-12_

  - [x] 1.3 Write AI validator unit tests
    - `tests/unit/spec/test_ai_validator.py`:
      - TS-09-E3 (AI unavailable graceful fallback)
      - Test that AI findings have severity `"hint"` and correct rule names
      - Test prompt construction includes acceptance criteria text
      - Test response parsing handles valid and malformed AI responses
    - _Test Spec: TS-09-E3_

  - [x] 1.4 Write property tests
    - `tests/property/spec/test_validator_props.py`:
      - TS-09-P1 (error findings imply non-zero exit)
      - TS-09-P2 (no errors imply zero exit)
      - TS-09-P3 (missing files count matches reality)
      - TS-09-P4 (oversized group threshold is exact)
      - TS-09-P5 (Finding immutability)
    - _Test Spec: TS-09-P1 through TS-09-P5_

  - [x] 1.5 Write CLI integration tests
    - `tests/integration/test_lint_spec.py`:
      - TS-09-E1 (no specs directory)
      - TS-09-E2 (empty specs directory)
      - TS-09-E4 (JSON output format)
      - TS-09-E5 (YAML output format)
      - TS-09-E6 (table output includes summary)
      - TS-09-E7 (exit code 0 when only warnings)
      - TS-09-E8 (valid dependencies produce no findings)
    - _Test Spec: TS-09-E1 through TS-09-E8_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement static validation rules
  - [x] 2.1 Create Finding data model
    - `agent_fox/spec/__init__.py`
    - `agent_fox/spec/validator.py`: `Finding` frozen dataclass, severity
      constants (`SEVERITY_ERROR`, `SEVERITY_WARNING`, `SEVERITY_HINT`),
      `EXPECTED_FILES` list, `MAX_SUBTASKS_PER_GROUP` constant
    - _Requirements: 09-REQ-2.1 (data model)_

  - [x] 2.2 Implement `check_missing_files`
    - Check for 5 expected files, return Error findings for missing ones
    - _Requirements: 09-REQ-2.1, 09-REQ-2.2_

  - [x] 2.3 Implement `check_oversized_groups`
    - Count subtasks excluding verification steps (N.V pattern)
    - Return Warning finding when count exceeds 6
    - _Requirements: 09-REQ-3.1, 09-REQ-3.2_

  - [x] 2.4 Implement `check_missing_verification`
    - Check for subtask matching N.V pattern in each task group
    - Return Warning finding when missing
    - _Requirements: 09-REQ-4.1, 09-REQ-4.2_

  - [x] 2.5 Implement `check_missing_acceptance_criteria`
    - Parse requirement sections from requirements.md
    - Check each section has at least one `[NN-REQ-N.N]` pattern
    - Return Error findings for sections without criteria
    - _Requirements: 09-REQ-5.1, 09-REQ-5.2_

  - [x] 2.6 Implement `check_broken_dependencies`
    - Parse dependency table from prd.md
    - Validate spec names and group numbers against known_specs
    - Return Error findings for invalid references
    - _Requirements: 09-REQ-6.1, 09-REQ-6.2, 09-REQ-6.3_

  - [x] 2.V Verify task group 2
    - [x] Static rule unit tests pass: `uv run pytest tests/unit/spec/test_validator.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/spec/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/validator.py`
    - [x] Requirements 09-REQ-2.* through 09-REQ-6.* acceptance criteria met

- [x] 3. Implement requirement traceability and AI analysis
  - [x] 3.1 Implement `check_untraced_requirements`
    - Collect requirement IDs from requirements.md via regex
    - Collect requirement references from test_spec.md via regex
    - Return Warning findings for IDs not found in test references
    - _Requirements: 09-REQ-7.1, 09-REQ-7.2_

  - [x] 3.2 Implement `validate_specs` orchestrator
    - Wire all static rules together: discovery, file checks, task checks,
      requirement checks, dependency checks, traceability checks
    - Build known_specs map from discovered specs
    - Sort findings by spec name, file, severity
    - _Requirements: 09-REQ-1.1, 09-REQ-1.2, 09-REQ-1.3_

  - [x] 3.3 Implement AI validator
    - `agent_fox/spec/ai_validator.py`: `analyze_acceptance_criteria()` and
      `run_ai_validation()` functions
    - Construct a structured prompt asking the model to identify vague and
      implementation-leaking criteria
    - Parse JSON response into Hint-severity findings
    - Handle API errors gracefully (log warning, return empty list)
    - _Requirements: 09-REQ-8.1, 09-REQ-8.2, 09-REQ-8.3, 09-REQ-8.E1_

  - [x] 3.V Verify task group 3
    - [x] Traceability unit tests pass: `uv run pytest tests/unit/spec/test_validator.py -q`
    - [x] AI validator tests pass: `uv run pytest tests/unit/spec/test_ai_validator.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/`
    - [x] Requirements 09-REQ-7.*, 09-REQ-8.* acceptance criteria met

- [x] 4. Implement CLI command and output formatting
  - [x] 4.1 Implement output formatters
    - `agent_fox/cli/lint_spec.py`: `format_table()`, `format_json()`,
      `format_yaml()` functions
    - Table: Rich table grouped by spec, with summary line
    - JSON: structured output with findings list and summary counts
    - YAML: same structure as JSON, serialized as YAML
    - _Requirements: 09-REQ-9.1, 09-REQ-9.2, 09-REQ-9.3_

  - [x] 4.2 Implement `lint-spec` CLI command
    - Register `lint-spec` as a Click command on the main group
    - Accept `--format` (table/json/yaml, default table) and `--ai` flag
    - Discover specs, run static validation, optionally run AI validation
    - Format and print output
    - Set exit code: 1 if any errors, 0 otherwise
    - _Requirements: 09-REQ-9.4, 09-REQ-9.5, 09-REQ-1.E1_

  - [x] 4.3 Register command in CLI app
    - Add `lint_spec` command to the `main` Click group in
      `agent_fox/cli/app.py`
    - Verify `agent-fox lint-spec --help` works

  - [x] 4.V Verify task group 4
    - [x] All spec tests pass: `uv run pytest tests/unit/spec/ tests/property/spec/ tests/integration/test_lint_spec.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/ agent_fox/cli/lint_spec.py`
    - [x] Type check passes: `uv run mypy agent_fox/spec/ agent_fox/cli/lint_spec.py`
    - [x] CLI is invocable: `uv run agent-fox lint-spec --help`
    - [x] Requirements 09-REQ-9.* acceptance criteria met

- [x] 5. Checkpoint -- Specification Validation Complete
  - [x] Ensure all tests pass: `uv run pytest tests/unit/spec/ tests/property/spec/ tests/integration/test_lint_spec.py -q`
  - [x] Ensure no regressions: `uv run pytest tests/ -q`
  - [x] Ensure linter clean: `uv run ruff check agent_fox/ tests/`
  - [x] Ensure type check clean: `uv run mypy agent_fox/`
  - [x] Verify `uv run agent-fox lint-spec` works end-to-end on the project's own
    `.specs/` directory

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 09-REQ-1.1 | TS-09-E1, TS-09-E2 | 3.2 | tests/integration/test_lint_spec.py |
| 09-REQ-1.2 | TS-09-12 | 3.2 | tests/unit/spec/test_validator.py |
| 09-REQ-1.3 | TS-09-12 | 3.2 | tests/unit/spec/test_validator.py |
| 09-REQ-1.E1 | TS-09-E1, TS-09-E2 | 4.2 | tests/integration/test_lint_spec.py |
| 09-REQ-2.1 | TS-09-1, TS-09-2 | 2.2 | tests/unit/spec/test_validator.py |
| 09-REQ-2.2 | TS-09-1 | 2.2 | tests/unit/spec/test_validator.py |
| 09-REQ-3.1 | TS-09-3, TS-09-4, TS-09-5 | 2.3 | tests/unit/spec/test_validator.py |
| 09-REQ-3.2 | TS-09-3, TS-09-4 | 2.3 | tests/unit/spec/test_validator.py |
| 09-REQ-4.1 | TS-09-6, TS-09-7 | 2.4 | tests/unit/spec/test_validator.py |
| 09-REQ-4.2 | TS-09-6 | 2.4 | tests/unit/spec/test_validator.py |
| 09-REQ-5.1 | TS-09-8 | 2.5 | tests/unit/spec/test_validator.py |
| 09-REQ-5.2 | TS-09-8 | 2.5 | tests/unit/spec/test_validator.py |
| 09-REQ-6.1 | TS-09-9, TS-09-E8 | 2.6 | tests/unit/spec/test_validator.py |
| 09-REQ-6.2 | TS-09-9 | 2.6 | tests/unit/spec/test_validator.py |
| 09-REQ-6.3 | TS-09-10 | 2.6 | tests/unit/spec/test_validator.py |
| 09-REQ-7.1 | TS-09-11 | 3.1 | tests/unit/spec/test_validator.py |
| 09-REQ-7.2 | TS-09-11 | 3.1 | tests/unit/spec/test_validator.py |
| 09-REQ-8.1 | (AI mock tests) | 3.3 | tests/unit/spec/test_ai_validator.py |
| 09-REQ-8.2 | (AI mock tests) | 3.3 | tests/unit/spec/test_ai_validator.py |
| 09-REQ-8.3 | (AI mock tests) | 3.3 | tests/unit/spec/test_ai_validator.py |
| 09-REQ-8.E1 | TS-09-E3 | 3.3 | tests/unit/spec/test_ai_validator.py |
| 09-REQ-9.1 | TS-09-E4, TS-09-E5, TS-09-E6 | 4.1 | tests/integration/test_lint_spec.py |
| 09-REQ-9.2 | TS-09-E6 | 4.1 | tests/integration/test_lint_spec.py |
| 09-REQ-9.3 | TS-09-E4, TS-09-E5 | 4.1 | tests/integration/test_lint_spec.py |
| 09-REQ-9.4 | TS-09-E1, TS-09-E2 | 4.2 | tests/integration/test_lint_spec.py |
| 09-REQ-9.5 | TS-09-E7 | 4.2 | tests/integration/test_lint_spec.py |
| Property 1 | TS-09-P5 | 2.1 | tests/property/spec/test_validator_props.py |
| Property 3 | TS-09-P1 | 4.2 | tests/property/spec/test_validator_props.py |
| Property 4 | TS-09-P2 | 4.2 | tests/property/spec/test_validator_props.py |
| Property 5 | TS-09-P3 | 2.2 | tests/property/spec/test_validator_props.py |
| Property 6 | TS-09-P4 | 2.3 | tests/property/spec/test_validator_props.py |

## Notes

- Task group 1 creates test fixtures and all test files. These tests should
  fail initially because no implementation exists yet.
- The `discover_specs()` and `parse_tasks()` functions come from spec 02. If
  spec 02 is not yet implemented, stub/mock these in tests.
- AI validator tests must mock the Anthropic client -- never make real API
  calls in tests.
- Use `click.testing.CliRunner` for CLI integration tests.
- Use `tmp_path` fixtures for tests that need temporary spec directories.
- Fixture directories under `tests/fixtures/specs/` are checked into version
  control for reproducibility.
