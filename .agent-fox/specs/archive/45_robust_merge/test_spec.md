# Test Specification: Robust Git Merging

## Overview

Tests verify two capabilities: (1) the merge lock serializes concurrent
operations and handles staleness/timeouts correctly, and (2) the agent
fallback resolves conflicts when deterministic strategies fail, replacing
the blind `-X theirs`/`-X ours` strategies.

## Test Cases

### TS-45-1: Lock Acquired Before Merge

**Requirement:** 45-REQ-1.1
**Type:** unit
**Description:** Verify that harvest acquires the merge lock before executing
git merge commands.

**Preconditions:**
- Mocked git commands and MergeLock.
- A workspace with new commits on the feature branch.

**Input:**
- Call `harvest(repo_root, workspace)`.

**Expected:**
- MergeLock.acquire() is called before any git checkout/merge command.

**Assertion pseudocode:**
```
mock_lock = Mock()
harvest(repo_root, workspace)
ASSERT mock_lock.__aenter__ called BEFORE git checkout
```

### TS-45-2: Lock Queues Concurrent Callers

**Requirement:** 45-REQ-1.2
**Type:** unit
**Description:** Verify that a second caller waits when the lock is held.

**Preconditions:**
- MergeLock with a very short poll interval.
- Lock file already exists (not stale).

**Input:**
- Two concurrent `lock.acquire()` calls.

**Expected:**
- Second caller blocks until first releases.

**Assertion pseudocode:**
```
lock = MergeLock(repo_root, timeout=5)
acquired_order = []
# Task 1 acquires, holds for 1 second, releases
# Task 2 tries to acquire immediately
ASSERT acquired_order == [1, 2]
```

### TS-45-3: Lock Timeout Raises IntegrationError

**Requirement:** 45-REQ-1.3
**Type:** unit
**Description:** Verify that exceeding the timeout raises IntegrationError.

**Preconditions:**
- Lock file exists and is not stale.
- Timeout set to 0.5 seconds.

**Input:**
- Call `lock.acquire()` with timeout=0.5.

**Expected:**
- IntegrationError raised with message containing "lock" and "timeout".

**Assertion pseudocode:**
```
lock = MergeLock(repo_root, timeout=0.5, stale_timeout=600)
create_lock_file(repo_root)  # held by "another process"
WITH pytest.raises(IntegrationError, match="lock.*timeout"):
    await lock.acquire()
```

### TS-45-4: Cross-Process Lock Serialization

**Requirement:** 45-REQ-1.4
**Type:** integration
**Description:** Verify that the lock works across OS processes.

**Preconditions:**
- Temporary git repository.

**Input:**
- Process A creates lock file.
- Process B attempts to acquire.

**Expected:**
- Process B blocks until Process A releases.

**Assertion pseudocode:**
```
# Subprocess A creates lock file and holds for 2 seconds
# Subprocess B tries to acquire with timeout=5
# B should succeed after A releases
ASSERT B_acquired_time > A_released_time
```

### TS-45-5: Lock Release on Success

**Requirement:** 45-REQ-2.1
**Type:** unit
**Description:** Verify the lock file is removed after successful harvest.

**Preconditions:**
- Mocked git commands that succeed.

**Input:**
- Call `harvest(repo_root, workspace)`.

**Expected:**
- Lock file does not exist after harvest returns.

**Assertion pseudocode:**
```
await harvest(repo_root, workspace)
ASSERT NOT (repo_root / ".agent-fox" / "merge.lock").exists()
```

### TS-45-6: Lock Release on Failure

**Requirement:** 45-REQ-2.2
**Type:** unit
**Description:** Verify the lock is released even when harvest raises.

**Preconditions:**
- Mocked git commands that all fail.
- Mocked merge agent that also fails.

**Input:**
- Call `harvest(repo_root, workspace)` expecting IntegrationError.

**Expected:**
- Lock file does not exist after the exception.

**Assertion pseudocode:**
```
WITH pytest.raises(IntegrationError):
    await harvest(repo_root, workspace)
ASSERT NOT (repo_root / ".agent-fox" / "merge.lock").exists()
```

### TS-45-7: Harvest Lock Covers Post-Harvest

**Requirement:** 45-REQ-3.1
**Type:** unit
**Description:** Verify the lock is held during post-harvest integration.

**Preconditions:**
- Mocked git and post_harvest_integrate.

**Input:**
- Call harvest + post-harvest flow.

**Expected:**
- post_harvest_integrate runs while lock is still held.

**Assertion pseudocode:**
```
# Track when post_harvest_integrate is called relative to lock release
ASSERT post_harvest_called BEFORE lock_released
```

### TS-45-8: Develop Sync Uses Lock

