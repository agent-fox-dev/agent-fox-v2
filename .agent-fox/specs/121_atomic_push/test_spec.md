# Test Specification: Atomic Push with Retry

## Overview

Tests verify three concerns: (1) the push happens inside the merge lock
scope, (2) push failures trigger a bounded fetch-rebase-retry loop, and
(3) audit events are emitted for push failures and retries. All tests use
mocked git operations since the behavior under test is orchestration logic.

## Test Cases

### TS-121-1: Push executes inside merge lock

**Requirement:** 121-REQ-1.1
**Type:** unit
**Description:** Verifies that `git push` is called while the merge lock
is still held, not after release.

**Preconditions:**
- Feature branch has new commits relative to develop.
- `push_to_remote` mock returns `True`.

**Input:**
- `harvest(repo, workspace, push=True)`

**Expected:**
- `push_to_remote` is called.
- At the time `push_to_remote` is called, the merge lock file exists on
  disk (lock is held).
- After `harvest()` returns, the merge lock file does not exist (lock
  released).

**Assertion pseudocode:**
```
lock_held_during_push = False
original_push = git.push_to_remote

async def tracking_push(*args, **kwargs):
    lock_held_during_push = lock_file.exists()
    return await original_push(*args, **kwargs)

mock push_to_remote with tracking_push
result = await harvest(repo, workspace, push=True)
ASSERT lock_held_during_push == True
ASSERT lock_file.exists() == False
ASSERT len(result) > 0
```

### TS-121-2: No concurrent merge while push in progress

**Requirement:** 121-REQ-1.2
**Type:** unit
**Description:** Verifies that a second harvest call blocks while the
first is pushing.

**Preconditions:**
- Two workspaces with commits to merge.
- `push_to_remote` mock adds a small delay.

**Input:**
- Two concurrent `harvest()` calls.

**Expected:**
- The second harvest does not start its merge until the first harvest
  (including push) completes.
- Merge operations are strictly serialized.

**Assertion pseudocode:**
```
call_order = []
async def slow_push(*a, **kw):
    call_order.append("push_start")
    await asyncio.sleep(0.1)
    call_order.append("push_end")
    return True

async def tracking_merge(*a, **kw):
    call_order.append("merge")
    return original_merge(*a, **kw)

mock push_to_remote with slow_push
mock _harvest_under_lock to also track merge
await asyncio.gather(harvest(r, ws1), harvest(r, ws2))
ASSERT call_order == ["merge", "push_start", "push_end", "merge", "push_start", "push_end"]
```

### TS-121-3: Lock released after successful push

**Requirement:** 121-REQ-1.3
**Type:** unit
**Description:** Verifies the lock is released and touched files are
returned after a successful push.

**Preconditions:**
- Feature branch has commits.
- Push succeeds.

**Input:**
- `harvest(repo, workspace, push=True)`

**Expected:**
- Returns non-empty list of touched files.
- Lock file does not exist after return.

**Assertion pseudocode:**
```
result = await harvest(repo, workspace, push=True)
ASSERT len(result) > 0
ASSERT not lock_file.exists()
```

### TS-121-4: Push failure triggers retry

**Requirement:** 121-REQ-1.4
**Type:** unit
**Description:** Verifies that when push fails inside the lock, the
retry loop is invoked before the lock is released.

**Preconditions:**
- Feature branch has commits.
- First push returns `False`, second push returns `True`.

**Input:**
- `harvest(repo, workspace, push=True)`

**Expected:**
- `push_to_remote` is called twice.
- `fetch_remote` is called once (between attempts).
- `rebase_onto` is called once (between attempts).
- Lock is held during all push and retry operations.

**Assertion pseudocode:**
```
push_count = 0
def mock_push(*a, **kw):
    push_count += 1
    return push_count >= 2  # fail first, succeed second

result = await harvest(repo, workspace, push=True)
ASSERT push_count == 2
ASSERT fetch_remote.called_once
ASSERT rebase_onto.called_once
ASSERT len(result) > 0
```

### TS-121-5: Retry fetches and rebases before each push attempt

