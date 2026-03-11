# Test Specification: Hard Reset Command

## Overview

Tests are organized into three categories: acceptance-criterion tests (unit and
integration), edge-case tests, and property tests. Unit tests mock git
operations and use in-memory state. Integration tests that verify git rollback
use real temporary repositories.

## Test Cases

### TS-35-1: Commit SHA Captured After Harvest

**Requirement:** 35-REQ-1.1
**Type:** integration
**Description:** Verify that `_run_and_harvest` populates `commit_sha` on
`SessionRecord` after a successful harvest.

**Preconditions:**
- A mock session runner that returns a completed session outcome.
- A git repo with a develop branch and a feature branch with new commits.

**Input:**
- A successful session outcome with `status="completed"`.
- Harvest merges feature branch into develop.

**Expected:**
- The returned `SessionRecord.commit_sha` is a 40-character hex string
  matching the current develop HEAD.

**Assertion pseudocode:**
```
record = await runner._run_and_harvest(node_id, attempt, workspace, ...)
ASSERT len(record.commit_sha) == 40
ASSERT record.commit_sha == git_rev_parse("develop")
```

### TS-35-2: Commit SHA Empty on Failed Session

**Requirement:** 35-REQ-1.2
**Type:** unit
**Description:** Verify that `commit_sha` is empty when the session fails.

**Preconditions:**
- A mock session runner that returns a failed session outcome.

**Input:**
- Session outcome with `status="failed"`.

**Expected:**
- `SessionRecord.commit_sha == ""`.

**Assertion pseudocode:**
```
record = await runner._run_and_harvest(node_id, attempt, workspace, ...)
ASSERT record.commit_sha == ""
```

### TS-35-3: Backward-Compatible Deserialization

**Requirement:** 35-REQ-1.3
**Type:** unit
**Description:** Verify that deserializing a `SessionRecord` without
`commit_sha` defaults to empty string.

**Preconditions:**
- A state.jsonl line with `session_history` entries lacking `commit_sha`.

**Input:**
- JSON dict without `commit_sha` key.

**Expected:**
- Deserialized `SessionRecord.commit_sha == ""`.

**Assertion pseudocode:**
```
data = {"node_id": "s:1", "attempt": 1, "status": "completed", ...}
# no "commit_sha" key
record = SessionRecord(**data)
ASSERT record.commit_sha == ""
```

### TS-35-4: Hard Flag Accepted by CLI

**Requirement:** 35-REQ-2.1
**Type:** unit
**Description:** Verify that the CLI accepts `--hard` as a valid flag.

**Preconditions:**
- Click test runner.

**Input:**
- `["reset", "--hard", "--yes"]`

**Expected:**
- Command invoked without Click errors (exit code 0 or expected behavior).

**Assertion pseudocode:**
```
result = runner.invoke(cli, ["reset", "--hard", "--yes"])
ASSERT result.exit_code == 0
```

### TS-35-5: Soft Reset Unchanged Without Hard Flag

**Requirement:** 35-REQ-2.2
**Type:** unit
**Description:** Verify that `reset` without `--hard` still calls the existing
soft-reset path.

**Preconditions:**
- State with failed tasks. Plan file exists.

**Input:**
- `["reset", "--yes"]`

**Expected:**
- Calls `reset_all()` (not `hard_reset_all()`).
- Only failed/blocked/in_progress tasks are reset.
- Completed tasks remain completed.

**Assertion pseudocode:**
```
result = runner.invoke(cli, ["reset", "--yes"])
ASSERT completed_task.status == "completed"
ASSERT failed_task.status == "pending"
```

### TS-35-6: Full Hard Reset Resets All Tasks

**Requirement:** 35-REQ-3.1
**Type:** unit
**Description:** Verify that `hard_reset_all()` resets every task to pending.

**Preconditions:**
- State with tasks in all statuses: pending, in_progress, completed, failed,
  blocked.

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- All `node_states` values are `"pending"`.

**Assertion pseudocode:**
```
result = hard_reset_all(state_path, plan_path, worktrees_dir, repo_path, memory_path)
state = load_state(state_path)
FOR task_id IN state.node_states:
    ASSERT state.node_states[task_id] == "pending"
```

