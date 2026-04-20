# Test Specification: Daemon Framework

## Overview

Tests validate the daemon framework against 10 requirements covering the work
stream protocol, daemon lifecycle, PID locking, stream scheduling, cost budget,
CLI integration, platform degradation, merge strategy, configuration, and the
spec executor stream. Tests are organized as unit tests for individual modules,
property tests for invariants, edge-case tests for error paths, and integration
smoke tests for end-to-end execution paths.

Test files follow the project convention:
- `tests/unit/nightshift/test_stream.py` — WorkStream protocol
- `tests/unit/nightshift/test_pid.py` — PID file management
- `tests/unit/nightshift/test_daemon.py` — DaemonRunner + SharedBudget
- `tests/unit/nightshift/test_streams.py` — Concrete stream implementations
- `tests/unit/nightshift/test_config_daemon.py` — Config extensions
- `tests/unit/platform/test_pr_creation.py` — PullRequestResult + create_pull_request
- `tests/integration/test_daemon_lifecycle.py` — Smoke tests
- `tests/property/test_daemon_props.py` — Property tests

## Test Cases

### TS-85-1: WorkStream protocol attributes

**Requirement:** 85-REQ-1.1
**Type:** unit
**Description:** Verify that WorkStream protocol requires name, interval, enabled, run_once, shutdown.

**Preconditions:**
- A concrete class implementing all WorkStream attributes and methods.
- A class missing one required attribute.

**Input:**
- Complete implementation class.
- Incomplete implementation class (missing `run_once`).

**Expected:**
- Complete class passes `isinstance(obj, WorkStream)` check.
- Incomplete class fails `isinstance(obj, WorkStream)` check.

**Assertion pseudocode:**
```
complete = CompleteStream()
incomplete = IncompleteStream()
ASSERT isinstance(complete, WorkStream) == True
ASSERT isinstance(incomplete, WorkStream) == False
ASSERT complete.name == "test"
ASSERT complete.interval == 60
ASSERT complete.enabled == True
```

### TS-85-2: Daemon registers all four built-in streams

**Requirement:** 85-REQ-1.2
**Type:** unit
**Description:** Verify that DaemonRunner registers all four stream types and returns their names.

**Preconditions:**
- Four mock WorkStream instances with distinct names.

**Input:**
- `DaemonRunner(config, platform, [spec_stream, fix_stream, hunt_stream, gen_stream], budget)`

**Expected:**
- Runner's registered stream list contains exactly 4 entries.
- Stream names are `["spec-executor", "fix-pipeline", "hunt-scan", "spec-generator"]`.

**Assertion pseudocode:**
```
runner = DaemonRunner(config, platform, streams, budget)
ASSERT len(runner.streams) == 4
ASSERT [s.name for s in runner.streams] == ["spec-executor", "fix-pipeline", "hunt-scan", "spec-generator"]
```

### TS-85-3: Disabled stream is skipped

**Requirement:** 85-REQ-1.3
**Type:** unit
**Description:** Verify that a stream with enabled=False is not invoked during a run cycle.

**Preconditions:**
- Two streams: one enabled, one disabled.

**Input:**
- Run DaemonRunner for one cycle then shutdown.

**Expected:**
- Enabled stream's `run_once()` called at least once.
- Disabled stream's `run_once()` never called.

**Assertion pseudocode:**
```
enabled_stream = MockStream(enabled=True)
disabled_stream = MockStream(enabled=False)
runner = DaemonRunner(config, platform, [enabled_stream, disabled_stream], budget)
# Run briefly then shutdown
await run_one_cycle(runner)
ASSERT enabled_stream.run_once.call_count >= 1
ASSERT disabled_stream.run_once.call_count == 0
```

### TS-85-4: Stream exception does not crash daemon

**Requirement:** 85-REQ-1.4
**Type:** unit
**Description:** Verify that an exception in run_once() is caught and the stream retries next cycle.

**Preconditions:**
- A stream whose run_once() raises RuntimeError on first call, succeeds on second.

**Input:**
- Run DaemonRunner for two cycles.

**Expected:**
- First cycle: exception logged, daemon continues.
- Second cycle: run_once() called again and succeeds.

**Assertion pseudocode:**
```
stream = MockStream(side_effect=[RuntimeError("fail"), None])
runner = DaemonRunner(config, platform, [stream], budget)
await run_two_cycles(runner)
ASSERT stream.run_once.call_count == 2
```

### TS-85-5: PID file written on startup

**Requirement:** 85-REQ-2.1
**Type:** unit
**Description:** Verify that the daemon writes its PID to the PID file on startup.

**Preconditions:**
- Temp directory with no existing PID file.

**Input:**
- `write_pid_file(pid_path)`

**Expected:**
- PID file exists and contains current process PID as plain integer.

**Assertion pseudocode:**
```
write_pid_file(pid_path)
content = pid_path.read_text().strip()
ASSERT content == str(os.getpid())
```

### TS-85-6: Graceful shutdown on single SIGINT

**Requirement:** 85-REQ-2.2
**Type:** integration
**Description:** Verify that a single SIGINT triggers graceful shutdown after current operation completes.

**Preconditions:**
- DaemonRunner with a mock stream whose run_once() takes 0.1s.

**Input:**
- Send SIGINT to the DaemonRunner after run_once() has started.

**Expected:**
- run_once() completes (not interrupted mid-execution).
- DaemonRunner exits after stream finishes.

**Assertion pseudocode:**
```
stream = SlowMockStream(duration=0.1)
runner = DaemonRunner(config, platform, [stream], budget)
task = asyncio.create_task(runner.run())
await asyncio.sleep(0.05)  # mid-operation
runner.request_shutdown()
state = await task
ASSERT stream.run_once.call_count >= 1
ASSERT stream.shutdown.call_count == 1
```

### TS-85-7: Double SIGINT exits with 130

**Requirement:** 85-REQ-2.3
**Type:** unit
**Description:** Verify that a second SIGINT causes immediate exit with code 130.

**Preconditions:**
- Signal handler installed.

**Input:**
- Two SIGINT signals in rapid succession.

