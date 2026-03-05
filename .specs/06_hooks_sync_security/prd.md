# PRD: Hooks, Sync Barriers, and Security

**Source:** `.specs/prd.md` -- Section 5 "Sync Barriers and Hot-Loading"
(REQ-050, REQ-051), "Hooks and Extensibility" (REQ-110 through REQ-114),
"Security" (REQ-130, REQ-131), Section 6 (Configuration: hook timeout, hook
mode, command allowlist, sync interval, hot-loading), Section 8 (Error
Handling: Hook Failures).

## Overview

This spec implements three related extensibility and safety systems for
agent-fox v2: (1) pre-session, post-session, and sync-barrier hook scripts
that let operators run custom validation at lifecycle boundaries,
(2) sync barriers that periodically pause execution to checkpoint, regenerate
the knowledge summary, and discover new specifications, and (3) the command
allowlist security system that restricts which shell commands the coding agent
may execute.

Together these systems give the operator control over quality gates, periodic
synchronization, and safety boundaries without modifying agent-fox core code.

## Problem Statement

Autonomous coding runs can last hours and execute dozens of sessions. Without
hooks, the operator has no way to inject custom validation (e.g., running a
proprietary linter, checking license headers, notifying a dashboard). Without
sync barriers, long runs cannot incorporate new specifications added mid-flight
and accumulate stale knowledge summaries. Without a command allowlist, the
coding agent has unrestricted shell access, creating security risk.

## Goals

- Execute configurable pre-session and post-session hook scripts in the
  workspace context, passing task metadata via environment variables
- Execute sync-barrier hook scripts at configurable intervals during execution
- Support per-hook failure modes: "abort" (stop execution) and "warn" (log and
  continue)
- Enforce configurable hook timeout with subprocess termination
- Provide a `--no-hooks` flag to bypass all hooks for a run
- Pause execution at sync barriers to regenerate the knowledge summary and
  check for new specification folders
- Hot-load new specifications discovered at sync barriers into the task graph
  without restarting
- Enforce a command allowlist on all Bash tool invocations via a claude-code-sdk
  PreToolUse hook
- Provide a default allowlist of approximately 35 standard development commands
- Allow operators to replace or extend the default allowlist via configuration

## Non-Goals

- Running hooks in parallel -- hooks execute sequentially
- Custom hook execution environments (Docker, nix) -- hooks run in the current
  shell
- Modifying existing task graph nodes at sync barriers -- only new specs are
  added
- Runtime command argument inspection beyond the command name -- the allowlist
  checks the first token only
- Per-session allowlist overrides -- the allowlist is global for the run

## Key Decisions

- **Hooks via subprocess:** Hook scripts are arbitrary executables. They run
  as subprocesses with `subprocess.run()`, not as Python callables. This gives
  operators maximum flexibility (bash, Python, Go binaries, etc.) without
  coupling to agent-fox internals.

- **Context via environment variables:** Hook scripts receive task context
  through environment variables (`AF_SPEC_NAME`, `AF_TASK_GROUP`,
  `AF_WORKSPACE`, `AF_BRANCH`). This is the simplest, most portable way to
  pass context to any executable.

- **Abort vs. warn modes:** Each hook script can be configured independently.
  "abort" mode is appropriate for mandatory quality gates (e.g., security
  scans). "warn" mode is appropriate for advisory checks (e.g., notifications,
  optional linters). Default is "abort" to fail safe.

- **Sync barriers as orchestrator checkpoints:** Sync barriers are implemented
  as a check in the orchestrator loop after every N completed sessions. The
  orchestrator pauses, runs barrier hooks, regenerates the memory summary,
  scans for new specs, and then resumes. This is simpler and more predictable
  than event-driven triggers.

- **Hot-loading discovers but does not reorder existing tasks:** New spec
  folders found at sync barriers are parsed and appended to the task graph.
  Existing task ordering is preserved. New nodes are placed after all existing
  nodes unless cross-spec dependencies dictate otherwise.

- **Command allowlist registered as PreToolUse hook:** The claude-code-sdk
  provides a hook system for intercepting tool calls. The allowlist is
  implemented as a `PreToolUse` callback that inspects Bash tool invocations
  and blocks commands not on the list. This is the documented, supported
  mechanism for tool-call filtering.

- **First-token extraction for command matching:** The allowlist checks only
  the first whitespace-delimited token of the command string. This handles
  standard invocations (`git status`, `python -m pytest`) without needing a
  full shell parser. Commands using path prefixes (`/usr/bin/git`) are matched
  against the basename.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 5 | 1 | `AgentFoxConfig`, `HookConfig`, `SecurityConfig`, `OrchestratorConfig`, `HookError`, `SecurityError`, logging |
| 03_session_and_workspace | 5 | 1 | Hook scripts run in the workspace context using `WorkspaceInfo`; security allowlist registers as PreToolUse hook during session execution |
| 04_orchestrator | 6 | 1 | Sync barriers integrate into the orchestrator execution loop; hot-loading modifies the `TaskGraph` managed by the orchestrator |
