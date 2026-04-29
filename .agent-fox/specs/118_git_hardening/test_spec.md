# Test Specification: Git Stack Hardening

## Overview

Tests are organized by requirement area: workspace health checks, force-clean,
non-retryable error classification, pre-session guards, develop sync audit,
run lifecycle, cascade blocking, and error diagnostics. Each test maps to one
or more acceptance criteria from `requirements.md` and correctness properties
from `design.md`.

Git operations are tested against real temporary repositories (via
`tmp_path` / `git init`). Only external I/O (audit event sinks, database writes)
is mocked.

## Test Cases

### TS-118-1: Health check detects untracked files

**Requirement:** 118-REQ-1.1
**Type:** unit
**Description:** Verify that `check_workspace_health` returns all untracked
files in the repo.

**Preconditions:**
- A git repository with 3 committed files and 2 untracked files in code
  directories (e.g., `src/foo.py`, `src/bar.py`).

**Input:**
- `repo_root` pointing to the test repository.

**Expected:**
- `HealthReport.untracked_files` contains exactly the 2 untracked file paths.
- `HealthReport.has_issues` is `True`.

**Assertion pseudocode:**
```
report = check_workspace_health(repo_root)
ASSERT set(report.untracked_files) == {"src/foo.py", "src/bar.py"}
ASSERT report.has_issues == True
```

### TS-118-2: Health check reports clean repo

**Requirement:** 118-REQ-1.3
**Type:** unit
**Description:** Verify that a clean repo produces an empty health report.

**Preconditions:**
- A git repository with all files committed, no untracked files.

**Input:**
- `repo_root` pointing to the clean repository.

**Expected:**
- `HealthReport.untracked_files` is empty.
- `HealthReport.dirty_index_files` is empty.
- `HealthReport.has_issues` is `False`.

**Assertion pseudocode:**
```
report = check_workspace_health(repo_root)
ASSERT report.untracked_files == []
ASSERT report.dirty_index_files == []
ASSERT report.has_issues == False
```

### TS-118-3: Health check aborts run when dirty and no force-clean

**Requirement:** 118-REQ-1.2
**Type:** unit
**Description:** Verify that the engine aborts the run when untracked files
are detected and force-clean is disabled.

**Preconditions:**
- A git repository with untracked files.
- `force_clean` is `False`.

**Input:**
- Engine startup with the dirty repo.

**Expected:**
- Run is aborted (WorkspaceError raised or run status set to "failed").
- Error message contains the file list and remediation commands.

**Assertion pseudocode:**
```
report = check_workspace_health(repo_root)
ASSERT report.has_issues == True
# Engine integration: run aborted with diagnostic message
ASSERT "git clean" in error_message
ASSERT "--force-clean" in error_message
```

### TS-118-4: Force-clean removes untracked files

**Requirement:** 118-REQ-2.1
**Type:** unit
**Description:** Verify that `force_clean_workspace` removes all untracked
files and returns an updated clean report.

**Preconditions:**
- A git repository with 3 untracked files.

**Input:**
- `repo_root` and a `HealthReport` listing the 3 files.

**Expected:**
- All 3 files are deleted from disk.
- Returned `HealthReport.has_issues` is `False`.
- WARNING log emitted listing all 3 removed files.

**Assertion pseudocode:**
```
initial = check_workspace_health(repo_root)
ASSERT len(initial.untracked_files) == 3
result = force_clean_workspace(repo_root, initial)
ASSERT result.has_issues == False
for f in initial.untracked_files:
    ASSERT not (repo_root / f).exists()
```

### TS-118-5: Force-clean via CLI flag

**Requirement:** 118-REQ-2.2
**Type:** unit
**Description:** Verify that `--force-clean` CLI flag and config option are
both accepted and the CLI flag takes precedence.

**Preconditions:**
- Config file with `workspace.force_clean = false`.

**Input:**
- CLI invocation with `--force-clean`.

**Expected:**
- Force-clean is enabled (CLI overrides config).

