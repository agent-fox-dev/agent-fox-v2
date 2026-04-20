# Test Specification: Spec-Scoped Reset

## Overview

Tests verify that `reset --spec <spec_name>` resets exactly the nodes belonging
to the named spec, cleans artifacts, synchronizes tasks.md/plan.json, and
preserves all other state. Tests map to requirements from `requirements.md` and
correctness properties from `design.md`.

## Test Cases

### TS-50-1: Reset Sets All Spec Nodes to Pending

**Requirement:** 50-REQ-1.1
**Type:** unit
**Description:** All nodes belonging to the target spec are set to `pending`.

**Preconditions:**
- State has nodes for spec `alpha` with statuses `completed`, `blocked`, `failed`.
- State has nodes for spec `beta` with status `completed`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- All `alpha` nodes have status `pending`.
- All `beta` nodes remain `completed`.

**Assertion pseudocode:**
```
result = reset_spec("alpha", state_path, plan_path, worktrees_dir, repo_path)
state = load_state(state_path)
FOR node_id IN alpha_node_ids:
    ASSERT state.node_states[node_id] == "pending"
FOR node_id IN beta_node_ids:
    ASSERT state.node_states[node_id] == "completed"
```

### TS-50-2: Reset Includes Archetype Nodes

**Requirement:** 50-REQ-1.2
**Type:** unit
**Description:** Archetype nodes (skeptic, auditor, verifier) are included in
the reset alongside coder nodes.

**Preconditions:**
- Plan has coder nodes `alpha:1`, `alpha:2` and archetype nodes `alpha:0`
  (skeptic), `alpha:1:auditor`, `alpha:3` (verifier).
- All nodes are `completed`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `result.reset_tasks` contains all five node IDs.
- All five nodes are `pending` in state.

**Assertion pseudocode:**
```
result = reset_spec("alpha", ...)
ASSERT set(result.reset_tasks) == {"alpha:0", "alpha:1", "alpha:1:auditor", "alpha:2", "alpha:3"}
```

### TS-50-3: Other Specs Unchanged

**Requirement:** 50-REQ-1.3
**Type:** unit
**Description:** Nodes from other specs are not modified.

**Preconditions:**
- State has `alpha:1` (completed) and `beta:1` (completed).

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `beta:1` remains `completed`.

**Assertion pseudocode:**
```
reset_spec("alpha", ...)
state = load_state(state_path)
ASSERT state.node_states["beta:1"] == "completed"
```

### TS-50-4: Worktrees and Branches Cleaned

**Requirement:** 50-REQ-1.4
**Type:** unit
**Description:** Worktrees and branches for reset nodes are cleaned up.

**Preconditions:**
- Worktree directory exists for `alpha:1`.
- Git branch `feature/alpha/1` exists.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `result.cleaned_worktrees` contains the worktree path.
- `result.cleaned_branches` contains the branch name.

**Assertion pseudocode:**
```
result = reset_spec("alpha", ...)
ASSERT len(result.cleaned_worktrees) >= 1
ASSERT len(result.cleaned_branches) >= 1
```

### TS-50-5: Tasks.md Checkboxes Reset

**Requirement:** 50-REQ-1.5
**Type:** unit
**Description:** Top-level checkboxes in tasks.md for the spec are reset.

**Preconditions:**
- `.specs/alpha/tasks.md` has `- [x] 1. Task One` and `- [x] 2. Task Two`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- tasks.md has `- [ ] 1. Task One` and `- [ ] 2. Task Two`.

**Assertion pseudocode:**
```
reset_spec("alpha", ...)
content = read_file(".specs/alpha/tasks.md")
ASSERT "- [ ] 1. Task One" IN content
ASSERT "- [ ] 2. Task Two" IN content
ASSERT "- [x]" NOT IN content
```

### TS-50-6: Plan.json Statuses Reset

**Requirement:** 50-REQ-1.6
**Type:** unit
**Description:** Node statuses in plan.json are set to pending for the spec.

**Preconditions:**
- plan.json has `alpha:1` with status `completed`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- plan.json has `alpha:1` with status `pending`.

**Assertion pseudocode:**
```
reset_spec("alpha", ...)
plan = load_plan(plan_path)
ASSERT plan["nodes"]["alpha:1"]["status"] == "pending"
```

### TS-50-7: No Git Rollback

**Requirement:** 50-REQ-1.7
**Type:** unit
**Description:** The develop branch is not modified by spec reset.

**Preconditions:**
- develop branch at SHA `abc123`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- develop branch still at SHA `abc123` after reset.

