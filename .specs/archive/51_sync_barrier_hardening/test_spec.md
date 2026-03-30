# Test Specification: Sync Barrier Hardening

## Overview

Tests are organized into three groups: barrier entry operations (drain,
worktree verification, develop sync), the hot-load gate pipeline (git-tracked,
completeness, lint), and property-based tests for gate correctness and
stateless re-evaluation. All tests use mocks for git operations and filesystem
access.

## Test Cases

### TS-51-1: Parallel drain waits for all in-flight tasks

**Requirement:** 51-REQ-1.1
**Type:** unit
**Description:** Verify that the orchestrator waits for all in-flight parallel
tasks to complete before entering the barrier.

**Preconditions:**
- Orchestrator running in parallel mode with `max_parallelism=3`.
- 3 tasks currently in-flight in the pool.
- Completed task count hits `sync_interval` boundary.

**Input:**
- Pool with 3 asyncio tasks (mocked to complete after short delays).

**Expected:**
- All 3 tasks complete before any barrier operation begins.
- Session results for all 3 tasks are processed.

**Assertion pseudocode:**
```
pool = [create_mock_task(delay=0.1) for _ in 3]
trigger barrier
ASSERT pool is empty after drain
ASSERT all 3 session results recorded in state
ASSERT barrier operations ran AFTER all results processed
```

### TS-51-2: Drained task results are processed

**Requirement:** 51-REQ-1.2
**Type:** unit
**Description:** Verify that session results from drained tasks are processed
(state updates, cascade blocking).

**Preconditions:**
- 2 in-flight tasks: one succeeds, one fails.

**Input:**
- Task A returns completed SessionRecord.
- Task B returns failed SessionRecord.

**Expected:**
- Task A node_state is "completed".
- Task B node_state is "pending" (retry) or "blocked" (exhausted).
- State is persisted after processing.

**Assertion pseudocode:**
```
drain_and_process(pool=[task_a, task_b])
ASSERT state.node_states["A"] == "completed"
ASSERT state.node_states["B"] in ("pending", "blocked")
ASSERT state_manager.save called
```

### TS-51-3: No new tasks dispatched during drain

**Requirement:** 51-REQ-1.3
**Type:** unit
**Description:** Verify that no new tasks are dispatched while the parallel
pool is being drained.

**Preconditions:**
- 2 in-flight tasks, 3 more tasks are ready.

**Input:**
- Pool with 2 tasks. Ready queue has 3 tasks.

**Expected:**
- After drain completes, pool is empty.
- The 3 ready tasks are NOT launched during the drain.
- They are launched only after the barrier completes.

**Assertion pseudocode:**
```
drain_pool(pool)
ASSERT no new tasks created during drain
ASSERT fill_pool called only after barrier completes
```

### TS-51-4: Serial mode skips drain

**Requirement:** 51-REQ-1.E1
**Type:** unit
**Description:** Verify that serial mode skips the parallel drain step.

**Preconditions:**
- Orchestrator running in serial mode (`parallel=1`).

**Input:**
- Barrier triggered after task completion.

**Expected:**
- No drain operation attempted.
- Barrier proceeds directly to worktree verification.

**Assertion pseudocode:**
```
orchestrator = Orchestrator(config=OrchestratorConfig(parallel=1))
trigger barrier
ASSERT drain not called
ASSERT verify_worktrees called
```

### TS-51-5: Worktree verification finds orphans

**Requirement:** 51-REQ-2.1, 51-REQ-2.2
**Type:** unit
**Description:** Verify that orphaned worktree directories are detected and
logged.

**Preconditions:**
- `.agent-fox/worktrees/` contains two subdirectories:
  `spec_a/1/` and `spec_b/2/`.

**Input:**
- Filesystem with orphaned worktree directories.

**Expected:**
- Returns list of 2 orphaned paths.
- WARNING log emitted listing both paths.

**Assertion pseudocode:**
```
create_dirs(".agent-fox/worktrees/spec_a/1", ".agent-fox/worktrees/spec_b/2")
result = verify_worktrees(repo_root)
ASSERT len(result) == 2
ASSERT "spec_a" in log_output
ASSERT "spec_b" in log_output
```

