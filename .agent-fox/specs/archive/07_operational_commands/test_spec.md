# Test Specification: Operational Commands

## Overview

Tests for the three operational commands: `agent-fox status`, `agent-fox
standup`, and `agent-fox reset`. Tests cover report generation, output
formatting, reset logic, cascade unblocking, and CLI integration. Tests map to
requirements in `requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-07-1: Status displays task counts by status

**Requirement:** 07-REQ-1.1
**Type:** unit
**Description:** Verify status report groups tasks correctly by status.

**Preconditions:**
- A state file with 3 completed, 1 failed, 1 blocked, 2 pending tasks.
- A plan file with 7 total tasks.

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.counts["completed"] == 3`
- `report.counts["failed"] == 1`
- `report.counts["blocked"] == 1`
- `report.counts["pending"] == 2`
- `report.total_tasks == 7`

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT report.counts["completed"] == 3
ASSERT report.counts["failed"] == 1
ASSERT report.counts["blocked"] == 1
ASSERT report.counts["pending"] == 2
ASSERT report.total_tasks == 7
```

---

### TS-07-2: Status displays token usage and cost

**Requirement:** 07-REQ-1.2
**Type:** unit
**Description:** Verify status report includes cumulative token and cost data.

**Preconditions:**
- A state file with 3 session records totaling 100k input, 50k output tokens,
  $2.50 cost.

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.input_tokens == 100_000`
- `report.output_tokens == 50_000`
- `report.estimated_cost == 2.50` (within floating point tolerance)

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT report.input_tokens == 100_000
ASSERT report.output_tokens == 50_000
ASSERT abs(report.estimated_cost - 2.50) < 0.01
```

---

### TS-07-3: Status lists blocked and failed tasks

**Requirement:** 07-REQ-1.3
**Type:** unit
**Description:** Verify status report includes problem tasks with reasons.

**Preconditions:**
- A state file with 1 failed task (error: "test failures") and 1 blocked
  task (blocked by the failed task).

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `len(report.problem_tasks) == 2`
- One task with status "failed" and reason containing "test failures".
- One task with status "blocked" and reason referencing the failed task.

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT len(report.problem_tasks) == 2
failed = [t for t in report.problem_tasks if t.status == "failed"]
ASSERT len(failed) == 1
ASSERT "test failures" in failed[0].reason
blocked = [t for t in report.problem_tasks if t.status == "blocked"]
ASSERT len(blocked) == 1
```

---

### TS-07-4: Standup agent activity within window

**Requirement:** 07-REQ-2.1
**Type:** unit
**Description:** Verify standup report filters agent activity to the time
window.

**Preconditions:**
- A state file with sessions at: 2 hours ago (within window), 6 hours ago
  (within window), 30 hours ago (outside window).
- Time window: 24 hours.

**Input:**
- `generate_standup(state_path, plan_path, repo_path, hours=24)`

**Expected:**
- `report.agent.sessions_run == 2` (only the two within-window sessions).
- `report.agent.tasks_completed` reflects only tasks completed in window.

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path, hours=24)
ASSERT report.agent.sessions_run == 2
ASSERT report.window_hours == 24
```

---

### TS-07-5: Standup includes human commits

**Requirement:** 07-REQ-2.2
**Type:** unit
**Description:** Verify standup report includes non-agent commits from git log.

**Preconditions:**
- A git repository with 2 human commits and 1 agent commit in the last
  24 hours.

**Input:**
- `_get_human_commits(repo_path, since=24h_ago, agent_author="agent-fox")`

**Expected:**
- Returns 2 HumanCommit records (agent commit excluded).
- Each record has non-empty sha, author, timestamp, and subject.

**Assertion pseudocode:**
```
commits = _get_human_commits(repo_path, since, "agent-fox")
ASSERT len(commits) == 2
FOR EACH commit IN commits:
    ASSERT commit.author != "agent-fox"
    ASSERT len(commit.sha) == 40