**Requirement:** 45-REQ-3.2
**Type:** unit
**Description:** Verify _sync_develop_with_remote acquires the merge lock.

**Preconditions:**
- Mocked git commands.

**Input:**
- Call `_sync_develop_with_remote(repo_root)`.

**Expected:**
- MergeLock is acquired and released around git operations.

**Assertion pseudocode:**
```
mock_lock = Mock()
await _sync_develop_with_remote(repo_root)
ASSERT mock_lock.__aenter__ called
ASSERT mock_lock.__aexit__ called
```

### TS-45-9: Agent Spawned on Merge Failure

**Requirement:** 45-REQ-4.1
**Type:** unit
**Description:** Verify that when all deterministic strategies fail, the merge
agent is spawned.

**Preconditions:**
- ff-merge, rebase, merge-commit all raise IntegrationError.
- Mocked merge agent that succeeds.

**Input:**
- Call `harvest(repo_root, workspace)`.

**Expected:**
- `run_merge_agent()` is called.
- Harvest completes successfully.

**Assertion pseudocode:**
```
mock_run_merge_agent.return_value = True
result = await harvest(repo_root, workspace)
ASSERT mock_run_merge_agent.called
ASSERT len(result) > 0  # changed files returned
```

### TS-45-10: Agent Uses ADVANCED Model

**Requirement:** 45-REQ-4.2
**Type:** unit
**Description:** Verify the merge agent uses the ADVANCED model tier.

**Preconditions:**
- Mocked resolve_model_id and run_merge_agent.

**Input:**
- Trigger agent fallback in harvest.

**Expected:**
- resolve_model_id("ADVANCED") is called.
- The returned model_id is passed to run_merge_agent.

**Assertion pseudocode:**
```
mock_resolve.return_value = "claude-opus-4-6"
await harvest(repo_root, workspace)
mock_resolve.assert_called_with("ADVANCED")
mock_run_merge_agent.assert_called_with(
    worktree_path=ANY, conflict_output=ANY, model_id="claude-opus-4-6"
)
```

### TS-45-11: Agent Prompt Is Conflict-Only

**Requirement:** 45-REQ-4.3
**Type:** unit
**Description:** Verify the merge agent's prompt restricts it to conflict
resolution only.

**Preconditions:**
- Capture the prompt passed to the agent session.

**Input:**
- Trigger agent fallback.

**Expected:**
- System prompt contains "merge conflict" and "only".
- System prompt prohibits refactoring, test fixes, and feature changes.

**Assertion pseudocode:**
```
prompt = captured_system_prompt
ASSERT "merge conflict" IN prompt.lower()
ASSERT "only" IN prompt.lower()
ASSERT "refactor" IN prompt.lower()  # as a prohibition
```

### TS-45-12: Agent Receives Conflict Output

**Requirement:** 45-REQ-4.4
**Type:** unit
**Description:** Verify the merge agent receives git conflict output as context.

**Preconditions:**
- Mocked git that produces conflict output.

**Input:**
- Trigger agent fallback.

**Expected:**
- The conflict_output passed to run_merge_agent contains the git output.

**Assertion pseudocode:**
```
mock_merge_commit raises IntegrationError("CONFLICT (content)")
await harvest(repo_root, workspace)
ASSERT "CONFLICT" IN mock_run_merge_agent.call_args.conflict_output
```

### TS-45-13: Agent Resolution Completes Merge

**Requirement:** 45-REQ-4.5
**Type:** unit
**Description:** Verify that after agent resolution, the merge into develop
is completed.

**Preconditions:**
- Mocked merge agent returns True.

**Input:**
- Trigger agent fallback in harvest.

**Expected:**
- After agent returns True, develop contains the merged changes.

**Assertion pseudocode:**
```
mock_run_merge_agent.return_value = True
result = await harvest(repo_root, workspace)
ASSERT len(result) > 0  # changed files
ASSERT git log shows merge commit
```

## Edge Case Tests

### TS-45-E1: Stale Lock Broken

**Requirement:** 45-REQ-1.E1
**Type:** unit
**Description:** Verify that a stale lock file is broken and re-acquired.

**Preconditions:**
- Lock file exists with mtime > stale_timeout.

**Input:**
- Call `lock.acquire()`.

**Expected:**
- Lock is acquired successfully.
- Old lock file is removed and replaced.

**Assertion pseudocode:**
```
create_lock_file(repo_root, mtime=time.time() - 600)
lock = MergeLock(repo_root, stale_timeout=300)
await lock.acquire()  # should succeed
ASSERT lock file exists with fresh mtime
```

### TS-45-E2: Missing .agent-fox Directory