**Assertion pseudocode:**
```
sha_before = git_rev_parse("develop")
reset_spec("alpha", ...)
sha_after = git_rev_parse("develop")
ASSERT sha_before == sha_after
```

### TS-50-8: Mutual Exclusivity with --hard

**Requirement:** 50-REQ-2.1
**Type:** unit
**Description:** Combining --spec with --hard produces an error.

**Preconditions:**
- CLI invoked with `reset --spec alpha --hard`.

**Input:**
- CLI args: `["reset", "--spec", "alpha", "--hard"]`

**Expected:**
- Non-zero exit code.
- Error message mentions mutual exclusivity.

**Assertion pseudocode:**
```
result = invoke_cli(["reset", "--spec", "alpha", "--hard"])
ASSERT result.exit_code != 0
ASSERT "mutually exclusive" IN result.output
```

### TS-50-9: Mutual Exclusivity with task_id

**Requirement:** 50-REQ-2.2
**Type:** unit
**Description:** Combining --spec with a positional task_id produces an error.

**Preconditions:**
- CLI invoked with `reset --spec alpha alpha:1`.

**Input:**
- CLI args: `["reset", "--spec", "alpha", "alpha:1"]`

**Expected:**
- Non-zero exit code.
- Error message mentions mutual exclusivity.

**Assertion pseudocode:**
```
result = invoke_cli(["reset", "--spec", "alpha", "alpha:1"])
ASSERT result.exit_code != 0
ASSERT "mutually exclusive" IN result.output
```

### TS-50-10: Confirmation Required

**Requirement:** 50-REQ-3.1
**Type:** unit
**Description:** Without --yes, confirmation is prompted.

**Preconditions:**
- CLI invoked with `reset --spec alpha` (no --yes).

**Input:**
- User input: "n" (decline)

**Expected:**
- No state modification.
- Exit code 0 (user chose to abort).

**Assertion pseudocode:**
```
result = invoke_cli(["reset", "--spec", "alpha"], input="n\n")
state = load_state(state_path)
ASSERT state unchanged
```

### TS-50-11: JSON Output

**Requirement:** 50-REQ-3.4
**Type:** unit
**Description:** JSON mode outputs structured result.

**Preconditions:**
- State has `alpha:1` (completed).

**Input:**
- CLI args: `["--json", "reset", "--spec", "alpha"]`

**Expected:**
- Valid JSON with keys `reset_tasks`, `cleaned_worktrees`, `cleaned_branches`.

**Assertion pseudocode:**
```
result = invoke_cli(["--json", "reset", "--spec", "alpha"])
data = json.loads(result.output)
ASSERT "reset_tasks" IN data
ASSERT "cleaned_worktrees" IN data
ASSERT "cleaned_branches" IN data
```

### TS-50-12: Session History Preserved

**Requirement:** 50-REQ-4.1, 50-REQ-4.2
**Type:** unit
**Description:** Session history and counters are not modified.

**Preconditions:**
- State has 5 session history records and total_cost = 10.0.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- State still has 5 session history records and total_cost = 10.0.

**Assertion pseudocode:**
```
reset_spec("alpha", ...)
state = load_state(state_path)
ASSERT len(state.session_history) == 5
ASSERT state.total_cost == 10.0
```

## Edge Case Tests

### TS-50-E1: Unknown Spec Name

**Requirement:** 50-REQ-1.E1
**Type:** unit
**Description:** Error with valid spec names when spec is unknown.

**Preconditions:**
- Plan has specs `alpha` and `beta`.

**Input:**
- `spec_name = "nonexistent"`

**Expected:**
- `AgentFoxError` raised.
- Error message contains `alpha` and `beta`.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError:
    reset_spec("nonexistent", ...)
ASSERT "alpha" IN error.message
ASSERT "beta" IN error.message
```

### TS-50-E2: Missing Plan File

**Requirement:** 50-REQ-1.E2
**Type:** unit
**Description:** Error when plan.json does not exist.

**Preconditions:**
- No plan.json file.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `AgentFoxError` raised mentioning `plan`.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError:
    reset_spec("alpha", state_path, missing_plan_path, ...)
```

### TS-50-E3: Missing State File

**Requirement:** 50-REQ-1.E3
**Type:** unit
**Description:** Error when state.jsonl does not exist.

**Preconditions:**
- No state.jsonl file.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `AgentFoxError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES AgentFoxError:
    reset_spec("alpha", missing_state_path, plan_path, ...)
```

