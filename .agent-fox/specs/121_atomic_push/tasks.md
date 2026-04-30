# Implementation Plan: Atomic Push with Retry

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation proceeds in five groups after the initial test group:
(1) failing spec tests, (2) git helpers (fetch, rebase abort extension),
(3) `_push_with_retry` + audit events, (4) harvest/session_lifecycle wiring
(atomic push under lock, no-double-push), (5) lock reentrancy for sync, and
(6) wiring verification. Groups are ordered so each builds on the previous:
git primitives first, then retry orchestration, then caller integration.

## Test Commands

- Spec tests: `uv run pytest -q tests/workspace/test_atomic_push.py`
- Unit tests: `uv run pytest -q tests/workspace/`
- Property tests: `uv run pytest -q tests/workspace/test_atomic_push.py -k property`
- All tests: `uv run pytest -q`
- Linter: `make check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file `tests/workspace/test_atomic_push.py`
    - Set up test file with imports, fixtures, mock helpers
    - Create `FakeAuditSink` helper for capturing audit events
    - Use existing test patterns from `tests/workspace/test_harvester.py`
    - _Test Spec: TS-121-1 through TS-121-16_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - `test_push_executes_inside_merge_lock` (TS-121-1)
    - `test_no_concurrent_merge_while_push_in_progress` (TS-121-2)
    - `test_lock_released_after_successful_push` (TS-121-3)
    - `test_push_failure_triggers_retry` (TS-121-4)
    - `test_retry_fetches_and_rebases_before_push` (TS-121-5)
    - `test_maximum_4_total_push_attempts` (TS-121-6)
    - `test_successful_retry_logs_info` (TS-121-7)
    - `test_exhausted_retries_logs_warning` (TS-121-8)
    - `test_retries_happen_under_merge_lock` (TS-121-9)
    - `test_push_failure_emits_audit_event` (TS-121-10)
    - `test_audit_payload_includes_required_fields` (TS-121-11)
    - `test_retries_exhausted_emits_final_audit` (TS-121-12)
    - `test_successful_retry_emits_push_retry_success` (TS-121-13)
    - `test_sync_under_held_lock_no_deadlock` (TS-121-14)
    - `test_harvest_push_true_then_post_harvest_skips` (TS-121-15)
    - `test_harvest_push_false_skips_push` (TS-121-16)
    - _Test Spec: TS-121-1 through TS-121-16_

  - [x] 1.3 Translate edge-case tests from test_spec.md
    - `test_no_remote_configured_skips_push` (TS-121-E1)
    - `test_fetch_fails_during_retry` (TS-121-E2)
    - `test_rebase_conflict_aborts_retry` (TS-121-E3)
    - `test_non_retryable_push_error_stops_immediately` (TS-121-E4)
    - `test_audit_sink_unavailable` (TS-121-E5)
    - `test_external_caller_sync_acquires_lock` (TS-121-E6)
    - _Test Spec: TS-121-E1 through TS-121-E6_

  - [x] 1.4 Translate property tests from test_spec.md
    - `test_property_bounded_retry_count` (TS-121-P1)
    - `test_property_audit_event_completeness` (TS-121-P2)
    - `test_property_no_double_push` (TS-121-P3)
    - _Test Spec: TS-121-P1 through TS-121-P3_

  - [x] 1.5 Translate integration smoke tests from test_spec.md
    - `test_smoke_harvest_push_retry` (TS-121-SMOKE-1)
    - `test_smoke_harvest_push_success_first_try` (TS-121-SMOKE-2)
    - _Test Spec: TS-121-SMOKE-1, TS-121-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make check`