**Expected:**
- SystemExit(130) raised on second signal.

**Assertion pseudocode:**
```
handler = DaemonSignalHandler(runner)
handler.handle_signal(SIGINT)  # first: graceful
ASSERT runner.is_shutting_down == True
with ASSERT_RAISES(SystemExit, code=130):
    handler.handle_signal(SIGINT)  # second: abort
```

### TS-85-8: PID file removed on shutdown

**Requirement:** 85-REQ-2.4
**Type:** unit
**Description:** Verify that PID file is removed and stop audit event emitted on shutdown.

**Preconditions:**
- PID file exists.

**Input:**
- DaemonRunner completes a graceful shutdown.

**Expected:**
- PID file no longer exists.
- Audit event emitted with phase="stop", total_cost, uptime_seconds.

**Assertion pseudocode:**
```
write_pid_file(pid_path)
runner = DaemonRunner(config, platform, [], budget)
runner.request_shutdown()
state = await runner.run()
ASSERT NOT pid_path.exists()
ASSERT state.uptime_seconds >= 0
```

### TS-85-9: Stream shutdown called on exit

**Requirement:** 85-REQ-2.5
**Type:** unit
**Description:** Verify that shutdown() is called on each registered stream.

**Preconditions:**
- Two mock streams registered.

**Input:**
- DaemonRunner shutdown sequence.

**Expected:**
- Both streams' shutdown() called exactly once.

**Assertion pseudocode:**
```
s1 = MockStream()
s2 = MockStream()
runner = DaemonRunner(config, platform, [s1, s2], budget)
runner.request_shutdown()
await runner.run()
ASSERT s1.shutdown.call_count == 1
ASSERT s2.shutdown.call_count == 1
```

### TS-85-10: code command blocked by live daemon

**Requirement:** 85-REQ-3.1
**Type:** unit
**Description:** Verify that code command exits with error when daemon PID is alive.

**Preconditions:**
- PID file contains current process PID (simulating live daemon).

**Input:**
- check_pid_file() returns ALIVE.

**Expected:**
- code command exits with code 1.

**Assertion pseudocode:**
```
write_pid_file(pid_path)  # current PID = alive
status, pid = check_pid_file(pid_path)
ASSERT status == PidStatus.ALIVE
ASSERT pid == os.getpid()
```

### TS-85-11: plan command blocked by live daemon

**Requirement:** 85-REQ-3.2
**Type:** unit
**Description:** Verify that plan command exits with error when daemon PID is alive.

**Preconditions:**
- PID file contains current process PID.

**Input:**
- check_pid_file() returns ALIVE.

**Expected:**
- plan command exits with code 1.

**Assertion pseudocode:**
```
write_pid_file(pid_path)
status, pid = check_pid_file(pid_path)
ASSERT status == PidStatus.ALIVE
```

### TS-85-12: Streams run as independent asyncio tasks

**Requirement:** 85-REQ-4.1
**Type:** integration
**Description:** Verify that streams run concurrently, not sequentially.

**Preconditions:**
- Two streams each with 0.1s run_once() duration and 0.0s interval.

**Input:**
- Run DaemonRunner, observe concurrent execution.

**Expected:**
- Both streams execute within ~0.1s (not ~0.2s if sequential).

**Assertion pseudocode:**
```
s1 = SlowMockStream(duration=0.1)
s2 = SlowMockStream(duration=0.1)
runner = DaemonRunner(config, platform, [s1, s2], budget)
start = time.monotonic()
# run one cycle then shutdown
elapsed = time.monotonic() - start
ASSERT elapsed < 0.15  # concurrent, not sequential
```

### TS-85-13: Stream startup priority order

**Requirement:** 85-REQ-4.2
**Type:** unit
**Description:** Verify streams launch in priority order: specs, fixes, then remaining.

**Preconditions:**
- Four streams with names matching the four built-in types.

**Input:**
- DaemonRunner startup.

**Expected:**
- Spec executor launched first, fix pipeline second, hunt/gen after.

**Assertion pseudocode:**
```
launch_order = []
# Each stream records launch time
runner = DaemonRunner(config, platform, [spec, fix, hunt, gen], budget)
await run_briefly(runner)
ASSERT launch_order == ["spec-executor", "fix-pipeline", "hunt-scan", "spec-generator"]
```

### TS-85-14: Simultaneous wake priority

**Requirement:** 85-REQ-4.3
**Type:** unit
**Description:** Verify that when multiple streams wake at the same time, they execute in priority order.

**Preconditions:**
- All four streams with interval=1 (wake simultaneously).

**Input:**
- Run DaemonRunner until all streams have fired once.

**Expected:**
- Execution order matches priority: spec-executor, fix-pipeline, hunt-scan, spec-generator.

**Assertion pseudocode:**
```
execution_order = []
# Streams record their name on run_once()
runner = DaemonRunner(config, platform, streams, budget)
await run_one_cycle(runner)
ASSERT execution_order == ["spec-executor", "fix-pipeline", "hunt-scan", "spec-generator"]
```

### TS-85-15: Shared cost accumulation

**Requirement:** 85-REQ-5.1
**Type:** unit
**Description:** Verify that SharedBudget accumulates cost from multiple streams.

**Preconditions:**
- SharedBudget with max_cost=10.0.

**Input:**
- `add_cost(3.0)`, `add_cost(4.5)`.

**Expected:**
- `total_cost == 7.5`.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=10.0)
budget.add_cost(3.0)
budget.add_cost(4.5)
ASSERT budget.total_cost == 7.5
ASSERT budget.exceeded == False
```

### TS-85-16: Cost limit triggers shutdown

**Requirement:** 85-REQ-5.2
**Type:** unit
**Description:** Verify that exceeding max_cost triggers daemon shutdown.

**Preconditions:**
- SharedBudget with max_cost=5.0.
- Stream whose run_once() adds cost=6.0.

**Input:**
- Run DaemonRunner for one cycle.

**Expected:**
- Budget.exceeded is True.
- DaemonRunner initiates shutdown after the cycle completes.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=5.0)
budget.add_cost(6.0)
ASSERT budget.exceeded == True
```

