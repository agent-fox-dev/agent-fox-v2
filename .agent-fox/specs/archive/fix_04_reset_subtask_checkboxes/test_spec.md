# Test Specification: Hard Reset Sub-task Checkbox Reset

## Overview

This test specification defines test contracts for the modified
`reset_tasks_md_checkboxes()` function. Tests verify that sub-task and
nested checkboxes are reset alongside top-level checkboxes, while preserving
other groups, non-checkbox content, and `[~]`/`[ ]` states.

## Test Cases

### TS-fix04-1: Sub-task Checkboxes Reset

**Requirement:** fix04-REQ-1.1
**Type:** unit
**Description:** Verify that indented sub-task checkboxes are reset.

**Preconditions:**
- tasks.md with group 1 containing `[x]` sub-tasks at 2-space indent.

**Input:**
```markdown
- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
  - [x] 1.2 Write extraction tests
```

**Expected:**
```markdown
- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test fixtures
  - [ ] 1.2 Write extraction tests
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [ ] 1." IN text
ASSERT "  - [ ] 1.1" IN text
ASSERT "  - [ ] 1.2" IN text
ASSERT "[x]" NOT IN text
```

### TS-fix04-2: Deeply Nested Checkboxes Reset

**Requirement:** fix04-REQ-1.2
**Type:** unit
**Description:** Verify that checkboxes at 4-space indent (under verification sub-tasks) are reset.

**Preconditions:**
- tasks.md with group 1 containing verification sub-task with nested items.

**Input:**
```markdown
- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
  - [x] 1.V Verify task group 1
    - [x] All spec tests exist
    - [x] No linter warnings introduced
```

**Expected:**
```markdown
- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test fixtures
  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist
    - [ ] No linter warnings introduced
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "[x]" NOT IN text
ASSERT "    - [ ] All spec tests exist" IN text
ASSERT "    - [ ] No linter warnings" IN text
```

### TS-fix04-3: Queued State Preserved

**Requirement:** fix04-REQ-1.3
**Type:** unit
**Description:** Verify that `[~]` checkboxes are not modified.

**Preconditions:**
- tasks.md with group 1 containing a mix of `[x]` and `[~]` sub-tasks.

**Input:**
```markdown
- [x] 1. Write tests
  - [x] 1.1 Done subtask
  - [~] 1.2 Queued subtask
```

**Expected:**
```markdown
- [ ] 1. Write tests
  - [ ] 1.1 Done subtask
  - [~] 1.2 Queued subtask
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "  - [~] 1.2 Queued subtask" IN text
ASSERT "  - [ ] 1.1 Done subtask" IN text
```

### TS-fix04-4: Other Groups Unaffected

**Requirement:** fix04-REQ-1.4
**Type:** unit
**Description:** Verify that resetting group 1 does not affect group 2.

**Preconditions:**
- tasks.md with groups 1 and 2, both fully checked.

**Input:**
```markdown
- [x] 1. Write tests
  - [x] 1.1 Sub one
- [x] 2. Implement feature
  - [x] 2.1 Sub two
```
Reset group 1 only.

**Expected:**
```markdown
- [ ] 1. Write tests
  - [ ] 1.1 Sub one
- [x] 2. Implement feature
  - [x] 2.1 Sub two
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [ ] 1." IN text
ASSERT "  - [ ] 1.1" IN text
ASSERT "- [x] 2." IN text
ASSERT "  - [x] 2.1" IN text
```

### TS-fix04-5: Section Boundary at Next Group

**Requirement:** fix04-REQ-2.1
**Type:** unit
**Description:** Verify section boundaries are correctly detected between groups.

**Preconditions:**
- tasks.md with groups 1, 2, 3, all with sub-tasks.

**Input:**
```markdown
- [x] 1. Group one
  - [x] 1.1 Sub
- [x] 2. Group two
  - [x] 2.1 Sub
- [x] 3. Group three
  - [x] 3.1 Sub
```
Reset group 2 only.

**Expected:**
- Group 1 checkboxes unchanged (`[x]`).
- Group 2 checkboxes reset (`[ ]`).
- Group 3 checkboxes unchanged (`[x]`).

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:2"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [x] 1." IN text
ASSERT "- [ ] 2." IN text
ASSERT "  - [ ] 2.1" IN text
ASSERT "- [x] 3." IN text
```

### TS-fix04-6: Multiple Groups Reset Independently

**Requirement:** fix04-REQ-2.2
**Type:** unit
**Description:** Verify resetting multiple groups resets each independently.

**Preconditions:**
- tasks.md with groups 1, 2, 3 all checked.

**Input:**
```markdown
- [x] 1. Group one
  - [x] 1.1 Sub
