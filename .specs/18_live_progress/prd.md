# PRD: Live Progress Line

## Problem

During `agent-fox code`, the user sees the banner and then **nothing** until
execution completes and the final summary is printed. This makes it impossible
to tell whether the fox is working, stuck, or idle -- especially for long
sessions that can run for minutes.

## Solution

Add a single-line live progress indicator that stays on the **last terminal
line** during orchestrator execution. The line shows a spinner animation and
an abbreviated description of the current model/API activity, including which
task is active. The line is overwritten in place (carriage-return, no newline)
so the terminal stays compact.

When the orchestrator has a "real" state change -- a task completing or
failing -- a permanent line is printed above the spinner so the user can see
milestones scrolling up while the spinner continues below.

## Behaviour

### Spinner Line

- Animated spinner character (cycling) followed by activity text.
- Activity text format: `[{task_id}] {tool_name} {abbreviated_arg}`
  - `task_id`: the short node ID (e.g. `03_session:2`)
  - `tool_name`: the SDK tool being invoked (Read, Edit, Bash, Write, etc.)
  - `abbreviated_arg`: first argument shortened (e.g. file paths show only the
    basename, long strings are truncated to ~30 chars).
- When no SDK tool activity is available (e.g. the model is thinking), show
  `[{task_id}] thinking...`.
- Truncated to terminal width; never wraps to a second line.

### Parallel Sessions

- Multiple coding sessions can run concurrently.
- The spinner line shows the **most recent** activity from any active session,
  rotating naturally as events arrive.
- The task ID prefix tells the user which session is active.

### Permanent Lines

- When a task **completes successfully**, print a permanent line:
  `{check_mark} {task_id} done ({duration})`.
- When a task **fails or is blocked**, print a permanent line:
  `{cross_mark} {task_id} {status} ({reason})`.
- Permanent lines scroll above the spinner. The spinner always remains on the
  last line.

### Quiet and Non-TTY

- `--quiet` suppresses all live progress (same as banner suppression).
- When stdout is not a TTY (piped), disable the spinner animation entirely.
  Optionally print task completion lines only (no carriage-return overwriting).

## Clarifications

1. **Content:** The spinner shows tool-level activity with task ID prefix --
   e.g. `[03_session:2] Read config.py`.
2. **Parallel:** Round-robin display of the most recent activity from any
   session.
3. **Permanent events:** Only task completion and failure produce permanent
   lines. Task starts, sync barriers, and cost updates do not.
4. **Path truncation:** File paths should be truncated meaningfully by keeping
   as many trailing path components as fit within `max_len`, prefixed with `…/`.
   For example, `/Users/dev/workspace/project/agent_fox/ui/events.py` with
   `max_len=30` becomes `…/agent_fox/ui/events.py`. If even one parent
   directory plus basename exceeds `max_len`, fall back to basename only.
   This preserves directory context so that two files with the same name in
   different directories remain distinguishable.
5. **Local SDK activity:** When the coding agent SDK performs local operations
   (Read, Write, Edit, Bash, etc.), these are shown on the spinner line with
   their tool name and abbreviated argument, same as model-driven tool calls.
   "Thinking ..." is shown when the model is processing (no tool invocation).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 4 | 2 | Uses AppTheme for styled console output |
| 04_orchestrator | 1 | 2 | Hooks into orchestrator dispatch loop for task events |
| 03_session_and_workspace | 3 | 3 | Hooks into session runner SDK message stream |
| 16_code_command | 1 | 5 | Integrates live progress into `code_cmd` |