**Assertion pseudocode:**
```
config = load_config(config_path, cli_overrides={"force_clean": True})
ASSERT config.workspace.force_clean == True
```

### TS-118-6: Force-clean during harvest removes divergent files

**Requirement:** 118-REQ-2.3
**Type:** unit
**Description:** Verify that harvest with `force_clean=True` removes divergent
untracked files and proceeds with the merge.

**Preconditions:**
- A git repository on `develop` branch with untracked files whose content
  differs from the incoming feature branch version.

**Input:**
- `harvest(repo_root, workspace, force_clean=True)`

**Expected:**
- Divergent files are removed (not preserved).
- Squash merge succeeds.
- No `IntegrationError` raised.

**Assertion pseudocode:**
```
changed = harvest(repo_root, workspace, force_clean=True)
ASSERT len(changed) > 0
# Verify divergent files are gone from working tree
for f in divergent_files:
    ASSERT not (repo_root / f).exists() or file_matches_branch_version(f)
```

### TS-118-7: Non-retryable error on divergent untracked files

**Requirement:** 118-REQ-3.1
**Type:** unit
**Description:** Verify that `_clean_conflicting_untracked` raises
`IntegrationError` with `retryable=False` when divergent files are found.

**Preconditions:**
- A git repository with untracked files whose content differs from the feature
  branch.
- `force_clean` is `False`.

**Input:**
- `_clean_conflicting_untracked(repo_root, feature_branch)`

**Expected:**
- `IntegrationError` raised with `retryable=False`.

**Assertion pseudocode:**
```
with ASSERT_RAISES IntegrationError as exc:
    _clean_conflicting_untracked(repo_root, feature_branch)
ASSERT exc.retryable == False
```

### TS-118-8: Result handler blocks immediately on non-retryable error

**Requirement:** 118-REQ-3.2
**Type:** unit
**Description:** Verify that the result handler blocks a node immediately when
the session record has `is_non_retryable=True`, without consuming escalation
ladder retries.

**Preconditions:**
- A `SessionRecord` with `status="failed"` and `is_non_retryable=True`.
- An escalation ladder with remaining retries.

**Input:**
- `result_handler.process(record, attempt=1, state, ...)`

**Expected:**
- Node is blocked (status = "blocked").
- Escalation ladder retry count is unchanged (no `record_failure` called).
- Blocked reason contains "workspace-state".

**Assertion pseudocode:**
```
record = SessionRecord(status="failed", is_non_retryable=True, ...)
handler.process(record, attempt=1, state, attempt_tracker, error_tracker)
ASSERT state.node_states[node_id] == "blocked"
ASSERT "workspace-state" in state.blocked_reasons[node_id]
ASSERT ladder.attempt_count == 1  # no additional failures recorded
```

### TS-118-9: Merge conflict errors remain retryable

**Requirement:** 118-REQ-3.E1
**Type:** unit
**Description:** Verify that harvest failures from merge conflicts (not
untracked files) produce retryable errors.

**Preconditions:**
- A git repository where squash merge produces a conflict.
- Merge agent fails to resolve.

**Input:**
- `harvest(repo_root, workspace)`

**Expected:**
- `IntegrationError` raised with `retryable=True` (default).

**Assertion pseudocode:**
```
with ASSERT_RAISES IntegrationError as exc:
    harvest(repo_root, workspace)
ASSERT exc.retryable == True
```

### TS-118-10: Pre-session check blocks node on dirty workspace

**Requirement:** 118-REQ-4.2
**Type:** unit
**Description:** Verify that the pre-session workspace check blocks the node
when untracked files are detected.

**Preconditions:**
- A git repository with untracked files.
- A node ready for dispatch.

**Input:**
- `prepare_launch(node_id, state, ...)`

**Expected:**
- Returns `None` (dispatch skipped).
- Node status is "blocked" with diagnostic message.

**Assertion pseudocode:**
```
# Create untracked files in repo
result = prepare_launch(node_id, state, attempt_tracker, error_tracker)
ASSERT result is None
ASSERT state.node_states[node_id] == "blocked"
```

### TS-118-11: Develop sync emits audit event on success