**Requirement:** 121-REQ-2.1
**Type:** unit
**Description:** Verifies the fetch-rebase-push sequence on retry.

**Preconditions:**
- Push fails on first attempt.

**Input:**
- `_push_with_retry(repo, "develop")`

**Expected:**
- Call order is: push, fetch, rebase, push.

**Assertion pseudocode:**
```
calls = []
mock push_to_remote: calls.append("push"); return len(calls) > 2
mock fetch_remote: calls.append("fetch"); return True
mock rebase_onto: calls.append("rebase"); return True

await _push_with_retry(repo, "develop")
ASSERT calls == ["push", "fetch", "rebase", "push"]
```

### TS-121-6: Maximum 4 total push attempts

**Requirement:** 121-REQ-2.2
**Type:** unit
**Description:** Verifies the retry count is bounded at 3 retries
(4 total attempts).

**Preconditions:**
- Push always fails.

**Input:**
- `_push_with_retry(repo, "develop", max_retries=3)`

**Expected:**
- `push_to_remote` is called exactly 4 times.
- Function returns `False`.

**Assertion pseudocode:**
```
push_count = 0
mock push_to_remote: push_count += 1; return False
mock fetch_remote: return True
mock rebase_onto: return True

result = await _push_with_retry(repo, "develop", max_retries=3)
ASSERT result == False
ASSERT push_count == 4
```

### TS-121-7: Successful retry logs at INFO

**Requirement:** 121-REQ-2.3
**Type:** unit
**Description:** Verifies INFO log on successful retry.

**Preconditions:**
- First push fails, second succeeds.

**Input:**
- `_push_with_retry(repo, "develop")`

**Expected:**
- INFO log message contains "retry" and "attempt 2".

**Assertion pseudocode:**
```
mock push_to_remote: return call_count >= 2
result = await _push_with_retry(repo, "develop")
ASSERT result == True
ASSERT any("attempt 2" in r.message for r in caplog.records if r.levelname == "INFO")
```

### TS-121-8: Exhausted retries logs WARNING

**Requirement:** 121-REQ-2.4
**Type:** unit
**Description:** Verifies WARNING log when all retries exhausted.

**Preconditions:**
- Push always fails.

**Input:**
- `_push_with_retry(repo, "develop", max_retries=3)`

**Expected:**
- WARNING log message indicates retries exhausted.
- Function returns `False` without raising.

**Assertion pseudocode:**
```
mock push_to_remote: return False
result = await _push_with_retry(repo, "develop", max_retries=3)
ASSERT result == False
ASSERT any("exhausted" in r.message or "retries" in r.message
           for r in caplog.records if r.levelname == "WARNING")
```

### TS-121-9: Retries happen under merge lock

**Requirement:** 121-REQ-2.5
**Type:** unit
**Description:** Verifies the lock is held during all retry attempts.

**Preconditions:**
- Push fails on first attempt, succeeds on second.
- Called from within `harvest()` (which holds the lock).

**Input:**
- `harvest(repo, workspace, push=True)` with push mock failing once.

**Expected:**
- Lock file exists during both push attempts.

**Assertion pseudocode:**
```
lock_states = []
def tracking_push(*a, **kw):
    lock_states.append(lock_file.exists())
    return len(lock_states) >= 2

await harvest(repo, workspace, push=True)
ASSERT lock_states == [True, True]
```

### TS-121-10: Push failure emits audit event

**Requirement:** 121-REQ-3.1
**Type:** unit
**Description:** Verifies audit event emitted on push failure.

**Preconditions:**
- Push fails, then succeeds on retry.
- Audit sink is provided.

**Input:**
- `_push_with_retry(repo, "develop", audit_sink=sink)`

**Expected:**
- At least one `git.push_failed` audit event emitted.

**Assertion pseudocode:**
```
mock push_to_remote: return call_count >= 2
await _push_with_retry(repo, "develop", audit_sink=sink)
events = [e for e in sink.events if e.event_type == "git.push_failed"]
ASSERT len(events) >= 1
```

### TS-121-11: Audit payload includes required fields