### TS-51-6: Worktree verification with no orphans

**Requirement:** 51-REQ-2.3
**Type:** unit
**Description:** Verify that verification passes cleanly when no orphaned
worktrees exist.

**Preconditions:**
- `.agent-fox/worktrees/` exists but is empty.

**Input:**
- Empty worktrees directory.

**Expected:**
- Returns empty list.
- No warnings logged.

**Assertion pseudocode:**
```
create_dir(".agent-fox/worktrees/")
result = verify_worktrees(repo_root)
ASSERT result == []
ASSERT no WARNING in log_output
```

### TS-51-7: Worktree dir missing

**Requirement:** 51-REQ-2.E1
**Type:** unit
**Description:** Verify that missing worktrees directory is handled gracefully.

**Preconditions:**
- `.agent-fox/worktrees/` does not exist.

**Expected:**
- Returns empty list, no exception.

**Assertion pseudocode:**
```
result = verify_worktrees(repo_root)
ASSERT result == []
```

### TS-51-8: Bidirectional develop sync success

**Requirement:** 51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3
**Type:** unit
**Description:** Verify that develop is pulled from origin then pushed back.

**Preconditions:**
- Origin remote exists.
- Local develop is behind origin (pull needed).

**Input:**
- Mock git commands for fetch, sync, and push.

**Expected:**
- Pull sync runs first.
- Push runs after pull completes.
- MergeLock acquired before operations, released after.

**Assertion pseudocode:**
```
mock_git(fetch=success, sync=success, push=success)
sync_develop_bidirectional(repo_root)
ASSERT call_order == [lock.acquire, fetch, sync, push, lock.release]
```

### TS-51-9: Pull sync failure skips push

**Requirement:** 51-REQ-3.E1
**Type:** unit
**Description:** Verify that push is skipped when pull sync fails.

**Preconditions:**
- Origin remote exists.

**Input:**
- Mock git fetch to fail.

**Expected:**
- Warning logged about sync failure.
- Push is NOT attempted.
- No exception raised.

**Assertion pseudocode:**
```
mock_git(fetch=failure)
sync_develop_bidirectional(repo_root)
ASSERT push not called
ASSERT WARNING in log_output
ASSERT no exception raised
```

### TS-51-10: Push failure is non-blocking

**Requirement:** 51-REQ-3.E2
**Type:** unit
**Description:** Verify that push failure does not block the barrier.

**Preconditions:**
- Pull sync succeeds.

**Input:**
- Mock push to fail.

**Expected:**
- Warning logged about push failure.
- No exception raised.

**Assertion pseudocode:**
```
mock_git(fetch=success, sync=success, push=failure)
sync_develop_bidirectional(repo_root)
ASSERT WARNING in log_output
ASSERT no exception raised
```

### TS-51-11: No origin remote skips sync

**Requirement:** 51-REQ-3.E3
**Type:** unit
**Description:** Verify that the entire sync is skipped when no origin remote.

**Preconditions:**
- No remote named `origin`.

**Input:**
- Mock git remote to report no origin.

**Expected:**
- Sync skipped entirely (no fetch, no push).
- No exception raised.

**Assertion pseudocode:**
```
mock_git(remote_exists=False)
sync_develop_bidirectional(repo_root)
ASSERT fetch not called
ASSERT push not called
```

### TS-51-12: Git-tracked gate accepts tracked spec

**Requirement:** 51-REQ-4.1
**Type:** unit
**Description:** Verify that a spec tracked on develop passes the gate.

**Preconditions:**
- Spec folder `42_feature` committed to develop branch.

**Input:**
- `git ls-tree develop -- .specs/42_feature` returns entries.

**Expected:**
- Returns True.

**Assertion pseudocode:**
```
mock_git(ls_tree="100644 blob abc123 prd.md")
result = is_spec_tracked_on_develop(repo_root, "42_feature")
ASSERT result is True
```

### TS-51-13: Git-tracked gate rejects untracked spec

**Requirement:** 51-REQ-4.2
**Type:** unit
**Description:** Verify that an untracked spec folder is rejected.

