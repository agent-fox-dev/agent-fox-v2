# Requirements Document

## Introduction

This specification defines the daemon framework for agent-fox v3. The daemon
refactors the existing `night-shift` command into a unified long-running
process with pluggable work streams. It introduces a work stream abstraction,
PID-based daemon locking, a shared cost budget, configurable merge strategy
with draft PR support, and platform degradation handling. Four work streams
(spec executor, fix pipeline, hunt scans, spec generator stub) run as
concurrent asyncio tasks sharing infrastructure.

## Glossary

| Term | Definition |
|------|-----------|
| Work stream | An independent, repeating unit of work registered with the daemon. Each stream has a name, polling interval, and a `run_once()` method that executes one cycle. |
| Daemon | The long-running `night-shift` process that manages work stream lifecycles, cost budget, and signal handling. |
| PID file | A file at `.agent-fox/daemon.pid` containing the process ID of the running daemon, used to prevent concurrent daemon/code/plan runs. |
| Cost budget | A single daemon-level spending limit (`max_cost`) shared across all work streams on a first-come, first-served basis. |
| Merge strategy | Configuration controlling how completed feature branches are landed: `"direct"` (merge to develop) or `"pr"` (create draft pull request). |
| Spec executor | A work stream that polls `.specs/` for new specifications and runs the orchestrator to implement them. |
| Fix pipeline | A work stream that polls for `af:fix` labeled GitHub issues and processes them through the archetype pipeline. |
| Hunt scan | A work stream that runs static/AI analysis categories to discover codebase issues. |
| Spec generator | A work stream (stub in this spec) that polls for `af:spec` labeled issues and generates specifications from them. |
| Graceful shutdown | Completing the current in-progress operation before exiting, triggered by a single SIGINT/SIGTERM. |
| Stale PID | A PID file whose recorded process is no longer alive, typically from a previous daemon crash. |
| Platform | An implementation of `PlatformProtocol` providing issue-tracking operations (e.g., GitHub). |
| `PullRequestResult` | A dataclass returned by `create_pull_request()` containing `number`, `url`, and `html_url` fields. |

## Requirements

### Requirement 1: Work Stream Protocol

**User Story:** As a developer, I want a common work stream interface, so that
new streams can be added without modifying the daemon core.

#### Acceptance Criteria

1. [85-REQ-1.1] THE daemon SHALL define a `WorkStream` protocol with the
   following attributes and methods: `name: str`, `interval: int` (seconds),
   `enabled: bool`, `async run_once() -> None`, and `async shutdown() -> None`.

2. [85-REQ-1.2] WHEN the daemon starts, THE daemon SHALL register all four
   built-in work streams (spec executor, fix pipeline, hunt scans, spec
   generator) AND return the list of registered stream names to the caller
   for logging.

3. [85-REQ-1.3] WHERE a work stream's `enabled` property is False, THE daemon
   SHALL skip that stream during scheduling and not invoke its `run_once()`.

4. [85-REQ-1.4] WHEN a work stream's `run_once()` raises an exception, THE
   daemon SHALL log the error, continue running, and retry the stream on its
   next scheduled cycle.

#### Edge Cases

1. [85-REQ-1.E1] IF a work stream's `run_once()` raises an exception on every
   cycle, THEN THE daemon SHALL continue running other streams without
   interruption.

2. [85-REQ-1.E2] IF all registered work streams have `enabled = False`, THEN
   THE daemon SHALL log a warning and enter an idle loop, responding only to
   shutdown signals.

### Requirement 2: Daemon Lifecycle

**User Story:** As a user, I want a single daemon command that starts, runs,
and shuts down cleanly, so I don't need to manage multiple processes.

#### Acceptance Criteria

1. [85-REQ-2.1] WHEN the daemon starts, THE daemon SHALL write its PID to
   `.agent-fox/daemon.pid` as a plain integer AND emit a `NIGHT_SHIFT_START`
   audit event.

2. [85-REQ-2.2] WHEN a single SIGINT or SIGTERM is received, THE daemon SHALL
   complete the current in-progress `run_once()` invocation and then shut down
   gracefully.

3. [85-REQ-2.3] WHEN a second SIGINT or SIGTERM is received, THE daemon SHALL
   abort immediately with exit code 130.

