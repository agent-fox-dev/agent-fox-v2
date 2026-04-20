# PRD: Hard Reset Sub-task Checkbox Reset

## Summary

`reset --hard` currently resets only task-group level checkboxes (`- [x] 1. ...`)
in `tasks.md`, leaving sub-task checkboxes (`  - [x] 1.1 ...`) and deeper
nested checkboxes checked. All checkboxes within an affected task group should
be reset for a complete hard reset.

## Current Behavior

The regex in `agent_fox/engine/reset.py` (`reset_tasks_md_checkboxes`):

```python
pattern = rf"^(- \[)[x\-](\] {group_num}\.)"
text = re.sub(pattern, r"\1 \2", text, flags=re.MULTILINE)
```

The `^` anchor with `re.MULTILINE` only matches lines starting at column 0.
Indented sub-tasks (2-space indent) and deeper nested checkboxes (4-space
indent) are skipped.

**Example -- before reset:**
```markdown
- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
  - [x] 1.2 Write extraction tests
  - [x] 1.V Verify task group 1
    - [x] All spec tests exist
    - [x] No linter warnings introduced
```

**After `reset --hard` (current):**
```markdown
- [ ] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
  - [x] 1.2 Write extraction tests
  - [x] 1.V Verify task group 1
    - [x] All spec tests exist
    - [x] No linter warnings introduced
```

## Expected Behavior

All checkboxes for the affected group should be reset, at all nesting depths:

```markdown
- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test fixtures
  - [ ] 1.2 Write extraction tests
  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist
    - [ ] No linter warnings introduced
```

## Implementation Approach

Instead of adding a second regex for numbered sub-tasks only, use a
section-based approach: identify the region of text belonging to each task
group (from the top-level `- [...] N.` line to the next top-level `- [...] M.`
line or end of file), and reset ALL checkboxes within that region regardless
of indent depth or format.

## Clarifications

1. **All nesting depths**: All checkboxes within a task group's section are
   reset, including deeply nested verification items that lack numbered IDs.
2. **Checkbox states**: Only `[x]` (completed) and `[-]` (in-progress) are
   reset to `[ ]`. `[~]` (queued) and `[ ]` (unchecked) are left unchanged.
3. **Optional task markers**: Sub-tasks marked optional (`- [ ]*`) use
   unchecked `[ ]` state and are unaffected by the reset.
4. **Section boundaries**: A task group's section starts at its top-level
   checkbox line and ends at the next top-level checkbox line (or EOF).

## Size

Small -- one function modification, one test update, one erratum.
