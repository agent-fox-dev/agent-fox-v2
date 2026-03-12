# Requirements Document: Hooks, Sync Barriers, and Security

## Introduction

This document specifies three related extensibility and safety systems for
agent-fox v2: hook script execution (pre-session, post-session, sync-barrier),
sync barriers with hot-loading of new specifications, and the command allowlist
security system. It depends on core foundation (spec 01) for configuration and
error types, session and workspace (spec 03) for workspace context, and the
orchestrator (spec 04) for execution loop integration.

## Glossary

| Term | Definition |
|------|-----------|
| Hook | A user-configured script that runs at a lifecycle boundary (before a session, after a session, or at a sync barrier) |
| Hook mode | The failure behavior for a hook: "abort" (stop execution) or "warn" (log and continue) |
| Sync barrier | A periodic checkpoint where execution pauses to run barrier hooks, regenerate the knowledge summary, and check for new specifications |
| Hot-loading | The process of discovering and incorporating new specification folders into the task graph during execution without restart |
| Command allowlist | The set of shell commands the coding agent is permitted to execute via the Bash tool |
| PreToolUse hook | A claude-code-sdk callback registered before tool invocations, used here to enforce the command allowlist |
| Hook context | Environment variables passed to hook scripts providing metadata about the current task and workspace |

## Requirements

### Requirement 1: Pre-Session and Post-Session Hooks

**User Story:** As an operator, I want to run custom scripts before and after
each coding session so that I can enforce quality gates, run proprietary
checks, and send notifications at session boundaries.

#### Acceptance Criteria

1. [06-REQ-1.1] WHEN pre-session hooks are configured, THE system SHALL
   execute each hook script in order before the coding session begins, in
   the workspace directory of the current task.

2. [06-REQ-1.2] WHEN post-session hooks are configured, THE system SHALL
   execute each hook script in order after the coding session completes
   (regardless of session outcome), in the workspace directory of the
   current task.

#### Edge Cases

1. [06-REQ-1.E1] IF no pre-session or post-session hooks are configured,
   THEN THE system SHALL proceed directly to the session without error.

---

### Requirement 2: Hook Failure Modes

**User Story:** As an operator, I want to configure whether a hook failure
stops execution or merely logs a warning, so that I can distinguish between
mandatory quality gates and advisory checks.

#### Acceptance Criteria

1. [06-REQ-2.1] WHEN a hook script exits with a non-zero exit code and the
   hook's mode is "abort", THE system SHALL raise a `HookError` identifying
   the failed hook script and its exit code, stopping execution.

2. [06-REQ-2.2] WHEN a hook script exits with a non-zero exit code and the
   hook's mode is "warn", THE system SHALL log a warning with the hook script
   name and exit code, and continue execution.

3. [06-REQ-2.3] WHERE no explicit mode is configured for a hook script, THE
   system SHALL default to "abort" mode.

#### Edge Cases

1. [06-REQ-2.E1] IF a hook script does not exist or is not executable, THEN
   THE system SHALL treat it as a failure and apply the configured mode
   (abort or warn).

---

### Requirement 3: Hook Timeout

**User Story:** As an operator, I want hook scripts to be terminated if they
exceed a timeout, so that a hanging hook does not block execution indefinitely.

#### Acceptance Criteria

1. [06-REQ-3.1] THE system SHALL enforce a configurable timeout (default: 300
   seconds) on each hook script execution using subprocess timeout.

2. [06-REQ-3.2] WHEN a hook script exceeds the timeout, THE system SHALL
   terminate the subprocess and treat the timeout as a hook failure, applying
   the configured mode (abort or warn).

---

### Requirement 4: Hook Context

**User Story:** As an operator writing hook scripts, I want access to
information about the current task so that my scripts can make context-aware
decisions.

#### Acceptance Criteria

1. [06-REQ-4.1] THE system SHALL pass the following environment variables to
   every hook script: `AF_SPEC_NAME` (the current specification name),
   `AF_TASK_GROUP` (the current task group number), `AF_WORKSPACE` (the
   absolute path to the workspace directory), and `AF_BRANCH` (the feature
   branch name).

2. [06-REQ-4.2] FOR sync-barrier hooks, THE system SHALL set `AF_SPEC_NAME`
   to `"__sync_barrier__"` and `AF_TASK_GROUP` to the barrier sequence number,
   since barrier hooks are not associated with a specific task.

---

### Requirement 5: Hook Bypass

**User Story:** As a developer, I want to skip all hooks for a run so that I
can iterate quickly during development without waiting for hooks to execute.

#### Acceptance Criteria

1. [06-REQ-5.1] WHEN the `--no-hooks` flag is passed to the code command, THE
   system SHALL skip all pre-session, post-session, and sync-barrier hook
   scripts for the entire run.

