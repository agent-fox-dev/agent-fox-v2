# Implementation Plan: Worktree Cleanup Hardening

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

A focused bug fix modifying two existing modules. Task group 1 writes failing
tests. Group 2 implements all three fixes (verification, self-healing,
orphan cleanup) since they touch the same two files and are tightly coupled.
Group 3 is wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/workspace/test_worktree_hardening.py tests/integration/workspace/test_worktree_hardening.py tests/property/workspace/test_worktree_hardening_props.py`
- Unit tests: `uv run pytest -q tests/unit/workspace/test_worktree_hardening.py`
- Property tests: `uv run pytest -q tests/property/workspace/test_worktree_hardening_props.py`
- Integration tests: `uv run pytest -q tests/integration/workspace/test_worktree_hardening.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/workspace/test_worktree_hardening.py`
    - Test `branch_used_by_worktree` — TS-80-1, TS-80-2, TS-80-10
    - Test `delete_branch` self-healing — TS-80-5, TS-80-6
    - Test `_cleanup_empty_ancestors` — TS-80-7
    - Test edge cases — TS-80-E2, TS-80-E3, TS-80-E4
    - Test post-prune retry — TS-80-9
    - _Test Spec: TS-80-1, TS-80-2, TS-80-5 through TS-80-10, TS-80-E2, TS-80-E3, TS-80-E4_

  - [x] 1.2 Create integration test file `tests/integration/workspace/test_worktree_hardening.py`
    - Test `destroy_worktree` with real git — TS-80-3
    - Test `create_worktree` with stale state — TS-80-4
    - Test `create_worktree` orphan cleanup — TS-80-8
    - Test live worktree protection — TS-80-E1
    - Test smoke scenarios — TS-80-SMOKE-1, TS-80-SMOKE-2
    - _Test Spec: TS-80-3, TS-80-4, TS-80-8, TS-80-E1, TS-80-SMOKE-1, TS-80-SMOKE-2_

  - [x] 1.3 Create property test file `tests/property/workspace/test_worktree_hardening_props.py`
    - Porcelain parsing accuracy — TS-80-P1
    - Ancestor cleanup safety — TS-80-P2
    - delete_branch stale worktree safety — TS-80-P3
    - _Test Spec: TS-80-P1, TS-80-P2, TS-80-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [ ] 2. Implement worktree hardening
  - [ ] 2.1 Add `branch_used_by_worktree()` to `agent_fox/workspace/git.py`
    - Parse `git worktree list --porcelain` output
    - Check for `branch refs/heads/{name}` in any entry
    - Return False on command failure (optimistic fallback)
    - _Requirements: 80-REQ-1.3, 80-REQ-1.E2_

  - [ ] 2.2 Modify `delete_branch()` in `agent_fox/workspace/git.py`
    - Detect "used by worktree" in stderr on failure
    - Extract worktree path from error message
    - If path does not exist: prune + retry once
    - If retry fails: log warning, return without raising
    - If path exists: raise WorkspaceError (legitimate use)
    - _Requirements: 80-REQ-2.1, 80-REQ-2.2, 80-REQ-2.E1_

  - [ ] 2.3 Add `_cleanup_empty_ancestors()` to `agent_fox/workspace/worktree.py`
    - Walk from worktree_path up to root
    - Remove empty directories, stop at non-empty
    - Swallow errors (log at DEBUG)
    - _Requirements: 80-REQ-3.1, 80-REQ-3.2, 80-REQ-3.E1, 80-REQ-3.E2_

  - [ ] 2.4 Modify `destroy_worktree()` in `agent_fox/workspace/worktree.py`
    - After prune: call `branch_used_by_worktree` to verify
    - If still referenced: prune again + re-verify
    - If still referenced after second prune: log warning, skip deletion
    - Call `_cleanup_empty_ancestors` after branch deletion
    - _Requirements: 80-REQ-1.1, 80-REQ-1.E1, 80-REQ-3.1_

  - [ ] 2.5 Modify `create_worktree()` in `agent_fox/workspace/worktree.py`
    - After stale cleanup: call `_cleanup_empty_ancestors`
    - After prune: call `branch_used_by_worktree` to verify
    - Same retry logic as destroy_worktree
    - _Requirements: 80-REQ-1.2, 80-REQ-3.2_

  - [ ] 2.V Verify task group 2
    - [ ] All unit tests pass: `uv run pytest -q tests/unit/workspace/test_worktree_hardening.py`
    - [ ] All property tests pass: `uv run pytest -q tests/property/workspace/test_worktree_hardening_props.py`
    - [ ] All integration tests pass: `uv run pytest -q tests/integration/workspace/test_worktree_hardening.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [ ] Full pipeline: `make check`
    - [ ] Requirements 80-REQ-1.*, 80-REQ-2.*, 80-REQ-3.* met

