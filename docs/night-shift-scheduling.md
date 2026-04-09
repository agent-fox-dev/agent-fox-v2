# Night-Shift Scheduling Reference

How the `night-shift` daemon schedules, orders, and paces its work.

---

## Work Streams

The daemon runs three independent work streams as concurrent asyncio tasks:

| Stream | Config name | Default interval | What it does |
|--------|-------------|------------------|--------------|
| **Spec-Executor** | `specs` | 60 s | Discovers and executes new specs from `.specs/` |
| **Fix-Pipeline** | `fixes` | 900 s (15 min) | Drains `af:fix`-labelled GitHub issues |
| **Hunt-Scan** | `hunts` | 14400 s (4 hrs) | Scans codebase for tech debt, creates `af:hunt` issues |

Each stream wraps a `WorkStream` protocol
(`agent_fox/nightshift/stream.py`) with `name`, `interval`, `enabled`,
`run_once()`, and `shutdown()`.

---

## Launch Order and Priority

Streams are launched in a fixed priority order defined in
`DaemonRunner._PRIORITY_ORDER` (`agent_fox/nightshift/daemon.py:104`):

1. `spec-executor` (highest)
2. `fix-pipeline`
3. `hunt-scan` (lowest)

Priority affects **initial launch order only**. Once all tasks are
created, `asyncio.gather()` runs them concurrently. There is no
runtime preemption.

```
DaemonRunner.run()
  1. Write PID file to .agent-fox/daemon.pid
  2. Emit start audit event
  3. Sort streams by priority, filter to enabled
  4. Create an asyncio.Task per enabled stream (sequential, in priority order)
  5. asyncio.gather(*tasks)  -- all run concurrently from here
  6. On exit: call shutdown() on every registered stream
  7. Remove PID file, emit stop audit event
```

---

## Tick Loop

Each stream task runs in `_run_stream_loop()` with a **0.05-second
tick** (`_TICK = 0.05`):

```
while not shutdown_event:
    stream.run_once()           # execute one cycle
    check budget                # stop if max_cost exceeded
    sleep 0.05s (or until shutdown_event)
```

The `interval` property on each stream is **advisory**. The daemon
does not enforce it -- streams fire `run_once()` on every tick. Actual
pacing comes from the I/O latency of the work itself (LLM calls,
GitHub API).

> **Implication**: a stream whose `run_once()` returns immediately (e.g.
> fix-pipeline finding zero `af:fix` issues) will re-fire every 50 ms.
> This is intentional -- it keeps the daemon responsive. Long-running
> streams (hunt scans, fix sessions) are naturally throttled by their
> own work duration.

---

## Startup Behavior

All streams fire immediately on startup -- there is no initial delay
before the first cycle. The daemon enters the tick loop as soon as
tasks are created, and each task calls `run_once()` immediately.

Typical startup sequence:

```
t=0.00s   PID file written, audit event emitted
t=0.00s   spec-executor task created  -> run_once() fires immediately
t=0.00s   fix-pipeline task created   -> run_once() fires immediately
t=0.00s   hunt-scan task created      -> run_once() fires immediately
          (all three running concurrently via asyncio)
```

---

## Stream Internals

### Spec-Executor (`SpecExecutorStream`)

**Source**: `agent_fox/nightshift/streams.py:42`

Each cycle:
1. Call `discover_fn()` to find new specs in `.specs/`.
2. If specs found, instantiate orchestrator via `orch_factory` and run
   the batch.
3. Report cost delta to `SharedBudget`.

Returns immediately when no specs are discovered.

### Fix-Pipeline (`FixPipelineStream`)

**Source**: `agent_fox/nightshift/streams.py:119`

Each cycle delegates to `NightShiftEngine._drain_issues()`, which loops:

