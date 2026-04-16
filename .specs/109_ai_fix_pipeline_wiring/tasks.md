# Implementation Plan: AI Fix Pipeline Wiring

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is minimal — approximately 60-80 lines of new code in
`agent_fox/spec/lint.py` plus test files. All AI generator and fixer functions
already exist and are tested. This spec wires them into the production code
path.

Three task groups: (1) write failing tests, (2) implement the wiring in
`lint.py`, (3) wiring verification.

## Test Commands

- Spec tests: `uv run pytest tests/unit/spec/test_ai_fix_wiring.py -q`
- Property tests: `uv run pytest tests/property/spec/test_ai_fix_wiring_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_ai_fix_wiring.py -q`
- All spec tests: `uv run pytest tests/unit/spec/test_ai_fix_wiring.py tests/property/spec/test_ai_fix_wiring_props.py tests/integration/test_ai_fix_wiring.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/spec/lint.py tests/unit/spec/test_ai_fix_wiring.py tests/property/spec/test_ai_fix_wiring_props.py tests/integration/test_ai_fix_wiring.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for dispatch logic
    - Create `tests/unit/spec/test_ai_fix_wiring.py`
    - Mock `rewrite_criteria`, `generate_test_spec_entries`, `fix_ai_criteria`,
      `fix_ai_test_spec_entries`, `resolve_model`
    - Test `_apply_ai_fixes()` and `_apply_ai_fixes_async()` dispatch behavior
    - _Test Spec: TS-109-1, TS-109-2, TS-109-3, TS-109-4, TS-109-5, TS-109-6,
      TS-109-7, TS-109-8, TS-109-9, TS-109-10, TS-109-11, TS-109-12, TS-109-13_

  - [x] 1.2 Create edge case tests
    - No AI-fixable findings, rewrite/generation failure isolation, empty dicts,
      missing test_spec.md, re-validation without re-fix
    - _Test Spec: TS-109-E1, TS-109-E2, TS-109-E3, TS-109-E4, TS-109-E5,
      TS-109-E6, TS-109-E7_

  - [x] 1.3 Create property tests
    - Create `tests/property/spec/test_ai_fix_wiring_props.py`
    - AI fix isolation, dispatch correctness, ordering invariant, batch bounds,
      per-spec error isolation, single-pass guarantee
    - _Test Spec: TS-109-P1, TS-109-P2, TS-109-P3, TS-109-P4, TS-109-P5,
      TS-109-P6_

  - [x] 1.4 Create integration smoke tests
    - Create `tests/integration/test_ai_fix_wiring.py`
    - Full criteria rewrite path with real `fix_ai_criteria()`
    - Full test spec generation path with real `fix_ai_test_spec_entries()`
    - _Test Spec: TS-109-SMOKE-1, TS-109-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/spec/test_ai_fix_wiring.py tests/property/spec/test_ai_fix_wiring_props.py tests/integration/test_ai_fix_wiring.py`

- [ ] 2. Implement AI fix dispatch and wiring
  - [ ] 2.1 Add batch limit constants to `agent_fox/spec/lint.py`
    - Add `_MAX_REWRITE_BATCH = 20` and `_MAX_UNTRACED_BATCH = 20`
    - _Requirements: 109-REQ-2.3, 109-REQ-3.2_

  - [ ] 2.2 Implement `_apply_ai_fixes_async()` in `agent_fox/spec/lint.py`
    - Filter findings to `AI_FIXABLE_RULES`
    - Group by spec name
    - For each spec: dispatch criteria rewrites (with batch splitting), then
      test spec generation (with batch splitting)
    - Build `findings_map` from finding messages using `_REQ_ID_IN_MESSAGE`
    - Handle per-spec errors with try/except and logging
    - Skip `fix_ai_criteria()` when rewrites is empty
    - Skip `fix_ai_test_spec_entries()` when entries is empty
    - Skip generation when `test_spec.md` is missing
    - _Requirements: 109-REQ-2.1, 109-REQ-2.2, 109-REQ-2.3, 109-REQ-3.1,
      109-REQ-3.2, 109-REQ-4.1, 109-REQ-2.E1, 109-REQ-2.E2, 109-REQ-3.E1,
      109-REQ-3.E2, 109-REQ-3.E3_

  - [ ] 2.3 Implement `_apply_ai_fixes()` sync wrapper in `agent_fox/spec/lint.py`
    - Resolve STANDARD model via `resolve_model("STANDARD")`
    - Call `asyncio.run(_apply_ai_fixes_async(...))`
    - Catch top-level exceptions, log warning, return empty list
    - _Requirements: 109-REQ-3.3, 109-REQ-1.E1_

  - [ ] 2.4 Wire `_apply_ai_fixes()` into `run_lint_specs()`
    - Insert call between AI analysis and mechanical fixes:
      `if ai: ai_fix_results = _apply_ai_fixes(...)`
    - Extend `all_fix_results` with AI fix results
    - Ensure re-validation triggers when any fixes applied (AI or mechanical)
    - Ensure AI fixes are NOT re-invoked during re-validation
    - _Requirements: 109-REQ-1.1, 109-REQ-1.2, 109-REQ-1.3, 109-REQ-4.2,
      109-REQ-5.1, 109-REQ-5.2, 109-REQ-5.E1_

  - [ ] 2.V Verify task group 2
    - [ ] All spec tests pass: `uv run pytest tests/unit/spec/test_ai_fix_wiring.py tests/property/spec/test_ai_fix_wiring_props.py tests/integration/test_ai_fix_wiring.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/spec/lint.py`
    - [ ] Requirements 109-REQ-1.*, 109-REQ-2.*, 109-REQ-3.*, 109-REQ-4.*, 109-REQ-5.* acceptance criteria met