**Preconditions:**
- Spec folder exists on disk but is not committed to develop.

**Input:**
- `git ls-tree develop -- .specs/42_feature` returns empty output.

**Expected:**
- Returns False.

**Assertion pseudocode:**
```
mock_git(ls_tree="")
result = is_spec_tracked_on_develop(repo_root, "42_feature")
ASSERT result is False
```

### TS-51-14: Git-tracked gate fallback on failure

**Requirement:** 51-REQ-4.E1
**Type:** unit
**Description:** Verify that git ls-tree failure falls back to permissive.

**Preconditions:**
- git ls-tree command fails (non-zero exit).

**Input:**
- Mock git ls-tree to fail.

**Expected:**
- Returns True (permissive fallback).
- Warning logged.

**Assertion pseudocode:**
```
mock_git(ls_tree=failure)
result = is_spec_tracked_on_develop(repo_root, "42_feature")
ASSERT result is True
ASSERT WARNING in log_output
```

### TS-51-15: Completeness gate with all files

**Requirement:** 51-REQ-5.1
**Type:** unit
**Description:** Verify that a spec with all 5 non-empty files passes.

**Preconditions:**
- Spec folder with prd.md, requirements.md, design.md, test_spec.md,
  tasks.md — all non-empty.

**Input:**
- Path to complete spec folder.

**Expected:**
- Returns (True, []).

**Assertion pseudocode:**
```
create_spec_files(all_five, content="non-empty")
passed, missing = is_spec_complete(spec_path)
ASSERT passed is True
ASSERT missing == []
```

### TS-51-16: Completeness gate with missing file

**Requirement:** 51-REQ-5.2
**Type:** unit
**Description:** Verify that a spec missing design.md is rejected.

**Preconditions:**
- Spec folder with 4 files (no design.md).

**Input:**
- Path to spec folder missing design.md.

**Expected:**
- Returns (False, ["design.md"]).

**Assertion pseudocode:**
```
create_spec_files(["prd.md", "requirements.md", "test_spec.md", "tasks.md"])
passed, missing = is_spec_complete(spec_path)
ASSERT passed is False
ASSERT "design.md" in missing
```

### TS-51-17: Completeness gate with empty file

**Requirement:** 51-REQ-5.E1
**Type:** unit
**Description:** Verify that a spec with an empty file is treated as
incomplete.

**Preconditions:**
- All 5 files exist, but requirements.md is 0 bytes.

**Input:**
- Path to spec folder with empty requirements.md.

**Expected:**
- Returns (False, ["requirements.md"]).

**Assertion pseudocode:**
```
create_spec_files(all_five, empty=["requirements.md"])
passed, missing = is_spec_complete(spec_path)
ASSERT passed is False
ASSERT "requirements.md" in missing
```

### TS-51-18: Lint gate accepts clean spec

**Requirement:** 51-REQ-6.1, 51-REQ-6.3
**Type:** unit
**Description:** Verify that a spec with no error findings passes the gate.

**Preconditions:**
- Validator returns findings with severity "warning" only.

**Input:**
- Mock validator returning 2 warnings, 0 errors.

**Expected:**
- Returns (True, []).

**Assertion pseudocode:**
```
mock_validator(findings=[warning1, warning2])
passed, errors = lint_spec_gate("42_feature", spec_path)
ASSERT passed is True
ASSERT errors == []
```

### TS-51-19: Lint gate rejects spec with errors

**Requirement:** 51-REQ-6.2
**Type:** unit
**Description:** Verify that a spec with error findings is rejected.

**Preconditions:**
- Validator returns findings including severity "error".

**Input:**
- Mock validator returning 1 error ("missing-file"), 1 warning.

**Expected:**
- Returns (False, ["missing-file: ..."]).

**Assertion pseudocode:**
```
mock_validator(findings=[error_finding, warning_finding])
passed, errors = lint_spec_gate("42_feature", spec_path)
ASSERT passed is False
ASSERT len(errors) == 1
ASSERT "missing-file" in errors[0]
```

### TS-51-20: Lint gate handles validator exception

**Requirement:** 51-REQ-6.E1
**Type:** unit
**Description:** Verify that a validator crash is handled gracefully.

