# Requirements Document

## Introduction

This specification defines two changes to the `night-shift` autonomous
maintenance daemon: (1) issue-first ordering that suppresses hunt scans while
open `af:fix` issues exist, and (2) real-time console status output matching
the `code` command's Rich Live display.

## Glossary

- **Hunt scan**: A scheduled scan of the codebase using registered hunt
  categories (linter debt, dead code, etc.) that produces findings and creates
  GitHub issues labelled `af:hunt`.
- **Issue check**: A poll of the platform for open issues labelled `af:fix`,
  followed by triage and processing through the fix pipeline.
- **Fix pipeline**: The three-stage archetype pipeline (skeptic → coder →
  verifier) that processes a single `af:fix` issue on a feature branch.
- **ProgressDisplay**: The existing Rich Live spinner and permanent-line
  display class in `agent_fox.ui.progress` used by the `code` command.
- **LiveAwareHandler**: The logging handler in `agent_fox.core.logging` that
  routes log messages through the Rich console when a Live display is active.
- **Phase**: A top-level engine operation: issue check, hunt scan, or idle.
- **Idle state**: The period between phases when the engine is waiting for a
  timer to elapse.
- **ActivityEvent**: A dataclass representing real-time tool-use activity from
  a coding session (tool name, argument, turn, tokens, archetype).
- **TaskEvent**: A dataclass representing a task state change (completed,
  failed, retry, etc.) with duration and archetype metadata.

## Requirements

### Requirement 1: Issue-First Gate

**User Story:** As an operator, I want night-shift to fix all known issues
before hunting for new ones, so that hunt scans do not rediscover problems
that would have been resolved by pending fixes.

#### Acceptance Criteria

1. [81-REQ-1.1] WHILE open `af:fix` issues exist on the platform, THE engine
   SHALL NOT start a hunt scan.

2. [81-REQ-1.2] WHEN the engine starts, THE engine SHALL run an issue check
   before the first hunt scan AND process all `af:fix` issues returned by that
   check before proceeding to the hunt scan.

3. [81-REQ-1.3] WHEN a hunt scan completes, THE engine SHALL run an immediate
   issue check AND process all `af:fix` issues before allowing the next hunt
   scan to fire.

4. [81-REQ-1.4] WHEN the hunt scan timer elapses and open `af:fix` issues
   exist, THE engine SHALL process all `af:fix` issues first AND THEN run
   the hunt scan.

5. [81-REQ-1.5] WHEN no open `af:fix` issues exist and the hunt scan timer
   has elapsed, THE engine SHALL start a hunt scan immediately.

#### Edge Cases

1. [81-REQ-1.E1] IF the platform API fails during the pre-hunt issue check,
   THEN THE engine SHALL log a warning and proceed with the hunt scan
   (fail-open, matching existing behaviour for issue check failures).

2. [81-REQ-1.E2] IF processing an `af:fix` issue fails, THEN THE engine SHALL
   continue processing remaining issues (existing behaviour) AND still run
   the hunt scan after all issues have been attempted.

3. [81-REQ-1.E3] IF the engine is in `--auto` mode and a hunt scan creates new
   `af:fix` issues, THEN THE engine SHALL process those new issues (via the
   post-hunt issue check per 81-REQ-1.3) before the next hunt scan can fire.

### Requirement 2: Progress Display Integration

**User Story:** As an operator, I want to see real-time status of what
night-shift is doing, so that I can monitor progress without reading log files.

#### Acceptance Criteria

1. [81-REQ-2.1] WHEN night-shift starts, THE CLI command SHALL create a
   `ProgressDisplay` instance and start the Rich Live spinner, using the
   same `AppTheme` and `LiveAwareHandler` integration as the `code` command.

2. [81-REQ-2.2] WHEN night-shift exits (cleanly or via signal), THE CLI
   command SHALL stop the `ProgressDisplay` and print a summary line showing
   scans completed, issues fixed, total cost, and status — matching the
   existing exit output format.

