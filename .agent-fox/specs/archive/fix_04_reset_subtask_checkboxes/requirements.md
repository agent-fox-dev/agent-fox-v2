# Requirements Document

## Introduction

This specification fixes a bug in the `reset --hard` command where sub-task
and nested checkboxes within a task group are not reset. The existing
`reset_tasks_md_checkboxes()` function in `agent_fox/engine/reset.py` only
resets top-level group checkboxes. This fix extends it to reset all
checkboxes within each affected task group's section, regardless of
indentation depth.

## Glossary

- **Top-level checkbox**: A markdown checkbox at column 0 matching the pattern
  `- [...] N.` where N is the task group number (e.g., `- [x] 1. Write tests`).
- **Sub-task checkbox**: A markdown checkbox indented under a top-level
  checkbox, typically with a numbered ID like `1.1`, `1.2`, or `1.V`
  (e.g., `  - [x] 1.1 Create fixtures`).
- **Nested checkbox**: A markdown checkbox at deeper indentation (4+ spaces)
  under a sub-task, typically without a numbered ID (e.g.,
  `    - [x] All spec tests exist`).
- **Task group section**: The region of text in `tasks.md` starting at a
  top-level checkbox line and extending to (but not including) the next
  top-level checkbox line, or to the end of the task list.
- **Checkbox state**: One of `[x]` (completed), `[-]` (in-progress),
  `[~]` (queued), `[ ]` (not started), or `[ ]*` (optional, not started).

## Requirements

### Requirement 1: Reset Sub-task Checkboxes

**User Story:** As an operator running `reset --hard`, I want all sub-task
checkboxes within affected task groups to be reset, so that the task group
is truly returned to its initial state.

#### Acceptance Criteria

1. [fix04-REQ-1.1] WHEN `reset_tasks_md_checkboxes` resets a task group,
   THE function SHALL reset all `[x]` and `[-]` checkboxes within the task
   group's section to `[ ]`, including indented sub-task checkboxes.
2. [fix04-REQ-1.2] WHEN `reset_tasks_md_checkboxes` resets a task group,
   THE function SHALL reset nested checkboxes at any indentation depth
   (2-space, 4-space, 6-space, etc.) within the task group's section.
3. [fix04-REQ-1.3] WHEN `reset_tasks_md_checkboxes` resets a task group,
   THE function SHALL NOT modify `[~]` (queued) or `[ ]` (unchecked)
   checkboxes.
4. [fix04-REQ-1.4] WHEN `reset_tasks_md_checkboxes` resets a task group,
   THE function SHALL NOT modify checkboxes belonging to other task groups.

#### Edge Cases

1. [fix04-REQ-1.E1] IF a task group section contains no sub-task or nested
   checkboxes, THEN THE function SHALL reset only the top-level checkbox
   (existing behavior preserved).
2. [fix04-REQ-1.E2] IF a sub-task checkbox uses the optional marker
   (`- [ ]*`), THEN THE function SHALL leave it unchanged (already unchecked).

### Requirement 2: Section Boundary Detection

**User Story:** As an operator, I want the reset to correctly identify which
checkboxes belong to which task group, so that only the affected group's
checkboxes are modified.

#### Acceptance Criteria

1. [fix04-REQ-2.1] THE function SHALL define a task group's section as
   starting at the top-level checkbox line (`- [...] N.`) and ending at the
   next top-level checkbox line (`- [...] M.`) or end of file.
2. [fix04-REQ-2.2] WHEN multiple task groups are reset in the same file,
   THE function SHALL correctly reset each group's section independently.

#### Edge Cases

1. [fix04-REQ-2.E1] IF the task group is the last group in the file, THEN
   THE function SHALL reset all checkboxes from the top-level line to the
   end of the tasks section.
2. [fix04-REQ-2.E2] IF the file contains non-checkbox content between task
   groups (e.g., markdown tables, prose), THEN THE function SHALL not
   modify that content.

### Requirement 3: Erratum Documentation

**User Story:** As a developer, I want the spec divergence documented, so
that the audit trail between spec 35 and the implementation is clear.

#### Acceptance Criteria

1. [fix04-REQ-3.1] THE fix SHALL include an erratum at
   `docs/errata/35_hard_reset_subtask_checkboxes.md` documenting the
   divergence from 35-REQ-7.1's original implementation scope.