### TS-35-7: Full Hard Reset Cleans All Worktrees

**Requirement:** 35-REQ-3.2
**Type:** unit
**Description:** Verify that all worktree directories are removed.

**Preconditions:**
- Worktree directories exist for multiple tasks (including completed ones).

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- All worktree directories under `.agent-fox/worktrees/` are removed.
- `result.cleaned_worktrees` lists all removed directories.

**Assertion pseudocode:**
```
result = hard_reset_all(...)
ASSERT len(result.cleaned_worktrees) == num_worktrees
ASSERT NOT worktrees_dir_has_contents()
```

### TS-35-8: Full Hard Reset Deletes All Local Branches

**Requirement:** 35-REQ-3.3
**Type:** unit
**Description:** Verify that all local feature branches are deleted.

**Preconditions:**
- Local feature branches exist for multiple tasks.

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- All `feature/{spec}/{group}` branches are deleted.
- `result.cleaned_branches` lists all deleted branches.

**Assertion pseudocode:**
```
result = hard_reset_all(...)
FOR task_id IN all_task_ids:
    branch = task_id_to_branch_name(task_id)
    ASSERT branch IN result.cleaned_branches
```

### TS-35-9: Full Hard Reset Compacts Knowledge Base

**Requirement:** 35-REQ-3.4
**Type:** unit
**Description:** Verify that knowledge compaction is called during hard reset.

**Preconditions:**
- Memory file with duplicate or superseded facts.

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- `compact()` is called.
- `result.compaction` reflects (original_count, surviving_count).

**Assertion pseudocode:**
```
result = hard_reset_all(...)
ASSERT result.compaction[0] >= result.compaction[1]
ASSERT result.compaction == compact_return_value
```

### TS-35-10: Full Hard Reset Rolls Back Develop

**Requirement:** 35-REQ-3.5
**Type:** integration
**Description:** Verify that develop is reset to the commit before the earliest
tracked task.

**Preconditions:**
- A git repo with develop branch.
- State with session history containing commit_sha values.
- The earliest commit_sha's first-parent predecessor is known.

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- Develop HEAD equals the first-parent predecessor of the earliest commit_sha.
- `result.rollback_sha` equals that predecessor.

**Assertion pseudocode:**
```
result = hard_reset_all(...)
ASSERT git_rev_parse("develop") == expected_predecessor
ASSERT result.rollback_sha == expected_predecessor
```

### TS-35-11: Full Hard Reset Preserves Counters and History

**Requirement:** 35-REQ-3.6
**Type:** unit
**Description:** Verify that session history and token/cost counters are not
modified.

**Preconditions:**
- State with session history and non-zero counters.

**Input:**
- Call `hard_reset_all()`.

**Expected:**
- `session_history`, `total_input_tokens`, `total_output_tokens`,
  `total_cost`, `total_sessions` are unchanged.

**Assertion pseudocode:**
```
original_history = state.session_history.copy()
original_cost = state.total_cost
hard_reset_all(...)
state = load_state(state_path)
ASSERT state.session_history == original_history
ASSERT state.total_cost == original_cost
```

### TS-35-12: Partial Hard Reset Rolls Back to Task Boundary

**Requirement:** 35-REQ-4.1
**Type:** integration
**Description:** Verify that partial hard reset rolls back develop to the
commit before the target task.

**Preconditions:**
- A git repo with 3 tasks committed sequentially on develop.
- Each task's SessionRecord has a commit_sha.

**Input:**
- `hard_reset_task("spec:2", ...)` — roll back to before task 2.

**Expected:**
- Develop HEAD equals the predecessor of task 2's commit_sha.
- Task 2 and task 3 are reset to pending.
- Task 1 remains completed.

**Assertion pseudocode:**
```
result = hard_reset_task("spec:2", ...)
ASSERT git_rev_parse("develop") == predecessor_of_task2_sha
ASSERT "spec:2" IN result.reset_tasks
ASSERT "spec:3" IN result.reset_tasks
ASSERT "spec:1" NOT IN result.reset_tasks
```

