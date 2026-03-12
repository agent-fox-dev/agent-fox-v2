# Implementation Plan: Post-Harvest Develop Reconciliation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a targeted fix to two existing functions. The implementation is split
into three task groups:

1. **Write failing tests** — translate test_spec.md into executable tests.
2. **Harden `_sync_develop_with_remote()`** — add merge-commit and `-X ours`
   fallbacks after rebase failure.
3. **Harden `_push_develop_if_pushable()`** — add reconciliation before push.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py`
- Unit tests: `uv run pytest -q tests/unit/workspace/test_develop_reconciliation.py`
- Integration tests: `uv run pytest -q tests/integration/test_develop_reconciliation.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/workspace/workspace.py agent_fox/workspace/harvest.py && uv run ruff format --check agent_fox/workspace/workspace.py agent_fox/workspace/harvest.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/workspace/test_develop_reconciliation.py`
    - Translate TS-36-3 (all strategies fail), TS-36-8 (in-sync no-op),
      TS-36-9 (local-ahead unchanged)
    - Translate TS-36-E1 (checkout fails), TS-36-E2 (fetch fails),
      TS-36-E3 (push fails after reconciliation)
    - Mock git subprocess calls to control failure points
    - _Test Spec: TS-36-3, TS-36-8, TS-36-9, TS-36-E1, TS-36-E2, TS-36-E3_

  - [x] 1.2 Create integration test file `tests/integration/test_develop_reconciliation.py`
    - Translate TS-36-1 (rebase fail + merge succeed), TS-36-2 (merge fail +
      ours succeed), TS-36-4 (fast-forward)
    - Translate TS-36-5 (post-harvest reconcile), TS-36-6 (push after
      reconcile), TS-36-7 (push when ahead)
    - Create helper to set up a git repo with origin remote and diverged
      develop branches
    - _Test Spec: TS-36-1, TS-36-2, TS-36-4, TS-36-5, TS-36-6, TS-36-7_

  - [x] 1.3 Create property test stubs in unit test file
    - Translate TS-36-P1 (fallback chain ordering) and TS-36-P2 (no-op
      idempotency)
    - _Test Spec: TS-36-P1, TS-36-P2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py && uv run ruff format --check tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py`

- [x] 2. Harden `_sync_develop_with_remote()`
  - [x] 2.1 Add merge-commit fallback after rebase failure
    - After `git rebase --abort`, attempt `git merge origin/develop` (with
      `--no-edit` to avoid interactive prompt)
    - If merge succeeds, log at INFO and return
    - _Requirements: 1.1_

  - [x] 2.2 Add `-X ours` fallback after merge-commit failure
    - If the merge commit from 2.1 fails, abort it and retry with
      `git merge -X ours origin/develop --no-edit`
    - If this succeeds, log at WARNING (signals potential data loss)
    - If this also fails, log warning and leave local as-is (existing behavior)
    - _Requirements: 1.2, 1.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py -k "sync_develop or rebase_fail or merge_fail or ours or fast_forward or no_op or ahead"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/workspace/workspace.py && uv run ruff format --check agent_fox/workspace/workspace.py`
    - [x] Requirements 1.1, 1.2, 1.3, 1.4, 1.E1, 3.1, 3.2 acceptance criteria met

- [x] 3. Harden `_push_develop_if_pushable()`
  - [x] 3.1 Add reconciliation before push
    - When origin/develop is ahead, call `_sync_develop_with_remote()` to
      reconcile before attempting the push
    - Import `_sync_develop_with_remote` from workspace.py into harvest.py
    - _Requirements: 2.1_

  - [x] 3.2 Retry push after reconciliation
    - After reconciliation, attempt the push regardless of whether
      reconciliation fully succeeded (the push itself will fail safely if
      local is still behind)
    - Log warning if push fails after reconciliation attempt
    - _Requirements: 2.2, 2.3, 2.E1_

  - [x] 3.3 Handle fetch failure during post-harvest
    - If fetch fails during reconciliation, skip reconciliation and attempt
      push as-is
    - _Requirements: 2.E2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py -k "post_harvest or push"`
    - [x] All spec tests pass: `uv run pytest -q tests/unit/workspace/test_develop_reconciliation.py tests/integration/test_develop_reconciliation.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/workspace/harvest.py && uv run ruff format --check agent_fox/workspace/harvest.py`
    - [x] Requirements 2.1-2.4, 2.E1, 2.E2 acceptance criteria met

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 36-REQ-1.1 | TS-36-1 | 2.1 | `test_develop_reconciliation.py::test_rebase_fail_merge_succeed` |
| 36-REQ-1.2 | TS-36-2 | 2.2 | `test_develop_reconciliation.py::test_merge_fail_ours_succeed` |
| 36-REQ-1.3 | TS-36-3 | 2.2 | `test_develop_reconciliation.py::test_all_strategies_fail` |
| 36-REQ-1.4 | TS-36-4 | 2.1 | `test_develop_reconciliation.py::test_fast_forward` |
| 36-REQ-1.E1 | TS-36-E1 | 2.1 | `test_develop_reconciliation.py::test_checkout_fail` |
| 36-REQ-1.E2 | TS-36-E2 | 3.3 | `test_develop_reconciliation.py::test_fetch_fail` |
| 36-REQ-2.1 | TS-36-5 | 3.1 | `test_develop_reconciliation.py::test_post_harvest_reconcile` |
| 36-REQ-2.2 | TS-36-6 | 3.2 | `test_develop_reconciliation.py::test_push_after_reconcile` |
| 36-REQ-2.3 | TS-36-E3 | 3.2 | `test_develop_reconciliation.py::test_push_fail_after_reconcile` |
| 36-REQ-2.4 | TS-36-7 | 3.1 | `test_develop_reconciliation.py::test_push_when_ahead` |
| 36-REQ-2.E1 | TS-36-E3 | 3.2 | `test_develop_reconciliation.py::test_push_fail_after_reconcile` |
| 36-REQ-2.E2 | TS-36-E2 | 3.3 | `test_develop_reconciliation.py::test_fetch_fail` |
| 36-REQ-3.1 | TS-36-8 | 2.1 | `test_develop_reconciliation.py::test_in_sync_no_op` |
| 36-REQ-3.2 | TS-36-9 | 2.1 | `test_develop_reconciliation.py::test_local_ahead_unchanged` |
| Property 1 | TS-36-P1 | 2.1, 2.2 | `test_develop_reconciliation.py::test_fallback_chain_ordering` |
| Property 2 | TS-36-P2 | 2.1 | `test_develop_reconciliation.py::test_no_op_idempotency` |

## Notes

- Integration tests need a helper that creates a bare "origin" repo and a
  cloned working repo with diverged develop branches. Use `tmp_path` fixture
  with `git init --bare` for origin and `git clone` for the working copy.
- The `-X ours` strategy preserves local changes, which means origin's changes
  are dropped. This is acceptable because local develop has the latest
  harvested task code, which is the source of truth. The origin-only commits
  are from a previous push of the same develop branch.
- The existing test file `tests/unit/workspace/test_harvester.py` has tests
  for the harvest merge fallback chain. The new tests should not duplicate
  those — they focus specifically on the develop reconciliation path.
- `_sync_develop_with_remote()` is currently a private function (prefixed
  with `_`). It needs to be importable by `harvest.py`. Either make it public
  or use a relative import within the `workspace` package.
