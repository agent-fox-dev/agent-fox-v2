# Test Specification: Spec Lint Fixes

## Overview

Tests cover the three bug fixes: parser regex, completed-group skip, and
alternative dependency table validation. All tests are unit tests against
existing modules.

## Test Cases

### TS-F3-1: Verification step subtask parsed

**Requirement:** F3-REQ-1.1
**Type:** unit
**Description:** Subtask with ID `N.V` is included in parsed group subtasks.

**Preconditions:**
- A tasks.md string containing `  - [x] 1.V Verify task group 1`

**Input:**
- Parse the tasks.md string with `parse_tasks()`

**Expected:**
- Group 1's subtask list contains a `SubtaskDef` with `id == "1.V"`

**Assertion pseudocode:**
```
groups = parse_tasks(tasks_path)
verify_subtask = [st for st in groups[0].subtasks if st.id == "1.V"]
ASSERT len(verify_subtask) == 1
ASSERT verify_subtask[0].completed == True
```

### TS-F3-2: Numeric subtask IDs still parsed (regression)

**Requirement:** F3-REQ-1.2
**Type:** unit
**Description:** Numeric subtask IDs continue to parse correctly.

**Preconditions:**
- A tasks.md string with subtasks `1.1`, `1.2`, `1.V`

**Input:**
- Parse with `parse_tasks()`

**Expected:**
- All three subtasks are in the group's subtask list

**Assertion pseudocode:**
```
groups = parse_tasks(tasks_path)
ids = [st.id for st in groups[0].subtasks]
ASSERT "1.1" in ids
ASSERT "1.2" in ids
ASSERT "1.V" in ids
```

### TS-F3-3: Completed group skips oversized check

**Requirement:** F3-REQ-2.1
**Type:** unit
**Description:** Completed groups produce no oversized-group findings.

**Preconditions:**
- A TaskGroupDef with `completed=True` and 8 subtasks

**Input:**
- Call `check_oversized_groups()` with this group

**Expected:**
- Empty findings list

**Assertion pseudocode:**
```
group = TaskGroupDef(number=1, completed=True, subtasks=8_subtasks, ...)
findings = check_oversized_groups("spec", [group])
ASSERT findings == []
```

### TS-F3-4: Completed group skips verification check

**Requirement:** F3-REQ-2.2
**Type:** unit
**Description:** Completed groups produce no missing-verification findings.

**Preconditions:**
- A TaskGroupDef with `completed=True` and no N.V subtask

**Input:**
- Call `check_missing_verification()` with this group

**Expected:**
- Empty findings list

**Assertion pseudocode:**
```
group = TaskGroupDef(number=1, completed=True, subtasks=no_verify, ...)
findings = check_missing_verification("spec", [group])
ASSERT findings == []
```

### TS-F3-5: Incomplete group still checked

**Requirement:** F3-REQ-2.3
**Type:** unit
**Description:** Incomplete groups are still validated.

**Preconditions:**
- A TaskGroupDef with `completed=False`, 8 subtasks, no N.V

**Input:**
- Call both check functions

**Expected:**
- Oversized finding and missing-verification finding both produced

**Assertion pseudocode:**
```
group = TaskGroupDef(number=1, completed=False, subtasks=8_subtasks, ...)
ASSERT len(check_oversized_groups("spec", [group])) == 1
ASSERT len(check_missing_verification("spec", [group])) == 1
```

### TS-F3-6: Alternative table — non-existent spec detected

**Requirement:** F3-REQ-3.2
**Type:** unit
**Description:** Alternative dependency table referencing unknown spec
produces ERROR finding.

**Preconditions:**
- A prd.md with alternative table referencing spec `99_nonexistent`
- `known_specs` dict does not contain `99_nonexistent`

**Input:**
- Call `check_broken_dependencies()`

**Expected:**
- ERROR finding with rule `broken-dependency` mentioning `99_nonexistent`

### TS-F3-7: Alternative table — non-existent from-group detected

**Requirement:** F3-REQ-3.3
**Type:** unit
**Description:** Alternative dependency table referencing non-existent group
in dependency spec produces ERROR finding.

**Preconditions:**
- A prd.md with alternative table: spec `01_core_foundation`, from-group `7`
- `known_specs["01_core_foundation"]` = `[1, 2, 3, 4, 5]`

**Input:**
- Call `check_broken_dependencies()`

**Expected:**
- ERROR finding with rule `broken-dependency` mentioning group 7

### TS-F3-8: Alternative table — non-existent to-group detected

**Requirement:** F3-REQ-3.4
**Type:** unit
**Description:** Alternative dependency table referencing non-existent group
in current spec produces ERROR finding.

**Preconditions:**
- A prd.md with alternative table: to-group `99`
- Current spec has groups `[1, 2, 3]`

**Input:**
- Call `check_broken_dependencies()` with current spec groups

**Expected:**
- ERROR finding mentioning group 99

## Edge Case Tests

### TS-F3-E1: Unknown subtask suffix ignored

**Requirement:** F3-REQ-1.E1
**Type:** unit
**Description:** Subtask with ID like `1.X` is not parsed.

**Preconditions:**
- A tasks.md with subtask line `  - [ ] 1.X Some unknown step`

**Input:**
- Parse with `parse_tasks()`

**Expected:**
- No subtask with id `1.X` in the group

### TS-F3-E2: Both table formats validated

**Requirement:** F3-REQ-3.E1
**Type:** unit
**Description:** A prd.md with both standard and alternative tables has
both validated.

**Preconditions:**
- A prd.md with one standard table and one alternative table, each
  containing a broken reference

**Input:**
- Call `check_broken_dependencies()`

**Expected:**
- Findings from both tables

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| F3-REQ-1.1 | TS-F3-1 | unit |
| F3-REQ-1.2 | TS-F3-2 | unit |
| F3-REQ-1.E1 | TS-F3-E1 | unit |
| F3-REQ-2.1 | TS-F3-3 | unit |
| F3-REQ-2.2 | TS-F3-4 | unit |
| F3-REQ-2.3 | TS-F3-5 | unit |
| F3-REQ-3.2 | TS-F3-6 | unit |
| F3-REQ-3.3 | TS-F3-7 | unit |
| F3-REQ-3.4 | TS-F3-8 | unit |
| F3-REQ-3.E1 | TS-F3-E2 | unit |
| F3-REQ-4.1 | (manual: read SKILL.md) | — |
| F3-REQ-4.2 | (manual: read SKILL.md) | — |