### TS-85-17: Cost check between cycles, not mid-operation

**Requirement:** 85-REQ-5.3
**Type:** integration
**Description:** Verify that a stream's run_once() is not interrupted when cost exceeds limit mid-cycle.

**Preconditions:**
- SharedBudget with max_cost=1.0.
- Stream whose run_once() adds cost 2.0 during execution.

**Input:**
- Run DaemonRunner.

**Expected:**
- run_once() completes fully (not interrupted).
- Shutdown happens after the cycle, not during.

**Assertion pseudocode:**
```
stream = CostlyStream(cost=2.0)
budget = SharedBudget(max_cost=1.0)
runner = DaemonRunner(config, platform, [stream], budget)
state = await runner.run()
ASSERT stream.run_once_completed == True
ASSERT budget.exceeded == True
```

### TS-85-18: CLI --no-specs disables spec executor

**Requirement:** 85-REQ-6.1
**Type:** unit
**Description:** Verify that --no-specs flag disables the spec executor stream.

**Preconditions:**
- Night-shift CLI with --no-specs flag.

**Input:**
- Parse CLI args: `["--no-specs"]`.

**Expected:**
- Spec executor stream has enabled=False.
- Other streams have enabled=True.

**Assertion pseudocode:**
```
streams = build_streams(config, no_specs=True, no_fixes=False, no_hunts=False, no_spec_gen=False)
spec_stream = find_stream(streams, "spec-executor")
ASSERT spec_stream.enabled == False
ASSERT find_stream(streams, "fix-pipeline").enabled == True
```

### TS-85-19: code --watch alias

**Requirement:** 85-REQ-6.2
**Type:** unit
**Description:** Verify that code --watch behaves as night-shift with only spec executor enabled.

**Preconditions:**
- code command with --watch flag.

**Input:**
- `code_cmd(watch=True)`.

**Expected:**
- Internally invokes daemon with no_fixes=True, no_hunts=True, no_spec_gen=True.

**Assertion pseudocode:**
```
# Verify the alias maps correctly
streams = build_streams_for_watch_mode(config)
enabled = [s for s in streams if s.enabled]
ASSERT len(enabled) == 1
ASSERT enabled[0].name == "spec-executor"
```

### TS-85-20: --auto flag labels hunt findings

**Requirement:** 85-REQ-6.3
**Type:** unit
**Description:** Verify that --auto flag is passed through to the hunt scan stream.

**Preconditions:**
- Night-shift CLI with --auto flag.

**Input:**
- Parse CLI args: `["--auto"]`.

**Expected:**
- Hunt scan stream configured with auto_fix=True.

**Assertion pseudocode:**
```
streams = build_streams(config, auto=True)
hunt_stream = find_stream(streams, "hunt-scan")
ASSERT hunt_stream.auto_fix == True
```

### TS-85-21: Platform none disables platform-dependent streams

**Requirement:** 85-REQ-7.1
**Type:** unit
**Description:** Verify that platform.type="none" disables fix, hunt, and spec-gen streams.

**Preconditions:**
- Config with platform.type = "none".

**Input:**
- Build streams with no-platform config.

**Expected:**
- Only spec executor is enabled.
- Fix, hunt, spec-gen are disabled.

**Assertion pseudocode:**
```
config = make_config(platform_type="none")
streams = build_streams(config)
enabled_names = [s.name for s in streams if s.enabled]
ASSERT enabled_names == ["spec-executor"]
```

### TS-85-22: Direct merge strategy (default)

**Requirement:** 85-REQ-8.1
**Type:** unit
**Description:** Verify that merge_strategy="direct" preserves existing merge behavior.

**Preconditions:**
- Config with merge_strategy="direct".

**Input:**
- Read merge_strategy from config.

**Expected:**
- `config.night_shift.merge_strategy == "direct"`.

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.merge_strategy == "direct"
```

### TS-85-23: Draft PR creation

**Requirement:** 85-REQ-8.2
**Type:** unit
**Description:** Verify that merge_strategy="pr" calls create_pull_request() and returns PullRequestResult.

**Preconditions:**
- Mock platform with create_pull_request() returning PullRequestResult.

**Input:**
- `platform.create_pull_request("title", "body", "fix/123", "develop", draft=True)`

**Expected:**
- Returns PullRequestResult with number, url, html_url.

**Assertion pseudocode:**
```
platform = MockPlatform()
platform.create_pull_request.return_value = PullRequestResult(42, "https://api...", "https://github.com/...")
result = await platform.create_pull_request("title", "body", "fix/123", "develop")
ASSERT result.number == 42
ASSERT result.html_url == "https://github.com/..."
```

### TS-85-24: PlatformProtocol has create_pull_request

**Requirement:** 85-REQ-8.3
**Type:** unit
**Description:** Verify that PlatformProtocol defines create_pull_request method.

**Preconditions:**
- Class implementing PlatformProtocol including create_pull_request.

**Input:**
- isinstance check against PlatformProtocol.

**Expected:**
- Class with create_pull_request passes isinstance check.
- Class without create_pull_request fails.

**Assertion pseudocode:**
```
class WithPR:
    # implements all methods including create_pull_request
    ...
ASSERT isinstance(WithPR(), PlatformProtocol) == True
```

### TS-85-25: GitHubPlatform.create_pull_request API call

**Requirement:** 85-REQ-8.4
**Type:** unit
**Description:** Verify GitHubPlatform.create_pull_request sends correct API request.

**Preconditions:**
- Mock httpx client returning 201 with PR JSON.

**Input:**
- `github.create_pull_request("Fix bug", "body", "fix/42", "develop", draft=True)`

**Expected:**
- POST to `/repos/{owner}/{repo}/pulls` with correct JSON body.
- Returns PullRequestResult with correct fields.

**Assertion pseudocode:**
```
# Mock httpx response
mock_response = {"number": 99, "url": "https://api...", "html_url": "https://github.com/..."}
github = GitHubPlatform("owner", "repo", "token")
result = await github.create_pull_request("Fix bug", "body", "fix/42", "develop")
ASSERT result.number == 99
ASSERT httpx_mock.last_request.method == "POST"
ASSERT "fix/42" in httpx_mock.last_request.json()["head"]
```

### TS-85-26: NightShiftConfig new fields defaults

**Requirement:** 85-REQ-9.1
**Type:** unit
**Description:** Verify new config fields have correct defaults.

**Preconditions:**
- Default NightShiftConfig instance.

**Input:**
- `NightShiftConfig()`

**Expected:**
- spec_interval=60, spec_gen_interval=300
- enabled_streams=["specs", "fixes", "hunts", "spec_gen"]
- merge_strategy="direct"

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.spec_interval == 60
ASSERT config.spec_gen_interval == 300
ASSERT config.enabled_streams == ["specs", "fixes", "hunts", "spec_gen"]
ASSERT config.merge_strategy == "direct"
```

