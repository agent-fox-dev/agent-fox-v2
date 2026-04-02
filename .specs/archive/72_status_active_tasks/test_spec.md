# Test Specification: Show Active Tasks in Status Command

## Overview

Tests cover three areas: data model population in `generate_status()`, text
formatting in `format_status()`, and JSON serialization. All tests use
synthetic execution state — no real orchestrator runs.

## Test Cases

### TS-72-1: In-progress tasks populated in StatusReport

**Requirement:** 72-REQ-1.1
**Type:** unit
**Description:** Verify `generate_status()` populates `in_progress_tasks` with
`TaskActivity` objects for all in-progress nodes.

**Preconditions:**
- State with 3 nodes: one completed, one in_progress (coder), one pending
- Session history with entries for the in_progress node

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.in_progress_tasks` has exactly 1 entry
- Entry `task_id` matches the in_progress node

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT len(report.in_progress_tasks) == 1
ASSERT report.in_progress_tasks[0].task_id == "spec/0:coder"
```

### TS-72-2: Both coder and non-coder in-progress nodes included

**Requirement:** 72-REQ-1.2
**Type:** unit
**Description:** Verify both coder tasks and non-coder archetype nodes are
included when in_progress.

**Preconditions:**
- State with 2 in_progress nodes: one coder, one verifier

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.in_progress_tasks` has 2 entries
- One has task_id containing "coder", other containing "verifier"

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT len(report.in_progress_tasks) == 2
task_ids = {ta.task_id for ta in report.in_progress_tasks}
ASSERT any("coder" in tid for tid in task_ids)
ASSERT any("verifier" in tid for tid in task_ids)
```

### TS-72-3: Session metrics computed correctly

**Requirement:** 72-REQ-1.3
**Type:** unit
**Description:** Verify `TaskActivity` session counts and token totals match
session history.

**Preconditions:**
- In-progress node with 3 sessions: 2 completed, 1 failed
- Known token counts and costs

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `completed_sessions == 2`, `total_sessions == 3`
- Token totals match sum of session records
- Cost matches sum of session costs

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ta = report.in_progress_tasks[0]
ASSERT ta.completed_sessions == 2
ASSERT ta.total_sessions == 3
ASSERT ta.input_tokens == sum of input tokens
ASSERT ta.output_tokens == sum of output tokens
ASSERT ta.cost == pytest.approx(sum of costs)
```

### TS-72-4: Text section rendered when tasks exist

**Requirement:** 72-REQ-2.1
**Type:** unit
**Description:** Verify "Active Tasks" section appears in text output when
`in_progress_tasks` is non-empty.

**Preconditions:**
- StatusReport with 1 in_progress_tasks entry (has sessions)

**Input:**
- `formatter.format_status(report)`

**Expected:**
- Output contains "Active Tasks" heading

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
ASSERT "Active Tasks" in output
```

### TS-72-5: Active Tasks section placed before Cost by Archetype

**Requirement:** 72-REQ-2.2
**Type:** unit
**Description:** Verify section ordering in text output.

**Preconditions:**
- StatusReport with both `in_progress_tasks` and `cost_by_archetype`

**Input:**
- `formatter.format_status(report)`

**Expected:**
- "Active Tasks" appears before "Cost by Archetype" in output

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
active_pos = output.index("Active Tasks")
cost_pos = output.index("Cost by Archetype")
ASSERT active_pos < cost_pos
```

### TS-72-6: Task with sessions formatted correctly

**Requirement:** 72-REQ-2.3
**Type:** unit
**Description:** Verify line format for tasks with sessions.

**Preconditions:**
- TaskActivity: task_id="spec/0:coder", completed_sessions=1,
  total_sessions=2, input_tokens=500000, output_tokens=750000, cost=12.34

**Input:**
- `formatter.format_status(report)`

**Expected:**
- Line: `spec/0/coder: in_progress. 1/2 sessions. tokens 500.0k in / 750.0k out. $12.34`

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
ASSERT "spec/0/coder: in_progress. 1/2 sessions. tokens 500.0k in / 750.0k out. $12.34" in output
```

### TS-72-7: Task with zero sessions formatted correctly

**Requirement:** 72-REQ-2.4
**Type:** unit
**Description:** Verify line format for tasks with no sessions.

**Preconditions:**
- TaskActivity: task_id="spec/0:verifier", total_sessions=0,
  completed_sessions=0, input_tokens=0, output_tokens=0, cost=0.0

**Input:**
- `formatter.format_status(report)`

**Expected:**
- Line: `spec/0/verifier: in_progress`
- No session/token details on the line

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
ASSERT "spec/0/verifier: in_progress" in output
ASSERT "spec/0/verifier: in_progress." not in output
```

### TS-72-8: Section omitted when no in-progress tasks

**Requirement:** 72-REQ-2.5
**Type:** unit
**Description:** Verify "Active Tasks" section is not rendered when list is
empty.

**Preconditions:**
- StatusReport with empty `in_progress_tasks`

**Input:**
- `formatter.format_status(report)`

**Expected:**
- "Active Tasks" does NOT appear in output

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
ASSERT "Active Tasks" not in output
```

### TS-72-9: JSON output includes in_progress_tasks array

**Requirement:** 72-REQ-3.1
**Type:** unit
**Description:** Verify JSON output contains the `in_progress_tasks` key.