### TS-35-13: Partial Hard Reset Identifies Affected Tasks

**Requirement:** 35-REQ-4.3
**Type:** unit
**Description:** Verify that `find_affected_tasks()` correctly identifies tasks
whose commit_sha is no longer an ancestor of the new HEAD.

**Preconditions:**
- Session history with multiple commit_shas.
- A known new HEAD SHA.

**Input:**
- Call `find_affected_tasks(session_history, new_head, repo_path)`.

**Expected:**
- Returns task IDs whose commit_sha is NOT an ancestor of new_head.
- Does not return tasks whose commit_sha IS an ancestor.

**Assertion pseudocode:**
```
affected = find_affected_tasks(history, new_head, repo_path)
ASSERT "spec:2" IN affected  # committed after rollback point
ASSERT "spec:1" NOT IN affected  # committed before rollback point
```

### TS-35-14: Partial Hard Reset Cleans Affected Artifacts

**Requirement:** 35-REQ-4.4
**Type:** unit
**Description:** Verify that worktrees and branches are cleaned for all
affected tasks.

**Preconditions:**
- Worktrees and branches exist for target and cascaded tasks.

**Input:**
- `hard_reset_task("spec:2", ...)`.

**Expected:**
- Worktrees and branches for spec:2 and spec:3 are cleaned.
- Worktree and branch for spec:1 are untouched.

**Assertion pseudocode:**
```
result = hard_reset_task("spec:2", ...)
ASSERT "feature/spec/2" IN result.cleaned_branches
ASSERT "feature/spec/3" IN result.cleaned_branches
ASSERT "feature/spec/1" NOT IN result.cleaned_branches
```

### TS-35-15: Confirmation Required Without --yes

**Requirement:** 35-REQ-5.1
**Type:** unit
**Description:** Verify that `reset --hard` prompts for confirmation.

**Preconditions:**
- Click test runner with input simulation.

**Input:**
- `["reset", "--hard"]` with simulated "n" input.

**Expected:**
- Output contains cancellation message.
- No tasks are reset.

**Assertion pseudocode:**
```
result = runner.invoke(cli, ["reset", "--hard"], input="n\n")
ASSERT "cancelled" IN result.output.lower()
```

### TS-35-16: JSON Output for Hard Reset

**Requirement:** 35-REQ-6.2
**Type:** unit
**Description:** Verify that hard reset produces structured JSON output in
JSON mode.

**Preconditions:**
- JSON mode enabled. State with tasks.

**Input:**
- `["--json", "reset", "--hard", "--yes"]`

**Expected:**
- Output is valid JSON with keys: `reset_tasks`, `cleaned_worktrees`,
  `cleaned_branches`, `compaction`, `rollback`.

**Assertion pseudocode:**
```
result = runner.invoke(cli, ["--json", "reset", "--hard", "--yes"])
data = json.loads(result.output)
ASSERT "reset_tasks" IN data
ASSERT "compaction" IN data
ASSERT "rollback" IN data
```

### TS-35-17: Hard Reset Resets Tasks.md Checkboxes

**Requirement:** 35-REQ-7.1
**Type:** unit
**Description:** Verify that tasks.md checkboxes are reset to `[ ]` for
affected task groups after hard reset.

**Preconditions:**
- A specs directory with `tasks.md` files containing `[x]` and `[-]`
  checkboxes for completed/in-progress task groups.

**Input:**
- Call `reset_tasks_md_checkboxes(["spec:1", "spec:2"], specs_dir)`.