### TS-85-27: Unknown stream name in enabled_streams

**Requirement:** 85-REQ-9.2
**Type:** unit
**Description:** Verify that unknown stream names are logged and ignored.

**Preconditions:**
- Config with enabled_streams=["specs", "unknown_stream"].

**Input:**
- Build streams from config.

**Expected:**
- "unknown_stream" ignored (warning logged).
- Only "specs" stream is enabled.

**Assertion pseudocode:**
```
config = NightShiftConfig(enabled_streams=["specs", "unknown_stream"])
streams = build_streams(config)
enabled = [s for s in streams if s.enabled]
ASSERT len(enabled) == 1
ASSERT enabled[0].name == "spec-executor"
```

### TS-85-28: Spec executor discovers new specs

**Requirement:** 85-REQ-10.1
**Type:** unit
**Description:** Verify spec executor calls discover_new_specs_gated and returns discovered names.

**Preconditions:**
- Mock discover_new_specs_gated returning two SpecInfo objects.

**Input:**
- `spec_executor.run_once()`

**Expected:**
- discover_new_specs_gated called once.
- Discovered spec names available for logging.

**Assertion pseudocode:**
```
mock_discover = AsyncMock(return_value=[SpecInfo("new_spec", ...)])
spec_executor = SpecExecutorStream(config, mock_discover, budget)
await spec_executor.run_once()
ASSERT mock_discover.call_count == 1
```

### TS-85-29: Spec executor runs orchestrator for discovered batch

**Requirement:** 85-REQ-10.2
**Type:** integration
**Description:** Verify that discovered specs trigger a fresh Orchestrator run with cost reporting.

**Preconditions:**
- Mock discover returning specs; mock Orchestrator returning ExecutionState with cost=2.5.

**Input:**
- `spec_executor.run_once()`

**Expected:**
- Orchestrator instantiated and run() called.
- budget.add_cost(2.5) called.

**Assertion pseudocode:**
```
mock_orch = MockOrchestrator(result_cost=2.5)
spec_executor = SpecExecutorStream(config, mock_discover, budget, orch_factory=lambda: mock_orch)
await spec_executor.run_once()
ASSERT mock_orch.run.call_count == 1
ASSERT budget.total_cost == 2.5
```

### TS-85-30: Spec executor no-op when no specs found

**Requirement:** 85-REQ-10.3
**Type:** unit
**Description:** Verify spec executor returns without side effects when no new specs discovered.

**Preconditions:**
- Mock discover_new_specs_gated returning empty list.

**Input:**
- `spec_executor.run_once()`

**Expected:**
- No Orchestrator created.
- Budget unchanged.

**Assertion pseudocode:**
```
mock_discover = AsyncMock(return_value=[])
spec_executor = SpecExecutorStream(config, mock_discover, budget)
await spec_executor.run_once()
ASSERT budget.total_cost == 0.0
```

## Edge Case Tests

### TS-85-E1: Persistent stream failure doesn't affect others

**Requirement:** 85-REQ-1.E1
**Type:** integration
**Description:** Verify a stream that always fails doesn't crash other streams.

**Preconditions:**
- Two streams: one always raises, one always succeeds.

**Input:**
- Run DaemonRunner for two cycles.

**Expected:**
- Failing stream's run_once() called on each cycle (retried).
- Healthy stream's run_once() called on each cycle (unaffected).

**Assertion pseudocode:**
```
failing = MockStream(side_effect=RuntimeError("always fail"))
healthy = MockStream()
runner = DaemonRunner(config, platform, [failing, healthy], budget)
await run_two_cycles(runner)
ASSERT failing.run_once.call_count == 2
ASSERT healthy.run_once.call_count == 2
```

### TS-85-E2: All streams disabled enters idle loop

**Requirement:** 85-REQ-1.E2
**Type:** unit
**Description:** Verify daemon enters idle loop when all streams disabled.

**Preconditions:**
- All four streams with enabled=False.

**Input:**
- Start DaemonRunner, then send shutdown signal.

**Expected:**
- No stream's run_once() called.
- Daemon responds to shutdown signal.

**Assertion pseudocode:**
```
streams = [MockStream(enabled=False) for _ in range(4)]
runner = DaemonRunner(config, platform, streams, budget)
runner.request_shutdown()
state = await runner.run()
for s in streams:
    ASSERT s.run_once.call_count == 0
```

### TS-85-E3: Live PID blocks daemon startup

**Requirement:** 85-REQ-2.E1
**Type:** unit
**Description:** Verify daemon refuses to start when PID file has a live process.

**Preconditions:**
- PID file with current process PID.

**Input:**
- `check_pid_file(pid_path)`

**Expected:**
- Returns (PidStatus.ALIVE, current_pid).

**Assertion pseudocode:**
```
pid_path.write_text(str(os.getpid()))
status, pid = check_pid_file(pid_path)
ASSERT status == PidStatus.ALIVE
ASSERT pid == os.getpid()
```

### TS-85-E4: Stale PID is cleaned up on daemon startup

**Requirement:** 85-REQ-2.E2
**Type:** unit
**Description:** Verify stale PID file is detected and removed.

**Preconditions:**
- PID file with a PID of a process that doesn't exist (e.g., 99999999).

**Input:**
- `check_pid_file(pid_path)`

**Expected:**
- Returns (PidStatus.STALE, 99999999).

