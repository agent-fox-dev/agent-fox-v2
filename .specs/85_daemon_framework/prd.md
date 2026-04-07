# PRD: Daemon Framework

## Summary

Refactor the existing `night-shift` command into a unified daemon with pluggable
work streams. The daemon subsumes `code --watch` and extends night-shift to
support spec execution, fix pipeline, hunt scans, and spec generation as
independent, concurrent work streams sharing a single cost budget, knowledge DB,
and platform client.

## Motivation

Today, agent-fox has three separate execution modes:

| Command | Behavior | Limitation |
|---------|----------|------------|
| `code` | One-shot spec execution | Exits when done |
| `code --watch` | Polls for new specs after completion | No issue awareness |
| `night-shift` | Polls `af:fix` issues + runs hunt scans | No spec execution |

Users wanting full autonomy must run `code --watch` AND `night-shift`
simultaneously, managing two processes that can't share cost budgets or
coordinate work. There's no pipeline from "GitHub issue" to "spec" to
"implementation" without human intervention at the spec-creation step.

## Goals

1. Single long-running daemon via `night-shift` that runs all work streams.
2. `code --watch` becomes a CLI alias (spec executor only, no fixes/hunts/spec-gen).
3. Each work stream operates independently; failure in one doesn't crash others.
4. Single daemon-level cost budget shared across all streams.
5. PID-based daemon lock prevents concurrent `code` and `plan` runs in the same repo.
6. Graceful degradation when GitHub platform is unavailable.
7. Configurable merge strategy: direct merge to develop (default) or draft PRs.

## Non-Goals