- [x] 2. Add git helpers and audit event types
  - [x] 2.1 Add `fetch_remote` function to `agent_fox/workspace/git.py`
    - `async def fetch_remote(repo_root, remote="origin", branch=None) -> bool`
    - Uses `run_git(["fetch", remote, branch], check=False)`
    - Returns True on success, False on failure
    - Logs warning on failure
    - _Requirements: 121-REQ-2.1, 121-REQ-2.E1_

  - [x] 2.2 Verify existing `rebase_onto` and `abort_rebase` in `agent_fox/workspace/git.py`
    - `rebase_onto` already exists (line 451) — verify signature matches design
    - `abort_rebase` already exists (line 478) — verify it works for retry use case
    - Adapt if needed: `_push_with_retry` needs a bool-returning rebase
    - _Requirements: 121-REQ-2.1, 121-REQ-2.E2_

  - [x] 2.3 Add new audit event types to `agent_fox/knowledge/audit.py`
    - Add `GIT_PUSH_FAILED = "git.push_failed"` to `AuditEventType`
    - Add `GIT_PUSH_RETRY_SUCCESS = "git.push_retry_success"` to `AuditEventType`
    - _Requirements: 121-REQ-3.1, 121-REQ-3.4_

  - [x] 2.4 Export new git functions from `agent_fox/workspace/__init__.py`
    - Add `fetch_remote` to the workspace package exports
    - _Requirements: 121-REQ-2.1_

  - [x] 2.V Verify task group 2
    - [x] New `fetch_remote` function importable and callable
    - [x] Audit event types importable: `from agent_fox.knowledge.audit import AuditEventType; AuditEventType.GIT_PUSH_FAILED`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make check`

- [ ] 3. Implement `_push_with_retry` in harvest.py
  - [ ] 3.1 Add `_push_with_retry` function to `agent_fox/workspace/harvest.py`
    - Signature: `async def _push_with_retry(repo_root, branch="develop", remote="origin", max_retries=3, audit_sink=None, run_id=None, node_id=None) -> bool`
    - Initial push attempt via `push_to_remote()`
    - On failure: classify error as retryable (non-fast-forward) vs non-retryable
    - Emit `git.push_failed` audit event on each failure
    - On retryable failure: `fetch_remote()`, then rebase, then retry push
    - On rebase conflict: `abort_rebase()`, emit audit, stop retrying
    - On success after retry: emit `git.push_retry_success` audit event
    - On retries exhausted: emit final `git.push_failed` with `retries_exhausted: true`, log WARNING
    - Handle fetch failure: skip rebase, attempt push as-is
    - Handle audit sink errors: catch, log WARNING, continue
    - _Requirements: 121-REQ-2.1, 121-REQ-2.2, 121-REQ-2.3, 121-REQ-2.4, 121-REQ-2.E1, 121-REQ-2.E2, 121-REQ-2.E3_
    - _Requirements: 121-REQ-3.1, 121-REQ-3.2, 121-REQ-3.3, 121-REQ-3.4, 121-REQ-3.E1_

  - [ ] 3.2 Add push error classification logic
    - Detect non-fast-forward rejection from git push stderr
    - Detect authentication/network errors (non-retryable)
    - Need to read stderr from `push_to_remote` or use `run_git` directly
    - _Requirements: 121-REQ-2.E3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest -q tests/workspace/test_atomic_push.py -k "test_retry or test_maximum or test_exhausted or test_successful_retry_logs or test_push_failure_emits or test_audit_payload or test_retries_exhausted_emits or test_successful_retry_emits or test_fetch_fails or test_rebase_conflict or test_non_retryable or test_audit_sink"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make check`
    - [ ] Requirements 121-REQ-2.*, 121-REQ-3.* acceptance criteria met