**Assertion pseudocode:**
```
pid_path.write_text("99999999")
status, pid = check_pid_file(pid_path)
ASSERT status == PidStatus.STALE
ASSERT pid == 99999999
```

### TS-85-E5: PID file write failure

**Requirement:** 85-REQ-2.E3
**Type:** unit
**Description:** Verify error on PID file write failure (e.g., read-only directory).

**Preconditions:**
- Read-only directory.

**Input:**
- `write_pid_file(readonly_dir / "daemon.pid")`

**Expected:**
- Raises OSError or PermissionError.

**Assertion pseudocode:**
```
readonly_dir = tmp_path / "readonly"
readonly_dir.mkdir(mode=0o444)
with ASSERT_RAISES(OSError):
    write_pid_file(readonly_dir / "daemon.pid")
```

### TS-85-E6: No PID file allows code/plan to proceed

**Requirement:** 85-REQ-3.E1
**Type:** unit
**Description:** Verify code/plan proceed when no PID file exists.

**Preconditions:**
- No PID file at the expected path.

**Input:**
- `check_pid_file(nonexistent_path)`

**Expected:**
- Returns (PidStatus.ABSENT, None).

**Assertion pseudocode:**
```
status, pid = check_pid_file(tmp_path / "daemon.pid")
ASSERT status == PidStatus.ABSENT
ASSERT pid is None
```

### TS-85-E7: Stale PID does not block code/plan

**Requirement:** 85-REQ-3.E2
**Type:** unit
**Description:** Verify code/plan proceed when PID file has stale PID.

**Preconditions:**
- PID file with dead process PID.

**Input:**
- `check_pid_file(pid_path)` with stale PID.

**Expected:**
- Returns (PidStatus.STALE, stale_pid).
- Code/plan should treat STALE same as ABSENT (proceed).

**Assertion pseudocode:**
```
pid_path.write_text("99999999")
status, _ = check_pid_file(pid_path)
ASSERT status == PidStatus.STALE
# Caller proceeds (STALE is not a blocker for code/plan)
```

### TS-85-E8: Disabled spec executor skips priority delay

**Requirement:** 85-REQ-4.E1
**Type:** unit
**Description:** Verify that disabling spec executor doesn't delay other stream launches.

**Preconditions:**
- Spec executor disabled; fix pipeline enabled.

**Input:**
- Start DaemonRunner.

**Expected:**
- Fix pipeline launches immediately (no wait for spec executor).

**Assertion pseudocode:**
```
spec = MockStream(name="spec-executor", enabled=False)
fix = MockStream(name="fix-pipeline", enabled=True)
runner = DaemonRunner(config, platform, [spec, fix], budget)
await run_one_cycle(runner)
ASSERT fix.run_once.call_count >= 1
```

### TS-85-E9: No cost limit configured

**Requirement:** 85-REQ-5.E1
**Type:** unit
**Description:** Verify daemon runs without cost limit when max_cost is None.

**Preconditions:**
- SharedBudget with max_cost=None.

**Input:**
- `add_cost(1000.0)`

**Expected:**
- `exceeded` returns False regardless of total cost.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=None)
budget.add_cost(1000.0)
ASSERT budget.exceeded == False
```

### TS-85-E10: All --no-* flags = idle loop

**Requirement:** 85-REQ-6.E1
**Type:** unit
**Description:** Verify all four --no-* flags results in idle loop.

**Preconditions:**
- CLI with --no-specs --no-fixes --no-hunts --no-spec-gen.

**Input:**
- Build streams with all disabled.

**Expected:**
- All streams disabled; warning logged.

**Assertion pseudocode:**
```
streams = build_streams(config, no_specs=True, no_fixes=True, no_hunts=True, no_spec_gen=True)
enabled = [s for s in streams if s.enabled]
ASSERT len(enabled) == 0
```

### TS-85-E11: Platform none + no-specs = idle loop

**Requirement:** 85-REQ-7.E1
**Type:** unit
**Description:** Verify no-platform + no-specs = idle loop.

**Preconditions:**
- Config with platform.type="none" and --no-specs flag.

**Input:**
- Build streams.

**Expected:**
- All streams disabled.

**Assertion pseudocode:**
```
config = make_config(platform_type="none")
streams = build_streams(config, no_specs=True)
enabled = [s for s in streams if s.enabled]
ASSERT len(enabled) == 0
```

### TS-85-E12: create_pull_request failure fallback

**Requirement:** 85-REQ-8.E1
**Type:** unit
**Description:** Verify PR creation failure logs error and posts branch name comment.

**Preconditions:**
- Mock platform where create_pull_request raises IntegrationError.

**Input:**
- Attempt to create PR from feature branch "fix/42".

**Expected:**
- Error logged.
- Comment posted on issue with branch name "fix/42".

**Assertion pseudocode:**
```
platform = MockPlatform()
platform.create_pull_request.side_effect = IntegrationError("API error")
# Trigger PR creation in merge strategy handler
await handle_merge(platform, issue_number=42, branch="fix/42", strategy="pr")
ASSERT platform.add_issue_comment.call_count == 1
ASSERT "fix/42" in platform.add_issue_comment.call_args[0][1]
```

### TS-85-E13: Unknown merge_strategy falls back to direct

**Requirement:** 85-REQ-8.E2
**Type:** unit
**Description:** Verify unknown merge_strategy defaults to "direct".

**Preconditions:**
- Config with merge_strategy="unknown".

**Input:**
- Read effective merge strategy.

**Expected:**
- Falls back to "direct" with warning logged.

**Assertion pseudocode:**
```
config = NightShiftConfig(merge_strategy="unknown")
effective = resolve_merge_strategy(config.merge_strategy)
ASSERT effective == "direct"
```

### TS-85-E14: spec_interval clamped to minimum

**Requirement:** 85-REQ-9.E1
**Type:** unit
**Description:** Verify spec_interval below 10 is clamped to 10.

**Preconditions:**
- NightShiftConfig with spec_interval=5.

**Input:**
- `NightShiftConfig(spec_interval=5)`

**Expected:**
- `config.spec_interval == 10`.

**Assertion pseudocode:**
```
config = NightShiftConfig(spec_interval=5)
ASSERT config.spec_interval == 10
```

### TS-85-E15: Empty enabled_streams = all enabled

**Requirement:** 85-REQ-9.E2
**Type:** unit
**Description:** Verify empty enabled_streams list defaults to all streams.

**Preconditions:**
- Config with enabled_streams=[].

**Input:**
- Build streams from config.

**Expected:**
- All four streams are enabled.

**Assertion pseudocode:**
```
config = NightShiftConfig(enabled_streams=[])
streams = build_streams(config)
enabled = [s for s in streams if s.enabled]
ASSERT len(enabled) == 4
```

### TS-85-E16: Spec executor handles discovery error

**Requirement:** 85-REQ-10.E1
**Type:** unit
**Description:** Verify spec executor logs error and returns on discovery failure.

**Preconditions:**
- Mock discover_new_specs_gated that raises OSError.

**Input:**
- `spec_executor.run_once()`

**Expected:**
- Exception caught and logged.
- No Orchestrator created.
- run_once() returns without raising.

**Assertion pseudocode:**
```
mock_discover = AsyncMock(side_effect=OSError("disk error"))
spec_executor = SpecExecutorStream(config, mock_discover, budget)
await spec_executor.run_once()  # should not raise
ASSERT budget.total_cost == 0.0
```

## Property Test Cases

### TS-85-P1: PID mutual exclusion

**Property:** Property 1 from design.md
**Validates:** 85-REQ-2.1, 85-REQ-2.E1, 85-REQ-3.1, 85-REQ-3.2
**Type:** property
**Description:** PID file mechanism ensures at most one daemon runs at a time.

**For any:** PID value in range [1, 2^31], alive or dead status
**Invariant:** check_pid_file returns ALIVE only for actually alive processes; write_pid_file + check_pid_file(same path) returns ALIVE for current process.

**Assertion pseudocode:**
```
FOR ANY pid IN st.integers(1, 2**31):
    pid_path.write_text(str(pid))
    status, read_pid = check_pid_file(pid_path)
    ASSERT read_pid == pid
    IF process_alive(pid):
        ASSERT status == PidStatus.ALIVE
    ELSE:
        ASSERT status == PidStatus.STALE