- [x] 2. Group two
  - [x] 2.1 Sub
- [x] 3. Group three
  - [x] 3.1 Sub
```
Reset groups 1 and 3.

**Expected:**
- Groups 1 and 3 reset to `[ ]`.
- Group 2 unchanged (`[x]`).

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1", "myspec:3"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [ ] 1." IN text
ASSERT "- [x] 2." IN text
ASSERT "- [ ] 3." IN text
```

### TS-fix04-7: In-Progress Checkboxes Reset

**Requirement:** fix04-REQ-1.1
**Type:** unit
**Description:** Verify `[-]` sub-task checkboxes are reset to `[ ]`.

**Preconditions:**
- tasks.md with `[-]` sub-tasks.

**Input:**
```markdown
- [-] 1. In progress group
  - [x] 1.1 Done
  - [-] 1.2 In progress
```

**Expected:**
```markdown
- [ ] 1. In progress group
  - [ ] 1.1 Done
  - [ ] 1.2 In progress
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "[-]" NOT IN text
ASSERT "- [ ] 1." IN text
ASSERT "  - [ ] 1.1" IN text
ASSERT "  - [ ] 1.2" IN text
```

## Edge Case Tests

### TS-fix04-E1: Group With No Sub-tasks

**Requirement:** fix04-REQ-1.E1
**Type:** unit
**Description:** Verify a group with only a top-level checkbox is handled correctly.

**Preconditions:**
- tasks.md with group 1 having no sub-tasks.

**Input:**
```markdown
- [x] 1. Single line group
- [x] 2. Another group
```

**Expected:**
```markdown
- [ ] 1. Single line group
- [x] 2. Another group
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [ ] 1." IN text
ASSERT "- [x] 2." IN text
```

### TS-fix04-E2: Optional Task Marker Preserved

**Requirement:** fix04-REQ-1.E2
**Type:** unit
**Description:** Verify optional task markers (`- [ ]*`) are not modified.

**Preconditions:**
- tasks.md with an optional sub-task.

**Input:**
```markdown
- [x] 1. Group one
  - [x] 1.1 Required sub
  - [ ]* 1.2 Optional sub
```

**Expected:**
```markdown
- [ ] 1. Group one
  - [ ] 1.1 Required sub
  - [ ]* 1.2 Optional sub
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "  - [ ]* 1.2 Optional sub" IN text
ASSERT "  - [ ] 1.1 Required sub" IN text
```

### TS-fix04-E3: Last Group in File

**Requirement:** fix04-REQ-2.E1
**Type:** unit
**Description:** Verify the last group's section extends to EOF.

**Preconditions:**
- tasks.md with group 2 as the last group.

**Input:**
```markdown
- [x] 1. Group one
  - [x] 1.1 Sub
- [x] 2. Last group
  - [x] 2.1 Sub one
  - [x] 2.V Verify
    - [x] All tests pass
```
Reset group 2.

**Expected:**
All group 2 checkboxes reset, including nested under 2.V.

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:2"], specs_dir)
text = tasks_md.read_text()
ASSERT "- [x] 1." IN text
ASSERT "- [ ] 2." IN text
ASSERT "  - [ ] 2.1" IN text
ASSERT "    - [ ] All tests pass" IN text
```

### TS-fix04-E4: Non-Checkbox Content Preserved

**Requirement:** fix04-REQ-2.E2
**Type:** unit
**Description:** Verify non-checkbox lines within a section are not modified.

**Preconditions:**
- tasks.md with prose and bullet points (not checkboxes) in a section.

**Input:**
```markdown
- [x] 1. Group one
  - [x] 1.1 Sub one
    - Implementation detail (not a checkbox)
    - Another detail
  - [x] 1.2 Sub two
```

**Expected:**
```markdown
- [ ] 1. Group one
  - [ ] 1.1 Sub one
    - Implementation detail (not a checkbox)
    - Another detail
  - [ ] 1.2 Sub two