**Requirement:** 45-REQ-1.E2
**Type:** unit
**Description:** Verify lock creates .agent-fox/ if missing.

**Preconditions:**
- repo_root exists but .agent-fox/ does not.

**Input:**
- Call `lock.acquire()`.

**Expected:**
- .agent-fox/ directory is created.
- Lock file is created within it.

**Assertion pseudocode:**
```
ASSERT NOT (repo_root / ".agent-fox").exists()
lock = MergeLock(repo_root)
await lock.acquire()
ASSERT (repo_root / ".agent-fox" / "merge.lock").exists()
await lock.release()
```

### TS-45-E3: Concurrent Stale Lock Break

**Requirement:** 45-REQ-1.E3
**Type:** unit
**Description:** Verify that concurrent stale-lock breaks don't both succeed.

**Preconditions:**
- Stale lock file exists.

**Input:**
- Two concurrent acquire() calls.

**Expected:**
- Exactly one acquires the lock; the other retries or waits.

**Assertion pseudocode:**
```
create_stale_lock(repo_root)
results = await asyncio.gather(
    lock1.acquire(), lock2.acquire(),
    return_exceptions=True
)
# Both should eventually succeed (one after the other releases)
# but at no point should both hold the lock simultaneously
```

### TS-45-E4: Lock File Already Gone on Release

**Requirement:** 45-REQ-2.E1
**Type:** unit
**Description:** Verify release handles missing lock file gracefully.

**Preconditions:**
- Lock was acquired, then lock file was externally deleted.

**Input:**
- Call `lock.release()`.

**Expected:**
- Warning logged, no exception raised.

**Assertion pseudocode:**
```
await lock.acquire()
os.unlink(lock_file_path)
await lock.release()  # should not raise
ASSERT "warning" IN captured_logs
```

### TS-45-E5: Agent Failure Aborts Harvest

**Requirement:** 45-REQ-4.E1
**Type:** unit
**Description:** Verify that agent failure raises IntegrationError in harvest.

**Preconditions:**
- All deterministic strategies fail.
- Merge agent returns False.

**Input:**
- Call `harvest(repo_root, workspace)`.

**Expected:**
- IntegrationError raised with message about agent failure.

**Assertion pseudocode:**
```
mock_run_merge_agent.return_value = False
WITH pytest.raises(IntegrationError, match="agent"):
    await harvest(repo_root, workspace)
```

### TS-45-E6: Agent API Error Treated as Failure

**Requirement:** 45-REQ-4.E2
**Type:** unit
**Description:** Verify that agent API errors are treated as agent failure.

**Preconditions:**
- Merge agent raises an exception.

**Input:**
- Trigger agent fallback.

**Expected:**
- IntegrationError raised.

**Assertion pseudocode:**
```
mock_run_merge_agent.side_effect = RuntimeError("API timeout")
WITH pytest.raises(IntegrationError):
    await harvest(repo_root, workspace)
```

### TS-45-E7: Develop Sync Agent Failure Logs Warning

**Requirement:** 45-REQ-5.E1
**Type:** unit
**Description:** Verify develop-sync agent failure logs warning and continues.

**Preconditions:**
- Develop sync deterministic strategies fail.
- Merge agent returns False.

**Input:**
- Call `_sync_develop_with_remote(repo_root)`.

**Expected:**
- Warning logged.
- No exception raised.
- Local develop is left as-is.

**Assertion pseudocode:**
```
mock_run_merge_agent.return_value = False
await _sync_develop_with_remote(repo_root)
ASSERT "warning" IN captured_logs
```

### TS-45-E8: No -X theirs in Harvest

**Requirement:** 45-REQ-6.1
**Type:** unit
**Description:** Verify `-X theirs` is not used in the harvest flow.

**Preconditions:**
- All deterministic strategies fail.

**Input:**
- Call `harvest(repo_root, workspace)`.

**Expected:**
- No git merge command is called with `-X theirs`.

**Assertion pseudocode:**
```
# Inspect all git merge calls
FOR call IN mock_run_git.calls:
    IF "merge" IN call.args:
        ASSERT "theirs" NOT IN call.args
```

### TS-45-E9: No -X ours in Develop Sync

**Requirement:** 45-REQ-6.2
**Type:** unit
**Description:** Verify `-X ours` is not used in the develop-sync flow.

**Preconditions:**
- Develop sync deterministic strategies fail.

**Input:**
- Call `_sync_develop_with_remote(repo_root)`.

**Expected:**
- No git merge command is called with `-X ours`.

**Assertion pseudocode:**
```
FOR call IN mock_run_git.calls:
    IF "merge" IN call.args:
        ASSERT "ours" NOT IN call.args
```