```

### TS-85-P2: Cost monotonicity and limit

**Property:** Property 2 from design.md
**Validates:** 85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1
**Type:** property
**Description:** SharedBudget total cost is monotonically non-decreasing and exceeded triggers correctly.

**For any:** sequence of non-negative cost values and max_cost >= 0 or None
**Invariant:** total_cost equals sum of all add_cost calls; exceeded is True iff total_cost >= max_cost (when max_cost is not None).

**Assertion pseudocode:**
```
FOR ANY costs IN st.lists(st.floats(0.0, 100.0)), max_cost IN st.one_of(st.none(), st.floats(0.0, 1000.0)):
    budget = SharedBudget(max_cost=max_cost)
    running_total = 0.0
    FOR cost IN costs:
        budget.add_cost(cost)
        running_total += cost
        ASSERT budget.total_cost == running_total
        IF max_cost is not None:
            ASSERT budget.exceeded == (running_total >= max_cost)
        ELSE:
            ASSERT budget.exceeded == False
```

### TS-85-P3: Stream isolation

**Property:** Property 3 from design.md
**Validates:** 85-REQ-1.4, 85-REQ-1.E1
**Type:** property
**Description:** A failing stream never prevents other streams from running.

**For any:** set of N streams (1..8) where a random subset raise exceptions
**Invariant:** non-failing streams' run_once() is always called on each cycle.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(1, 8), fail_mask IN st.lists(st.booleans(), min_size=n, max_size=n):
    streams = [MockStream(fail=fail_mask[i]) for i in range(n)]
    runner = DaemonRunner(config, platform, [s for s in streams if s.enabled], budget)
    await run_one_cycle(runner)
    FOR i, stream IN enumerate(streams):
        ASSERT stream.run_once.call_count >= 1
```

### TS-85-P4: Shutdown completeness

**Property:** Property 4 from design.md
**Validates:** 85-REQ-2.2, 85-REQ-2.4, 85-REQ-2.5
**Type:** property
**Description:** Every registered stream's shutdown() is called on graceful shutdown.

**For any:** set of N streams (1..8)
**Invariant:** after DaemonRunner.run() returns, shutdown() called on all N streams.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(1, 8):
    streams = [MockStream() for _ in range(n)]
    runner = DaemonRunner(config, platform, streams, budget)
    runner.request_shutdown()
    await runner.run()
    FOR stream IN streams:
        ASSERT stream.shutdown.call_count == 1
```

### TS-85-P5: Config interval clamping

**Property:** Property 5 from design.md
**Validates:** 85-REQ-9.1, 85-REQ-9.E1
**Type:** property
**Description:** Interval config fields are always >= their documented minimum after validation.

**For any:** spec_interval in range [-1000, 10000], spec_gen_interval in range [-1000, 10000]
**Invariant:** validated spec_interval >= 10; validated spec_gen_interval >= 60.

**Assertion pseudocode:**
```
FOR ANY si IN st.integers(-1000, 10000), sgi IN st.integers(-1000, 10000):
    config = NightShiftConfig(spec_interval=si, spec_gen_interval=sgi)
    ASSERT config.spec_interval >= 10
    ASSERT config.spec_gen_interval >= 60
```

### TS-85-P6: Platform degradation

**Property:** Property 6 from design.md
**Validates:** 85-REQ-7.1, 85-REQ-7.E1
**Type:** property
**Description:** With platform.type="none", only spec executor can be enabled.

**For any:** combination of --no-* flags
**Invariant:** with platform="none", enabled set is subset of {"spec-executor"}.

**Assertion pseudocode:**
```
FOR ANY no_specs IN st.booleans():
    config = make_config(platform_type="none")
    streams = build_streams(config, no_specs=no_specs)
    enabled_names = {s.name for s in streams if s.enabled}
    ASSERT enabled_names.issubset({"spec-executor"})
    IF no_specs:
        ASSERT enabled_names == set()
    ELSE:
        ASSERT enabled_names == {"spec-executor"}