```
_drain_issues()  (max 50 iterations)
  |
  +-> _run_issue_check()
  |     1. Fetch all open af:fix issues (sorted by creation date, oldest first)
  |     2. Local sort fallback by issue number
  |     3. Parse explicit text references (depends on, blocked by, requires)
  |     4. Fetch GitHub cross-references from timeline API
  |     5. If >= 3 issues: run AI batch triage
  |        - Detect dependency edges
  |        - Detect supersession pairs
  |        - Merge edges into global graph
  |     6. Topological sort via Kahn's algorithm (tie-break: issue number)
  |     7. Close superseded issues before processing
  |     8. For each issue in dependency order:
  |        a. _process_fix(issue) -> FixPipeline.process_issue()
  |        b. Update cost & session counters
  |        c. Check staleness of remaining issues
  |        d. Close obsolete issues
  |        e. Break if shutdown/cost/session limit hit
  |
  +-> Re-poll for remaining af:fix issues
  +-> If none remain: drain complete
  +-> If limits hit: drain stops
```

Reports cost delta to `SharedBudget` after each drain cycle.

### Hunt-Scan (`HuntScanStream`)

**Source**: `agent_fox/nightshift/streams.py:172`

Each cycle delegates to `NightShiftEngine._run_hunt_scan()`:

```
_run_hunt_scan()
  1. Check hunt_scan_in_progress flag (skip if already running)
  2. Run HuntScanner with all enabled categories in parallel:
     - linter_debt, dead_code, test_coverage, dependency_freshness,
       deprecated_api, documentation_drift, todo_fixme, quality_gate
  3. Consolidate findings via LLM critic:
     - Grouping (merge by root cause)
     - Validation (drop insufficient evidence)
     - Calibration (adjust severity)
     - Accounting (all findings tracked)
  4. Filter known duplicates using fingerprints
  5. Create GitHub issues from remaining groups (af:hunt label)
  6. If --auto: also assign af:fix label (feeds into fix-pipeline)
  7. Increment hunt_scans_completed counter
```

Overlap prevention: if a hunt scan is already in progress when
`run_once()` fires again, the overlapping invocation is skipped with a
log message.

---

## Fix Pipeline Detail

Each `af:fix` issue goes through a three-stage pipeline in an isolated
git worktree (`agent_fox/nightshift/fix_pipeline.py`):

```
process_issue(issue)
  1. Reject empty issue body (post comment, return)
  2. Build in-memory spec from issue (title, body, branch name)
  3. Create isolated worktree: fix/{sanitized-slug}
  4. Post "Starting fix session..." comment
  5. Triage session (archetype: "triage")
     - Parse structured output -> TriageResult (criteria, affected files)
     - Post triage report comment
  6. Coder-reviewer loop (max_retries + 1 attempts):
     a. Coder session (archetype: "coder")
        - Includes triage criteria in system prompt
        - On retry: includes previous reviewer feedback in task prompt
        - On escalation: model tier bumps (STANDARD -> ADVANCED)
     b. Reviewer session (archetype: "fix_reviewer")
        - Verifies each acceptance criterion
        - Produces JSON verdict (PASS/FAIL per criterion)
        - On parse failure: retry reviewer once
     c. Post review comment
     d. If PASS: exit loop (success)
     e. If FAIL: record failure in EscalationLadder, loop
  7. Harvest fix branch into develop, push to origin
  8. Close issue with completion comment
  9. Remove af:fix label
  10. Destroy worktree
```

The escalation ladder (`retries_before_escalation`, default 1) controls
how many failures at the current tier before bumping the model. The
`max_retries` setting (default 3) caps total retry attempts.

---

## Enabling and Disabling Streams

Three layers of filtering determine which streams run:

1. **Config** (`[night_shift] enabled_streams`): list of config names.
   Empty list = all enabled.
2. **CLI flags**: `--no-specs`, `--no-fixes`, `--no-hunts` disable
   individual streams.
3. **Platform degradation**: if `platform.type = "none"`, fix-pipeline
   and hunt-scan are auto-disabled (they require GitHub).

The final enabled set is the intersection of config and CLI, minus any
platform-degraded streams.

```
final_enabled = (config_enabled & cli_enabled) - platform_degraded
```

---

## Cost and Session Limits

### SharedBudget