- [ ] 3. Wiring verification
  - [ ] 3.1 Trace every execution path from design.md end-to-end
    - Verify destroy_worktree calls branch_used_by_worktree before delete_branch
    - Verify create_worktree calls branch_used_by_worktree before delete_branch
    - Verify _cleanup_empty_ancestors is called in both destroy and create paths
    - Confirm no function is a stub
    - _Requirements: all_

  - [ ] 3.2 Verify return values propagate correctly
    - branch_used_by_worktree return value controls deletion flow
    - delete_branch self-healing uses prune result
    - _Requirements: all_

  - [ ] 3.3 Run the integration smoke tests
    - All `TS-80-SMOKE-*` tests pass using real git repos
    - _Test Spec: TS-80-SMOKE-1, TS-80-SMOKE-2_

  - [ ] 3.4 Stub / dead-code audit
    - Search worktree.py and git.py for stubs, TODOs, NotImplementedError
    - Each hit must be justified or replaced
    - _Requirements: all_

  - [ ] 3.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 80-REQ-1.1 | TS-80-3 | 2.4 | tests/integration/workspace/test_worktree_hardening.py |
| 80-REQ-1.2 | TS-80-4 | 2.5 | tests/integration/workspace/test_worktree_hardening.py |
| 80-REQ-1.3 | TS-80-1, TS-80-2 | 2.1 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-1.E1 | TS-80-9, TS-80-E4 | 2.4 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-1.E2 | TS-80-10 | 2.1 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-2.1 | TS-80-5 | 2.2 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-2.2 | TS-80-6 | 2.2 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-2.E1 | TS-80-E1 | 2.2 | tests/integration/workspace/test_worktree_hardening.py |
| 80-REQ-3.1 | TS-80-7 | 2.3, 2.4 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-3.2 | TS-80-8 | 2.3, 2.5 | tests/integration/workspace/test_worktree_hardening.py |
| 80-REQ-3.E1 | TS-80-E2 | 2.3 | tests/unit/workspace/test_worktree_hardening.py |
| 80-REQ-3.E2 | TS-80-E3 | 2.3 | tests/unit/workspace/test_worktree_hardening.py |
| Property 1 | TS-80-P1 | 2.1 | tests/property/workspace/test_worktree_hardening_props.py |
| Property 2 | TS-80-P2 | 2.3 | tests/property/workspace/test_worktree_hardening_props.py |
| Property 3 | TS-80-P3 | 2.2 | tests/property/workspace/test_worktree_hardening_props.py |
| Path 2 | TS-80-SMOKE-1 | 2.4 | tests/integration/workspace/test_worktree_hardening.py |
| Path 4 | TS-80-SMOKE-2 | 2.5 | tests/integration/workspace/test_worktree_hardening.py |

## Notes

- Integration tests need real git repos in tmp directories. Use `pytest`'s
  `tmp_path` fixture and initialize with `git init`.
- The porcelain output format for `git worktree list` is stable across git
  versions (documented in git-worktree(1)).
- Property tests for `branch_used_by_worktree` should generate valid porcelain
  output strings rather than running real git commands.
- Existing worktree tests in `tests/unit/workspace/test_worktree.py` and
  `tests/integration/workspace/test_worktree.py` should not be modified —
  new tests go in separate `*_hardening*` files.