3. [81-REQ-2.3] WHEN a fix session runs an archetype, THE engine SHALL
   forward `ActivityEvent` callbacks from the session runner to the
   `ProgressDisplay`, showing tool name, argument, turn count, tokens,
   and archetype label — identical to the `code` command's display.

4. [81-REQ-2.4] WHEN a fix session archetype completes or fails, THE engine
   SHALL emit a `TaskEvent` to the `ProgressDisplay`, producing a permanent
   line with a check/cross icon, node ID, archetype label, and duration —
   identical to the `code` command's display.

#### Edge Cases

1. [81-REQ-2.E1] IF stdout is not a TTY, THEN THE `ProgressDisplay` SHALL
   disable the Live spinner and print task events as plain lines (existing
   `ProgressDisplay` behaviour — no new code needed).

2. [81-REQ-2.E2] IF the `--quiet` flag is active on the parent CLI group,
   THEN THE `ProgressDisplay` SHALL suppress all output (existing behaviour).

### Requirement 3: Phase Status Lines

**User Story:** As an operator, I want to see permanent status lines when
night-shift transitions between phases, so I know what it is doing at a
glance without reading the spinner.

#### Acceptance Criteria

1. [81-REQ-3.1] WHEN the engine starts an issue check, THE engine SHALL print
   a permanent status line via the `ProgressDisplay` indicating the phase
   (e.g. "Checking for af:fix issues…").

2. [81-REQ-3.2] WHEN the engine starts a hunt scan, THE engine SHALL print
   a permanent status line via the `ProgressDisplay` indicating the phase
   (e.g. "Starting hunt scan…").

3. [81-REQ-3.3] WHEN a hunt scan completes, THE engine SHALL print a permanent
   status line showing the number of findings and issues created.

4. [81-REQ-3.4] WHEN an issue fix completes successfully, THE engine SHALL
   print a permanent status line showing the issue number, title, and
   duration.

5. [81-REQ-3.5] WHEN an issue fix fails, THE engine SHALL print a permanent
   status line showing the issue number and failure indication.

#### Edge Cases

1. [81-REQ-3.E1] IF the `ProgressDisplay` is in quiet mode, THEN THE engine
   SHALL skip all phase status lines (existing quiet-mode behaviour of
   `ProgressDisplay`).

### Requirement 4: Idle State Display

**User Story:** As an operator, I want the spinner to show when the next
action will occur during idle periods, so I know the daemon is alive and
when it will next act.

#### Acceptance Criteria

1. [81-REQ-4.1] WHILE the engine is idle (waiting for a timer to elapse),
   THE spinner SHALL display the time of the next scheduled action in the
   user's local timezone (e.g. "Waiting until 03:42 for next issue check").

2. [81-REQ-4.2] WHEN the engine transitions from idle to active (starting
   an issue check or hunt scan), THE spinner SHALL clear the idle message
   and begin showing activity events.

#### Edge Cases

1. [81-REQ-4.E1] IF both the issue check timer and the hunt scan timer are
   pending, THEN THE spinner SHALL display the earlier of the two
   (whichever fires next).

### Requirement 5: Callback Plumbing

**User Story:** As a developer, I want the engine and fix pipeline to accept
and forward display callbacks, so that real-time activity flows from session
runner to console.

#### Acceptance Criteria

1. [81-REQ-5.1] WHEN the `NightShiftEngine` is constructed, THE constructor
   SHALL accept optional `activity_callback` and `task_callback` parameters
   AND store them for use during fix sessions.

2. [81-REQ-5.2] WHEN the `FixPipeline` runs a session, THE pipeline SHALL
   pass the `activity_callback` to the session runner so that `ActivityEvent`s
   flow from the SDK to the display.

3. [81-REQ-5.3] WHEN the `FixPipeline` completes or fails an archetype
   session, THE pipeline SHALL emit a `TaskEvent` via the `task_callback`
   with the correct node ID, status, duration, and archetype AND return the
   `TaskEvent` to the caller for state tracking.

#### Edge Cases

1. [81-REQ-5.E1] IF callbacks are `None` (not provided), THEN THE engine and
   pipeline SHALL operate without display output (backward-compatible
   default).