**Requirement:** 121-REQ-3.2
**Type:** unit
**Description:** Verifies the push failure audit event payload.

**Preconditions:**
- Push fails once, succeeds on retry.

**Input:**
- `_push_with_retry(repo, "develop", audit_sink=sink)`

**Expected:**
- Payload contains: attempt, error, branch, will_retry.

**Assertion pseudocode:**
```
mock push_to_remote: return call_count >= 2
await _push_with_retry(repo, "develop", audit_sink=sink)
event = sink.events[0]
payload = event.payload
ASSERT "attempt" in payload
ASSERT "error" in payload
ASSERT "branch" in payload
ASSERT "will_retry" in payload
ASSERT payload["attempt"] == 1
ASSERT payload["will_retry"] == True
```

### TS-121-12: Retries exhausted emits final audit event

**Requirement:** 121-REQ-3.3
**Type:** unit
**Description:** Verifies final audit event when retries exhausted.

**Preconditions:**
- Push always fails.

**Input:**
- `_push_with_retry(repo, "develop", max_retries=3, audit_sink=sink)`

**Expected:**
- Last audit event has `retries_exhausted: true`.

**Assertion pseudocode:**
```
mock push_to_remote: return False
await _push_with_retry(repo, "develop", max_retries=3, audit_sink=sink)
last_event = [e for e in sink.events if e.event_type == "git.push_failed"][-1]
ASSERT last_event.payload["retries_exhausted"] == True
```

### TS-121-13: Successful retry emits push_retry_success

**Requirement:** 121-REQ-3.4
**Type:** unit
**Description:** Verifies audit event on successful retry.

**Preconditions:**
- Push fails once, succeeds on second attempt.

**Input:**
- `_push_with_retry(repo, "develop", audit_sink=sink)`

**Expected:**
- One `git.push_retry_success` event with `total_attempts: 2`.

**Assertion pseudocode:**
```
mock push_to_remote: return call_count >= 2
await _push_with_retry(repo, "develop", audit_sink=sink)
success_events = [e for e in sink.events if e.event_type == "git.push_retry_success"]
ASSERT len(success_events) == 1
ASSERT success_events[0].payload["total_attempts"] == 2
```

### TS-121-14: Sync under already-held lock does not deadlock

**Requirement:** 121-REQ-4.1
**Type:** unit
**Description:** Verifies that reconciliation logic can run when the
merge lock is already held.

**Preconditions:**
- Merge lock is held by the current task.
- `origin/develop` is ahead of local develop.

**Input:**
- `_sync_develop_with_remote(repo, _lock_held=True)` called from within
  a `MergeLock` context.

**Expected:**
- Function completes without deadlocking.
- Does not attempt to acquire the lock again.

**Assertion pseudocode:**
```
lock = MergeLock(repo)
async with lock:
    result = await _sync_develop_with_remote(repo, _lock_held=True)
    # If this line is reached, no deadlock occurred
    ASSERT result in (None, "fast-forward", "rebase", "merge", "merge-agent")
```

### TS-121-15: harvest(push=True) pushes, post_harvest skips

**Requirement:** 121-REQ-5.1, 121-REQ-5.3
**Type:** unit
**Description:** Verifies that when harvest pushes, post_harvest_integrate
does not push again.

**Preconditions:**
- Feature branch has commits.
- Push succeeds inside harvest.

**Input:**
- `harvest(repo, workspace, push=True)` then
  `post_harvest_integrate(repo, workspace, push_already_done=True)`

**Expected:**
- `push_to_remote` called exactly once (inside harvest).

**Assertion pseudocode:**
```
push_count = 0
mock push_to_remote: push_count += 1; return True

await harvest(repo, workspace, push=True)
await post_harvest_integrate(repo, workspace, push_already_done=True)
ASSERT push_count == 1
```

### TS-121-16: harvest(push=False) skips push

**Requirement:** 121-REQ-5.2
**Type:** unit
**Description:** Verifies push is skipped when push=False.

**Preconditions:**
- Feature branch has commits.

**Input:**
- `harvest(repo, workspace, push=False)`

