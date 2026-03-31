# Test Specification: Plan Always Rebuild

## Overview

Tests verify that the plan cache is removed, `--reanalyze` is gone, dead code
is cleaned up, and the `plan` command always rebuilds from `.specs/`.

## Test Cases

### TS-63-1: Plan Always Rebuilds From Specs

**Requirement:** 63-REQ-1.1
**Type:** integration
**Description:** Verify that `plan` rebuilds the graph even when `plan.json`
already exists.

**Preconditions:**
- A project with `.specs/` containing at least one spec with `tasks.md`.
- A valid `plan.json` already exists.

**Input:**
- Modify a spec's `tasks.md` (e.g., add a new task group).
- Run `agent-fox plan`.

**Expected:**
- The output reflects the modified spec content (new task group visible).

**Assertion pseudocode:**
```
setup_project_with_spec(tmp)
result1 = cli_runner.invoke(main, ["plan"])
ASSERT result1.exit_code == 0

add_task_group_to_spec(tmp)
result2 = cli_runner.invoke(main, ["plan"])
ASSERT result2.exit_code == 0
ASSERT "new_group" IN result2.output
```

### TS-63-2: Plan Persists To plan.json

**Requirement:** 63-REQ-1.2
**Type:** integration
**Description:** Verify that `plan` writes the built graph to `plan.json`.

**Preconditions:**
- A project with `.specs/` containing at least one spec with `tasks.md`.
- No `plan.json` exists.

**Input:**
- Run `agent-fox plan`.

**Expected:**
- `plan.json` exists after the command.

**Assertion pseudocode:**
```
setup_project_with_spec(tmp)
plan_path = tmp / ".agent-fox" / "plan.json"
ASSERT NOT plan_path.exists()

result = cli_runner.invoke(main, ["plan"])
ASSERT result.exit_code == 0
ASSERT plan_path.exists()
```

### TS-63-3: Node Status Derived From Checkboxes

**Requirement:** 63-REQ-1.3
**Type:** unit
**Description:** Verify that completed task groups get COMPLETED status and
incomplete groups get PENDING status.

**Preconditions:**
- A spec with two task groups: one fully checked, one not.

**Input:**
- Build the plan from the spec.

**Expected:**
- Completed group node has status COMPLETED.
- Incomplete group node has status PENDING.

**Assertion pseudocode:**
```
graph = _build_plan(specs_dir, None, False, config)
ASSERT graph.nodes["spec:1"].status == NodeStatus.COMPLETED
ASSERT graph.nodes["spec:2"].status == NodeStatus.PENDING
```

### TS-63-4: Reanalyze Option Rejected

**Requirement:** 63-REQ-2.1, 63-REQ-2.2
**Type:** integration
**Description:** Verify that `--reanalyze` is no longer accepted.

**Preconditions:**
- A project with `.specs/`.

**Input:**
- Run `agent-fox plan --reanalyze`.

**Expected:**
- Command exits with error (Click rejects unrecognized option).

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["plan", "--reanalyze"])
ASSERT result.exit_code != 0
ASSERT "No such option" IN result.output OR "no such option" IN result.output
```

### TS-63-5: Dead Functions Removed

**Requirement:** 63-REQ-3.1
**Type:** unit
**Description:** Verify that cache-related functions no longer exist in the
plan module.

**Preconditions:**
- Module `agent_fox.cli.plan` is importable.

**Input:**
- Check for removed function names.

**Expected:**
- `_compute_specs_hash`, `_compute_config_hash`, and `_cache_matches_request`
  do not exist in the module.

**Assertion pseudocode:**
```
import agent_fox.cli.plan as plan_mod
ASSERT NOT hasattr(plan_mod, "_compute_specs_hash")
ASSERT NOT hasattr(plan_mod, "_compute_config_hash")
ASSERT NOT hasattr(plan_mod, "_cache_matches_request")
```

### TS-63-6: PlanMetadata Fields Removed

**Requirement:** 63-REQ-3.2
**Type:** unit
**Description:** Verify that `PlanMetadata` no longer has `specs_hash` or
`config_hash` fields.

**Preconditions:**
- `PlanMetadata` is importable from `agent_fox.graph.types`.

**Input:**
- Inspect `PlanMetadata` fields.

**Expected:**
- No `specs_hash` or `config_hash` field.

**Assertion pseudocode:**
```
from agent_fox.graph.types import PlanMetadata
fields = {f.name for f in dataclasses.fields(PlanMetadata)}
ASSERT "specs_hash" NOT IN fields
ASSERT "config_hash" NOT IN fields
```

## Edge Case Tests

### TS-63-E1: Old plan.json With Hash Fields Loads Successfully

**Requirement:** 63-REQ-3.E1
**Type:** unit
**Description:** Verify that a `plan.json` written by a prior version
(containing `specs_hash` and `config_hash`) can still be loaded.

**Preconditions:**
- A `plan.json` file containing `specs_hash` and `config_hash` in metadata.

**Input:**
- Call `load_plan()` on the file.

**Expected:**
- Returns a valid `TaskGraph` without error.
- The loaded `PlanMetadata` does not contain the removed fields.

**Assertion pseudocode:**
```
write_old_plan_json(plan_path, specs_hash="abc", config_hash="def")
graph = load_plan(plan_path)
ASSERT graph IS NOT None
ASSERT NOT hasattr(graph.metadata, "specs_hash")
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 63-REQ-1.1 | TS-63-1 | integration |
| 63-REQ-1.2 | TS-63-2 | integration |
| 63-REQ-1.3 | TS-63-3 | unit |
| 63-REQ-2.1 | TS-63-4 | integration |
| 63-REQ-2.2 | TS-63-4 | integration |
| 63-REQ-3.1 | TS-63-5 | unit |
| 63-REQ-3.2 | TS-63-6 | unit |
| 63-REQ-3.E1 | TS-63-E1 | unit |
