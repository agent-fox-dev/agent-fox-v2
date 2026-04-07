# Implementation Plan: Daemon Framework

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The daemon framework is implemented in six task groups. Group 1 writes all
failing tests. Groups 2-4 build the implementation bottom-up: core
abstractions first (protocol, PID, config), then the daemon runner and
scheduling, then concrete stream implementations and CLI integration. Group 5
adds platform PR creation and merge strategy. Group 6 is the wiring
verification.

Ordering rationale: PID and config are leaf dependencies with no upstream
requirements. DaemonRunner depends on WorkStream protocol and SharedBudget.
Concrete streams depend on DaemonRunner and the engine. CLI integration
depends on all of the above. PR creation is independent of the daemon core
and can be built in parallel with streams if desired.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_stream.py tests/unit/nightshift/test_pid.py tests/unit/nightshift/test_daemon.py tests/unit/nightshift/test_streams.py tests/unit/nightshift/test_config_daemon.py tests/unit/platform/test_pr_creation.py tests/integration/test_daemon_lifecycle.py tests/property/test_daemon_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/unit/nightshift/test_stream.py` — WorkStream protocol tests
    - Create `tests/unit/nightshift/test_pid.py` — PID file tests
    - Create `tests/unit/nightshift/test_daemon.py` — DaemonRunner + SharedBudget tests
    - Create `tests/unit/nightshift/test_streams.py` — Concrete stream tests
    - Create `tests/unit/nightshift/test_config_daemon.py` — Config extension tests
    - Create `tests/unit/platform/test_pr_creation.py` — PR creation tests
    - Create `tests/integration/test_daemon_lifecycle.py` — Smoke tests
    - Create `tests/property/test_daemon_props.py` — Property tests
    - _Test Spec: TS-85-1 through TS-85-30, TS-85-E1 through TS-85-E16_

  - [x] 1.2 Translate acceptance-criterion tests
    - TS-85-1 through TS-85-30: one test function per entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-85-1 through TS-85-30_

  - [x] 1.3 Translate edge-case tests
    - TS-85-E1 through TS-85-E16: one test function per entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-85-E1 through TS-85-E16_

  - [x] 1.4 Translate property tests
    - TS-85-P1 through TS-85-P7: one property test per entry
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-85-P1 through TS-85-P7_

  - [x] 1.5 Translate integration smoke tests
    - TS-85-SMOKE-1 through TS-85-SMOKE-7: one smoke test per entry
    - Mark with `@pytest.mark.asyncio`
    - _Test Spec: TS-85-SMOKE-1 through TS-85-SMOKE-7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Core abstractions: WorkStream protocol, PID module, config, data types
  - [x] 2.1 Create `nightshift/stream.py` — WorkStream protocol
    - Define `WorkStream` as a `@runtime_checkable` Protocol
    - Properties: `name: str`, `interval: int`, `enabled: bool`
    - Methods: `async run_once() -> None`, `async shutdown() -> None`
    - _Requirements: 85-REQ-1.1_

  - [x] 2.2 Create `nightshift/pid.py` — PID file management
    - `PidStatus` enum: `ALIVE`, `STALE`, `ABSENT`
    - `check_pid_file(pid_path) -> tuple[PidStatus, int | None]`
    - `write_pid_file(pid_path) -> None`
    - `remove_pid_file(pid_path) -> None`
    - Stale detection via `os.kill(pid, 0)` with `ProcessLookupError` handling
    - _Requirements: 85-REQ-2.1, 85-REQ-2.4, 85-REQ-2.E1, 85-REQ-2.E2, 85-REQ-2.E3_

  - [x] 2.3 Extend `nightshift/config.py` — new NightShiftConfig fields
    - Add `spec_interval: int` (default 60, min 10)
    - Add `spec_gen_interval: int` (default 300, min 60)
    - Add `enabled_streams: list[str]` (default all four)
    - Add `merge_strategy: str` (default "direct")
    - Add field validators for clamping spec_interval and spec_gen_interval
    - _Requirements: 85-REQ-9.1, 85-REQ-9.E1, 85-REQ-9.E2_

  - [x] 2.4 Create `PullRequestResult` dataclass in `platform/github.py`
    - Fields: `number: int`, `url: str`, `html_url: str`
    - Frozen dataclass
    - _Requirements: 85-REQ-8.3_

  - [x] 2.5 Create `SharedBudget` and `DaemonState` in `nightshift/daemon.py`
    - `SharedBudget`: `max_cost`, `add_cost()`, `total_cost`, `exceeded`
    - `DaemonState`: cost, sessions, issues, scans, specs, uptime fields
    - _Requirements: 85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_stream.py tests/unit/nightshift/test_pid.py tests/unit/nightshift/test_config_daemon.py -k "TS_85_1 or TS_85_5 or TS_85_10 or TS_85_11 or TS_85_15 or TS_85_16 or TS_85_22 or TS_85_26 or E3 or E4 or E5 or E6 or E7 or E9 or E14 or E15"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_daemon_props.py -k "P1 or P2 or P5"`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 85-REQ-1.1, 85-REQ-2.1, 85-REQ-2.E1-E3, 85-REQ-3.1-E2, 85-REQ-5.1-E1, 85-REQ-9.1-E2 met