A single `SharedBudget` instance is shared across all streams
(`agent_fox/nightshift/daemon.py:36`). Cost is accumulated on a
first-come, first-served basis -- no per-stream allocation.

The budget is checked **between tick cycles** (after each `run_once()`),
not mid-operation. When exceeded, `DaemonRunner` sets the shutdown event
and all streams stop after their current cycle.

### Engine-Level Checks

`NightShiftEngine` performs its own checks between issue fixes
(`agent_fox/nightshift/engine.py:80`):

- **Cost limit**: triggers when remaining budget < 50% of `max_cost`
  (conservative headroom to prevent overspending).
- **Session limit**: triggers when `total_sessions >= max_sessions`.

These are checked between issues within a drain iteration, providing
finer-grained control than the daemon-level budget check.

---

## Signal Handling and Shutdown

**Source**: `agent_fox/cli/nightshift.py:136`

| Signal | Behavior |
|--------|----------|
| First SIGINT/SIGTERM | Graceful: sets shutdown event, current operations complete, exit 0 |
| Second SIGINT | Immediate abort: `sys.exit(130)` |

Shutdown sequence:

```
1. DaemonRunner._shutdown_event is set
2. Each stream task's _run_stream_loop() detects event after current run_once()
3. All asyncio tasks complete via gather()
4. DaemonRunner calls shutdown() on all registered streams
5. PID file removed
6. Stop audit event emitted
7. Platform connection closed
8. Final stats printed (scans completed, issues fixed, total cost)
```

---

## Configuration Reference

All timing parameters live under `[night_shift]` in `config.toml`:

```toml
[night_shift]
issue_check_interval = 900     # seconds, minimum 60
hunt_scan_interval = 14400     # seconds, minimum 60
spec_interval = 60             # seconds, minimum 10
enabled_streams = ["specs", "fixes", "hunts"]  # empty = all
merge_strategy = "direct"      # "direct" or "pr"

[night_shift.categories]
dependency_freshness = true
todo_fixme = true
test_coverage = true
deprecated_api = true
linter_debt = true
dead_code = true
documentation_drift = true
quality_gate = true

[orchestrator]
max_cost = 50.0                # USD limit (optional, omit for unlimited)
max_sessions = 100             # session count limit (optional)
max_retries = 3                # coder-reviewer retry cap
retries_before_escalation = 1  # failures before model tier bump
```

Minimum values are enforced via Pydantic validators in
`NightShiftConfig` (`agent_fox/nightshift/config.py`). Values below the
minimum are clamped up with a warning.

---

## CLI Flags

```
agent-fox night-shift [OPTIONS]

  --auto       Auto-assign af:fix to every hunt issue (autonomous loop)
  --no-specs   Disable spec-executor stream
  --no-fixes   Disable fix-pipeline stream
  --no-hunts   Disable hunt-scan stream
```

Exit codes: 0 (clean shutdown), 1 (startup failure), 130 (double SIGINT).

---

## Timeline Example

A typical `--auto` session with default intervals:

```
t=0s       Daemon starts. All three streams fire immediately.
           - Spec-executor: discovers 0 specs, returns
           - Fix-pipeline: polls GitHub, finds 0 af:fix issues, returns
           - Hunt-scan: begins scanning 8 categories in parallel

t~120s     Hunt scan completes. Creates 3 af:hunt issues, assigns af:fix.

t~120s     Fix-pipeline (on next tick): picks up 3 af:fix issues.
           - AI batch triage (>= 3 issues): dependency + supersession analysis
           - Topological sort -> processing order
           - Issue #1: triage -> coder -> reviewer -> PASS -> harvest
           - Staleness check: issue #3 marked obsolete, closed
           - Issue #2: triage -> coder -> reviewer -> FAIL
             - Retry with feedback: coder -> reviewer -> PASS -> harvest
           - Re-poll: 0 af:fix issues remain. Drain complete.

t~900s     Fix-pipeline fires again (nothing to do, returns immediately)
t~14400s   Hunt-scan fires again (next 4-hour cycle)
```

---

*See also: [Night-Shift Architecture](architecture/04-night-shift.md)*