```

---

### TS-07-6: Standup detects file overlaps

**Requirement:** 07-REQ-2.3
**Type:** unit
**Description:** Verify file overlap detection finds files touched by both
agent and human.

**Preconditions:**
- Agent touched files: `["src/a.py", "src/b.py", "src/c.py"]`
- Human commits changed files: `["src/b.py", "src/d.py"]`

**Input:**
- `_detect_overlaps(agent_files, human_commits)`

**Expected:**
- One overlap: `src/b.py`.
- No overlap for `src/a.py`, `src/c.py`, or `src/d.py`.

**Assertion pseudocode:**
```
agent_files = {"src/a.py": ["task:1"], "src/b.py": ["task:2"], "src/c.py": ["task:1"]}
human_commits = [HumanCommit(..., files_changed=["src/b.py", "src/d.py"])]
overlaps = _detect_overlaps(agent_files, human_commits)
ASSERT len(overlaps) == 1
ASSERT overlaps[0].path == "src/b.py"
```

---

### TS-07-7: Standup includes queue summary

**Requirement:** 07-REQ-2.4
**Type:** unit
**Description:** Verify standup report includes current queue status.

**Preconditions:**
- A plan with 10 tasks: 3 completed, 2 ready, 3 pending, 1 blocked, 1 failed.

**Input:**
- `generate_standup(state_path, plan_path, repo_path)`

**Expected:**
- `report.queue.completed == 3`
- `report.queue.ready == 2`
- `report.queue.pending == 3`
- `report.queue.blocked == 1`
- `report.queue.failed == 1`

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path)
ASSERT report.queue.completed == 3
ASSERT report.queue.ready == 2
ASSERT report.queue.pending == 3
ASSERT report.queue.blocked == 1
ASSERT report.queue.failed == 1
```

---

### TS-07-8: Standup includes cost breakdown by model

**Requirement:** 07-REQ-2.5
**Type:** unit
**Description:** Verify standup report breaks down cost by model tier.

**Preconditions:**
- Sessions in window used STANDARD model (2 sessions, $3.00) and SIMPLE
  model (1 session, $0.50).

**Input:**
- `generate_standup(state_path, plan_path, repo_path)`