```

**Assertion pseudocode:**
```
reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
text = tasks_md.read_text()
ASSERT "    - Implementation detail (not a checkbox)" IN text
ASSERT "    - Another detail" IN text
```

## Property Test Cases

### TS-fix04-P1: All Nested Checkboxes Reset

**Property:** Property 1 from design.md
**Validates:** fix04-REQ-1.1, fix04-REQ-1.2
**Type:** property
**Description:** All `[x]` and `[-]` checkboxes within a reset group's section become `[ ]`.

**For any:** tasks.md content with N task groups, each with M sub-tasks at
varying depths (1-3 indent levels), with randomly assigned checkbox states.
**Invariant:** After resetting group K, no `[x]` or `[-]` checkboxes remain
within group K's section.

**Assertion pseudocode:**
```
FOR ANY (tasks_content, target_group) IN generated_tasks:
    reset_tasks_md_checkboxes([f"myspec:{target_group}"], specs_dir)
    section = extract_section(tasks_md.read_text(), target_group)
    ASSERT "[x]" NOT IN section
    ASSERT "[-]" NOT IN section
```

### TS-fix04-P2: Other Groups Unaffected

**Property:** Property 2 from design.md
**Validates:** fix04-REQ-1.4, fix04-REQ-2.1
**Type:** property
**Description:** Resetting group K leaves all other groups' checkboxes unchanged.

**For any:** tasks.md content with N task groups (N >= 2), reset one group.
**Invariant:** The text of every other group's section is identical before
and after the reset.

**Assertion pseudocode:**
```
FOR ANY (tasks_content, target_group, num_groups) IN generated_tasks:
    original_sections = {g: extract_section(text, g) for g in range(1, num_groups+1) if g != target_group}
    reset_tasks_md_checkboxes([f"myspec:{target_group}"], specs_dir)
    new_text = tasks_md.read_text()
    FOR g IN original_sections:
        ASSERT extract_section(new_text, g) == original_sections[g]
```

### TS-fix04-P3: Queued and Unchecked Preserved

**Property:** Property 3 from design.md
**Validates:** fix04-REQ-1.3
**Type:** property
**Description:** `[~]` and `[ ]` checkboxes are never modified.

**For any:** tasks.md content with `[~]` and `[ ]` checkboxes interspersed.
**Invariant:** Count of `[~]` and `[ ]` checkboxes is the same before and
after reset (and their positions are unchanged).

**Assertion pseudocode:**
```
FOR ANY tasks_content IN generated_tasks_with_mixed_states:
    queued_before = count_pattern(text, r"\[~\]")
    unchecked_before = count_pattern(text, r"\[ \]")
    reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
    new_text = tasks_md.read_text()
    queued_after = count_pattern(new_text, r"\[~\]")
    ASSERT queued_after == queued_before
    # unchecked count increases by number of reset checkboxes
```

### TS-fix04-P4: Idempotent Reset

**Property:** Property 4 from design.md
**Validates:** fix04-REQ-1.1
**Type:** property
**Description:** Applying reset twice produces the same result as once.

**For any:** tasks.md content with any combination of checkbox states.
**Invariant:** `f(f(x)) == f(x)`.

**Assertion pseudocode:**
```
FOR ANY tasks_content IN generated_tasks:
    reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
    after_first = tasks_md.read_text()
    reset_tasks_md_checkboxes(["myspec:1"], specs_dir)
    after_second = tasks_md.read_text()
    ASSERT after_first == after_second
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| fix04-REQ-1.1 | TS-fix04-1, TS-fix04-7 | unit |
| fix04-REQ-1.2 | TS-fix04-2 | unit |
| fix04-REQ-1.3 | TS-fix04-3 | unit |
| fix04-REQ-1.4 | TS-fix04-4 | unit |
| fix04-REQ-1.E1 | TS-fix04-E1 | unit |
| fix04-REQ-1.E2 | TS-fix04-E2 | unit |
| fix04-REQ-2.1 | TS-fix04-5 | unit |
| fix04-REQ-2.2 | TS-fix04-6 | unit |
| fix04-REQ-2.E1 | TS-fix04-E3 | unit |
| fix04-REQ-2.E2 | TS-fix04-E4 | unit |
| fix04-REQ-3.1 | (erratum file existence check) | unit |
| Property 1 | TS-fix04-P1 | property |
| Property 2 | TS-fix04-P2 | property |
| Property 3 | TS-fix04-P3 | property |
| Property 4 | TS-fix04-P4 | property |