**Requirement:** 118-REQ-5.1
**Type:** unit
**Description:** Verify that a successful develop sync emits a `develop.sync`
audit event with the correct payload.

**Preconditions:**
- A git repository with develop behind origin/develop by 2 commits.
- Audit event sink (mock).

**Input:**
- `_sync_develop_under_lock(repo_root, remote_ahead=2, local_ahead=0)`

**Expected:**
- `develop.sync` audit event emitted with `method="fast-forward"`,
  `remote_ahead=2`, `local_ahead=0`.

**Assertion pseudocode:**
```
sync_develop_under_lock(repo_root, remote_ahead=2, local_ahead=0)
ASSERT sink.events[-1].event_type == "develop.sync"
ASSERT sink.events[-1].payload["method"] == "fast-forward"
```

### TS-118-12: Develop sync emits audit event on failure

**Requirement:** 118-REQ-5.2
**Type:** unit
**Description:** Verify that a failed develop sync emits a
`develop.sync_failed` audit event.

**Preconditions:**
- A git repository where develop sync fails (e.g., rebase conflict + merge
  agent failure).
- Audit event sink (mock).

**Input:**
- Trigger develop sync that fails.

**Expected:**
- `develop.sync_failed` audit event emitted with failure reason.

**Assertion pseudocode:**
```
# Trigger sync failure
ASSERT sink.events[-1].event_type == "develop.sync_failed"
ASSERT "reason" in sink.events[-1].payload
```

### TS-118-13: Stale run detection on startup

**Requirement:** 118-REQ-6.1
**Type:** unit
**Description:** Verify that stale "running" runs are detected and transitioned
to "stalled" on engine startup.

**Preconditions:**
- Knowledge database with 2 runs: one with status "running" (from prior
  process), one with status "completed".

**Input:**
- Engine startup sequence.

**Expected:**
- The "running" run is transitioned to "stalled".
- The "completed" run is unchanged.
- Returned stale count is 1.

**Assertion pseudocode:**
```
stale_count = detect_and_clean_stale_runs(conn)
ASSERT stale_count == 1
run = conn.execute("SELECT status FROM runs WHERE id = ?", [stale_id]).fetchone()
ASSERT run[0] == "stalled"
```

### TS-118-14: Cleanup handler transitions run on exit

**Requirement:** 118-REQ-6.2
**Type:** unit
**Description:** Verify that the registered cleanup handler transitions the
current run to "stalled" when invoked.

**Preconditions:**
- A run with status "running" in the database.
- Cleanup handler registered.

**Input:**
- Invoke the cleanup handler directly.

**Expected:**
- Run status transitions to "stalled".

**Assertion pseudocode:**
```
cleanup_handler(run_id, conn)
run = conn.execute("SELECT status FROM runs WHERE id = ?", [run_id]).fetchone()
ASSERT run[0] == "stalled"
```

### TS-118-15: Idempotent cascade blocking on blocked node

**Requirement:** 118-REQ-7.1
**Type:** unit
**Description:** Verify that cascade-blocking an already-blocked node produces
no warning and no state change.

**Preconditions:**
- A task graph where node B depends on node A.
- Node B is already in "blocked" state.

**Input:**
- `mark_blocked(node_B, reason="cascade from A")`

**Expected:**
- No state change (B remains blocked with original reason).
- No WARNING log emitted.

**Assertion pseudocode:**
```
graph_sync.mark_blocked(node_B, "original reason")
# Capture log output
graph_sync.mark_blocked(node_B, "cascade from A")
ASSERT state.node_states[node_B] == "blocked"
ASSERT "original reason" in state.blocked_reasons[node_B]
ASSERT no WARNING in captured_logs
```

### TS-118-16: Cascade blocking skips completed nodes

**Requirement:** 118-REQ-7.2
**Type:** unit
**Description:** Verify that cascade-blocking a completed node is silently
skipped.

**Preconditions:**
- A task graph where node B depends on node A.
- Node B is in "completed" state.

**Input:**
- `mark_blocked(node_A, reason="test")` which cascades to B.