**Expected:**
- `len(report.cost_breakdown) == 2`
- STANDARD entry: sessions=2, cost=3.00
- SIMPLE entry: sessions=1, cost=0.50

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path)
by_tier = {cb.tier: cb for cb in report.cost_breakdown}
ASSERT by_tier["STANDARD"].sessions == 2
ASSERT abs(by_tier["STANDARD"].cost - 3.00) < 0.01
ASSERT by_tier["SIMPLE"].sessions == 1
```

---

### TS-07-9: JSON formatter produces valid JSON

**Requirement:** 07-REQ-3.2
**Type:** unit
**Description:** Verify JSON formatter produces parseable output.

**Preconditions:**
- A StatusReport with known values.

**Input:**
- `JsonFormatter().format_status(report)`

**Expected:**
- Output is valid JSON (parseable by `json.loads`).
- Parsed JSON contains expected keys and values.

**Assertion pseudocode:**
```
formatter = JsonFormatter()
output = formatter.format_status(report)
parsed = json.loads(output)
ASSERT parsed["total_tasks"] == report.total_tasks
ASSERT parsed["estimated_cost"] == report.estimated_cost
```

---

### TS-07-10: YAML formatter produces valid YAML

**Requirement:** 07-REQ-3.3
**Type:** unit
**Description:** Verify YAML formatter produces parseable output.

**Preconditions:**
- A StandupReport with known values.

**Input:**
- `YamlFormatter().format_standup(report)`

**Expected:**
- Output is valid YAML (parseable by `yaml.safe_load`).
- Parsed YAML contains expected keys and values.

**Assertion pseudocode:**
```
formatter = YamlFormatter()
output = formatter.format_standup(report)
parsed = yaml.safe_load(output)
ASSERT parsed["window_hours"] == report.window_hours
```

---

### TS-07-11: Full reset clears incomplete tasks

**Requirement:** 07-REQ-4.1, 07-REQ-4.2
**Type:** unit
**Description:** Verify full reset resets failed, blocked, and in_progress
tasks to pending and cleans up artifacts.

**Preconditions:**
- State with 2 completed, 1 failed, 1 blocked, 1 in_progress tasks.
- Worktree directories exist for the failed and in_progress tasks.

**Input:**
- `reset_all(state_path, plan_path, worktrees_dir, repo_path)`

**Expected:**
- `result.reset_tasks` contains the 3 incomplete task IDs.
- Completed tasks are not in `result.reset_tasks`.
- Worktree directories for reset tasks are removed.

**Assertion pseudocode:**
```
result = reset_all(state_path, plan_path, worktrees_dir, repo_path)
ASSERT len(result.reset_tasks) == 3
ASSERT "completed_task" NOT IN result.reset_tasks
ASSERT NOT worktrees_dir.joinpath("failed_task_dir").exists()
```

---

### TS-07-12: Single-task reset unblocks downstream

**Requirement:** 07-REQ-5.1, 07-REQ-5.2
**Type:** unit
**Description:** Verify single-task reset unblocks downstream tasks where the
reset task was the sole blocker.

**Preconditions:**
- Task A is failed. Task B depends only on A and is blocked. Task C depends on
  A and another completed task D, and is blocked.

**Input:**
- `reset_task("A", state_path, plan_path, worktrees_dir, repo_path)`

**Expected:**
- Task A is reset to pending.
- Task B is unblocked (A was sole blocker, D is completed).
- Task C is unblocked (A was the only non-completed dependency).

**Assertion pseudocode:**
```
result = reset_task("A", state_path, plan_path, worktrees_dir, repo_path)
ASSERT "A" IN result.reset_tasks
ASSERT "B" IN result.unblocked_tasks
ASSERT "C" IN result.unblocked_tasks
```

## Property Test Cases

### TS-07-P1: Status count consistency

**Property:** Property 1 from design.md
**Validates:** 07-REQ-1.1
**Type:** property
**Description:** Sum of all status counts equals total_tasks.

**For any:** valid ExecutionState and TaskGraph
**Invariant:** `sum(report.counts.values()) == report.total_tasks`

**Assertion pseudocode:**
```
FOR ANY state IN valid_execution_states(),
        plan IN valid_task_graphs():
    report = generate_status(state, plan)
    ASSERT sum(report.counts.values()) == report.total_tasks
```

---

### TS-07-P2: Reset preserves completed tasks

**Property:** Property 4 from design.md
**Validates:** 07-REQ-4.1
**Type:** property
**Description:** Full reset never changes completed tasks.

**For any:** valid ExecutionState with some completed tasks
**Invariant:** After `reset_all()`, all previously completed task IDs are
absent from `result.reset_tasks`.

**Assertion pseudocode:**
```
FOR ANY state IN states_with_completed_tasks():
    completed_ids = {id for id, s in state.node_statuses.items() if s == "completed"}
    result = reset_all(state_path, plan_path, worktrees_dir, repo_path)
    ASSERT completed_ids.isdisjoint(set(result.reset_tasks))
```

---

### TS-07-P3: JSON roundtrip fidelity

**Property:** Property 6 from design.md
**Validates:** 07-REQ-3.2
**Type:** property
**Description:** JSON format/parse roundtrip preserves data.

**For any:** valid StatusReport
**Invariant:** `json.loads(JsonFormatter().format_status(report))` equals
`dataclasses.asdict(report)`.

**Assertion pseudocode:**
```
FOR ANY report IN valid_status_reports():
    output = JsonFormatter().format_status(report)
    parsed = json.loads(output)
    expected = dataclasses.asdict(report)
    ASSERT parsed == expected