4. [85-REQ-2.4] WHEN the daemon shuts down (gracefully or via cost limit), THE
   daemon SHALL remove the PID file AND emit a `NIGHT_SHIFT_START` audit event
   with `"phase": "stop"` payload containing `total_cost` and `uptime_seconds`.

5. [85-REQ-2.5] WHEN the daemon shuts down, THE daemon SHALL call `shutdown()`
   on each registered work stream before exiting.

#### Edge Cases

1. [85-REQ-2.E1] IF the PID file exists at startup AND the recorded process is
   alive, THEN THE daemon SHALL refuse to start and exit with code 1 and an
   error message.

2. [85-REQ-2.E2] IF the PID file exists at startup AND the recorded process is
   dead (stale PID), THEN THE daemon SHALL log a warning, remove the stale
   file, and proceed with startup.

3. [85-REQ-2.E3] IF the PID file cannot be written (e.g., permission error),
   THEN THE daemon SHALL exit with code 1 and an error message.

### Requirement 3: PID Lock Enforcement

**User Story:** As a user, I want `code` and `plan` commands to refuse to run
when the daemon is active, so I don't get conflicting concurrent executions.

#### Acceptance Criteria

1. [85-REQ-3.1] WHEN the `code` command starts, THE system SHALL check
   `.agent-fox/daemon.pid` for a live daemon process AND refuse to start with
   a clear error message if one is found.

2. [85-REQ-3.2] WHEN the `plan` command starts, THE system SHALL check
   `.agent-fox/daemon.pid` for a live daemon process AND refuse to start with
   a clear error message if one is found.

#### Edge Cases

1. [85-REQ-3.E1] IF `.agent-fox/daemon.pid` does not exist, THEN THE `code`
   and `plan` commands SHALL proceed normally without error.

2. [85-REQ-3.E2] IF `.agent-fox/daemon.pid` contains a stale PID, THEN THE
   `code` and `plan` commands SHALL proceed normally (they do not clean up
   stale PIDs; only the daemon startup does).

### Requirement 4: Stream Scheduling

**User Story:** As a user, I want work streams to run concurrently with a
defined priority order, so that specs and fixes are processed before hunts.

#### Acceptance Criteria

1. [85-REQ-4.1] THE daemon SHALL run work streams as independent asyncio tasks,
   each sleeping for its configured `interval` between cycles.

2. [85-REQ-4.2] WHEN the daemon starts, THE daemon SHALL launch streams in
   priority order: spec executor first, then fix pipeline, then remaining
   streams (hunt scans, spec generator) concurrently.

3. [85-REQ-4.3] WHEN multiple streams wake simultaneously, THE daemon SHALL
   prioritize execution in the order: spec executor, fix pipeline, hunt scans,
   spec generator.

#### Edge Cases

1. [85-REQ-4.E1] IF the spec executor stream is disabled, THEN THE daemon
   SHALL proceed directly to launching the fix pipeline and remaining streams
   without delay.

### Requirement 5: Shared Cost Budget

**User Story:** As a user, I want a single cost budget across all streams, so
I can control total spending.

#### Acceptance Criteria

1. [85-REQ-5.1] THE daemon SHALL maintain a single cumulative cost counter
   incremented by each work stream after every `run_once()` cycle.

2. [85-REQ-5.2] WHEN the cumulative cost reaches or exceeds the configured
   `max_cost`, THE daemon SHALL initiate graceful shutdown.

3. [85-REQ-5.3] WHILE a work stream's `run_once()` is executing, THE daemon
   SHALL allow other streams to continue running (the budget check occurs
   between cycles, not mid-operation).

#### Edge Cases

1. [85-REQ-5.E1] IF `max_cost` is not configured (None), THEN THE daemon SHALL
   run without a cost limit.

### Requirement 6: CLI Integration

**User Story:** As a user, I want CLI flags to selectively enable/disable
streams and an alias for watch mode.

#### Acceptance Criteria

1. [85-REQ-6.1] THE `night-shift` command SHALL accept `--no-specs`,
   `--no-fixes`, `--no-hunts`, and `--no-spec-gen` flags that disable the
   corresponding work streams.

2. [85-REQ-6.2] THE `code --watch` invocation SHALL behave as an alias for
   `night-shift --no-fixes --no-hunts --no-spec-gen`, running only the spec
   executor stream.

3. [85-REQ-6.3] THE `--auto` flag SHALL auto-label hunt findings with `af:fix`,
   consistent with the existing behavior.