**Expected:**
- Node B remains "completed" (no transition).

**Assertion pseudocode:**
```
state.node_states[node_B] = "completed"
graph_sync.mark_blocked(node_A, "test")
ASSERT state.node_states[node_B] == "completed"
```

### TS-118-17: Error message includes remediation hints

**Requirement:** 118-REQ-8.1
**Type:** unit
**Description:** Verify that harvest error messages include file list,
remediation command, and force-clean suggestion.

**Preconditions:**
- A harvest failure due to divergent untracked files.

**Input:**
- The error message from the `IntegrationError`.

**Expected:**
- Message contains at least one file path.
- Message contains `git clean`.
- Message contains `--force-clean`.

**Assertion pseudocode:**
```
with ASSERT_RAISES IntegrationError as exc:
    _clean_conflicting_untracked(repo_root, feature_branch)
msg = str(exc)
ASSERT "src/foo.py" in msg  # at least one file
ASSERT "git clean" in msg
ASSERT "--force-clean" in msg
```

### TS-118-18: Health check diagnostic format

**Requirement:** 118-REQ-8.2
**Type:** unit
**Description:** Verify that `format_health_diagnostic` produces actionable
output with file list, remediation, and force-clean suggestion.

**Preconditions:**
- A `HealthReport` with 3 untracked files.

**Input:**
- `format_health_diagnostic(report)`

**Expected:**
- Output contains all 3 file paths.
- Output contains `git clean`.
- Output contains `--force-clean`.

**Assertion pseudocode:**
```
report = HealthReport(untracked_files=["a.py", "b.py", "c.py"], dirty_index_files=[])
msg = format_health_diagnostic(report)
ASSERT "a.py" in msg
ASSERT "b.py" in msg
ASSERT "c.py" in msg
ASSERT "git clean" in msg
ASSERT "--force-clean" in msg
```

## Property Test Cases

### TS-118-P1: Health check completeness

**Property:** Property 1 from design.md
**Validates:** 118-REQ-1.1
**Type:** property
**Description:** For any set of untracked files, the health check reports
all of them.

**For any:** Set of 0-20 file paths (ascii alphanumeric + `/` + `.`),
created as untracked files in a git repo.
**Invariant:** `set(report.untracked_files) == set(created_files)`

**Assertion pseudocode:**
```
FOR ANY files IN sets_of_file_paths(min=0, max=20):
    create_untracked_files(repo_root, files)
    report = check_workspace_health(repo_root)
    ASSERT set(report.untracked_files) == set(files)
```

### TS-118-P2: Force-clean safety

**Property:** Property 2 from design.md
**Validates:** 118-REQ-2.1
**Type:** property
**Description:** Force-clean only removes files listed in the health report.

**For any:** Set of 1-10 untracked files in a git repo plus 1-5 committed
(tracked) files.
**Invariant:** After force-clean, all tracked files still exist on disk.
Only files from the report are removed.

**Assertion pseudocode:**
```
FOR ANY untracked IN file_sets(1, 10), tracked IN file_sets(1, 5):
    setup_repo(tracked, untracked)
    report = check_workspace_health(repo_root)
    force_clean_workspace(repo_root, report)
    for f in tracked:
        ASSERT (repo_root / f).exists()
    for f in untracked:
        ASSERT not (repo_root / f).exists()
```

### TS-118-P3: Non-retryable classification correctness

**Property:** Property 3 from design.md
**Validates:** 118-REQ-3.1, 118-REQ-3.E1
**Type:** property
**Description:** Divergent-file errors are non-retryable; merge-conflict
errors are retryable.

**For any:** IntegrationError raised by `_clean_conflicting_untracked`
(divergent case) or by merge conflict handler.
**Invariant:** Divergent-file errors have `retryable=False`; merge errors
have `retryable=True`.

