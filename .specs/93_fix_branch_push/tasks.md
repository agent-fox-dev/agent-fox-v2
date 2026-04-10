# Implementation Plan: Fix Branch Push to Upstream

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec modifies three existing modules (`config.py`, `spec_builder.py`,
`fix_pipeline.py`) and one utility (`git.py`). The implementation is split
into a test-first group, a single implementation group covering all changes,
and a wiring verification group.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_fix_branch_push.py tests/property/nightshift/test_fix_branch_push_props.py tests/integration/nightshift/test_fix_branch_push_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/nightshift/test_fix_branch_push.py`
- Property tests: `uv run pytest -q tests/property/nightshift/test_fix_branch_push_props.py`
- Integration tests: `uv run pytest -q tests/integration/nightshift/test_fix_branch_push_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file
    - Create `tests/unit/nightshift/test_fix_branch_push.py`
    - Implement tests TS-93-1 through TS-93-9 and TS-93-E1 through TS-93-E4
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-93-1 through TS-93-9, TS-93-E1 through TS-93-E4_
    - Note: TS-93-4 is integration type per test_spec.md; placed in smoke test file

  - [x] 1.2 Create property test file
    - Create `tests/property/nightshift/test_fix_branch_push_props.py`
    - Implement property tests TS-93-P1 through TS-93-P5
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-93-P1 through TS-93-P5_

  - [x] 1.3 Create integration smoke test file
    - Create `tests/integration/nightshift/test_fix_branch_push_smoke.py`
    - Implement smoke tests TS-93-SMOKE-1, TS-93-SMOKE-2, and TS-93-4
    - _Test Spec: TS-93-SMOKE-1, TS-93-SMOKE-2, TS-93-4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet (18 failures, 5 trivial passes)
    - [x] No linter warnings introduced: `make lint`

- [ ] 2. Implement config, branch naming, and push logic
  - [ ] 2.1 Add `push_fix_branch` field to `NightShiftConfig`
    - Add `push_fix_branch: bool = Field(default=False, ...)` to
      `agent_fox/nightshift/config.py`
    - Pydantic handles boolean validation (93-REQ-1.E1) automatically
    - _Requirements: 93-REQ-1.1, 93-REQ-1.2, 93-REQ-1.E1_

  - [ ] 2.2 Update branch naming in `spec_builder.py`
    - Modify `sanitise_branch_name(title, issue_number=None)` to include
      issue number: `fix/{N}-{slug}` or `fix/{N}` when slug is empty
    - Update `build_in_memory_spec` to pass `issue.number` to
      `sanitise_branch_name`
    - _Requirements: 93-REQ-2.1, 93-REQ-2.2, 93-REQ-2.E1_

  - [ ] 2.3 Add `force` parameter to `push_to_remote` in `git.py`
    - Add `force: bool = False` keyword argument to
      `agent_fox/workspace/git.py: push_to_remote`
    - When `force=True`, prepend `"--force"` to the git push args
    - _Requirements: 93-REQ-3.2_

  - [ ] 2.4 Add `_push_fix_branch_upstream` method to `FixPipeline`
    - New async method on `FixPipeline` in `fix_pipeline.py`
    - Calls `push_to_remote(repo_root, spec.branch_name, force=True)`
    - Returns `bool`; catches all exceptions and logs warnings
    - _Requirements: 93-REQ-3.1, 93-REQ-3.2, 93-REQ-3.E1, 93-REQ-3.E2_

  - [ ] 2.5 Wire push step into `process_issue`
    - In `FixPipeline.process_issue`, after coder-reviewer loop returns
      `True` and before `_harvest_and_push`, conditionally call
      `_push_fix_branch_upstream` when
      `self._config.night_shift.push_fix_branch` is `True`
    - _Requirements: 93-REQ-3.1, 93-REQ-3.3, 93-REQ-3.4, 93-REQ-4.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_fix_branch_push.py tests/property/nightshift/test_fix_branch_push_props.py tests/integration/nightshift/test_fix_branch_push_smoke.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 93-REQ-1.1, 93-REQ-1.2, 93-REQ-1.E1, 93-REQ-2.1,
          93-REQ-2.2, 93-REQ-2.E1, 93-REQ-3.1 through 93-REQ-3.4,
          93-REQ-3.E1, 93-REQ-3.E2, 93-REQ-4.1 acceptance criteria met

