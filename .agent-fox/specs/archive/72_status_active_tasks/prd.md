# PRD: Show Active Tasks in Status Command

## Summary

Add an "Active Tasks" section to the `status` command output that lists all
currently in-progress tasks with the same formatting used by the `standup`
command's "Agent Activity" section. This applies to both the text (stdout) and
JSON output modes.

## Current Behavior

The `status` command shows a summary line (`Tasks: X/Y done | Z in progress |
...`) and an `active_agents` list (archetype names of running non-coder nodes),
but does not list the actual in-progress task details — task IDs, session
counts, token usage, or cost.

The `standup` command already shows per-task details in its "Agent Activity"
section using `TaskActivity` records, but only within a time window.

## Expected Behavior

The `status` command gains a new "Active Tasks" section that appears before
"Cost by Archetype" in the text output. It lists every task (coder and
non-coder) with status `in_progress`, formatted identically to standup's
Agent Activity:

```
Active Tasks
  spec/0:coder: in_progress. 1/2 sessions. tokens 500.0k in / 750.0k out. $12.34
  spec/0:verifier: in_progress. 0/0 sessions.
```

If no tasks are in progress, the section shows `(no active tasks)`.

In JSON mode, the same data appears as a list of task activity objects in the
`in_progress_tasks` field of the status report.

## Scope

- **Data model**: Add `in_progress_tasks: list[TaskActivity]` to
  `StatusReport`. Reuse the existing `TaskActivity` dataclass from
  `reporting/standup.py`.
- **Report generation**: Filter all nodes with `in_progress` status (both
  coder and non-coder), compute session metrics from `session_history`, and
  populate the new field.
- **Text formatter**: Add "Active Tasks" section before "Cost by Archetype"
  using the same format as standup's Agent Activity.
- **JSON output**: `in_progress_tasks` is automatically included via
  `asdict()` serialization.

## Clarifications

1. **All task types**: Both coder tasks and non-coder archetype nodes
   (verifier, auditor, skeptic) are included if they have `in_progress`
   status.
2. **Relationship to `active_agents`**: The existing `active_agents` field
   is unchanged. The new `in_progress_tasks` field provides a superset of
   information with full task details.
3. **Format**: Matches standup's Agent Activity exactly — same line format,
   same token formatting, same `_display_node_id()` transformation.
4. **Section placement**: In text output, "Active Tasks" appears as a new
   section before "Cost by Archetype" and after the Tokens line.
5. **Reuse**: `TaskActivity` dataclass and `_compute_task_activities()` logic
   from `reporting/standup.py` are reused. The status report filters to
   only in-progress tasks rather than showing all tasks.
