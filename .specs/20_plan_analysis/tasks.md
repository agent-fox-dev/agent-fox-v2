# Implementation Plan: Plan Analysis and Dependency Quality

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md -- all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec adds parallelism analysis and critical path computation to the
plan command, two new lint rules for dependency quality, auto-fix for
mechanically fixable findings, and a prompt update to the af-spec skill.
Six task groups: tests, analyzer, lint rules, fixers, CLI integration, and
af-spec prompt update.

## Test Commands

- Unit tests: `uv run pytest tests/unit/graph/test_analyzer.py tests/unit/spec/test_validator_plan_rules.py tests/unit/spec/test_fixer.py -q`
- Property tests: `uv run pytest tests/property/graph/test_analyzer_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_plan_analyze.py tests/integration/test_lint_fix.py -q`
- All spec tests: `uv run pytest tests/unit/graph/test_analyzer.py tests/unit/spec/test_validator_plan_rules.py tests/unit/spec/test_fixer.py tests/property/graph/test_analyzer_props.py tests/integration/test_plan_analyze.py tests/integration/test_lint_fix.py -q`
- Linter: `uv run ruff check agent_fox/graph/analyzer.py agent_fox/spec/validator.py agent_fox/spec/fixer.py agent_fox/cli/plan.py agent_fox/cli/lint_spec.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create analyzer test fixtures
    - `tests/unit/graph/conftest.py` (extend): add fixtures for diamond,
      chain, wide, and complex DAGs with known phase structure
    - Diamond: A -> B, A -> C, B -> D, C -> D
    - Chain: A -> B -> C -> D
    - Wide: A -> {B, C, D, E} -> F
    - _Test Spec: TS-20-1 through TS-20-7_

  - [x] 1.2 Write analyzer unit tests
    - `tests/unit/graph/test_analyzer.py`: TS-20-1 (diamond phases),
      TS-20-2 (chain phases), TS-20-3 (wide peak), TS-20-4 (critical path),
      TS-20-5 (float on critical), TS-20-6 (float on non-critical),
      TS-20-7 (empty graph), TS-20-E1 (tied paths)
    - _Test Spec: TS-20-1 through TS-20-7, TS-20-E1_
    - _Requirements: 20-REQ-1.*, 20-REQ-2.*_

  - [x] 1.3 Write lint rule unit tests
    - `tests/unit/spec/test_validator_plan_rules.py`: TS-20-8 (coarse dep
      detected), TS-20-9 (group-level no finding), TS-20-10 (no deps no
      finding), TS-20-11 (circular dep detected), TS-20-12 (acyclic no
      finding), TS-20-13 (missing spec skipped)
    - Create test fixture prd.md files with standard format, group-level
      format, no deps, and circular deps
    - _Test Spec: TS-20-8 through TS-20-13_
    - _Requirements: 20-REQ-3.*, 20-REQ-4.*_

  - [x] 1.4 Write fixer unit tests
    - `tests/unit/spec/test_fixer.py`: TS-20-14 (coarse dep rewrite),
      TS-20-15 (unknown upstream groups), TS-20-16 (idempotency),
      TS-20-17 (missing verification append), TS-20-18 (skip existing
      verification), TS-20-19 (unfixable findings skipped),
      TS-20-20 (no fixable findings no-op)
    - Create test fixture prd.md and tasks.md files for fix scenarios
    - _Test Spec: TS-20-14 through TS-20-20_
    - _Requirements: 20-REQ-6.*_

  - [x] 1.5 Write property tests
    - `tests/property/graph/test_analyzer_props.py`: TS-20-P1 (phase
      completeness), TS-20-P2 (phase ordering), TS-20-P3 (critical path =
      makespan), TS-20-P4 (zero float = critical), TS-20-P5 (non-negative
      float)
    - Use Hypothesis to generate random DAGs
    - _Test Spec: TS-20-P1 through TS-20-P5_

  - [x] 1.6 Write integration tests
    - `tests/integration/test_plan_analyze.py`: verify `agent-fox plan
      --analyze` CLI output includes phase listing, critical path, and
      summary
    - `tests/integration/test_lint_fix.py`: verify `agent-fox lint-spec
      --fix` rewrites files and re-validates
    - _Requirements: 20-REQ-1.1, 20-REQ-6.1_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced

- [x] 2. Implement plan analyzer
  - [x] 2.1 Create analyzer module
    - `agent_fox/graph/analyzer.py`: `NodeTiming`, `Phase`, `PlanAnalysis`
      dataclasses
    - Implement `analyze_plan()`: forward pass (ES), backward pass (LS),
      float, phase grouping, critical path tracing
    - _Requirements: 20-REQ-1.2, 20-REQ-1.3, 20-REQ-1.4, 20-REQ-2.1,
      20-REQ-2.2, 20-REQ-2.3, 20-REQ-2.4_

  - [x] 2.2 Implement format_analysis
    - `agent_fox/graph/analyzer.py`: `format_analysis()` function
    - Format phases, critical path, and summary for terminal output
    - _Requirements: 20-REQ-1.1, 20-REQ-1.3_

  - [x] 2.3 Handle edge cases
    - Empty graph: return empty PlanAnalysis
    - Tied critical paths: detect and flag
    - _Requirements: 20-REQ-1.E1, 20-REQ-1.E2, 20-REQ-2.E1_

  - [x] 2.V Verify task group 2
    - [x] Analyzer unit tests pass
    - [x] Property tests pass
    - [x] No linter warnings

- [x] 3. Implement lint rules
  - [x] 3.1 Implement coarse-dependency rule
    - Extend `agent_fox/spec/validator.py`: add `_check_coarse_dependency()`
    - Detect standard format header (`| This Spec | Depends On |`)
    - Produce Warning-severity finding with actionable message
    - Wire into `validate_specs()` pipeline
    - _Requirements: 20-REQ-3.1, 20-REQ-3.2, 20-REQ-3.3_

  - [x] 3.2 Implement circular-dependency rule
    - Extend `agent_fox/spec/validator.py`: add
      `_check_circular_dependency()`
    - Build spec-level directed graph from all prd.md dependency tables
    - Run cycle detection (Kahn's algorithm or DFS coloring)
    - Produce Error-severity finding listing cycle specs
    - Skip edges to non-existent specs
    - Wire into `validate_specs()` pipeline
    - _Requirements: 20-REQ-4.1, 20-REQ-4.2, 20-REQ-4.3_

  - [x] 3.V Verify task group 3
    - [x] Lint rule unit tests pass
    - [x] No linter warnings
    - [x] Existing lint-spec tests still pass (no regressions)

- [x] 4. Implement fixers
  - [x] 4.1 Create fixer module
    - `agent_fox/spec/fixer.py`: `FixResult` dataclass, `FIXABLE_RULES` set
    - _Requirements: 20-REQ-6.1_

  - [x] 4.2 Implement fix_coarse_dependency
    - `agent_fox/spec/fixer.py`: parse standard table, look up upstream
      group numbers, rewrite to alt format, preserve description as
      Relationship
    - Handle unknown upstream groups (sentinel 0)
    - _Requirements: 20-REQ-6.3, 20-REQ-6.E2_

  - [x] 4.3 Implement fix_missing_verification
    - `agent_fox/spec/fixer.py`: find groups missing N.V, append
      verification step with standard checklist
    - _Requirements: 20-REQ-6.4_

  - [x] 4.4 Implement apply_fixes
    - `agent_fox/spec/fixer.py`: orchestrate fixers, deduplicate by
      (spec_name, rule), handle write errors gracefully
    - _Requirements: 20-REQ-6.2, 20-REQ-6.5, 20-REQ-6.E1, 20-REQ-6.E3,
      20-REQ-6.E4_

  - [x] 4.V Verify task group 4
    - [x] Fixer unit tests pass (TS-20-14 through TS-20-20)
    - [x] No linter warnings
    - [x] Existing tests still pass

- [ ] 5. Wire CLI and integration
  - [ ] 5.1 Add --analyze flag to plan command
    - Extend `agent_fox/cli/plan.py`: add `--analyze` option
    - Call `analyze_plan()` and `format_analysis()` after plan is built
    - Display analysis output after the standard plan summary
    - _Requirements: 20-REQ-1.1_

  - [ ] 5.2 Add --fix flag to lint-spec command
    - Extend `agent_fox/cli/lint_spec.py`: add `--fix` option
    - After detection, call `apply_fixes()` for fixable findings
    - Print fix summary to stderr
    - Re-validate and output remaining findings
    - _Requirements: 20-REQ-6.1, 20-REQ-6.2, 20-REQ-6.5, 20-REQ-6.6_

  - [ ] 5.3 Verify integration
    - Run integration tests for both --analyze and --fix
    - _Requirements: 20-REQ-1.1, 20-REQ-6.1_

  - [ ] 5.V Verify task group 5
    - [ ] Integration tests pass
    - [ ] All existing plan tests still pass
    - [ ] All existing lint-spec tests still pass
    - [ ] No linter warnings

- [ ] 6. Update af-spec skill and checkpoint
  - [ ] 6.1 Update af-spec Step 2 instructions
    - Edit `skills/af-spec/SKILL.md`: update Step 2 (Learn the Context)
    - Add guidance to identify earliest sufficient upstream group
    - Require group-level format in generated dependency tables
    - Require justification in Relationship column
    - _Requirements: 20-REQ-5.1, 20-REQ-5.2, 20-REQ-5.3_

  - [ ] 6.2 Update af-spec sentinel handling
    - Add note about using group 0 sentinel when upstream spec has no
      tasks.md yet
    - _Requirements: 20-REQ-5.E1_

  - [ ] 6.V Verify task group 6
    - [ ] Skill file updated with dependency granularity guidance
    - [ ] All spec tests pass (full suite)
    - [ ] No linter warnings
    - [ ] `agent-fox plan --analyze` works with project's own specs
    - [ ] `agent-fox lint-spec --fix` works with project's own specs

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 20-REQ-1.1 | TS-20-1 | 5.1 | tests/integration/test_plan_analyze.py |
| 20-REQ-1.2 | TS-20-1, TS-20-2 | 2.1 | tests/unit/graph/test_analyzer.py |
| 20-REQ-1.3 | TS-20-1 | 2.2 | tests/unit/graph/test_analyzer.py |
| 20-REQ-1.4 | TS-20-3 | 2.1 | tests/unit/graph/test_analyzer.py |
| 20-REQ-1.E1 | TS-20-7 | 2.3 | tests/unit/graph/test_analyzer.py |
| 20-REQ-1.E2 | TS-20-2 | 2.3 | tests/unit/graph/test_analyzer.py |
| 20-REQ-2.1 | TS-20-4 | 2.1 | tests/unit/graph/test_analyzer.py |
| 20-REQ-2.2 | TS-20-4 | 2.1 | tests/unit/graph/test_analyzer.py |
| 20-REQ-2.3 | TS-20-5, TS-20-6 | 2.1 | tests/unit/graph/test_analyzer.py |
| 20-REQ-2.4 | TS-20-6 | 2.2 | tests/unit/graph/test_analyzer.py |
| 20-REQ-2.E1 | TS-20-E1 | 2.3 | tests/unit/graph/test_analyzer.py |
| 20-REQ-3.1 | TS-20-8 | 3.1 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-3.2 | TS-20-8 | 3.1 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-3.3 | TS-20-8 | 3.1 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-3.E1 | TS-20-10 | 3.1 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-3.E2 | TS-20-9 | 3.1 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-4.1 | TS-20-11 | 3.2 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-4.2 | TS-20-12 | 3.2 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-4.3 | TS-20-11 | 3.2 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-4.E1 | TS-20-13 | 3.2 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-4.E2 | TS-20-12 | 3.2 | tests/unit/spec/test_validator_plan_rules.py |
| 20-REQ-5.1 | -- | 6.1 | manual review |
| 20-REQ-5.2 | -- | 6.1 | manual review |
| 20-REQ-5.3 | -- | 6.1 | manual review |
| 20-REQ-5.E1 | -- | 6.2 | manual review |
| 20-REQ-6.1 | TS-20-14, TS-20-20 | 5.2 | tests/integration/test_lint_fix.py |
| 20-REQ-6.2 | TS-20-16 | 4.4 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.3 | TS-20-14 | 4.2 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.4 | TS-20-17, TS-20-18 | 4.3 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.5 | TS-20-14 | 4.4 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.6 | -- | 5.2 | tests/integration/test_lint_fix.py |
| 20-REQ-6.E1 | TS-20-20 | 4.4 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.E2 | TS-20-15 | 4.2 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.E3 | -- | 4.4 | tests/unit/spec/test_fixer.py |
| 20-REQ-6.E4 | TS-20-19 | 4.4 | tests/unit/spec/test_fixer.py |
| Property 1 | TS-20-P1 | 2.1 | tests/property/graph/test_analyzer_props.py |
| Property 2 | TS-20-P2 | 2.1 | tests/property/graph/test_analyzer_props.py |
| Property 3 | TS-20-P3 | 2.1 | tests/property/graph/test_analyzer_props.py |
| Property 4 | TS-20-P4 | 2.1 | tests/property/graph/test_analyzer_props.py |
| Property 5 | TS-20-P5 | 2.1 | tests/property/graph/test_analyzer_props.py |

## Notes

- The analyzer operates on the existing `TaskGraph` data structure. No
  schema changes are needed to plan.json -- analysis is computed on demand.
- The `coarse-dependency` rule reuses the same regex patterns already in
  `parser.py` (`_DEP_TABLE_HEADER` and `_DEP_TABLE_HEADER_ALT`). Import
  them rather than duplicating.
- The `circular-dependency` rule operates at spec level (ignoring group
  numbers) since cycles are a spec-level concept. It builds its own
  lightweight adjacency list, not a full TaskGraph.
- The fixer module (`spec/fixer.py`) is separate from the validator to
  maintain single-responsibility: validator detects, fixer corrects.
- The `fix_coarse_dependency` fixer must parse the standard table itself
  (not just detect it) to extract row data for the rewrite. It reuses
  `_DEP_TABLE_HEADER` and `_TABLE_SEP` patterns from parser.py.
- Property tests for the analyzer should use the existing random DAG
  generation strategy from `tests/property/graph/` if one exists, or
  create a new Hypothesis strategy that generates valid `TaskGraph`
  objects.
- Requirement 5 (af-spec guidance) is a prompt-only change with no
  automated test. It is verified by manual review of the updated SKILL.md
  and by running af-spec on a test PRD to confirm group-level dependency
  tables are generated.