- [x] 3. DaemonRunner: lifecycle, scheduling, cost budget, signal handling
  - [x] 3.1 Implement `DaemonRunner.__init__()` and stream registration
    - Accept config, platform, streams, budget, pid_path
    - Filter streams by `enabled` property
    - Log warning for unknown stream names in `enabled_streams`
    - _Requirements: 85-REQ-1.2, 85-REQ-1.3, 85-REQ-9.2_

  - [x] 3.2 Implement `DaemonRunner.run()` — main lifecycle
    - Write PID file on start, emit audit event
    - Launch stream tasks in priority order (specs → fixes → rest)
    - Main loop: check budget.exceeded between cycles, shutdown if exceeded
    - On exit: call shutdown() on all streams, remove PID, emit stop audit
    - `finally` block ensures PID cleanup
    - _Requirements: 85-REQ-2.1, 85-REQ-2.2, 85-REQ-2.4, 85-REQ-2.5, 85-REQ-4.1, 85-REQ-4.2_

  - [x] 3.3 Implement stream task scheduling
    - Each stream runs as `asyncio.create_task` with independent sleep loop
    - Priority ordering at simultaneous wake: use an asyncio.Lock or ordered launch
    - Handle stream exceptions: log and continue (do not cancel task)
    - _Requirements: 85-REQ-4.1, 85-REQ-4.3, 85-REQ-1.4, 85-REQ-1.E1_

  - [x] 3.4 Implement `request_shutdown()` and signal integration
    - Set `_shutting_down` asyncio.Event
    - Stream tasks check event between cycles
    - Idle loop when all streams disabled (wait for shutdown event)
    - _Requirements: 85-REQ-2.2, 85-REQ-2.3, 85-REQ-1.E2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_daemon.py tests/integration/test_daemon_lifecycle.py -k "TS_85_2 or TS_85_3 or TS_85_4 or TS_85_6 or TS_85_7 or TS_85_8 or TS_85_9 or TS_85_12 or TS_85_13 or TS_85_14 or TS_85_17 or TS_85_27 or E1 or E2 or E8 or E10 or SMOKE_1 or SMOKE_5"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_daemon_props.py -k "P3 or P4 or P7"`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 85-REQ-1.2-E2, 85-REQ-2.1-2.5, 85-REQ-4.1-E1, 85-REQ-5.2-5.3 met

- [x] 4. Stream implementations and CLI integration
  - [x] 4.1 Implement `SpecExecutorStream` in `nightshift/streams.py`
    - `run_once()`: call `discover_new_specs_gated()`, build plan, run Orchestrator
    - Report cost to SharedBudget from ExecutionState.total_cost
    - Handle discovery errors gracefully (log and return)
    - No-op when no specs discovered
    - _Requirements: 85-REQ-10.1, 85-REQ-10.2, 85-REQ-10.3, 85-REQ-10.E1_

  - [x] 4.2 Implement `FixPipelineStream` in `nightshift/streams.py`
    - Wrap `NightShiftEngine._drain_issues()`
    - Compute cost delta from `engine.state.total_cost` before/after
    - Report delta to SharedBudget
    - _Requirements: 85-REQ-1.1 (conforms to WorkStream protocol)_

  - [x] 4.3 Implement `HuntScanStream` in `nightshift/streams.py`
    - Wrap `NightShiftEngine._run_hunt_scan()`
    - Compute and report cost delta to SharedBudget
    - _Requirements: 85-REQ-1.1 (conforms to WorkStream protocol)_

  - [x] 4.4 Implement `SpecGeneratorStream` (stub) in `nightshift/streams.py`
    - `run_once()`: no-op (log debug "spec generator not yet implemented")
    - Placeholder for spec 86
    - _Requirements: 85-REQ-1.1 (conforms to WorkStream protocol)_

  - [x] 4.5 Implement platform degradation and CLI integration
    - `build_streams()` factory: create all 4 streams, apply enabled_streams
      config, --no-* flags, platform degradation
    - Platform type "none": disable fix, hunt, spec-gen streams with warning
    - Update `cli/nightshift.py`: add --no-specs, --no-fixes, --no-hunts,
      --no-spec-gen flags; wire DaemonRunner; PID file lifecycle
    - Update `cli/code.py`: add PID check guard; map --watch to daemon alias
    - Update `cli/plan.py`: add PID check guard
    - _Requirements: 85-REQ-6.1, 85-REQ-6.2, 85-REQ-6.3, 85-REQ-6.E1, 85-REQ-7.1, 85-REQ-7.E1, 85-REQ-3.1, 85-REQ-3.2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_streams.py -k "TS_85_18 or TS_85_19 or TS_85_20 or TS_85_21 or TS_85_28 or TS_85_29 or TS_85_30 or E10 or E11 or E16"`
    - [x] Smoke tests pass: `uv run pytest -q tests/integration/test_daemon_lifecycle.py -k "SMOKE_2 or SMOKE_3 or SMOKE_4 or SMOKE_6"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_daemon_props.py -k "P6 or P7"`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 85-REQ-3.*, 85-REQ-6.*, 85-REQ-7.*, 85-REQ-10.* met