**Expected:**
- Top-level checkboxes for groups 1 and 2 in `spec/tasks.md` are `[ ]`.
- Other checkboxes (e.g., subtasks already `[ ]`) are unchanged.

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["spec:1", "spec:2"], specs_dir)
text = read_file(specs_dir / "spec" / "tasks.md")
ASSERT "- [ ] 1." IN text
ASSERT "- [ ] 2." IN text
```

### TS-35-18: Hard Reset Updates Plan.json Statuses

**Requirement:** 35-REQ-7.2
**Type:** unit
**Description:** Verify that plan.json node statuses are set to `"pending"`
for affected tasks after hard reset.

**Preconditions:**
- A plan.json with nodes having `"completed"` status.

**Input:**
- Call `reset_plan_statuses(plan_path, ["spec:1", "spec:2"])`.

**Expected:**
- Nodes `spec:1` and `spec:2` have `status: "pending"` in plan.json.
- Other nodes are unchanged.

**Assertion pseudocode:**
```
reset_plan_statuses(plan_path, ["spec:1", "spec:2"])
data = json.loads(read_file(plan_path))
ASSERT data["nodes"]["spec:1"]["status"] == "pending"
ASSERT data["nodes"]["spec:2"]["status"] == "pending"
ASSERT data["nodes"]["spec:0"]["status"] == "completed"  # unchanged
```

## Property Test Cases

### TS-35-P1: Total Task Reset

**Property:** Property 1 from design.md
**Validates:** 35-REQ-3.1, 35-REQ-4.2, 35-REQ-4.3
**Type:** property
**Description:** For any execution state, hard reset sets all tasks to pending.

**For any:** ExecutionState with 1-20 tasks in random statuses (pending,
in_progress, completed, failed, blocked).
**Invariant:** After `hard_reset_all()`, every task status is `"pending"`.

**Assertion pseudocode:**
```
FOR ANY state IN random_execution_states(1, 20):
    hard_reset_all(state)
    new_state = load_state()
    FOR task_id IN new_state.node_states:
        ASSERT new_state.node_states[task_id] == "pending"
```

### TS-35-P2: Counter Preservation

**Property:** Property 2 from design.md
**Validates:** 35-REQ-3.6
**Type:** property
**Description:** Hard reset never modifies counters or session history.

**For any:** ExecutionState with random counter values and 0-10 session records.
**Invariant:** After hard reset, `total_cost`, `total_input_tokens`,
`total_output_tokens`, `total_sessions`, and `len(session_history)` are
unchanged.

**Assertion pseudocode:**
```
FOR ANY state IN random_execution_states():
    original_cost = state.total_cost
    original_sessions = state.total_sessions
    original_history_len = len(state.session_history)
    hard_reset_all(state)
    new_state = load_state()
    ASSERT new_state.total_cost == original_cost
    ASSERT new_state.total_sessions == original_sessions
    ASSERT len(new_state.session_history) == original_history_len
```

### TS-35-P3: Graceful Degradation

**Property:** Property 6 from design.md
**Validates:** 35-REQ-3.E1, 35-REQ-4.E1
**Type:** property
**Description:** When no commit_sha data exists, hard reset completes
successfully with rollback_sha=None.

**For any:** ExecutionState where all session records have `commit_sha=""`.
**Invariant:** `HardResetResult.rollback_sha is None` and all tasks are reset.

**Assertion pseudocode:**
```
FOR ANY state IN random_states_without_commit_shas():
    result = hard_reset_all(state)
    ASSERT result.rollback_sha IS None
    new_state = load_state()
    FOR task_id IN new_state.node_states:
        ASSERT new_state.node_states[task_id] == "pending"
```

### TS-35-P4: Backward-Compatible Deserialization

**Property:** Property 7 from design.md
**Validates:** 35-REQ-1.3
**Type:** property
**Description:** Deserialization of legacy SessionRecord JSON always yields
commit_sha="".

**For any:** SessionRecord JSON dict with random valid fields but no
`commit_sha` key.
**Invariant:** The deserialized `SessionRecord.commit_sha == ""`.

**Assertion pseudocode:**
```
FOR ANY record_data IN random_session_record_dicts_without_commit_sha():
    record = SessionRecord(**record_data)
    ASSERT record.commit_sha == ""