- [ ] 4. Wire atomic push into harvest and session lifecycle
  - [ ] 4.1 Modify `harvest()` signature in `agent_fox/workspace/harvest.py`
    - Add parameters: `push: bool = True`, `audit_sink=None`, `run_id=None`, `node_id=None`
    - Pass through to `_harvest_under_lock()`
    - _Requirements: 121-REQ-5.1, 121-REQ-5.2_

  - [ ] 4.2 Modify `_harvest_under_lock()` to call `_push_with_retry`
    - Add parameters: `push`, `audit_sink`, `run_id`, `node_id`
    - After successful squash-merge commit, if `push=True`: call `_push_with_retry()`
    - Check for remote configured before pushing (skip if no remote)
    - Push happens before lock release (still inside `async with lock:`)
    - _Requirements: 121-REQ-1.1, 121-REQ-1.2, 121-REQ-1.3, 121-REQ-1.4, 121-REQ-1.E1_

  - [ ] 4.3 Modify `post_harvest_integrate()` to accept `push_already_done`
    - Add parameter: `push_already_done: bool = False`
    - When `push_already_done=True`, skip the call to `_push_develop_if_pushable()`
    - _Requirements: 121-REQ-5.3, 121-REQ-5.E1_

  - [ ] 4.4 Update `_harvest_and_integrate()` in `agent_fox/engine/session_lifecycle.py`
    - Pass `push=True`, `audit_sink=self._sink`, `run_id=self._run_id`, `node_id=node_id` to `harvest()`
    - Pass `push_already_done=True` to `post_harvest_integrate()` when harvest was called with `push=True`
    - _Requirements: 121-REQ-1.1, 121-REQ-5.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/workspace/test_atomic_push.py -k "test_push_executes or test_no_concurrent or test_lock_released or test_push_failure_triggers or test_retries_happen or test_harvest_push or test_no_remote or test_smoke"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make check`
    - [ ] Requirements 121-REQ-1.*, 121-REQ-5.* acceptance criteria met

- [ ] 5. Lock reentrancy for sync
  - [ ] 5.1 Modify `_sync_develop_with_remote()` in `agent_fox/workspace/develop.py`
    - Add parameter: `_lock_held: bool = False`
    - When `_lock_held=True`, call `_sync_develop_under_lock()` directly without acquiring `MergeLock`
    - When `_lock_held=False` (default), acquire lock as before — no behavioral change for existing callers
    - _Requirements: 121-REQ-4.1, 121-REQ-4.2, 121-REQ-4.E1_

  - [ ] 5.2 Update callers of `_sync_develop_with_remote` in harvest.py
    - In `_push_develop_if_pushable()`, if called from within lock scope, pass `_lock_held=True`
    - Ensure no deadlock in the harvest → push → sync path
    - _Requirements: 121-REQ-4.1_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest -q tests/workspace/test_atomic_push.py -k "test_sync_under or test_external_caller"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make check`
    - [ ] Requirements 121-REQ-4.* acceptance criteria met