- [ ] 3. Wiring verification

  - [ ] 3.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 3.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - Specifically verify: `_apply_ai_fixes()` return value is extended into
      `all_fix_results` in `run_lint_specs()`
    - _Requirements: all_

  - [ ] 3.3 Run the integration smoke tests
    - All `TS-109-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-109-SMOKE-1, TS-109-SMOKE-2_

  - [ ] 3.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 3.5 Cross-spec entry point verification
    - Verify that `_apply_ai_fixes()` is actually called from
      `run_lint_specs()` in production code (not just in tests)
    - Verify that `run_lint_specs()` is called from `lint_specs_cmd()` in
      `cli/lint_specs.py`
    - Trace the full chain: CLI command -> run_lint_specs -> _apply_ai_fixes
      -> rewrite_criteria / generate_test_spec_entries -> fix_ai_criteria /
      fix_ai_test_spec_entries
    - _Requirements: all_

  - [ ] 3.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 109-REQ-1.1 | TS-109-1 | 2.4 | `test_ai_fix_wiring.py::test_ai_fix_results_in_lint_result` |
| 109-REQ-1.2 | TS-109-2 | 2.4 | `test_ai_fix_wiring.py::test_no_ai_fix_without_ai_flag` |
| 109-REQ-1.3 | TS-109-3 | 2.4 | `test_ai_fix_wiring.py::test_no_ai_fix_without_fix_flag` |
| 109-REQ-1.E1 | TS-109-E1 | 2.3 | `test_ai_fix_wiring.py::test_no_fixable_findings_skips_pipeline` |
| 109-REQ-2.1 | TS-109-4 | 2.2 | `test_ai_fix_wiring.py::test_vague_criterion_dispatch` |
| 109-REQ-2.2 | TS-109-5 | 2.2 | `test_ai_fix_wiring.py::test_findings_map_construction` |
| 109-REQ-2.3 | TS-109-6 | 2.2 | `test_ai_fix_wiring.py::test_rewrite_batch_splitting` |
| 109-REQ-2.E1 | TS-109-E2 | 2.2 | `test_ai_fix_wiring.py::test_rewrite_failure_continues_other_specs` |
| 109-REQ-2.E2 | TS-109-E3 | 2.2 | `test_ai_fix_wiring.py::test_empty_rewrite_skips_fixer` |
| 109-REQ-3.1 | TS-109-7 | 2.2 | `test_ai_fix_wiring.py::test_untraced_requirement_dispatch` |
| 109-REQ-3.2 | TS-109-8 | 2.2 | `test_ai_fix_wiring.py::test_untraced_batch_splitting` |
| 109-REQ-3.3 | TS-109-9 | 2.3 | `test_ai_fix_wiring.py::test_standard_model_used` |
| 109-REQ-3.E1 | TS-109-E4 | 2.2 | `test_ai_fix_wiring.py::test_generation_failure_continues_other_specs` |
| 109-REQ-3.E2 | TS-109-E5 | 2.2 | `test_ai_fix_wiring.py::test_empty_entries_skips_fixer` |
| 109-REQ-3.E3 | TS-109-E6 | 2.2 | `test_ai_fix_wiring.py::test_missing_test_spec_skips_generation` |
| 109-REQ-4.1 | TS-109-10 | 2.2 | `test_ai_fix_wiring.py::test_rewrite_before_generation` |
| 109-REQ-4.2 | TS-109-11 | 2.4 | `test_ai_fix_wiring.py::test_ai_fixes_before_mechanical` |
| 109-REQ-5.1 | TS-109-12 | 2.4 | `test_ai_fix_wiring.py::test_revalidation_after_ai_fixes` |
| 109-REQ-5.2 | TS-109-13 | 2.4 | `test_ai_fix_wiring.py::test_no_re_invocation_during_revalidation` |
| 109-REQ-5.E1 | TS-109-E7 | 2.4 | `test_ai_fix_wiring.py::test_still_flagged_criterion_reported` |
| Property 1 | TS-109-P1 | 2.4 | `test_ai_fix_wiring_props.py::test_ai_fix_isolation` |
| Property 2 | TS-109-P2 | 2.2 | `test_ai_fix_wiring_props.py::test_dispatch_correctness` |
| Property 3 | TS-109-P3 | 2.2 | `test_ai_fix_wiring_props.py::test_ordering_invariant` |
| Property 4 | TS-109-P4 | 2.2 | `test_ai_fix_wiring_props.py::test_batch_size_bound` |
| Property 5 | TS-109-P5 | 2.2 | `test_ai_fix_wiring_props.py::test_per_spec_error_isolation` |
| Property 6 | TS-109-P6 | 2.4 | `test_ai_fix_wiring_props.py::test_single_pass_guarantee` |
| Path 1 | TS-109-SMOKE-1 | 3.3 | `test_ai_fix_wiring.py::test_smoke_criteria_rewrite` |
| Path 2 | TS-109-SMOKE-2 | 3.3 | `test_ai_fix_wiring.py::test_smoke_test_spec_generation` |

## Notes

- All AI calls are mocked in tests — no live API calls.
- The implementation touches only `agent_fox/spec/lint.py`. All AI generator
  and fixer functions are already implemented and tested.
- The async inner function (`_apply_ai_fixes_async`) uses `asyncio.run()` in
  the sync wrapper, matching the pattern established by `_merge_ai_findings()`.
- The `_MAX_REWRITE_BATCH` constant in `lint.py` replaces the unused
  `_MAX_CRITERIA_PER_BATCH` constant in `ai_validation.py` for batch
  splitting in the wiring layer.