```

### TS-35-P5: Artifact Synchronization Consistency

**Property:** Property 8 from design.md
**Validates:** 35-REQ-7.1, 35-REQ-7.2
**Type:** property
**Description:** After hard reset, tasks.md checkboxes and plan.json statuses
are consistent with the reset state.

**For any:** Set of 1-10 task IDs with randomly assigned statuses.
**Invariant:** After `reset_tasks_md_checkboxes()` and `reset_plan_statuses()`,
all affected task group checkboxes are `[ ]` and all affected plan.json
statuses are `"pending"`.

**Assertion pseudocode:**
```
FOR ANY task_ids IN random_task_id_sets(1, 10):
    setup_tasks_md_with_mixed_checkboxes(task_ids)
    setup_plan_json_with_mixed_statuses(task_ids)
    reset_tasks_md_checkboxes(task_ids, specs_dir)
    reset_plan_statuses(plan_path, task_ids)
    FOR task_id IN task_ids:
        ASSERT checkbox_for(task_id) == "[ ]"
        ASSERT plan_status_for(task_id) == "pending"
```

## Edge Case Tests

### TS-35-E1: Git Rev-Parse Fails After Harvest

**Requirement:** 35-REQ-1.E1
**Type:** unit
**Description:** Verify graceful handling when `git rev-parse develop` fails.

**Preconditions:**
- Mock `git rev-parse` to raise an error.

**Input:**
- Successful session with harvest completing normally.

**Expected:**
- Warning is logged.
- `SessionRecord.commit_sha == ""`.
- Session is not marked as failed.

**Assertion pseudocode:**
```
with mock_git_rev_parse_failure():
    record = await runner._run_and_harvest(...)
    ASSERT record.commit_sha == ""
    ASSERT record.status == "completed"
```

### TS-35-E2: No Commit SHAs in History (Full Reset)

**Requirement:** 35-REQ-3.E1
**Type:** unit
**Description:** Full hard reset skips rollback when no revision data exists.

**Preconditions:**
- State with completed tasks but all `commit_sha=""`.

**Input:**
- `hard_reset_all()`

**Expected:**
- All tasks reset to pending.
- `result.rollback_sha is None`.
- No git reset command is executed.

**Assertion pseudocode:**
```
result = hard_reset_all(...)
ASSERT result.rollback_sha IS None
ASSERT all(s == "pending" FOR s IN state.node_states.values())
```

### TS-35-E3: Rollback Target Unresolvable

**Requirement:** 35-REQ-3.E2
**Type:** unit
**Description:** Hard reset continues when the rollback SHA cannot be resolved.

**Preconditions:**
- State with commit_sha values that don't exist in the repo (e.g., after
  history rewrite).

**Input:**
- `hard_reset_all()`

**Expected:**
- Warning logged.
- `result.rollback_sha is None`.
- Tasks still reset to pending.

**Assertion pseudocode:**
```
result = hard_reset_all(...)
ASSERT result.rollback_sha IS None
ASSERT all(s == "pending" FOR s IN state.node_states.values())
```

### TS-35-E4: Target Task Not in Plan

**Requirement:** 35-REQ-4.E2
**Type:** unit
**Description:** Error raised when task_id doesn't exist in the plan.

**Preconditions:**
- Plan with tasks spec:1, spec:2, spec:3.

**Input:**
- `hard_reset_task("nonexistent:99", ...)`

**Expected:**
- `AgentFoxError` raised with valid task IDs listed.

**Assertion pseudocode:**
```
WITH RAISES AgentFoxError AS exc:
    hard_reset_task("nonexistent:99", ...)