**Preconditions:**
- Validator raises RuntimeError.

**Input:**
- Mock validator to raise RuntimeError("boom").

**Expected:**
- Returns (False, ["Validator error: boom"]).
- No exception propagated.

**Assertion pseudocode:**
```
mock_validator(raises=RuntimeError("boom"))
passed, errors = lint_spec_gate("42_feature", spec_path)
ASSERT passed is False
ASSERT "boom" in errors[0]
```

### TS-51-21: Full gate pipeline filters correctly

**Requirement:** 51-REQ-7.1
**Type:** unit
**Description:** Verify that the full pipeline filters specs through all gates.

**Preconditions:**
- 3 candidate specs on filesystem:
  - spec_a: tracked, complete, lint-clean
  - spec_b: tracked, complete, has lint errors
  - spec_c: not tracked on develop

**Input:**
- Specs dir with 3 candidate folders.

**Expected:**
- Only spec_a is returned from `discover_new_specs_gated`.
- spec_b skipped at lint gate.
- spec_c skipped at git-tracked gate.

**Assertion pseudocode:**
```
setup_specs(spec_a=valid, spec_b=lint_errors, spec_c=untracked)
result = discover_new_specs_gated(specs_dir, known={}, repo_root)
ASSERT result == [spec_a_info]
```

### TS-51-22: Previously skipped spec accepted after fix

**Requirement:** 51-REQ-7.2, 51-REQ-7.3
**Type:** unit
**Description:** Verify that a spec skipped at barrier N passes at barrier N+1
after being fixed.

**Preconditions:**
- Spec was incomplete (missing design.md) at first evaluation.
- design.md added before second evaluation.

**Input:**
- First call: spec missing design.md.
- Second call: spec has all 5 files.

**Expected:**
- First call returns empty (spec skipped).
- Second call returns spec (accepted).

**Assertion pseudocode:**
```
# Barrier N
result_1 = discover_new_specs_gated(specs_dir, known={}, repo_root)
ASSERT result_1 == []

# Fix spec
add_file("design.md")

# Barrier N+1
result_2 = discover_new_specs_gated(specs_dir, known={}, repo_root)
ASSERT len(result_2) == 1
```

## Property Test Cases

### TS-51-P1: Parallel drain empties pool

**Property:** Property 1 from design.md
**Validates:** 51-REQ-1.1, 51-REQ-1.2
**Type:** property
**Description:** For any set of tasks in the pool, the drain operation empties
the pool and processes all results.

**For any:** Set of 1-10 mock tasks with random success/failure outcomes.
**Invariant:** After drain, pool size is 0 and len(processed_results) equals
original pool size.

**Assertion pseudocode:**
```
FOR ANY tasks IN sets_of(mock_tasks, min=1, max=10):
    pool = set(tasks)
    results = drain_pool(pool)
    ASSERT len(pool) == 0
    ASSERT len(results) == len(tasks)
```

### TS-51-P2: Worktree verification never raises

**Property:** Property 2 from design.md
**Validates:** 51-REQ-2.1, 51-REQ-2.E1
**Type:** property
**Description:** For any filesystem state, worktree verification completes
without exception.

**For any:** Filesystem state where `.agent-fox/worktrees/` may or may not
exist and may contain 0-5 subdirectories.
**Invariant:** `verify_worktrees` returns a list (possibly empty) without
raising.

**Assertion pseudocode:**
```
FOR ANY fs_state IN worktree_filesystem_states():
    setup_filesystem(fs_state)
    result = verify_worktrees(repo_root)
    ASSERT isinstance(result, list)
```

### TS-51-P3: Develop sync never raises

**Property:** Property 3 from design.md
**Validates:** 51-REQ-3.E1, 51-REQ-3.E2, 51-REQ-3.E3
**Type:** property
**Description:** For any combination of git operation outcomes, bidirectional
sync completes without raising.

**For any:** Combination of (fetch: ok|fail, sync: ok|fail, push: ok|fail,
remote_exists: true|false).
**Invariant:** `sync_develop_bidirectional` completes without exception.

