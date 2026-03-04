# Implementation Plan: Spec Lint Fixes

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three bug fixes (parser regex, completed-group skip, alt dependency table
validation) plus a skill document update. Task group 1 writes tests, task
group 2 implements all code fixes, task group 3 updates the skill document and
verifies end-to-end.

## Test Commands

- Unit tests: `uv run pytest tests/unit/spec/test_validator.py tests/unit/spec/test_parser.py -q`
- All spec 09 tests: `uv run pytest tests/unit/spec/ tests/property/spec/ -q`
- Full suite: `uv run pytest tests/ -q`
- Linter: `uv run ruff check agent_fox/spec/ tests/unit/spec/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Add parser tests for N.V subtask parsing
    - Add tests to `tests/unit/spec/test_parser.py` (or create if needed)
    - TS-F3-1: verify `1.V` subtask is parsed with correct id and completed state
    - TS-F3-2: verify numeric IDs (`1.1`, `1.2`) still parse alongside `1.V`
    - TS-F3-E1: verify `1.X` is ignored (not parsed)
    - _Test Spec: TS-F3-1, TS-F3-2, TS-F3-E1_

  - [x] 1.2 Add validator tests for completed-group exemption
    - Add tests to `tests/unit/spec/test_validator.py`
    - TS-F3-3: completed group with 8 subtasks produces no oversized finding
    - TS-F3-4: completed group without N.V produces no missing-verification finding
    - TS-F3-5: incomplete group still produces both findings
    - _Test Spec: TS-F3-3, TS-F3-4, TS-F3-5_

  - [x] 1.3 Add validator tests for alternative dependency table
    - Add tests to `tests/unit/spec/test_validator.py`
    - TS-F3-6: alt table referencing non-existent spec → ERROR finding
    - TS-F3-7: alt table referencing non-existent from-group → ERROR finding
    - TS-F3-8: alt table referencing non-existent to-group → ERROR finding
    - TS-F3-E2: prd.md with both table formats → findings from both
    - _Test Spec: TS-F3-6, TS-F3-7, TS-F3-8, TS-F3-E2_

  - [x] 1.V Verify task group 1
    - [x] All new tests exist and are syntactically valid
    - [x] All new tests FAIL (red) — no implementation yet
    - [x] Existing tests still pass: `uv run pytest tests/unit/spec/ -q`
    - [x] No linter warnings: `uv run ruff check tests/unit/spec/`

- [x] 2. Implement fixes
  - [x] 2.1 Fix parser subtask regex
    - In `agent_fox/spec/parser.py`, change `_SUBTASK_PATTERN` from
      `(\d+\.\d+)` to `(\d+\.(?:\d+|V))` to accept `N.V` IDs
    - _Requirements: F3-REQ-1.1, F3-REQ-1.2, F3-REQ-1.E1_

  - [x] 2.2 Add completed-group skip to validator
    - In `check_oversized_groups`: add `if group.completed: continue`
    - In `check_missing_verification`: add `if group.completed: continue`
    - _Requirements: F3-REQ-2.1, F3-REQ-2.2, F3-REQ-2.3_

  - [x] 2.3 Add alternative dependency table validation
    - Add `_DEP_TABLE_HEADER_ALT` regex to `validator.py`
    - Extend `check_broken_dependencies` to detect and parse both formats
    - For alt format: validate spec name, from-group, and to-group
    - Add `current_spec_groups` parameter (or derive from context)
    - _Requirements: F3-REQ-3.1, F3-REQ-3.2, F3-REQ-3.3, F3-REQ-3.4, F3-REQ-3.E1_

  - [x] 2.V Verify task group 2
    - [x] All new tests pass: `uv run pytest tests/unit/spec/ -q`
    - [x] All existing tests still pass: `uv run pytest tests/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/`
    - [x] `uv run agent-fox lint-spec` no longer reports false positives for completed specs

- [x] 3. Update skill document and checkpoint
  - [x] 3.1 Update SKILL.md dependency validation instructions
    - Add validation checkpoint to the Cross-Spec Dependencies section in
      `/Users/candlekeep/.claude/skills/af-spec/SKILL.md`
    - Instructions must tell the agent to verify spec names exist in `.specs/`
      and group numbers exist in the referenced spec's `tasks.md`
    - _Requirements: F3-REQ-4.1, F3-REQ-4.2_

  - [x] 3.2 End-to-end verification
    - Run `uv run agent-fox lint-spec` on the project's `.specs/` directory
    - Confirm no false positives on completed specs
    - Confirm the 18_live_progress dangling reference (now fixed) would have
      been caught
    - Run full test suite: `uv run pytest tests/ -q`

  - [x] 3.V Verify task group 3
    - [x] SKILL.md contains dependency validation instructions
    - [x] `uv run agent-fox lint-spec` produces clean output for completed specs
    - [x] All tests pass: `uv run pytest tests/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| F3-REQ-1.1 | TS-F3-1 | 2.1 | tests/unit/spec/test_parser.py |
| F3-REQ-1.2 | TS-F3-2 | 2.1 | tests/unit/spec/test_parser.py |
| F3-REQ-1.E1 | TS-F3-E1 | 2.1 | tests/unit/spec/test_parser.py |
| F3-REQ-2.1 | TS-F3-3 | 2.2 | tests/unit/spec/test_validator.py |
| F3-REQ-2.2 | TS-F3-4 | 2.2 | tests/unit/spec/test_validator.py |
| F3-REQ-2.3 | TS-F3-5 | 2.2 | tests/unit/spec/test_validator.py |
| F3-REQ-3.1 | TS-F3-6 | 2.3 | tests/unit/spec/test_validator.py |
| F3-REQ-3.2 | TS-F3-6 | 2.3 | tests/unit/spec/test_validator.py |
| F3-REQ-3.3 | TS-F3-7 | 2.3 | tests/unit/spec/test_validator.py |
| F3-REQ-3.4 | TS-F3-8 | 2.3 | tests/unit/spec/test_validator.py |
| F3-REQ-3.E1 | TS-F3-E2 | 2.3 | tests/unit/spec/test_validator.py |
| F3-REQ-4.1 | — | 3.1 | read SKILL.md |
| F3-REQ-4.2 | — | 3.1 | read SKILL.md |

## Notes

- This is a fix spec extending `09_spec_validation`. No new modules created.
- The parser regex change is minimal and backward-compatible.
- The `check_broken_dependencies` signature may need a new parameter for the
  current spec's group numbers (to validate `To Group` column). Update the
  caller in `validate_specs()` accordingly.
- The SKILL.md file lives outside the repo at
  `/Users/candlekeep/.claude/skills/af-spec/SKILL.md`.