```

---

### TS-07-P4: Cascade unblock correctness

**Property:** Property 5 from design.md
**Validates:** 07-REQ-5.2
**Type:** property
**Description:** A downstream task is unblocked iff all its non-reset
prerequisites are completed.

**For any:** task graph with a blocked task whose sole blocker is the reset
target
**Invariant:** `_find_sole_blocker_dependents(task_id, plan, state)` returns
exactly those downstream tasks whose every predecessor is either `completed`
or the reset target.

**Assertion pseudocode:**
```
FOR ANY task_id IN blocked_tasks(),
        plan IN valid_task_graphs(),
        state IN valid_states():
    unblockable = _find_sole_blocker_dependents(task_id, plan, state)
    FOR EACH downstream IN unblockable:
        preds = plan.predecessors(downstream)
        FOR EACH pred IN preds:
            ASSERT state.node_statuses[pred] == "completed" OR pred == task_id
```

## Edge Case Tests

### TS-07-E1: Status with no state file

**Requirement:** 07-REQ-1.E1
**Type:** unit
**Description:** Status works with plan-only (no execution yet).

**Preconditions:**
- Plan file exists with 5 tasks. No state file.

**Input:**
- `generate_status(nonexistent_state, plan_path)`

**Expected:**
- All tasks show as pending.
- Token counts and cost are zero.
- No problem tasks.

**Assertion pseudocode:**
```
report = generate_status(Path("/nonexistent"), plan_path)
ASSERT report.counts["pending"] == 5
ASSERT report.input_tokens == 0
ASSERT report.estimated_cost == 0.0
```

---

### TS-07-E2: Status with no plan file

**Requirement:** 07-REQ-1.E2
**Type:** unit
**Description:** Status fails gracefully when no plan exists.

**Preconditions:**
- Neither state nor plan file exists.

**Input:**
- `generate_status(nonexistent_state, nonexistent_plan)`

**Expected:**
- `AgentFoxError` raised.
- Error message mentions `agent-fox plan`.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError FROM generate_status(bad_state, bad_plan)
ASSERT "plan" IN str(error).lower()
```

---

### TS-07-E3: Standup with no agent activity

**Requirement:** 07-REQ-2.E1
**Type:** unit
**Description:** Standup report works when agent did nothing in window.

**Preconditions:**
- State file exists but all sessions are older than the window.

**Input:**
- `generate_standup(state_path, plan_path, repo_path, hours=1)`

**Expected:**
- `report.agent.sessions_run == 0`
- `report.agent.cost == 0.0`
- Queue summary still populated.

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path, hours=1)
ASSERT report.agent.sessions_run == 0
ASSERT report.agent.cost == 0.0
ASSERT report.queue.completed >= 0  # queue is populated
```

---

### TS-07-E4: Standup with no git commits

**Requirement:** 07-REQ-2.E2
**Type:** unit
**Description:** Standup handles empty git history gracefully.

**Preconditions:**
- A git repository with no commits in the last 24 hours.

**Input:**
- `_get_human_commits(repo_path, since=24h_ago, agent_author="agent-fox")`

**Expected:**
- Returns an empty list.
- No exception raised.

**Assertion pseudocode:**
```
commits = _get_human_commits(repo_path, since, "agent-fox")
ASSERT len(commits) == 0
```

---

### TS-07-E5: Output file not writable

**Requirement:** 07-REQ-3.E1
**Type:** unit
**Description:** Writing to unwritable path raises error.

**Preconditions:**
- An output path pointing to a read-only directory.

**Input:**
- `write_output("content", output_path=Path("/nonexistent/dir/report.json"))`

**Expected:**
- `AgentFoxError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError FROM write_output("data", Path("/no/such/dir/f.json"))
```

---

### TS-07-E6: Reset with no incomplete tasks

**Requirement:** 07-REQ-4.E1
**Type:** unit
**Description:** Reset exits cleanly when nothing to reset.

**Preconditions:**
- State where all tasks are completed or pending (none failed/blocked).

**Input:**
- `reset_all(state_path, plan_path, worktrees_dir, repo_path)`

**Expected:**
- `result.reset_tasks` is empty.

**Assertion pseudocode:**
```
result = reset_all(state_path, plan_path, worktrees_dir, repo_path)
ASSERT len(result.reset_tasks) == 0
```

---

### TS-07-E7: Reset with no state file

**Requirement:** 07-REQ-4.E2
**Type:** unit
**Description:** Reset fails when no execution state exists.

**Preconditions:**
- No state file exists.

**Input:**
- `reset_all(nonexistent_state, plan_path, worktrees_dir, repo_path)`

**Expected:**
- `AgentFoxError` raised.
- Error message mentions running `agent-fox code`.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError FROM reset_all(bad_state, plan_path, wtdir, repo)
ASSERT "code" IN str(error).lower()
```