**Expected:**
- `push_to_remote` is not called.
- Returns non-empty list of touched files.

**Assertion pseudocode:**
```
mock push_to_remote: raise AssertionError("should not be called")
result = await harvest(repo, workspace, push=False)
ASSERT len(result) > 0
```

## Property Test Cases

### TS-121-P1: Bounded retry count

**Property:** Property 2 from design.md
**Validates:** 121-REQ-2.2, 121-REQ-2.4
**Type:** property
**Description:** For any sequence of push outcomes, the total push attempts
never exceeds `max_retries + 1`.

**For any:** `max_retries` in [0, 10], `outcomes` as list of booleans
(True=push success, False=push fail) of length >= max_retries + 1.
**Invariant:** `push_to_remote` is called at most `max_retries + 1` times.

**Assertion pseudocode:**
```
FOR ANY max_retries IN integers(0, 10):
    FOR ANY outcomes IN lists(booleans, min_size=max_retries+1):
        call_count = 0
        mock push_to_remote: call_count += 1; return outcomes[call_count-1]
        mock fetch_remote: return True
        mock rebase_onto: return True
        await _push_with_retry(repo, max_retries=max_retries)
        ASSERT call_count <= max_retries + 1
```

### TS-121-P2: Audit event completeness

**Property:** Property 4 from design.md
**Validates:** 121-REQ-3.1, 121-REQ-3.4
**Type:** property
**Description:** For any push failure, at least one audit event is emitted.
For any eventual success after failures, exactly one retry_success event.

**For any:** `outcomes` as list where first element is False and eventually
contains True (or all False).
**Invariant:** `len(push_failed_events) >= 1`. If final result is True,
`len(retry_success_events) == 1`.

**Assertion pseudocode:**
```
FOR ANY outcomes IN lists(booleans, min_size=1, max_size=5):
    ASSUME outcomes[0] == False  # at least one failure
    mock push_to_remote: return outcomes[call_count-1]
    await _push_with_retry(repo, audit_sink=sink, max_retries=len(outcomes)-1)
    failed = [e for e in sink.events if e.type == "git.push_failed"]
    success = [e for e in sink.events if e.type == "git.push_retry_success"]
    ASSERT len(failed) >= 1
    if any(outcomes[1:]):  # eventually succeeded
        ASSERT len(success) == 1
```

### TS-121-P3: No double push

**Property:** Property 5 from design.md
**Validates:** 121-REQ-5.3, 121-REQ-5.E1
**Type:** property
**Description:** Regardless of whether harvest pushes or not, the total
number of pushes across harvest + post_harvest_integrate is at most 1.

**For any:** `push_flag` in {True, False}.
**Invariant:** `push_to_remote` called at most once across both functions.

**Assertion pseudocode:**
```
FOR ANY push_flag IN booleans():
    push_count = 0
    mock push_to_remote: push_count += 1; return True
    await harvest(repo, workspace, push=push_flag)
    await post_harvest_integrate(repo, workspace, push_already_done=push_flag)
    ASSERT push_count <= 1
```

## Edge Case Tests

### TS-121-E1: No remote configured skips push

**Requirement:** 121-REQ-1.E1
**Type:** unit
**Description:** Verifies push is skipped when no remote exists.

**Preconditions:**
- Repository has no configured remote.
- Feature branch has commits.

**Input:**
- `harvest(repo, workspace, push=True)`

**Expected:**
- Push is not attempted.
- Harvest succeeds and returns touched files.

**Assertion pseudocode:**
```
mock get_remote_url: return None
mock push_to_remote: raise AssertionError("should not be called")
result = await harvest(repo, workspace, push=True)
ASSERT len(result) > 0
```

### TS-121-E2: Fetch fails during retry

**Requirement:** 121-REQ-2.E1
**Type:** unit
**Description:** Verifies push is attempted even if fetch fails during retry.

**Preconditions:**
- Push fails on first attempt.
- Fetch returns False.

**Input:**
- `_push_with_retry(repo, "develop")`

**Expected:**
- Rebase is skipped.
- Push is retried anyway.
- Total push attempts is > 1.