- [ ] 3. Wiring verification

  - [ ] 3.1 Trace every execution path from design.md end-to-end
    - For each path (push enabled, push disabled, branch naming), verify the
      entry point actually calls the next function in the chain (read the
      calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [ ] 3.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - `sanitise_branch_name` -> `build_in_memory_spec` -> `InMemorySpec.branch_name`
    - `_push_fix_branch_upstream` -> `process_issue` (return value logged)
    - `push_to_remote` -> `_push_fix_branch_upstream` (return value used)
    - _Requirements: all_

  - [ ] 3.3 Run the integration smoke tests
    - All `TS-93-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/nightshift/test_fix_branch_push_smoke.py`
    - _Test Spec: TS-93-SMOKE-1, TS-93-SMOKE-2_

  - [ ] 3.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 3.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 93-REQ-1.1 | TS-93-2 | 2.1 | `test_fix_branch_push.py::test_config_reads_true` |
| 93-REQ-1.2 | TS-93-1 | 2.1 | `test_fix_branch_push.py::test_config_defaults_false` |
| 93-REQ-1.E1 | TS-93-E1 | 2.1 | `test_fix_branch_push.py::test_config_rejects_non_bool` |
| 93-REQ-2.1 | TS-93-3 | 2.2 | `test_fix_branch_push.py::test_branch_name_includes_issue_number` |
| 93-REQ-2.2 | TS-93-3 | 2.2 | `test_fix_branch_push.py::test_branch_name_includes_issue_number` |
| 93-REQ-2.E1 | TS-93-E2, TS-93-E3 | 2.2 | `test_fix_branch_push.py::test_empty_title_branch_name` |
| 93-REQ-3.1 | TS-93-4 | 2.4, 2.5 | `test_fix_branch_push_smoke.py::test_push_before_harvest` |
| 93-REQ-3.2 | TS-93-6 | 2.3, 2.4 | `test_fix_branch_push.py::test_force_push_flag` |
| 93-REQ-3.3 | TS-93-5 | 2.5 | `test_fix_branch_push.py::test_push_not_called_when_disabled` |
| 93-REQ-3.4 | TS-93-9 | 2.5 | `test_fix_branch_push.py::test_no_remote_branch_delete` |
| 93-REQ-3.E1 | TS-93-7 | 2.4 | `test_fix_branch_push.py::test_push_failure_continues` |
| 93-REQ-3.E2 | TS-93-E4 | 2.4 | `test_fix_branch_push.py::test_push_failure_logs_reason` |
| 93-REQ-4.1 | TS-93-8 | 2.5 | `test_fix_branch_push.py::test_independence_from_merge_strategy` |
| Property 1 | TS-93-P1 | 2.5 | `test_fix_branch_push_props.py::test_push_gating` |
| Property 2 | TS-93-P2 | 2.2 | `test_fix_branch_push_props.py::test_branch_name_contains_number` |
| Property 3 | TS-93-P3 | 2.5 | `test_fix_branch_push_props.py::test_push_before_harvest` |
| Property 4 | TS-93-P4 | 2.4 | `test_fix_branch_push_props.py::test_push_failure_resilience` |
| Property 5 | TS-93-P5 | 2.4 | `test_fix_branch_push_props.py::test_force_push_semantics` |
| Path 1 | TS-93-SMOKE-1 | 2.5 | `test_fix_branch_push_smoke.py::test_full_pipeline_push_enabled` |
| Path 2 | TS-93-SMOKE-2 | 2.5 | `test_fix_branch_push_smoke.py::test_full_pipeline_push_disabled` |

## Notes

- Existing tests for `sanitise_branch_name` will need updating since the
  function signature changes (new `issue_number` parameter). Existing callers
  only include `build_in_memory_spec`, which is updated in task 2.2.
- The `push_to_remote` change (adding `force` kwarg) is backward-compatible
  since the parameter defaults to `False`.
- Use `suppress_health_check=[HealthCheck.function_scoped_fixture]` in all
  Hypothesis property tests per project conventions.