**Assertion pseudocode:**
```
FOR ANY divergent_files IN non_empty_file_sets():
    setup_divergent_untracked(repo_root, divergent_files)
    with ASSERT_RAISES IntegrationError as exc:
        _clean_conflicting_untracked(repo_root, branch)
    ASSERT exc.retryable == False

FOR ANY conflict_files IN non_empty_file_sets():
    setup_merge_conflict(repo_root, conflict_files)
    with ASSERT_RAISES IntegrationError as exc:
        harvest(repo_root, workspace)
    ASSERT exc.retryable == True
```

### TS-118-P4: Idempotent cascade blocking

**Property:** Property 4 from design.md
**Validates:** 118-REQ-7.1
**Type:** property
**Description:** Blocking an already-blocked node is a no-op.

**For any:** Node in "blocked" state with any blocked reason string.
**Invariant:** Re-blocking produces identical state and no log output.

**Assertion pseudocode:**
```
FOR ANY reason IN text_strings(), new_reason IN text_strings():
    mark_blocked(node, reason)
    state_before = snapshot(state)
    mark_blocked(node, new_reason)  # cascade or direct
    ASSERT snapshot(state) == state_before
```

### TS-118-P5: Run lifecycle completeness

**Property:** Property 5 from design.md
**Validates:** 118-REQ-6.1, 118-REQ-6.2, 118-REQ-6.3
**Type:** property
**Description:** Stale runs are always cleaned up.

**For any:** Set of 1-5 runs with status "running" inserted into the DB.
**Invariant:** After `detect_and_clean_stale_runs`, all have status "stalled".

**Assertion pseudocode:**
```
FOR ANY run_ids IN lists_of_uuids(1, 5):
    insert_runs(conn, run_ids, status="running")
    detect_and_clean_stale_runs(conn)
    for rid in run_ids:
        ASSERT get_run_status(conn, rid) == "stalled"
```

### TS-118-P6: Error message completeness

**Property:** Property 6 from design.md
**Validates:** 118-REQ-8.1, 118-REQ-8.2
**Type:** property
**Description:** Error messages always contain remediation hints.

**For any:** HealthReport with 1-30 untracked files.
**Invariant:** Formatted message contains `git clean` and `--force-clean`.

**Assertion pseudocode:**
```
FOR ANY files IN non_empty_file_lists(max=30):
    report = HealthReport(untracked_files=files, dirty_index_files=[])
    msg = format_health_diagnostic(report)
    ASSERT "git clean" in msg
    ASSERT "--force-clean" in msg
```

### TS-118-P7: Pre-session monotonicity

**Property:** Property 7 from design.md
**Validates:** 118-REQ-4.1, 118-REQ-4.3
**Type:** property
**Description:** A clean health check remains clean on re-check.

**For any:** Clean git repository (no untracked files, clean index).
**Invariant:** Two consecutive calls to `check_workspace_health` both return
`has_issues=False`.

**Assertion pseudocode:**
```
FOR ANY committed_files IN file_sets(1, 10):
    setup_clean_repo(repo_root, committed_files)
    r1 = check_workspace_health(repo_root)
    r2 = check_workspace_health(repo_root)
    ASSERT r1.has_issues == False
    ASSERT r2.has_issues == False
```

## Edge Case Tests

### TS-118-E1: Dirty index detected

**Requirement:** 118-REQ-1.E1
**Type:** unit
**Description:** Verify health check detects staged but uncommitted changes.

**Preconditions:**
- A git repository with a file staged (`git add`) but not committed.

**Input:**
- `check_workspace_health(repo_root)`

**Expected:**
- `HealthReport.dirty_index_files` contains the staged file.
- `HealthReport.has_issues` is `True`.

**Assertion pseudocode:**
```
# Stage a new file without committing
report = check_workspace_health(repo_root)
ASSERT "staged_file.py" in report.dirty_index_files
ASSERT report.has_issues == True
```

### TS-118-E2: Git command error during health check

**Requirement:** 118-REQ-1.E2
**Type:** unit
**Description:** Verify health check fails open on git errors.

**Preconditions:**
- `run_git` patched to return non-zero for `ls-files`.

**Input:**
- `check_workspace_health(repo_root)`

**Expected:**
- Returns empty `HealthReport` (fail-open).
- WARNING logged.