**Assertion pseudocode:**
```
push_count = 0
mock push_to_remote: push_count += 1; return push_count >= 3
mock fetch_remote: return False
mock rebase_onto: raise AssertionError("should not be called after fetch fail")

result = await _push_with_retry(repo, "develop")
ASSERT push_count >= 2
```

### TS-121-E3: Rebase conflict aborts retry

**Requirement:** 121-REQ-2.E2
**Type:** unit
**Description:** Verifies rebase conflict aborts the retry loop.

**Preconditions:**
- Push fails on first attempt.
- Rebase fails (conflict).

**Input:**
- `_push_with_retry(repo, "develop")`

**Expected:**
- `rebase_abort` is called.
- No further push attempts after rebase failure.
- Returns False.

**Assertion pseudocode:**
```
push_count = 0
mock push_to_remote: push_count += 1; return False
mock fetch_remote: return True
mock rebase_onto: return False
mock rebase_abort: pass

result = await _push_with_retry(repo, "develop")
ASSERT result == False
ASSERT push_count == 1  # no retry after rebase conflict
ASSERT rebase_abort.called
```

### TS-121-E4: Non-retryable push error stops immediately

**Requirement:** 121-REQ-2.E3
**Type:** unit
**Description:** Verifies that authentication/network errors are not retried.

**Preconditions:**
- Push fails with auth error (stderr contains "Authentication failed" or
  similar non-fast-forward indicators).

**Input:**
- `_push_with_retry(repo, "develop")`

**Expected:**
- Push is attempted once.
- No fetch or rebase.
- Returns False.

**Assertion pseudocode:**
```
mock push_to_remote: return False
mock run_git for push: return (128, "", "fatal: Authentication failed")

result = await _push_with_retry(repo, "develop")
ASSERT result == False
ASSERT fetch_remote.not_called
```

### TS-121-E5: Audit sink unavailable

**Requirement:** 121-REQ-3.E1
**Type:** unit
**Description:** Verifies push failure is logged even when audit sink fails.

**Preconditions:**
- Push fails once, succeeds on retry.
- Audit sink raises on emit.

**Input:**
- `_push_with_retry(repo, "develop", audit_sink=failing_sink)`

**Expected:**
- Function completes without raising.
- WARNING log for push failure exists.
- Push retry succeeds.

**Assertion pseudocode:**
```
mock push_to_remote: return call_count >= 2
mock emit_audit_event: raise RuntimeError("sink broken")

result = await _push_with_retry(repo, "develop", audit_sink=failing_sink)
ASSERT result == True
ASSERT any("push" in r.message for r in caplog.records if r.levelname == "WARNING")
```

### TS-121-E6: External caller of sync acquires lock

**Requirement:** 121-REQ-4.E1
**Type:** unit
**Description:** Verifies `_sync_develop_with_remote()` acquires lock when
called without `_lock_held=True`.

**Preconditions:**
- `origin/develop` is ahead of local develop.

**Input:**
- `_sync_develop_with_remote(repo)` (default `_lock_held=False`)

**Expected:**
- Lock file is created and released during the call.

**Assertion pseudocode:**
```
lock_observed = False
original_sync = _sync_develop_under_lock
async def tracking_sync(*a, **kw):
    lock_observed = lock_file.exists()
    return await original_sync(*a, **kw)

result = await _sync_develop_with_remote(repo)
ASSERT lock_observed == True
ASSERT not lock_file.exists()
```

## Integration Smoke Tests

### TS-121-SMOKE-1: End-to-end harvest with push retry

**Execution Path:** Path 2 from design.md
**Description:** Verifies the full harvest-merge-push-retry-push flow
from session completion to successful push after one retry.

**Setup:** Mock `run_git` to simulate: successful merge, first push
returning non-ff rejection, successful fetch, successful rebase, second
push succeeding. Audit sink is a list collector.

**Trigger:** `harvest(repo, workspace, push=True, audit_sink=sink)`