- [x] 5. Platform PR creation and merge strategy
  - [x] 5.1 Extend `PlatformProtocol` with `create_pull_request()`
    - Add method signature to protocol: `async def create_pull_request(self, title, body, head, base, draft=True) -> PullRequestResult`
    - _Requirements: 85-REQ-8.3_

  - [x] 5.2 Implement `GitHubPlatform.create_pull_request()`
    - POST to `/repos/{owner}/{repo}/pulls`
    - JSON body: title, body, head, base, draft
    - Parse response into PullRequestResult
    - Raise IntegrationError on API failure
    - _Requirements: 85-REQ-8.4_

  - [x] 5.3 Implement merge strategy wiring
    - Add `resolve_merge_strategy()` helper: validate config value,
      fall back to "direct" on unknown values with warning
    - Wire into fix pipeline and spec executor post-session merge logic
    - On PR creation failure: log error, post comment with branch name
    - _Requirements: 85-REQ-8.1, 85-REQ-8.2, 85-REQ-8.E1, 85-REQ-8.E2_

  - [x] 5.V Verify task group 5
    - [x] Spec tests pass: `uv run pytest -q tests/unit/platform/test_pr_creation.py -k "TS_85_23 or TS_85_24 or TS_85_25 or E12 or E13"`
    - [x] Smoke test passes: `uv run pytest -q tests/integration/test_daemon_lifecycle.py -k "SMOKE_7"`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 85-REQ-8.* met