**Assertion pseudocode:**
```
FOR ANY (fetch, sync, push, remote) IN git_outcome_combos():
    mock_git_outcomes(fetch, sync, push, remote)
    sync_develop_bidirectional(repo_root)  # must not raise
```

### TS-51-P4: Gate pipeline is monotonically filtering

**Property:** Property 4 from design.md
**Validates:** 51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1, 51-REQ-7.1
**Type:** property
**Description:** For any set of candidate specs with arbitrary gate states,
the output is a subset where every element passes all three gates.

**For any:** List of 1-10 specs, each with random (tracked: bool, complete:
bool, lint_clean: bool).
**Invariant:** Every spec in the output has tracked=True AND complete=True AND
lint_clean=True. Output size <= input size.

**Assertion pseudocode:**
```
FOR ANY specs IN lists_of(spec_states, min=1, max=10):
    result = run_gate_pipeline(specs)
    ASSERT len(result) <= len(specs)
    FOR EACH spec IN result:
        ASSERT spec.tracked AND spec.complete AND spec.lint_clean
```

### TS-51-P5: Git-tracked gate correctness

**Property:** Property 5 from design.md
**Validates:** 51-REQ-4.1, 51-REQ-4.E1
**Type:** property
**Description:** Git-tracked gate returns True iff ls-tree has output, or
True on failure (permissive fallback).

**For any:** ls-tree output in {"entries", "", failure}.
**Invariant:** Result is True when output is non-empty OR on failure. False
only when output is empty and command succeeded.

**Assertion pseudocode:**
```
FOR ANY (output, success) IN ls_tree_outcomes():
    result = is_spec_tracked_on_develop(repo_root, spec_name)
    IF not success:
        ASSERT result is True  # permissive fallback
    ELIF output != "":
        ASSERT result is True
    ELSE:
        ASSERT result is False
```

### TS-51-P6: Completeness gate correctness

**Property:** Property 6 from design.md
**Validates:** 51-REQ-5.1, 51-REQ-5.E1
**Type:** property
**Description:** Completeness gate passes iff all 5 files exist and are
non-empty.

**For any:** Subset of the 5 required files present, each either empty or
non-empty.
**Invariant:** Passes iff all 5 present AND all non-empty. Missing list
contains exactly the files that are absent or empty.

**Assertion pseudocode:**
```
FOR ANY file_states IN file_presence_combos():
    setup_spec_dir(file_states)
    passed, missing = is_spec_complete(spec_path)
    expected_missing = [f for f in REQUIRED if not present(f) or empty(f)]
    ASSERT passed == (len(expected_missing) == 0)
    ASSERT set(missing) == set(expected_missing)
```

### TS-51-P7: Lint gate correctness

**Property:** Property 7 from design.md
**Validates:** 51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1
**Type:** property
**Description:** Lint gate passes iff validator produces no error-severity
findings. On exception, gate fails.

**For any:** List of 0-10 findings with random severities, or a validator
exception.
**Invariant:** Passes iff no finding has severity "error" and no exception
occurred.

**Assertion pseudocode:**
```
FOR ANY findings IN lists_of(finding_severities(), max=10):
    mock_validator(findings)
    passed, errors = lint_spec_gate(spec_name, spec_path)
    has_errors = any(f.severity == "error" for f in findings)
    ASSERT passed == (not has_errors)
```

### TS-51-P8: Stateless re-evaluation

**Property:** Property 8 from design.md
**Validates:** 51-REQ-7.2, 51-REQ-7.3
**Type:** property
**Description:** The gate pipeline outcome for a spec depends only on its
current state, not on prior evaluations.

**For any:** Spec evaluated twice with potentially different states between
evaluations.
**Invariant:** The second evaluation's result depends only on the spec's
state at evaluation time, not on the first evaluation's outcome.

**Assertion pseudocode:**
```
FOR ANY (state_1, state_2) IN pairs_of(spec_states()):
    setup_spec(state_1)
    result_1 = run_gate_pipeline([spec])
    setup_spec(state_2)
    result_2 = run_gate_pipeline([spec])
    # Verify result_2 matches what state_2 alone would produce
    setup_spec(state_2)
    result_fresh = run_gate_pipeline([spec])
    ASSERT result_2 == result_fresh
```