- [ ] 6. Wiring verification

  - [ ] 6.1 Trace every execution path from design.md end-to-end
    - For each path (1-4), verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Path 1: `session_lifecycle._harvest_and_integrate` → `harvest(push=True)` → `_harvest_under_lock` → `_push_with_retry` → `push_to_remote` → return `list[str]`
    - Path 2: Same as Path 1 but push fails → `fetch_remote` → rebase → retry push → `git.push_retry_success` audit
    - Path 3: Push fails, all retries exhausted → `git.push_failed` with `retries_exhausted`
    - Path 4: Push fails, rebase conflict → `abort_rebase` → `git.push_failed` with `rebase_conflict`
    - Confirm no function in the chain is a stub
    - Every path must be live in production code
    - _Requirements: all_

  - [ ] 6.2 Verify return values propagate correctly
    - `_push_with_retry` returns `bool` — verify `_harvest_under_lock` uses the return value (or logs it)
    - `harvest()` returns `list[str]` — verify `_harvest_and_integrate` uses it
    - `fetch_remote` returns `bool` — verify `_push_with_retry` uses it to gate rebase
    - Grep for callers of each function; confirm none discards the return
    - _Requirements: all_

  - [ ] 6.3 Run the integration smoke tests
    - All `TS-121-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-121-SMOKE-1, TS-121-SMOKE-2_

  - [ ] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 6.5 Cross-spec entry point verification
    - Verify `_harvest_and_integrate` (session_lifecycle.py) calls `harvest()` with new parameters
    - Verify `post_harvest_integrate` is called with `push_already_done=True`
    - Grep codebase for all callers of `harvest()` and `post_harvest_integrate()` to confirm backward compatibility
    - _Requirements: all_

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

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
| 121-REQ-1.1 | TS-121-1 | 4.2 | `test_push_executes_inside_merge_lock` |
| 121-REQ-1.2 | TS-121-2 | 4.2 | `test_no_concurrent_merge_while_push_in_progress` |
| 121-REQ-1.3 | TS-121-3 | 4.2 | `test_lock_released_after_successful_push` |
| 121-REQ-1.4 | TS-121-4 | 4.2 | `test_push_failure_triggers_retry` |
| 121-REQ-1.E1 | TS-121-E1 | 4.2 | `test_no_remote_configured_skips_push` |
| 121-REQ-1.E2 | (existing) | (existing) | (existing merge lock tests) |
| 121-REQ-2.1 | TS-121-5 | 3.1, 2.1 | `test_retry_fetches_and_rebases_before_push` |
| 121-REQ-2.2 | TS-121-6 | 3.1 | `test_maximum_4_total_push_attempts` |
| 121-REQ-2.3 | TS-121-7 | 3.1 | `test_successful_retry_logs_info` |
| 121-REQ-2.4 | TS-121-8 | 3.1 | `test_exhausted_retries_logs_warning` |
| 121-REQ-2.5 | TS-121-9 | 4.2 | `test_retries_happen_under_merge_lock` |
| 121-REQ-2.E1 | TS-121-E2 | 3.1 | `test_fetch_fails_during_retry` |
| 121-REQ-2.E2 | TS-121-E3 | 3.1 | `test_rebase_conflict_aborts_retry` |
| 121-REQ-2.E3 | TS-121-E4 | 3.2 | `test_non_retryable_push_error_stops_immediately` |
| 121-REQ-3.1 | TS-121-10 | 3.1 | `test_push_failure_emits_audit_event` |
| 121-REQ-3.2 | TS-121-11 | 3.1 | `test_audit_payload_includes_required_fields` |
| 121-REQ-3.3 | TS-121-12 | 3.1 | `test_retries_exhausted_emits_final_audit` |
| 121-REQ-3.4 | TS-121-13 | 3.1 | `test_successful_retry_emits_push_retry_success` |
| 121-REQ-3.E1 | TS-121-E5 | 3.1 | `test_audit_sink_unavailable` |
| 121-REQ-4.1 | TS-121-14 | 5.1 | `test_sync_under_held_lock_no_deadlock` |
| 121-REQ-4.2 | TS-121-14 | 5.1 | `test_sync_under_held_lock_no_deadlock` |
| 121-REQ-4.E1 | TS-121-E6 | 5.1 | `test_external_caller_sync_acquires_lock` |
| 121-REQ-5.1 | TS-121-15 | 4.1 | `test_harvest_push_true_then_post_harvest_skips` |
| 121-REQ-5.2 | TS-121-16 | 4.1 | `test_harvest_push_false_skips_push` |
| 121-REQ-5.3 | TS-121-15 | 4.3 | `test_harvest_push_true_then_post_harvest_skips` |
| 121-REQ-5.E1 | TS-121-15 | 4.4 | `test_harvest_push_true_then_post_harvest_skips` |
| Property 2 | TS-121-P1 | 3.1 | `test_property_bounded_retry_count` |
| Property 4 | TS-121-P2 | 3.1 | `test_property_audit_event_completeness` |
| Property 5 | TS-121-P3 | 4.3 | `test_property_no_double_push` |

## Notes

- All tests mock `run_git` or individual git helper functions — no real git
  operations needed. Follow patterns in `tests/workspace/test_harvester.py`.
- Property tests use Hypothesis. Import `hypothesis.given`, `hypothesis.strategies`.
- The `AuditSink` type used in production is typically a list-like collector.
  Use a simple list or `FakeAuditSink` class in tests.
- `push_to_remote` currently returns `bool` but does not expose stderr. Task
  3.2 may require calling `run_git` directly to access stderr for error
  classification, or modifying `push_to_remote` to return richer error info.
- Existing `rebase_onto` raises `IntegrationError` on conflict instead of
  returning `bool`. The `_push_with_retry` implementation should catch
  `IntegrationError` from `rebase_onto` and treat it as a rebase conflict.
