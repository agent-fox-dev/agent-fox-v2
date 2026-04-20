# PRD: Night Shift — Issue-First Ordering & Console Status Output

## Problem Statement

The `night-shift` command has two UX gaps:

1. **Ordering**: The engine runs issue checks and hunt scans on independent
   timers. In `--auto` mode this can discover new problems (hunt scan) while
   existing `af:fix` issues remain unresolved. Fixing known issues first is
   preferable because their fixes may resolve problems that hunt scans would
   otherwise (re-)discover.

2. **Visibility**: Unlike the `code` command, `night-shift` produces no
   real-time console output. The operator cannot see what the daemon is
   currently doing — which issue it is fixing, which archetype is running,
   what the next scheduled action is, or how much it has cost so far.

## Proposed Changes

### Change 1: Issue-First Ordering

Suppress hunt scans entirely while any open `af:fix` issues remain. The engine
should:

1. On startup, run an issue check first. If `af:fix` issues exist, process
   them all before running the first hunt scan.
2. After a hunt scan completes (which may create new `af:fix` issues in
   `--auto` mode), run a full issue check and process all `af:fix` issues
   before allowing the next hunt scan.
3. In the timed loop, only start a hunt scan when the hunt interval has elapsed
   **and** no open `af:fix` issues exist. If issues exist when the hunt timer
   fires, process them first, then run the hunt scan.

This ensures that known issues are always resolved before the system looks for
new problems.

### Change 2: Console Status Output

Add real-time console output to `night-shift` that matches the look and feel
of the `code` command. Specifically:

- **Reuse the existing `ProgressDisplay`** (Rich Live spinner + permanent
  lines) from `agent_fox.ui.progress`.
- **Show detailed activity** during fix sessions: which issue is being fixed,
  which archetype (skeptic/coder/verifier) is active, what tool is being used,
  turn count, and token usage — exactly like `code` does.
- **Show phase transitions** as permanent lines: starting issue check, starting
  hunt scan, issue fixed, issue creation, scan complete.
- **Show idle/waiting state** in the spinner: "Waiting until HH:MM for next
  scan" using the user's local timezone.
- **Integrate logging** with the Rich Live display via `LiveAwareHandler`,
  same as `code` does, so log messages render cleanly above the spinner.
- **Print a summary** on exit matching the `code` command's format (tasks done,
  tokens, cost, status).

## Clarifications

1. **"First" means suppression**: Hunt scans are entirely suppressed while any
   `af:fix` issues remain open. This is not just ordering within a single
   cycle — it is a gate.
2. **Post-hunt-scan behavior**: After a hunt scan completes, run an issue check
   immediately. Process all discovered issues before the next hunt scan can
   fire.
3. **Output format**: Match the `code` command's `ProgressDisplay` — Rich Live
   spinner with permanent milestone lines, same styling, same detail level.
4. **Timezone**: Display times in the user's local timezone.
5. **Fix session detail**: Show the same level of detail as `code` — archetype
   labels, tool verbs, turn counts, token usage, duration on completion.
6. **Logging integration**: Use the same `LiveAwareHandler` mechanism as `code`
   so log messages route through the Rich console when the spinner is active.

## Non-Goals

- No changes to hunt scan categories, triage logic, or fix pipeline internals.
- No changes to configuration schema (intervals, category toggles).
- No new CLI flags beyond what already exists.
- No JSON output mode for night-shift (can be added later).