## Edge Case Tests

### TS-51-E1: SIGINT during parallel drain

**Requirement:** 51-REQ-1.E2
**Type:** unit
**Description:** Verify that SIGINT during drain cancels remaining tasks and
proceeds to shutdown.

**Preconditions:**
- 3 tasks in pool, SIGINT delivered after first completes.

**Input:**
- Mock SIGINT delivery during asyncio.wait.

**Expected:**
- Remaining tasks cancelled.
- Orchestrator enters shutdown state.

**Assertion pseudocode:**
```
deliver_sigint_during_drain()
ASSERT state.run_status == RunStatus.INTERRUPTED
```

### TS-51-E2: Empty spec file treated as incomplete

**Requirement:** 51-REQ-5.E1
**Type:** unit
**Description:** Verify that a zero-byte spec file causes the completeness
gate to fail.

**Preconditions:**
- All 5 files exist, tasks.md is 0 bytes.

**Input:**
- Spec folder with empty tasks.md.

**Expected:**
- Returns (False, ["tasks.md"]).

**Assertion pseudocode:**
```
create_spec_files(all_five, empty=["tasks.md"])
passed, missing = is_spec_complete(spec_path)
ASSERT passed is False
ASSERT "tasks.md" in missing
```

### TS-51-E3: Validator crash handled gracefully

**Requirement:** 51-REQ-6.E1
**Type:** unit
**Description:** Same as TS-51-20 (validator exception handling).

**Preconditions:**
- Validator raises an exception.

**Input:**
- Mock validator to raise.

**Expected:**
- Gate returns (False, [...]).
- No exception propagated.

**Assertion pseudocode:**
```
mock_validator(raises=Exception("crash"))
passed, errors = lint_spec_gate(spec_name, spec_path)
ASSERT passed is False
ASSERT no exception propagated
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 51-REQ-1.1 | TS-51-1 | unit |
| 51-REQ-1.2 | TS-51-2 | unit |
| 51-REQ-1.3 | TS-51-3 | unit |
| 51-REQ-1.E1 | TS-51-4 | unit |
| 51-REQ-1.E2 | TS-51-E1 | unit |
| 51-REQ-2.1 | TS-51-5 | unit |
| 51-REQ-2.2 | TS-51-5 | unit |
| 51-REQ-2.3 | TS-51-6 | unit |
| 51-REQ-2.E1 | TS-51-7 | unit |
| 51-REQ-3.1 | TS-51-8 | unit |
| 51-REQ-3.2 | TS-51-8 | unit |
| 51-REQ-3.3 | TS-51-8 | unit |
| 51-REQ-3.E1 | TS-51-9 | unit |
| 51-REQ-3.E2 | TS-51-10 | unit |
| 51-REQ-3.E3 | TS-51-11 | unit |
| 51-REQ-4.1 | TS-51-12 | unit |
| 51-REQ-4.2 | TS-51-13 | unit |
| 51-REQ-4.E1 | TS-51-14 | unit |
| 51-REQ-5.1 | TS-51-15 | unit |
| 51-REQ-5.2 | TS-51-16 | unit |
| 51-REQ-5.E1 | TS-51-17, TS-51-E2 | unit |
| 51-REQ-6.1 | TS-51-18 | unit |
| 51-REQ-6.2 | TS-51-19 | unit |
| 51-REQ-6.3 | TS-51-18 | unit |
| 51-REQ-6.E1 | TS-51-20, TS-51-E3 | unit |
| 51-REQ-7.1 | TS-51-21 | unit |
| 51-REQ-7.2 | TS-51-22 | unit |
| 51-REQ-7.3 | TS-51-22 | unit |
| Property 1 | TS-51-P1 | property |
| Property 2 | TS-51-P2 | property |
| Property 3 | TS-51-P3 | property |
| Property 4 | TS-51-P4 | property |
| Property 5 | TS-51-P5 | property |
| Property 6 | TS-51-P6 | property |
| Property 7 | TS-51-P7 | property |
| Property 8 | TS-51-P8 | property |