## Property Test Cases

### TS-45-P1: Mutual Exclusion

**Property:** Property 1 from design.md
**Validates:** 45-REQ-1.1, 45-REQ-1.4
**Type:** property
**Description:** At most one lock holder at any time.

**For any:** N concurrent acquire/release cycles (N in 2..8) with random
hold durations (0-100ms).
**Invariant:** A shared counter never exceeds 1 during any lock-held period.

**Assertion pseudocode:**
```
FOR ANY (n_tasks, hold_durations) IN generated_scenarios:
    counter = AtomicCounter()
    async def worker():
        async with lock:
            counter.increment()
            ASSERT counter.value <= 1
            await sleep(hold_duration)
            counter.decrement()
    await gather(*[worker() for _ in range(n_tasks)])
```

### TS-45-P2: Lock Always Released

**Property:** Property 2 from design.md
**Validates:** 45-REQ-2.1, 45-REQ-2.2
**Type:** property
**Description:** Lock is always released regardless of exception.

**For any:** operation that raises an arbitrary exception within the lock.
**Invariant:** After the `async with` block exits, the lock file does not exist.

**Assertion pseudocode:**
```
FOR ANY exception_type IN [ValueError, RuntimeError, IntegrationError, None]:
    TRY:
        async with lock:
            IF exception_type:
                RAISE exception_type()
    EXCEPT: pass
    ASSERT NOT lock_file.exists()
```

### TS-45-P3: Stale Lock Recovery

**Property:** Property 3 from design.md
**Validates:** 45-REQ-1.E1
**Type:** property
**Description:** Stale locks are always recoverable.

**For any:** lock file with mtime in (stale_timeout, stale_timeout * 10).
**Invariant:** acquire() succeeds within stale_timeout + 2 * poll_interval.

**Assertion pseudocode:**
```
FOR ANY stale_age IN range(stale_timeout, stale_timeout * 10):
    create_lock_file(mtime=now - stale_age)
    start = time.time()
    await lock.acquire()
    elapsed = time.time() - start
    ASSERT elapsed < stale_timeout + 2 * poll_interval
    await lock.release()
```

### TS-45-P4: No Blind Strategy Options

**Property:** Property 4 from design.md
**Validates:** 45-REQ-6.1, 45-REQ-6.2
**Type:** unit
**Description:** Source code does not contain -X theirs or -X ours calls.

**For any:** N/A (static analysis)
**Invariant:** harvest.py and workspace.py do not contain `"-X", "theirs"` or
`"-X", "ours"` argument sequences in merge calls.

**Assertion pseudocode:**
```
harvest_src = read("agent_fox/workspace/harvest.py")
workspace_src = read("agent_fox/workspace/workspace.py")
ASSERT '"-X", "theirs"' NOT IN harvest_src
ASSERT '"theirs"' NOT IN harvest_src  # as strategy_option
ASSERT '"-X", "ours"' NOT IN workspace_src
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 45-REQ-1.1 | TS-45-1 | unit |
| 45-REQ-1.2 | TS-45-2 | unit |
| 45-REQ-1.3 | TS-45-3 | unit |
| 45-REQ-1.4 | TS-45-4 | integration |
| 45-REQ-1.E1 | TS-45-E1 | unit |
| 45-REQ-1.E2 | TS-45-E2 | unit |
| 45-REQ-1.E3 | TS-45-E3 | unit |
| 45-REQ-2.1 | TS-45-5 | unit |
| 45-REQ-2.2 | TS-45-6 | unit |
| 45-REQ-2.E1 | TS-45-E4 | unit |
| 45-REQ-3.1 | TS-45-7 | unit |
| 45-REQ-3.2 | TS-45-8 | unit |
| 45-REQ-4.1 | TS-45-9 | unit |
| 45-REQ-4.2 | TS-45-10 | unit |
| 45-REQ-4.3 | TS-45-11 | unit |
| 45-REQ-4.4 | TS-45-12 | unit |
| 45-REQ-4.5 | TS-45-13 | unit |
| 45-REQ-4.E1 | TS-45-E5 | unit |
| 45-REQ-4.E2 | TS-45-E6 | unit |
| 45-REQ-5.1 | TS-45-9 | unit |
| 45-REQ-5.2 | TS-45-13 | unit |
| 45-REQ-5.E1 | TS-45-E7 | unit |
| 45-REQ-6.1 | TS-45-E8 | unit |
| 45-REQ-6.2 | TS-45-E9 | unit |
| Property 1 | TS-45-P1 | property |
| Property 2 | TS-45-P2 | property |
| Property 3 | TS-45-P3 | property |
| Property 4 | TS-45-P4 | unit |
