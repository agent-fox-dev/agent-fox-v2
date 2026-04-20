# PRD: Fix Command Progress Display

## Problem

Running `agent-fox code` produces rich, real-time output to stdout that makes
it visible what the system is doing at every moment — a live spinner showing
tool activity (file reads, edits, command execution), permanent milestone lines
when tasks complete or fail, and a final summary. Running `agent-fox fix` is
completely silent during execution; the user sees nothing until the final report
is printed after all work is done. For long-running fix sessions (multiple
passes, each with multiple coding sessions), this silence is frustrating and
gives no indication of progress, phase, or even whether the tool is still
working.

## Goal

Add real-time progress visualization to the `fix` command that is consistent
with the `code` command's output style. The user should see:

1. **Banner** at startup (same fox banner as `code`).
2. **Phase/pass-level progress lines** that make it obvious which phase
   (repair vs improve) and which pass the system is currently executing, and
   what it's doing at a high level (running checks, clustering failures,
   running fix sessions).
3. **Session-level activity** — the same live spinner showing tool-level detail
   (Reading, Editing, Running command, etc.) that `code` displays, wired
   through the existing `activity_callback` parameter on `run_session()`.
4. **Check execution visibility** — when quality checks are running (ruff,
   pytest, etc.), the display should show which check is currently executing.
5. **Quiet/JSON mode suppression** — all progress output is suppressed when
   `--quiet` or `--json` flags are active, consistent with `code`.

## Non-Goals

- Changing the final report format (the existing `render_fix_report` and
  `render_combined_report` functions remain unchanged).
- Adding new CLI flags beyond what already exists.
- Changing the fix loop or improve loop algorithms.

## Clarifications

- **Output style**: Consistent with `code` command — same `ProgressDisplay`
  infrastructure, same spinner, same milestone line format.
- **Banner**: Show the same fox banner as `code` at startup.
- **Phase transitions**: No hard visual divider between phases. Instead, use
  phase-prefixed milestone lines (e.g., `[repair] Pass 1/3: running checks…`)
  so the current phase is always obvious from the output stream.
- **Pass-level progress**: Same approach — milestone lines prefixed with phase
  and pass number flow naturally in the output alongside session activity.
- **Quiet/JSON mode**: Suppress all progress output, matching `code` behavior.
- **Session activity**: Wire the existing `activity_callback` parameter through
  to `ProgressDisplay.on_activity()` so inner coding sessions show tool-level
  detail.
- **Check visibility**: Show which quality check is currently executing, e.g.,
  a spinner line like `Running check: ruff…`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 18_progress_display | — | — | Reuses ProgressDisplay, ActivityEvent, TaskEvent infrastructure (already implemented) |