- Web UI or dashboard
- Webhook-driven mode (polling is sufficient)
- PR auto-merge (the fox opens PRs or merges; humans review)
- Auto-restart on crash (user's responsibility)
- Spec generator stream implementation (see spec 86)

## Requirements

### Command & CLI

- The unified command remains `night-shift`.
- `code --watch` becomes an alias for `night-shift --no-fixes --no-hunts --no-spec-gen`.
- CLI flags: `--no-specs`, `--no-fixes`, `--no-hunts`, `--no-spec-gen`, `--auto`.
- Polling intervals, max-cost, and parallel settings are config.toml only (no CLI options).
- `code` (one-shot) and `plan` check the daemon PID file; they refuse to start
  if the daemon is running.

### Work Streams

Four work streams, each on independent timers, running as concurrent asyncio tasks:

1. **Spec Executor**: Polls `.specs/` for new specs. Extracts the hot-load
   polling logic from the orchestrator and calls a fresh `Orchestrator` instance
   per discovered spec batch. Default interval: 60s.
2. **Fix Pipeline**: Polls `af:fix` labeled issues. Existing night-shift
   behavior. Default interval: 900s (15 min).
3. **Hunt Scans**: Runs hunt categories. Existing night-shift behavior.
   Default interval: 14400s (4 hours).
4. **Spec Generator**: Polls `af:spec` labeled issues. New capability
   (implementation deferred to spec 86). Default interval: 300s (5 min).

All streams enabled by default. Configurable via `enabled_streams` in config.toml.

#### Stream Scheduling

Work streams run in parallel as independent asyncio tasks. Within a single
scheduling cycle, the daemon enforces this priority order:

1. **Specs first** — the spec executor runs before other streams begin their cycle.
2. **Fixes second** — `af:fix` issues are processed next.
3. **Remaining streams** — hunt scans and spec generator run concurrently after
   specs and fixes have had their turn.

Each stream sleeps for its configured interval between cycles. The priority
order only governs the initial startup sequence and tie-breaking when multiple
streams wake simultaneously.

### Work Stream Interface

Every work stream implements a common protocol:

- `name: str` — human-readable identifier (e.g. `"spec-executor"`).
- `interval: int` — polling interval in seconds.
- `enabled: bool` — whether this stream is active.
- `async run_once() -> None` — execute one cycle of work. Must be safe to call
  repeatedly. Must report cost consumed back to the shared budget tracker.
- `async shutdown() -> None` — clean up resources (optional, default no-op).

The daemon registers streams at startup and manages their lifecycle. A stream
that raises an exception during `run_once()` is logged and retried on the next
cycle; it does not crash the daemon or other streams.

### Daemon Lifecycle

- On start: write PID file to `.agent-fox/daemon.pid`, emit
  `NIGHT_SHIFT_START` audit event, start all enabled streams.
- On SIGINT (once): complete current operations, shut down gracefully.
- On SIGINT (twice): abort immediately, exit 130.
- On cost limit reached: shut down gracefully.
- On shutdown: remove PID file, emit `NIGHT_SHIFT_START` audit event with
  `"phase": "stop"` payload containing total cost and uptime.

#### PID File Management

The daemon writes its PID to `.agent-fox/daemon.pid` on startup as a plain
integer. Before writing, it checks for an existing PID file:

- If the PID file exists and the process is alive (via `os.kill(pid, 0)`),
  the daemon refuses to start with a clear error message.
- If the PID file exists but the process is dead (stale PID), the daemon
  logs a warning, removes the stale file, and proceeds with startup.
- On shutdown (graceful or cost-limit), the PID file is removed in a
  `finally` block to minimize stale-PID scenarios.
- On crash (unhandled exception), the PID file may remain; the stale-detection
  logic handles this on next startup.

The `code` and `plan` commands check `.agent-fox/daemon.pid` before starting.
If a live daemon process is detected, they exit with an error message directing
the user to stop the daemon first.

### Cost Budget

A single daemon-level cost budget (`max_cost` from the existing
`[night_shift]` config section) is shared across all work streams. Each stream
reports its cost after every `run_once()` cycle. The daemon sums all reported
costs and initiates graceful shutdown when the total reaches the limit.

There are no per-stream cost caps in this spec. The budget is first-come,
first-served across all active streams.

### Merge Strategy

- `merge_strategy = "direct"` (default): auto-merge feature branches into
  develop after successful verification. This is the existing behavior.
- `merge_strategy = "pr"`: create draft pull requests from feature branches
  to develop instead of merging. Requires adding `create_pull_request()` to
  `PlatformProtocol` and implementing it on `GitHubPlatform`.

The `create_pull_request()` method signature:

```
async def create_pull_request(
    title: str,
    body: str,
    head: str,       # feature branch
    base: str,       # target branch (e.g. "develop")
    draft: bool = True,
) -> PullRequestResult
```

Where `PullRequestResult` is a new dataclass with `number: int`, `url: str`,
and `html_url: str`.

### Platform Degradation

- If `platform.type = "none"`: warn, disable fix/hunt/spec-gen streams.
  Spec executor continues on local specs.

## Clarifications

- The existing `NightShiftEngine` is refactored to support pluggable work
  streams, not replaced wholesale.
- The spec executor stream extracts the hot-load polling logic from the
  existing orchestrator watch loop. On each cycle, it calls
  `hot_load_specs()` / `discover_new_specs_gated()` to find new specs,
  then instantiates a fresh `Orchestrator` per discovered batch and runs it
  to completion. It does NOT wrap the orchestrator's built-in `_watch_loop()`.
- The `code` command's `--watch` flag is removed from `code.py`. The
  equivalent functionality is provided by the `night-shift` daemon with
  only the spec executor stream enabled.
- Work streams are implementable incrementally. The framework supports
  registering a stream whose `run_once()` is a no-op stub, so that spec 86
  can plug in the spec generator later without modifying the framework.
- All new configuration values are added to the existing `[night_shift]`
  section in config.toml. No new top-level config section is introduced.
- The `--auto` CLI flag (existing) auto-labels hunt findings with `af:fix`.
  No rename; it keeps its current name.

## Dependencies

None. This is new code that modifies existing modules.

## Scope

This spec covers the daemon framework, work stream abstraction, PID file
management, `create_pull_request()` on the platform protocol, and the
integration of existing capabilities (spec executor, fix pipeline, hunt scans)
into the new architecture. The spec generator stream is defined as a no-op stub
in this spec and implemented in spec 86.