**Preconditions:**
- StatusReport with 1 in_progress_tasks entry

**Input:**
- `JsonFormatter().format_status(report)`

**Expected:**
- Parsed JSON has `in_progress_tasks` key with list of 1

**Assertion pseudocode:**
```
output = JsonFormatter().format_status(report)
data = json.loads(output)
ASSERT "in_progress_tasks" in data
ASSERT len(data["in_progress_tasks"]) == 1
```

### TS-72-10: JSON TaskActivity has all required fields

**Requirement:** 72-REQ-3.2
**Type:** unit
**Description:** Verify each TaskActivity object in JSON has all 7 fields.

**Preconditions:**
- StatusReport with 1 in_progress_tasks entry

**Input:**
- `JsonFormatter().format_status(report)`

**Expected:**
- Each object has: task_id, current_status, completed_sessions,
  total_sessions, input_tokens, output_tokens, cost

**Assertion pseudocode:**
```
output = JsonFormatter().format_status(report)
data = json.loads(output)
task = data["in_progress_tasks"][0]
ASSERT set(task.keys()) == {"task_id", "current_status", "completed_sessions",
    "total_sessions", "input_tokens", "output_tokens", "cost"}
```

## Edge Case Tests

### TS-72-E1: No execution state

**Requirement:** 72-REQ-1.E2
**Type:** unit
**Description:** When no state.jsonl exists, `in_progress_tasks` is empty.

**Preconditions:**
- state.jsonl does not exist
- plan.json exists with nodes

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.in_progress_tasks == []`

**Assertion pseudocode:**
```
report = generate_status(nonexistent_state_path, plan_path)
ASSERT report.in_progress_tasks == []
```

### TS-72-E2: No in-progress tasks

**Requirement:** 72-REQ-1.E1
**Type:** unit
**Description:** When all tasks are completed/pending, list is empty.

**Preconditions:**
- State with nodes: 2 completed, 1 pending, 0 in_progress

**Input:**
- `generate_status(state_path, plan_path)`

**Expected:**
- `report.in_progress_tasks == []`

**Assertion pseudocode:**
```
report = generate_status(state_path, plan_path)
ASSERT report.in_progress_tasks == []
```

### TS-72-E3: Zero tokens with non-zero session count

**Requirement:** 72-REQ-2.E1
**Type:** unit
**Description:** Task with sessions but zero tokens displays `0 in / 0 out`.

**Preconditions:**
- TaskActivity: total_sessions=1, input_tokens=0, output_tokens=0

**Input:**
- `formatter.format_status(report)`

**Expected:**
- Line contains `tokens 0 in / 0 out`

**Assertion pseudocode:**
```
output = TableFormatter().format_status(report)
ASSERT "tokens 0 in / 0 out" in output
```

## Property Test Cases

### TS-72-P1: In-Progress Filter Invariant

**Property:** Property 1 from design.md
**Validates:** 72-REQ-1.1, 72-REQ-1.2
**Type:** property
**Description:** `in_progress_tasks` contains exactly the tasks with
`in_progress` status.

**For any:** set of N node states with statuses drawn from
{pending, in_progress, completed, failed, blocked}
**Invariant:** `len(in_progress_tasks) == count of in_progress nodes`
and every entry has `current_status == "in_progress"`

**Assertion pseudocode:**
```
FOR ANY node_states IN st.dictionaries(
    st.text(min_size=1), st.sampled_from(["pending", "in_progress", "completed", "failed"]),
    min_size=1, max_size=10
):
    # Build state and plan from node_states, run generate_status
    expected_count = sum(1 for s in node_states.values() if s == "in_progress")
    ASSERT len(report.in_progress_tasks) == expected_count
    ASSERT all(ta.current_status == "in_progress" for ta in report.in_progress_tasks)
```

### TS-72-P2: Text Section Presence Invariant

**Property:** Property 4 from design.md
**Validates:** 72-REQ-2.1, 72-REQ-2.5
**Type:** property
**Description:** "Active Tasks" appears in text iff `in_progress_tasks` is
non-empty.

**For any:** StatusReport with 0..5 in_progress_tasks entries
**Invariant:** `("Active Tasks" in output) == (len(in_progress_tasks) > 0)`

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(0, 5):
    report = make_report(in_progress_count=n)
    output = TableFormatter().format_status(report)
    ASSERT ("Active Tasks" in output) == (n > 0)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 72-REQ-1.1 | TS-72-1 | unit |
| 72-REQ-1.2 | TS-72-2 | unit |
| 72-REQ-1.3 | TS-72-3 | unit |
| 72-REQ-1.E1 | TS-72-E2 | unit |
| 72-REQ-1.E2 | TS-72-E1 | unit |
| 72-REQ-2.1 | TS-72-4 | unit |
| 72-REQ-2.2 | TS-72-5 | unit |
| 72-REQ-2.3 | TS-72-6 | unit |
| 72-REQ-2.4 | TS-72-7 | unit |
| 72-REQ-2.5 | TS-72-8 | unit |
| 72-REQ-2.E1 | TS-72-E3 | unit |
| 72-REQ-3.1 | TS-72-9 | unit |
| 72-REQ-3.2 | TS-72-10 | unit |
| Property 1 | TS-72-P1 | property |
| Property 2 | TS-72-P2 | property |