```

### TS-85-P7: Enabled stream filtering

**Property:** Property 7 from design.md
**Validates:** 85-REQ-1.3, 85-REQ-6.1, 85-REQ-9.2
**Type:** property
**Description:** Running streams are the intersection of config-enabled and CLI-enabled.

**For any:** enabled_streams subset of {"specs","fixes","hunts","spec_gen"}, --no-* flags
**Invariant:** running set = (config enabled names) intersect (CLI enabled names), mapped to stream names.

**Assertion pseudocode:**
```
FOR ANY config_enabled IN st.subsets({"specs","fixes","hunts","spec_gen"}),
       no_flags IN st.tuples(st.booleans(), st.booleans(), st.booleans(), st.booleans()):
    config = NightShiftConfig(enabled_streams=list(config_enabled))
    streams = build_streams(config, no_specs=no_flags[0], no_fixes=no_flags[1],
                           no_hunts=no_flags[2], no_spec_gen=no_flags[3])
    cli_enabled = set()
    if not no_flags[0]: cli_enabled.add("specs")
    if not no_flags[1]: cli_enabled.add("fixes")
    if not no_flags[2]: cli_enabled.add("hunts")
    if not no_flags[3]: cli_enabled.add("spec_gen")
    expected = config_enabled & cli_enabled
    actual = {stream_name_to_config_name(s.name) for s in streams if s.enabled}
    ASSERT actual == expected
```

## Integration Smoke Tests

### TS-85-SMOKE-1: Daemon full lifecycle

**Execution Path:** Path 1 (startup) + Path 5 (shutdown)
**Description:** Verify daemon starts, writes PID, runs streams, shuts down, removes PID.

**Setup:** Mock platform. Real DaemonRunner, real PID module. Mock stream that
counts invocations and signals completion after 2 cycles.

**Trigger:** `DaemonRunner.run()` followed by `request_shutdown()`.

**Expected side effects:**
- PID file created with correct PID at start.
- Stream run_once() called at least once.
- PID file removed after shutdown.
- DaemonState.uptime_seconds > 0.

**Must NOT satisfy with:** Mocked DaemonRunner, mocked PID module.

**Assertion pseudocode:**
```
pid_path = tmp_path / "daemon.pid"
stream = MockStream(enabled=True)
budget = SharedBudget(max_cost=None)
runner = DaemonRunner(config, None, [stream], budget, pid_path=pid_path)

# Start and run briefly
task = asyncio.create_task(runner.run())
await asyncio.sleep(0.2)
ASSERT pid_path.exists()
ASSERT pid_path.read_text().strip() == str(os.getpid())

runner.request_shutdown()
state = await task
ASSERT NOT pid_path.exists()
ASSERT state.uptime_seconds > 0
ASSERT stream.run_once.call_count >= 1
ASSERT stream.shutdown.call_count == 1
```

### TS-85-SMOKE-2: Spec executor end-to-end

**Execution Path:** Path 2 (spec executor discovers and executes)
**Description:** Verify spec executor discovers specs, runs orchestrator, reports cost.

**Setup:** Mock `discover_new_specs_gated` to return one SpecInfo. Mock
Orchestrator to return ExecutionState with cost=1.5. Real SpecExecutorStream,
real SharedBudget.

**Trigger:** `spec_executor.run_once()`

**Expected side effects:**
- discover_new_specs_gated called with correct args.
- Orchestrator.run() called.
- budget.total_cost == 1.5.

**Must NOT satisfy with:** Mocked SpecExecutorStream, mocked SharedBudget.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=10.0)
mock_discover = AsyncMock(return_value=[SpecInfo("test_spec", 99, Path("/tmp/specs/99_test"))])
mock_orch = MockOrchestrator(result=ExecutionState(total_cost=1.5))
executor = SpecExecutorStream(config, budget, discover_fn=mock_discover, orch_factory=lambda: mock_orch)
await executor.run_once()
ASSERT mock_discover.call_count == 1
ASSERT mock_orch.run.call_count == 1
ASSERT budget.total_cost == 1.5
```

### TS-85-SMOKE-3: Fix pipeline stream end-to-end

**Execution Path:** Path 3 (fix pipeline processes issues)
**Description:** Verify fix pipeline stream wraps engine and reports cost.

**Setup:** Mock NightShiftEngine with _drain_issues() that increments
state.total_cost by 3.0. Real FixPipelineStream, real SharedBudget.

**Trigger:** `fix_pipeline.run_once()`

**Expected side effects:**
- engine._drain_issues() called.
- budget.total_cost == 3.0 (delta from engine).

**Must NOT satisfy with:** Mocked FixPipelineStream.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=10.0)
engine = MockNightShiftEngine(drain_cost_delta=3.0)
fix_stream = FixPipelineStream(engine, budget)
await fix_stream.run_once()
ASSERT engine._drain_issues.call_count == 1
ASSERT budget.total_cost == 3.0
```

### TS-85-SMOKE-4: Hunt scan stream end-to-end

**Execution Path:** Path 4 (hunt scan discovers issues)
**Description:** Verify hunt scan stream wraps engine and reports cost.

**Setup:** Mock NightShiftEngine with _run_hunt_scan(). Real HuntScanStream,
real SharedBudget.

**Trigger:** `hunt_scan.run_once()`

**Expected side effects:**
- engine._run_hunt_scan() called.

**Must NOT satisfy with:** Mocked HuntScanStream.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=10.0)
engine = MockNightShiftEngine()
hunt_stream = HuntScanStream(engine, budget)
await hunt_stream.run_once()
ASSERT engine._run_hunt_scan.call_count == 1
```

### TS-85-SMOKE-5: Graceful shutdown preserves state

**Execution Path:** Path 5 (graceful shutdown)
**Description:** Verify shutdown sequence calls all stream shutdowns and removes PID.

**Setup:** Real DaemonRunner with two mock streams. Real PID module.

**Trigger:** `request_shutdown()` during run.