ASSERT "spec:1" IN str(exc)
```

### TS-35-E5: Target Task Has No Commit SHA (Partial Reset)

**Requirement:** 35-REQ-4.E1
**Type:** unit
**Description:** Partial hard reset skips rollback when target has no revision
data.

**Preconditions:**
- Target task completed but `commit_sha=""`.

**Input:**
- `hard_reset_task("spec:2", ...)`

**Expected:**
- Target task reset to pending.
- No code rollback.
- `result.rollback_sha is None`.

**Assertion pseudocode:**
```
result = hard_reset_task("spec:2", ...)
ASSERT result.rollback_sha IS None
ASSERT state.node_states["spec:2"] == "pending"
```

### TS-35-E6: User Declines Confirmation

**Requirement:** 35-REQ-5.E1
**Type:** unit
**Description:** Operation aborted when user says no.

**Preconditions:**
- Click test runner with input "n".

**Input:**
- `["reset", "--hard"]` with input "n\n".

**Expected:**
- No tasks reset. Cancellation message printed.

**Assertion pseudocode:**
```
result = runner.invoke(cli, ["reset", "--hard"], input="n\n")
ASSERT "cancelled" IN result.output.lower()
ASSERT result.exit_code == 0
```

### TS-35-E7: Tasks.md File Missing

**Requirement:** 35-REQ-7.E1
**Type:** unit
**Description:** Verify that missing tasks.md files are skipped gracefully.

**Preconditions:**
- Specs directory where one spec folder lacks a tasks.md file.

**Input:**
- `reset_tasks_md_checkboxes(["existing_spec:1", "missing_spec:1"], specs_dir)`

**Expected:**
- Existing spec's tasks.md is updated.
- No error raised for missing spec.

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["existing_spec:1", "missing_spec:1"], specs_dir)
# no exception raised
text = read_file(specs_dir / "existing_spec" / "tasks.md")
ASSERT "- [ ] 1." IN text
```

### TS-35-E8: Plan.json Missing

**Requirement:** 35-REQ-7.E2
**Type:** unit
**Description:** Verify that missing plan.json is skipped gracefully.

**Preconditions:**
- No plan.json file exists.

**Input:**
- `reset_plan_statuses(nonexistent_path, ["spec:1"])`

**Expected:**
- No error raised. Function returns silently.

**Assertion pseudocode:**
```
reset_plan_statuses(Path("/does/not/exist/plan.json"), ["spec:1"])
# no exception raised
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 35-REQ-1.1 | TS-35-1 | integration |
| 35-REQ-1.2 | TS-35-2 | unit |
| 35-REQ-1.3 | TS-35-3 | unit |
| 35-REQ-1.E1 | TS-35-E1 | unit |
| 35-REQ-2.1 | TS-35-4 | unit |
| 35-REQ-2.2 | TS-35-5 | unit |
| 35-REQ-3.1 | TS-35-6 | unit |
| 35-REQ-3.2 | TS-35-7 | unit |
| 35-REQ-3.3 | TS-35-8 | unit |
| 35-REQ-3.4 | TS-35-9 | unit |
| 35-REQ-3.5 | TS-35-10 | integration |
| 35-REQ-3.6 | TS-35-11 | unit |
| 35-REQ-3.E1 | TS-35-E2 | unit |
| 35-REQ-3.E2 | TS-35-E3 | unit |
| 35-REQ-3.7 | TS-35-9 | unit |
| 35-REQ-4.1 | TS-35-12 | integration |
| 35-REQ-4.2 | TS-35-12 | integration |
| 35-REQ-4.3 | TS-35-13 | unit |
| 35-REQ-4.4 | TS-35-14 | unit |
| 35-REQ-4.5 | TS-35-9 | unit |
| 35-REQ-4.E1 | TS-35-E5 | unit |
| 35-REQ-4.E2 | TS-35-E4 | unit |
| 35-REQ-5.1 | TS-35-15 | unit |
| 35-REQ-5.2 | TS-35-4 | unit |
| 35-REQ-5.3 | TS-35-16 | unit |
| 35-REQ-5.E1 | TS-35-E6 | unit |
| 35-REQ-6.1 | TS-35-6 | unit |
| 35-REQ-6.2 | TS-35-16 | unit |
| Property 1 | TS-35-P1 | property |
| Property 2 | TS-35-P2 | property |
| Property 6 | TS-35-P3 | property |
| 35-REQ-7.1 | TS-35-17 | unit |
| 35-REQ-7.2 | TS-35-18 | unit |
| 35-REQ-7.3 | TS-35-17 | unit |
| 35-REQ-7.E1 | TS-35-E7 | unit |
| 35-REQ-7.E2 | TS-35-E8 | unit |
| Property 7 | TS-35-P4 | property |
| Property 8 | TS-35-P5 | property |