---

### TS-07-E8: Reset unknown task ID

**Requirement:** 07-REQ-5.E1
**Type:** unit
**Description:** Single-task reset fails for nonexistent task ID.

**Preconditions:**
- A valid plan with known task IDs.

**Input:**
- `reset_task("nonexistent:99", state_path, plan_path, worktrees_dir, repo_path)`

**Expected:**
- `AgentFoxError` raised.
- Error message lists valid task IDs.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError FROM reset_task("nonexistent:99", ...)
ASSERT any valid task ID IN str(error)
```

---

### TS-07-E9: Reset completed task

**Requirement:** 07-REQ-5.E2
**Type:** unit
**Description:** Resetting a completed task is rejected.

**Preconditions:**
- A task with status `completed`.

**Input:**
- `reset_task("completed_task:1", state_path, plan_path, worktrees_dir, repo_path)`

**Expected:**
- No changes to state.
- Warning message about completed tasks.
- No exception raised (exits successfully).

**Assertion pseudocode:**
```
result = reset_task("completed_task:1", ...)
ASSERT len(result.reset_tasks) == 0
# Function returns empty result with a warning, or raises a specific
# warning-level response.
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 07-REQ-1.1 | TS-07-1 | unit |
| 07-REQ-1.2 | TS-07-2 | unit |
| 07-REQ-1.3 | TS-07-3 | unit |
| 07-REQ-1.E1 | TS-07-E1 | unit |
| 07-REQ-1.E2 | TS-07-E2 | unit |
| 07-REQ-2.1 | TS-07-4 | unit |
| 07-REQ-2.2 | TS-07-5 | unit |
| 07-REQ-2.3 | TS-07-6 | unit |
| 07-REQ-2.4 | TS-07-7 | unit |
| 07-REQ-2.5 | TS-07-8 | unit |
| 07-REQ-2.E1 | TS-07-E3 | unit |
| 07-REQ-2.E2 | TS-07-E4 | unit |
| 07-REQ-3.1 | TS-07-9, TS-07-10 | unit |
| 07-REQ-3.2 | TS-07-9 | unit |
| 07-REQ-3.3 | TS-07-10 | unit |
| 07-REQ-3.4 | (verified by CLI integration) | integration |
| 07-REQ-3.E1 | TS-07-E5 | unit |
| 07-REQ-4.1 | TS-07-11 | unit |
| 07-REQ-4.2 | TS-07-11 | unit |
| 07-REQ-4.3 | (verified by CLI integration) | integration |
| 07-REQ-4.4 | (verified by CLI integration) | integration |
| 07-REQ-4.E1 | TS-07-E6 | unit |
| 07-REQ-4.E2 | TS-07-E7 | unit |
| 07-REQ-5.1 | TS-07-12 | unit |
| 07-REQ-5.2 | TS-07-12 | unit |
| 07-REQ-5.3 | (verified by CLI integration) | integration |
| 07-REQ-5.E1 | TS-07-E8 | unit |
| 07-REQ-5.E2 | TS-07-E9 | unit |
| Property 1 | TS-07-P1 | property |
| Property 4 | TS-07-P2 | property |
| Property 5 | TS-07-P4 | property |
| Property 6 | TS-07-P3 | property |