**Expected side effects:**
- Returns non-empty list of touched files.
- `run_git` called with `push` args exactly twice.
- `run_git` called with `fetch` args once.
- `run_git` called with `rebase` args once.
- Audit sink contains one `git.push_failed` event and one
  `git.push_retry_success` event.

**Must NOT satisfy with:** Mocking `_push_with_retry` — the real
function must execute to validate the full retry loop.

**Assertion pseudocode:**
```
git_calls = []
async def tracking_git(args, **kw):
    git_calls.append(args[0])
    if args[0] == "push" and len([c for c in git_calls if c == "push"]) == 1:
        return (1, "", "non-fast-forward")
    return (0, "ok", "")

mock run_git with tracking_git
result = await harvest(repo, workspace, push=True, audit_sink=sink)
ASSERT len(result) > 0
ASSERT git_calls.count("push") == 2
ASSERT git_calls.count("fetch") == 1
ASSERT git_calls.count("rebase") == 1
ASSERT len([e for e in sink if e.type == "git.push_failed"]) == 1
ASSERT len([e for e in sink if e.type == "git.push_retry_success"]) == 1
```

### TS-121-SMOKE-2: End-to-end harvest with push success first try

**Execution Path:** Path 1 from design.md
**Description:** Verifies the happy path where push succeeds on first
attempt with no retries needed.

**Setup:** Mock `run_git` to simulate: successful merge, successful push.

**Trigger:** `harvest(repo, workspace, push=True, audit_sink=sink)`

**Expected side effects:**
- Returns non-empty list of touched files.
- `push_to_remote` called exactly once.
- No `git.push_failed` events in audit sink.
- No fetch or rebase calls.

**Must NOT satisfy with:** Mocking `harvest` or `_harvest_under_lock`.

**Assertion pseudocode:**
```
result = await harvest(repo, workspace, push=True, audit_sink=sink)
ASSERT len(result) > 0
ASSERT push_to_remote.call_count == 1
ASSERT len([e for e in sink if e.type == "git.push_failed"]) == 0
ASSERT fetch_remote.not_called
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 121-REQ-1.1 | TS-121-1 | unit |
| 121-REQ-1.2 | TS-121-2 | unit |
| 121-REQ-1.3 | TS-121-3 | unit |
| 121-REQ-1.4 | TS-121-4 | unit |
| 121-REQ-1.E1 | TS-121-E1 | unit |
| 121-REQ-1.E2 | (covered by existing merge lock tests) | unit |
| 121-REQ-2.1 | TS-121-5 | unit |
| 121-REQ-2.2 | TS-121-6 | unit |
| 121-REQ-2.3 | TS-121-7 | unit |
| 121-REQ-2.4 | TS-121-8 | unit |
| 121-REQ-2.5 | TS-121-9 | unit |
| 121-REQ-2.E1 | TS-121-E2 | unit |
| 121-REQ-2.E2 | TS-121-E3 | unit |
| 121-REQ-2.E3 | TS-121-E4 | unit |
| 121-REQ-3.1 | TS-121-10 | unit |
| 121-REQ-3.2 | TS-121-11 | unit |
| 121-REQ-3.3 | TS-121-12 | unit |
| 121-REQ-3.4 | TS-121-13 | unit |
| 121-REQ-3.E1 | TS-121-E5 | unit |
| 121-REQ-4.1 | TS-121-14 | unit |
| 121-REQ-4.E1 | TS-121-E6 | unit |
| 121-REQ-5.1 | TS-121-15 | unit |
| 121-REQ-5.2 | TS-121-16 | unit |
| 121-REQ-5.3 | TS-121-15 | unit |
| 121-REQ-5.E1 | TS-121-15 | unit |
| Property 1 | (validated by TS-121-1, TS-121-9) | unit |
| Property 2 | TS-121-P1 | property |
| Property 3 | (validated by TS-121-5 — rebase produces linear history) | unit |
| Property 4 | TS-121-P2 | property |
| Property 5 | TS-121-P3 | property |
| Property 6 | (validated by TS-121-E3) | unit |
| Path 1 | TS-121-SMOKE-2 | integration |
| Path 2 | TS-121-SMOKE-1 | integration |