**Assertion pseudocode:**
```
# Patch run_git to fail
report = check_workspace_health(repo_root)
ASSERT report.has_issues == False  # fail-open
ASSERT WARNING in captured_logs
```

### TS-118-E3: Force-clean resets dirty index

**Requirement:** 118-REQ-2.E1
**Type:** unit
**Description:** Verify force-clean resets the git index when dirty.

**Preconditions:**
- A git repository with staged changes and `force_clean=True`.

**Input:**
- `force_clean_workspace(repo_root, report)`

**Expected:**
- Index is clean after force-clean.
- WARNING logged listing reset files.

**Assertion pseudocode:**
```
report = HealthReport(untracked_files=[], dirty_index_files=["modified.py"])
result = force_clean_workspace(repo_root, report)
ASSERT result.dirty_index_files == []
```

### TS-118-E4: Permission error during force-clean

**Requirement:** 118-REQ-2.E2
**Type:** unit
**Description:** Verify force-clean handles permission errors gracefully.

**Preconditions:**
- An untracked file with read-only parent directory (cannot be deleted).

**Input:**
- `force_clean_workspace(repo_root, report)`

**Expected:**
- WARNING logged for the failed file.
- Returned report still has the unresolved file.
- `has_issues` remains `True`.

**Assertion pseudocode:**
```
# Make file undeletable
result = force_clean_workspace(repo_root, report)
ASSERT result.has_issues == True
ASSERT "undeletable.py" in result.untracked_files
```

### TS-118-E5: Pre-session check fails open on git error

**Requirement:** 118-REQ-4.E1
**Type:** unit
**Description:** Verify pre-session check proceeds on git command failure.

**Preconditions:**
- `run_git` patched to fail for `ls-files`.

**Input:**
- Pre-session health check during dispatch.

**Expected:**
- Dispatch proceeds (not blocked).
- WARNING logged.

**Assertion pseudocode:**
```
# Patch run_git to fail
result = prepare_launch(node_id, state, ...)
ASSERT result is not None  # dispatch proceeds
```

### TS-118-E6: Remote unreachable during develop fetch

**Requirement:** 118-REQ-5.E1
**Type:** unit
**Description:** Verify develop sync emits audit event on fetch failure.

**Preconditions:**
- Git remote configured but unreachable.
- Audit event sink (mock).

**Input:**
- `ensure_develop(repo_root)`

**Expected:**
- `develop.fetch_failed` audit event emitted.
- Sync proceeds with local state.

**Assertion pseudocode:**
```
ensure_develop(repo_root)
ASSERT any(e.event_type == "develop.fetch_failed" for e in sink.events)
```

### TS-118-E7: Cleanup handler DB write failure

**Requirement:** 118-REQ-6.E1
**Type:** unit
**Description:** Verify cleanup handler doesn't block on DB failure.

**Preconditions:**
- Database connection that raises on write.

**Input:**
- Invoke cleanup handler.

**Expected:**
- WARNING logged.
- Handler returns without raising.

**Assertion pseudocode:**
```
# Patch DB to raise on UPDATE
cleanup_handler(run_id, broken_conn)  # should not raise
ASSERT WARNING in captured_logs
```

### TS-118-E8: Multiple stale runs cleaned

**Requirement:** 118-REQ-6.E2
**Type:** unit
**Description:** Verify all stale runs are cleaned on startup.

**Preconditions:**
- 3 runs with status "running" in the database.

**Input:**
- `detect_and_clean_stale_runs(conn)`

**Expected:**
- All 3 transitioned to "stalled".
- Returned count is 3.

**Assertion pseudocode:**
```
insert_runs(conn, ["r1", "r2", "r3"], status="running")
count = detect_and_clean_stale_runs(conn)
ASSERT count == 3
for rid in ["r1", "r2", "r3"]:
    ASSERT get_run_status(conn, rid) == "stalled"
```

### TS-118-E9: Cascade skip on in-progress node

**Requirement:** 118-REQ-7.E1
**Type:** unit
**Description:** Verify cascade-blocking skips in-progress nodes with DEBUG
log.