---

### Requirement 6: Sync Barriers

**User Story:** As a developer, I want execution to periodically pause and
synchronize so that the knowledge summary stays current and new specifications
are picked up without restarting.

#### Acceptance Criteria

1. [06-REQ-6.1] AT configurable intervals (default: every 5 completed
   sessions, controlled by `orchestrator.sync_interval`), THE system SHALL
   pause execution and run all configured sync-barrier hook scripts.

2. [06-REQ-6.2] AT each sync barrier, THE system SHALL regenerate the
   human-readable knowledge summary from the current knowledge base.

3. [06-REQ-6.3] AT each sync barrier WHERE hot-loading is enabled, THE system
   SHALL scan `.specs/` for new specification folders not present in the
   current task graph.

#### Edge Cases

1. [06-REQ-6.E1] IF `sync_interval` is set to 0, THEN THE system SHALL not
   trigger sync barriers at all.

---

### Requirement 7: Hot-Loading New Specifications

**User Story:** As a developer, I want new specifications added during a run
to be automatically discovered and incorporated into the plan so that I do not
have to restart to pick them up.

#### Acceptance Criteria

1. [06-REQ-7.1] WHEN new specification folders are discovered at a sync
   barrier, THE system SHALL parse their task definitions using the existing
   spec parser and add the resulting nodes to the task graph.

2. [06-REQ-7.2] WHEN new nodes are added to the task graph, THE system SHALL
   resolve any cross-spec dependencies declared in the new specifications'
   `prd.md` files and add appropriate edges to the graph.

3. [06-REQ-7.3] WHEN new nodes are added, THE system SHALL re-compute the
   topological ordering to incorporate them and persist the updated plan.

#### Edge Cases

1. [06-REQ-7.E1] IF a new specification declares a dependency on a
   specification that does not exist, THEN THE system SHALL log a warning
   and skip the new specification rather than failing the entire run.

2. [06-REQ-7.E2] IF no new specifications are found at a sync barrier, THEN
   THE system SHALL continue execution without modifying the task graph.

---

### Requirement 8: Command Allowlist Enforcement

**User Story:** As an operator, I want to restrict which shell commands the
coding agent can execute so that dangerous operations (e.g., `rm -rf /`,
arbitrary network access) are blocked.

#### Acceptance Criteria

1. [06-REQ-8.1] THE system SHALL register a PreToolUse hook that intercepts
   all Bash tool invocations and extracts the command name (the first
   whitespace-delimited token of the command string, with path prefix
   stripped to basename).

2. [06-REQ-8.2] IF the extracted command is not on the effective allowlist,
   THEN THE hook SHALL block the tool invocation by returning a block
   decision with a message identifying the blocked command and listing
   available alternatives.

3. [06-REQ-8.3] THE default allowlist SHALL contain approximately 35 standard
   development commands: `git`, `python`, `python3`, `uv`, `pip`, `npm`,
   `npx`, `node`, `pytest`, `ruff`, `mypy`, `make`, `cargo`, `go`, `rustc`,
   `gcc`, `ls`, `cat`, `mkdir`, `cp`, `mv`, `rm`, `find`, `grep`, `sed`,
   `awk`, `echo`, `curl`, `wget`, `tar`, `gzip`, `which`, `env`, `printenv`,
   `date`, `head`, `tail`, `wc`, `sort`, `diff`, `touch`, `chmod`, `cd`,
   `pwd`, `test`, `true`, `false`.

#### Edge Cases

1. [06-REQ-8.E1] IF the command string is empty or contains only whitespace,
   THEN THE hook SHALL block the invocation with a descriptive error message.

2. [06-REQ-8.E2] IF the tool invocation is not a Bash tool (e.g., Read,
   Write), THEN THE hook SHALL allow it without inspection.

---

### Requirement 9: Allowlist Configuration

**User Story:** As an operator, I want to customize the command allowlist so
that I can permit project-specific tools or restrict the default set.

#### Acceptance Criteria

1. [06-REQ-9.1] WHERE `security.bash_allowlist` is configured, THE system
   SHALL use it as the complete allowlist, replacing the default list entirely.

2. [06-REQ-9.2] WHERE `security.bash_allowlist_extend` is configured (and
   `bash_allowlist` is not), THE system SHALL use the default allowlist plus
   the additional commands from `bash_allowlist_extend`.

#### Edge Cases

1. [06-REQ-9.E1] IF both `bash_allowlist` and `bash_allowlist_extend` are
   configured, THEN `bash_allowlist` SHALL take precedence and
   `bash_allowlist_extend` SHALL be ignored with a logged warning.