- [x] 6. Wiring verification

  - [x] 6.1 Trace every execution path from design.md end-to-end
    - Path 1 (daemon startup): verify CLI → PID check → write PID → DaemonRunner → stream launch
    - Path 2 (spec executor): verify stream → discover_new_specs_gated → Orchestrator → cost
    - Path 3 (fix pipeline): verify stream → engine._drain_issues → cost delta
    - Path 4 (hunt scan): verify stream → engine._run_hunt_scan → cost delta
    - Path 5 (shutdown): verify signal → request_shutdown → stream.shutdown() → remove PID
    - Path 6 (PID check): verify code/plan → check_pid_file → exit on ALIVE
    - Path 7 (PR creation): verify platform.create_pull_request → PullRequestResult
    - Confirm no function in any chain is a stub that was never replaced
    - _Requirements: all_

  - [x] 6.2 Verify return values propagate correctly
    - `check_pid_file()` → PidStatus consumed by CLI guards and daemon startup
    - `discover_new_specs_gated()` → list[SpecInfo] consumed by SpecExecutorStream
    - `Orchestrator.run()` → ExecutionState.total_cost consumed by SharedBudget
    - `create_pull_request()` → PullRequestResult consumed by merge strategy handler
    - Grep for callers; confirm none discards the return value
    - _Requirements: all_

  - [x] 6.3 Run the integration smoke tests
    - All TS-85-SMOKE-1 through TS-85-SMOKE-7 pass using real components
    - `uv run pytest -q tests/integration/test_daemon_lifecycle.py -k SMOKE`
    - _Test Spec: TS-85-SMOKE-1 through TS-85-SMOKE-7_

  - [x] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Exception: `SpecGeneratorStream.run_once()` is an intentional stub
      (placeholder for spec 86) — document this
    - Each other hit must be justified or replaced with real implementation
    - _Requirements: all_

  - [x] 6.V Verify wiring group
    - [x] All smoke tests pass: `uv run pytest -q tests/integration/test_daemon_lifecycle.py`
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All existing tests still pass: `make check`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 85-REQ-1.1 | TS-85-1 | 2.1 | tests/unit/nightshift/test_stream.py |
| 85-REQ-1.2 | TS-85-2 | 3.1 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-1.3 | TS-85-3 | 3.1 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-1.4 | TS-85-4 | 3.3 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-1.E1 | TS-85-E1 | 3.3 | tests/integration/test_daemon_lifecycle.py |
| 85-REQ-1.E2 | TS-85-E2 | 3.4 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-2.1 | TS-85-5 | 2.2, 3.2 | tests/unit/nightshift/test_pid.py |
| 85-REQ-2.2 | TS-85-6 | 3.2, 3.4 | tests/integration/test_daemon_lifecycle.py |
| 85-REQ-2.3 | TS-85-7 | 3.4 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-2.4 | TS-85-8 | 3.2 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-2.5 | TS-85-9 | 3.2 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-2.E1 | TS-85-E3 | 2.2 | tests/unit/nightshift/test_pid.py |
| 85-REQ-2.E2 | TS-85-E4 | 2.2 | tests/unit/nightshift/test_pid.py |
| 85-REQ-2.E3 | TS-85-E5 | 2.2 | tests/unit/nightshift/test_pid.py |
| 85-REQ-3.1 | TS-85-10 | 4.5 | tests/unit/nightshift/test_pid.py |
| 85-REQ-3.2 | TS-85-11 | 4.5 | tests/unit/nightshift/test_pid.py |
| 85-REQ-3.E1 | TS-85-E6 | 4.5 | tests/unit/nightshift/test_pid.py |
| 85-REQ-3.E2 | TS-85-E7 | 4.5 | tests/unit/nightshift/test_pid.py |
| 85-REQ-4.1 | TS-85-12 | 3.3 | tests/integration/test_daemon_lifecycle.py |
| 85-REQ-4.2 | TS-85-13 | 3.2 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-4.3 | TS-85-14 | 3.3 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-4.E1 | TS-85-E8 | 3.3 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-5.1 | TS-85-15 | 2.5 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-5.2 | TS-85-16 | 2.5, 3.2 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-5.3 | TS-85-17 | 3.2 | tests/integration/test_daemon_lifecycle.py |
| 85-REQ-5.E1 | TS-85-E9 | 2.5 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-6.1 | TS-85-18 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-6.2 | TS-85-19 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-6.3 | TS-85-20 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-6.E1 | TS-85-E10 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-7.1 | TS-85-21 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-7.E1 | TS-85-E11 | 4.5 | tests/unit/nightshift/test_streams.py |
| 85-REQ-8.1 | TS-85-22 | 5.3 | tests/unit/nightshift/test_config_daemon.py |
| 85-REQ-8.2 | TS-85-23 | 5.3 | tests/unit/platform/test_pr_creation.py |
| 85-REQ-8.3 | TS-85-24 | 5.1 | tests/unit/platform/test_pr_creation.py |
| 85-REQ-8.4 | TS-85-25 | 5.2 | tests/unit/platform/test_pr_creation.py |
| 85-REQ-8.E1 | TS-85-E12 | 5.3 | tests/unit/platform/test_pr_creation.py |
| 85-REQ-8.E2 | TS-85-E13 | 5.3 | tests/unit/platform/test_pr_creation.py |
| 85-REQ-9.1 | TS-85-26 | 2.3 | tests/unit/nightshift/test_config_daemon.py |
| 85-REQ-9.2 | TS-85-27 | 3.1 | tests/unit/nightshift/test_daemon.py |
| 85-REQ-9.E1 | TS-85-E14 | 2.3 | tests/unit/nightshift/test_config_daemon.py |
| 85-REQ-9.E2 | TS-85-E15 | 2.3 | tests/unit/nightshift/test_config_daemon.py |
| 85-REQ-10.1 | TS-85-28 | 4.1 | tests/unit/nightshift/test_streams.py |
| 85-REQ-10.2 | TS-85-29 | 4.1 | tests/integration/test_daemon_lifecycle.py |
| 85-REQ-10.3 | TS-85-30 | 4.1 | tests/unit/nightshift/test_streams.py |
| 85-REQ-10.E1 | TS-85-E16 | 4.1 | tests/unit/nightshift/test_streams.py |
| Property 1 | TS-85-P1 | 2.2 | tests/property/test_daemon_props.py |
| Property 2 | TS-85-P2 | 2.5 | tests/property/test_daemon_props.py |
| Property 3 | TS-85-P3 | 3.3 | tests/property/test_daemon_props.py |
| Property 4 | TS-85-P4 | 3.2 | tests/property/test_daemon_props.py |
| Property 5 | TS-85-P5 | 2.3 | tests/property/test_daemon_props.py |
| Property 6 | TS-85-P6 | 4.5 | tests/property/test_daemon_props.py |
| Property 7 | TS-85-P7 | 4.5 | tests/property/test_daemon_props.py |

## Notes

- **Hypothesis:** Use `suppress_health_check=[HealthCheck.function_scoped_fixture]` in
  all property tests using pytest fixtures.
- **Async tests:** Mark with `@pytest.mark.asyncio` and use `AsyncMock` for
  async method mocks.
- **SpecGeneratorStream:** Intentional stub — document in 6.4 stub audit as
  placeholder for spec 86.
- **Existing engine methods:** `_run_issue_check`, `_drain_issues`,
  `_run_hunt_scan`, `_process_fix` remain in `nightshift/engine.py`.
  Stream wrappers call them; the `run()` timed-loop method is superseded
  by DaemonRunner.
- **PID file permissions:** Use standard `Path.write_text()` — the PID file
  contains only a process ID and is not security-sensitive.
- **Cost delta pattern:** FixPipelineStream and HuntScanStream read
  `engine.state.total_cost` before and after calling engine methods,
  then report the delta to SharedBudget.