**Preconditions:**
- Node B in "in_progress" state, depends on node A.

**Input:**
- `mark_blocked(node_A, reason="test")` which cascades to B.

**Expected:**
- Node B remains "in_progress".
- DEBUG log emitted.

**Assertion pseudocode:**
```
state.node_states[node_B] = "in_progress"
graph_sync.mark_blocked(node_A, "test")
ASSERT state.node_states[node_B] == "in_progress"
ASSERT DEBUG in captured_logs
```

### TS-118-E10: File list truncation at 20

**Requirement:** 118-REQ-8.E1
**Type:** unit
**Description:** Verify file list is truncated when exceeding 20 files.

**Preconditions:**
- A `HealthReport` with 25 untracked files.

**Input:**
- `format_health_diagnostic(report)`

**Expected:**
- Output lists exactly 20 file paths.
- Output contains "... and 5 more".

**Assertion pseudocode:**
```
files = [f"file_{i}.py" for i in range(25)]
report = HealthReport(untracked_files=files, dirty_index_files=[])
msg = format_health_diagnostic(report)
ASSERT msg.count("\n") <= 25  # max 20 files + header lines
ASSERT "... and 5 more" in msg
```

## Integration Smoke Tests

### TS-118-SMOKE-1: Pre-run health gate blocks dirty repo

**Execution Path:** Path 1 from design.md
**Description:** Full path from engine startup through health check failure
with actionable diagnostics.

**Setup:** Real git repository with untracked files. Mock only the audit event
sink. Do NOT mock `check_workspace_health`, `run_git`, or file I/O.

**Trigger:** Start engine run with `force_clean=False`.

**Expected side effects:**
- Run aborts before any session is dispatched.
- Error message contains file list, `git clean`, and `--force-clean`.
- No session records created.
- Run status is "failed" in DB.

**Must NOT satisfy with:** Mocking `check_workspace_health` or `run_git` —
those are the components under test.

**Assertion pseudocode:**
```
repo = create_dirty_git_repo(tmp_path)
engine = create_engine(repo, force_clean=False)
result = engine.run()
ASSERT result.status == "failed"
ASSERT "git clean" in result.error_message
ASSERT session_count(conn) == 0
```

### TS-118-SMOKE-2: Force-clean enables successful harvest

**Execution Path:** Path 1 + Path 2 from design.md
**Description:** Full path from engine startup through force-clean, session
dispatch, and successful harvest.

**Setup:** Real git repository with untracked files that overlap with spec
output. Real worktree, real harvest. Mock only the coding session (returns
predetermined commits) and the audit event sink.

**Trigger:** Start engine run with `force_clean=True`.

**Expected side effects:**
- Pre-run health check cleans untracked files.
- Session dispatched and completes.
- Harvest succeeds (squash merge to develop).
- No `IntegrationError` raised.

**Must NOT satisfy with:** Mocking `check_workspace_health`,
`force_clean_workspace`, `harvest`, or `_clean_conflicting_untracked`.

**Assertion pseudocode:**
```
repo = create_dirty_git_repo(tmp_path)
engine = create_engine(repo, force_clean=True)
result = engine.run()
ASSERT result.status in ("completed", "stalled")  # run completes
ASSERT harvest_succeeded(conn)
```

### TS-118-SMOKE-3: Non-retryable error skips escalation ladder

**Execution Path:** Path 2 from design.md
**Description:** Full path from harvest failure through non-retryable
classification to immediate node blocking, verifying no escalation retries.

**Setup:** Real git repository with divergent untracked files. Real harvest
(will fail). Mock only the coding session. Do NOT mock harvest or result
handler.

**Trigger:** Session completes, harvest fails due to divergent files.

**Expected side effects:**
- `IntegrationError` raised with `retryable=False`.
- Node blocked immediately (no retry).
- Escalation ladder shows 0 additional failures recorded.
- Blocked reason contains "workspace-state".

**Must NOT satisfy with:** Mocking `_clean_conflicting_untracked`, `harvest`,
or `_handle_failure`.