#### Edge Cases

1. [85-REQ-6.E1] IF all four `--no-*` flags are passed simultaneously, THEN
   THE daemon SHALL log a warning and enter an idle loop (same as 85-REQ-1.E2).

### Requirement 7: Platform Degradation

**User Story:** As a user, I want the daemon to continue on local specs when
no platform is configured, so I can use it without GitHub.

#### Acceptance Criteria

1. [85-REQ-7.1] WHEN `platform.type` is `"none"`, THE daemon SHALL log a
   warning, disable the fix pipeline, hunt scans, and spec generator streams,
   and run only the spec executor stream.

#### Edge Cases

1. [85-REQ-7.E1] IF `platform.type` is `"none"` AND the spec executor stream
   is also disabled via `--no-specs`, THEN THE daemon SHALL log a warning and
   enter an idle loop.

### Requirement 8: Merge Strategy

**User Story:** As a user, I want to choose between direct merges and draft
PRs, so I can require human review before code lands.

#### Acceptance Criteria

1. [85-REQ-8.1] WHERE `merge_strategy` is `"direct"` (default), THE daemon
   SHALL auto-merge feature branches into develop after verification, preserving
   the existing behavior.

2. [85-REQ-8.2] WHERE `merge_strategy` is `"pr"`, THE daemon SHALL create a
   draft pull request from the feature branch to develop instead of merging,
   using `PlatformProtocol.create_pull_request()` AND return a `PullRequestResult`
   containing `number`, `url`, and `html_url` to the caller for logging.

3. [85-REQ-8.3] THE `PlatformProtocol` SHALL define a `create_pull_request()`
   method accepting `title: str`, `body: str`, `head: str`, `base: str`, and
   `draft: bool = True`, AND returning a `PullRequestResult`.

4. [85-REQ-8.4] THE `GitHubPlatform` SHALL implement `create_pull_request()`
   using the GitHub REST API to create pull requests.

#### Edge Cases

1. [85-REQ-8.E1] IF `create_pull_request()` fails (API error, auth failure),
   THEN THE daemon SHALL log the error, post a comment on the related issue
   with the branch name for manual PR creation, and continue processing.

2. [85-REQ-8.E2] IF `merge_strategy` has an unrecognized value, THEN THE daemon
   SHALL log a warning and fall back to `"direct"`.

### Requirement 9: Configuration

**User Story:** As a user, I want to configure stream intervals, merge
strategy, and enabled streams in config.toml.

#### Acceptance Criteria

1. [85-REQ-9.1] THE `NightShiftConfig` model SHALL add fields for:
   `spec_interval` (default 60, minimum 10), `spec_gen_interval` (default 300,
   minimum 60), `enabled_streams` (list of stream names, default all four),
   and `merge_strategy` (default `"direct"`, valid values `"direct"` and `"pr"`).

2. [85-REQ-9.2] WHEN a stream name in `enabled_streams` does not match any
   registered stream, THE system SHALL log a warning and ignore the unknown
   entry.

#### Edge Cases

1. [85-REQ-9.E1] IF `spec_interval` is below the minimum (10), THEN THE system
   SHALL clamp it to 10 and log a warning.

2. [85-REQ-9.E2] IF `enabled_streams` is an empty list, THEN THE daemon SHALL
   treat it as "all streams enabled" (empty = default = all).

### Requirement 10: Spec Executor Work Stream

**User Story:** As a user, I want new specs discovered in `.specs/` to be
automatically planned and executed without restarting the daemon.

#### Acceptance Criteria

1. [85-REQ-10.1] WHEN the spec executor's `run_once()` fires, THE stream SHALL
   call `discover_new_specs_gated()` to find new specs AND return the list of
   discovered spec names to the daemon for cost tracking.

2. [85-REQ-10.2] WHEN new specs are discovered, THE spec executor SHALL
   instantiate a fresh `Orchestrator` for the discovered batch and run it to
   completion, reporting the resulting cost to the shared budget.

3. [85-REQ-10.3] WHEN no new specs are discovered, THE spec executor's
   `run_once()` SHALL return without side effects.

#### Edge Cases

1. [85-REQ-10.E1] IF `discover_new_specs_gated()` raises an exception, THEN
   THE spec executor SHALL log the error and return, allowing retry on the next
   cycle.