**Expected side effects:**
- Both streams' shutdown() called.
- PID file removed.
- Audit event emitted (captured in logs).

**Must NOT satisfy with:** Mocked DaemonRunner.

**Assertion pseudocode:**
```
pid_path = tmp_path / "daemon.pid"
s1, s2 = MockStream(), MockStream()
runner = DaemonRunner(config, None, [s1, s2], budget, pid_path=pid_path)
runner.request_shutdown()
await runner.run()
ASSERT s1.shutdown.call_count == 1
ASSERT s2.shutdown.call_count == 1
ASSERT NOT pid_path.exists()
```

### TS-85-SMOKE-6: PID check blocks code command

**Execution Path:** Path 6 (code/plan PID check)
**Description:** Verify code command is blocked when live daemon PID exists.

**Setup:** Real PID module. Write current PID to PID file.

**Trigger:** `check_pid_file(pid_path)` from code command guard.

**Expected side effects:**
- Returns PidStatus.ALIVE.
- Code command would exit(1).

**Must NOT satisfy with:** Mocked check_pid_file.

**Assertion pseudocode:**
```
pid_path = tmp_path / "daemon.pid"
write_pid_file(pid_path)
status, pid = check_pid_file(pid_path)
ASSERT status == PidStatus.ALIVE
ASSERT pid == os.getpid()
```

### TS-85-SMOKE-7: Draft PR creation

**Execution Path:** Path 7 (draft PR creation)
**Description:** Verify GitHubPlatform.create_pull_request sends correct API request.

**Setup:** Mock httpx to intercept POST request. Real GitHubPlatform.

**Trigger:** `github.create_pull_request("Fix", "body", "fix/1", "develop", draft=True)`

**Expected side effects:**
- POST to `/repos/owner/repo/pulls` with body containing head="fix/1",
  base="develop", draft=true.
- Returns PullRequestResult with correct fields.

**Must NOT satisfy with:** Mocked GitHubPlatform.

**Assertion pseudocode:**
```
# httpx mock returns 201 with PR JSON
github = GitHubPlatform("owner", "repo", "token")
result = await github.create_pull_request("Fix", "body", "fix/1", "develop", draft=True)
ASSERT result.number > 0
ASSERT "github.com" in result.html_url
ASSERT httpx_mock.last_request.url.path == "/repos/owner/repo/pulls"
ASSERT httpx_mock.last_request.json()["draft"] == True
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 85-REQ-1.1 | TS-85-1 | unit |
| 85-REQ-1.2 | TS-85-2 | unit |
| 85-REQ-1.3 | TS-85-3 | unit |
| 85-REQ-1.4 | TS-85-4 | unit |
| 85-REQ-1.E1 | TS-85-E1 | integration |
| 85-REQ-1.E2 | TS-85-E2 | unit |
| 85-REQ-2.1 | TS-85-5 | unit |
| 85-REQ-2.2 | TS-85-6 | integration |
| 85-REQ-2.3 | TS-85-7 | unit |
| 85-REQ-2.4 | TS-85-8 | unit |
| 85-REQ-2.5 | TS-85-9 | unit |
| 85-REQ-2.E1 | TS-85-E3 | unit |
| 85-REQ-2.E2 | TS-85-E4 | unit |
| 85-REQ-2.E3 | TS-85-E5 | unit |
| 85-REQ-3.1 | TS-85-10 | unit |
| 85-REQ-3.2 | TS-85-11 | unit |
| 85-REQ-3.E1 | TS-85-E6 | unit |
| 85-REQ-3.E2 | TS-85-E7 | unit |
| 85-REQ-4.1 | TS-85-12 | integration |
| 85-REQ-4.2 | TS-85-13 | unit |
| 85-REQ-4.3 | TS-85-14 | unit |
| 85-REQ-4.E1 | TS-85-E8 | unit |
| 85-REQ-5.1 | TS-85-15 | unit |
| 85-REQ-5.2 | TS-85-16 | unit |
| 85-REQ-5.3 | TS-85-17 | integration |
| 85-REQ-5.E1 | TS-85-E9 | unit |
| 85-REQ-6.1 | TS-85-18 | unit |
| 85-REQ-6.2 | TS-85-19 | unit |
| 85-REQ-6.3 | TS-85-20 | unit |
| 85-REQ-6.E1 | TS-85-E10 | unit |
| 85-REQ-7.1 | TS-85-21 | unit |
| 85-REQ-7.E1 | TS-85-E11 | unit |
| 85-REQ-8.1 | TS-85-22 | unit |
| 85-REQ-8.2 | TS-85-23 | unit |
| 85-REQ-8.3 | TS-85-24 | unit |
| 85-REQ-8.4 | TS-85-25 | unit |
| 85-REQ-8.E1 | TS-85-E12 | unit |
| 85-REQ-8.E2 | TS-85-E13 | unit |
| 85-REQ-9.1 | TS-85-26 | unit |
| 85-REQ-9.2 | TS-85-27 | unit |
| 85-REQ-9.E1 | TS-85-E14 | unit |
| 85-REQ-9.E2 | TS-85-E15 | unit |
| 85-REQ-10.1 | TS-85-28 | unit |
| 85-REQ-10.2 | TS-85-29 | integration |
| 85-REQ-10.3 | TS-85-30 | unit |
| 85-REQ-10.E1 | TS-85-E16 | unit |
| Property 1 | TS-85-P1 | property |
| Property 2 | TS-85-P2 | property |
| Property 3 | TS-85-P3 | property |
| Property 4 | TS-85-P4 | property |
| Property 5 | TS-85-P5 | property |
| Property 6 | TS-85-P6 | property |
| Property 7 | TS-85-P7 | property |
| Path 1+5 | TS-85-SMOKE-1 | integration |
| Path 2 | TS-85-SMOKE-2 | integration |
| Path 3 | TS-85-SMOKE-3 | integration |
| Path 4 | TS-85-SMOKE-4 | integration |
| Path 5 | TS-85-SMOKE-5 | integration |
| Path 6 | TS-85-SMOKE-6 | integration |
| Path 7 | TS-85-SMOKE-7 | integration |