**Assertion pseudocode:**
```
repo = create_repo_with_divergent_untracked(tmp_path)
engine = create_engine(repo, force_clean=False)
result = engine.run()
ASSERT node_status(conn, "spec:1") == "blocked"
ASSERT "workspace-state" in blocked_reason(conn, "spec:1")
ASSERT session_count(conn, "spec:1") == 1  # no retries
```

### TS-118-SMOKE-4: Stale run cleanup on startup

**Execution Path:** Path 5 from design.md
**Description:** Engine startup detects and cleans stale runs before dispatch.

**Setup:** Knowledge database with a stale "running" run from a prior process.
Real engine startup. Mock only the session runner (no sessions dispatched).

**Trigger:** Engine startup.

**Expected side effects:**
- Stale run transitioned to "stalled" in DB.
- `run.stale_detected` audit event emitted.
- Current run proceeds normally.

**Must NOT satisfy with:** Mocking `detect_and_clean_stale_runs` or the
database connection.

**Assertion pseudocode:**
```
insert_stale_run(conn, "old_run_id")
engine = create_engine(repo)
engine.run()
ASSERT get_run_status(conn, "old_run_id") == "stalled"
ASSERT any(e.event_type == "run.stale_detected" for e in sink.events)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 118-REQ-1.1 | TS-118-1 | unit |
| 118-REQ-1.2 | TS-118-3 | unit |
| 118-REQ-1.3 | TS-118-2 | unit |
| 118-REQ-1.E1 | TS-118-E1 | unit |
| 118-REQ-1.E2 | TS-118-E2 | unit |
| 118-REQ-2.1 | TS-118-4 | unit |
| 118-REQ-2.2 | TS-118-5 | unit |
| 118-REQ-2.3 | TS-118-6 | unit |
| 118-REQ-2.E1 | TS-118-E3 | unit |
| 118-REQ-2.E2 | TS-118-E4 | unit |
| 118-REQ-3.1 | TS-118-7 | unit |
| 118-REQ-3.2 | TS-118-8 | unit |
| 118-REQ-3.3 | TS-118-8 | unit |
| 118-REQ-3.E1 | TS-118-9 | unit |
| 118-REQ-4.1 | TS-118-10 | unit |
| 118-REQ-4.2 | TS-118-10 | unit |
| 118-REQ-4.3 | TS-118-10 | unit |
| 118-REQ-4.E1 | TS-118-E5 | unit |
| 118-REQ-5.1 | TS-118-11 | unit |
| 118-REQ-5.2 | TS-118-12 | unit |
| 118-REQ-5.3 | TS-118-11 | unit |
| 118-REQ-5.E1 | TS-118-E6 | unit |
| 118-REQ-6.1 | TS-118-13 | unit |
| 118-REQ-6.2 | TS-118-14 | unit |
| 118-REQ-6.3 | TS-118-14 | unit |
| 118-REQ-6.E1 | TS-118-E7 | unit |
| 118-REQ-6.E2 | TS-118-E8 | unit |
| 118-REQ-7.1 | TS-118-15 | unit |
| 118-REQ-7.2 | TS-118-16 | unit |
| 118-REQ-7.E1 | TS-118-E9 | unit |
| 118-REQ-8.1 | TS-118-17 | unit |
| 118-REQ-8.2 | TS-118-18 | unit |
| 118-REQ-8.3 | TS-118-3 | unit |
| 118-REQ-8.E1 | TS-118-E10 | unit |
| Property 1 | TS-118-P1 | property |
| Property 2 | TS-118-P2 | property |
| Property 3 | TS-118-P3 | property |
| Property 4 | TS-118-P4 | property |
| Property 5 | TS-118-P5 | property |
| Property 6 | TS-118-P6 | property |
| Property 7 | TS-118-P7 | property |
| Path 1 | TS-118-SMOKE-1 | integration |
| Path 1+2 | TS-118-SMOKE-2 | integration |
| Path 2 | TS-118-SMOKE-3 | integration |
| Path 5 | TS-118-SMOKE-4 | integration |