### TS-50-E4: All Nodes Already Pending

**Requirement:** 50-REQ-1.E4
**Type:** unit
**Description:** No-op when all spec nodes are already pending.

**Preconditions:**
- All `alpha` nodes have status `pending`.

**Input:**
- `spec_name = "alpha"`

**Expected:**
- `result.reset_tasks` is empty.

**Assertion pseudocode:**
```
result = reset_spec("alpha", ...)
ASSERT result.reset_tasks == []
```

## Property Test Cases

### TS-50-P1: Spec Isolation

**Property:** Property 1 from design.md
**Validates:** 50-REQ-1.1, 50-REQ-1.3
**Type:** property
**Description:** Only nodes from the target spec are modified.

**For any:** Plan with 2-5 specs, each with 1-5 nodes, random statuses.
**Invariant:** After `reset_spec(S)`, nodes not in S retain original status.

**Assertion pseudocode:**
```
FOR ANY plan IN random_plans, spec IN plan.specs:
    original = copy(state.node_states)
    reset_spec(spec, ...)
    FOR nid, status IN state.node_states:
        IF node_spec(nid) != spec:
            ASSERT status == original[nid]
```

### TS-50-P2: Complete Spec Coverage

**Property:** Property 2 from design.md
**Validates:** 50-REQ-1.1, 50-REQ-1.2
**Type:** property
**Description:** Every node in the spec is reset regardless of archetype.

**For any:** Plan with mixed coder/archetype nodes, random statuses.
**Invariant:** After reset, all nodes with matching spec_name are `pending`.

**Assertion pseudocode:**
```
FOR ANY plan IN random_plans, spec IN plan.specs:
    reset_spec(spec, ...)
    FOR nid IN plan.nodes:
        IF node_spec(nid) == spec:
            ASSERT state.node_states[nid] == "pending"
```

### TS-50-P3: Preservation

**Property:** Property 4 from design.md
**Validates:** 50-REQ-4.1, 50-REQ-4.2
**Type:** property
**Description:** Session history and counters are unchanged.

**For any:** State with random session history and counters.
**Invariant:** After reset, history length, total_cost, total_sessions unchanged.

**Assertion pseudocode:**
```
FOR ANY state IN random_states:
    original_history_len = len(state.session_history)
    original_cost = state.total_cost
    reset_spec(spec, ...)
    ASSERT len(state.session_history) == original_history_len
    ASSERT state.total_cost == original_cost
```

### TS-50-P4: Artifact Synchronization

**Property:** Property 5 from design.md
**Validates:** 50-REQ-1.5, 50-REQ-1.6
**Type:** property
**Description:** tasks.md and plan.json are consistent with state after reset.

**For any:** Spec with 1-5 task groups, random checkbox states.
**Invariant:** After reset, all checkboxes are `[ ]` and plan statuses are `pending`.

**Assertion pseudocode:**
```
FOR ANY spec IN random_specs:
    reset_spec(spec, ...)
    content = read_file(tasks_md_path)
    ASSERT no "[x]" or "[-]" checkboxes for reset groups
    plan = load_plan(plan_path)
    FOR nid IN spec_nodes:
        ASSERT plan.nodes[nid].status == "pending"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 50-REQ-1.1 | TS-50-1 | unit |
| 50-REQ-1.2 | TS-50-2 | unit |
| 50-REQ-1.3 | TS-50-3 | unit |
| 50-REQ-1.4 | TS-50-4 | unit |
| 50-REQ-1.5 | TS-50-5 | unit |
| 50-REQ-1.6 | TS-50-6 | unit |
| 50-REQ-1.7 | TS-50-7 | unit |
| 50-REQ-1.E1 | TS-50-E1 | unit |
| 50-REQ-1.E2 | TS-50-E2 | unit |
| 50-REQ-1.E3 | TS-50-E3 | unit |
| 50-REQ-1.E4 | TS-50-E4 | unit |
| 50-REQ-2.1 | TS-50-8 | unit |
| 50-REQ-2.2 | TS-50-9 | unit |
| 50-REQ-3.1 | TS-50-10 | unit |
| 50-REQ-3.4 | TS-50-11 | unit |
| 50-REQ-4.1 | TS-50-12 | unit |
| 50-REQ-4.2 | TS-50-12 | unit |
| Property 1 | TS-50-P1 | property |
| Property 2 | TS-50-P2 | property |
| Property 4 | TS-50-P3 | property |
| Property 5 | TS-50-P4 | property |
