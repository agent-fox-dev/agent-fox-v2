# Test Specification: Night Shift — Issue-First Ordering & Console Status Output

## Overview

Test cases are organized into four sections: acceptance-criterion tests
(one per requirement), property tests (one per correctness property), edge
case tests, and integration smoke tests. All tests use a mock platform that
simulates `list_issues_by_label`, `close_issue`, and `add_issue_comment` and
a mock session runner that returns canned `SessionOutcome` objects.

## Test Cases

### TS-81-1: Hunt scan suppressed while af:fix issues exist

**Requirement:** 81-REQ-1.1
**Type:** unit
**Description:** Verify that the engine never calls `_run_hunt_scan` when
the platform reports open `af:fix` issues.

**Preconditions:**
- Mock platform returns 2 open `af:fix` issues on every `list_issues_by_label` call.
- Mock `_run_hunt_scan` to record calls.
- Hunt scan interval set to 1 second (fires immediately).

**Input:**
- Run engine for 3 ticks then request shutdown.

**Expected:**
- `_run_hunt_scan` is never called.
- `_run_issue_check` is called at least once.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform)
mock _run_hunt_scan to record calls
mock _run_issue_check to process issues (issues never clear)
run engine for 3 ticks
ASSERT _run_hunt_scan.call_count == 0
ASSERT _run_issue_check.call_count >= 1
```

### TS-81-2: Startup processes issues before hunt scan

**Requirement:** 81-REQ-1.2
**Type:** unit
**Description:** Verify that on startup the engine runs issue check and
processes all issues before the first hunt scan.

**Preconditions:**
- Mock platform returns 1 `af:fix` issue on first call, 0 on subsequent calls.
- Record call order of `_run_issue_check` and `_run_hunt_scan`.

**Input:**
- Start engine, let it complete startup sequence, then shutdown.

**Expected:**
- Call order: `_run_issue_check` before `_run_hunt_scan`.
- The issue is processed (fix pipeline called) before hunt scan starts.

**Assertion pseudocode:**
```
call_log = []
mock _run_issue_check to append "issue_check" to call_log
mock _run_hunt_scan to append "hunt_scan" to call_log
run engine startup
ASSERT call_log[0] == "issue_check"
ASSERT call_log.index("hunt_scan") > call_log.index("issue_check")
```

### TS-81-3: Post-hunt issue drain

**Requirement:** 81-REQ-1.3
**Type:** unit
**Description:** Verify that after a hunt scan completes, the engine
immediately runs an issue check before allowing the next hunt scan.

**Preconditions:**
- Mock platform returns 0 issues initially (to allow first hunt scan).
- After hunt scan, mock platform returns 1 `af:fix` issue, then 0.
- Record call order.

**Input:**
- Run engine through startup + one hunt scan + post-hunt drain.

**Expected:**
- After `_run_hunt_scan`, `_run_issue_check` is called before any subsequent
  `_run_hunt_scan`.

**Assertion pseudocode:**
```
call_log = []
# ... setup mocks to log calls ...
run engine through one full cycle
hunt_idx = call_log.index("hunt_scan")
subsequent = call_log[hunt_idx + 1:]
ASSERT subsequent[0] == "issue_check"
```

### TS-81-4: Hunt timer fires with pending issues — issues first

**Requirement:** 81-REQ-1.4
**Type:** unit
**Description:** Verify that when the hunt timer elapses but issues exist,
issues are processed before the hunt scan runs.

**Preconditions:**
- Mock platform returns 1 issue on first issue check, 0 on second.
- Hunt interval set to 1 second.
- Issue interval set to 1 second.

**Input:**
- Let both timers elapse simultaneously.

**Expected:**
- Issue check and processing happen before hunt scan.

**Assertion pseudocode:**
```
call_log = []
# both timers fire at same tick
run engine for enough ticks
ASSERT call_log shows issue_check before hunt_scan after the simultaneous fire
```

### TS-81-5: Hunt scan fires when no issues exist

**Requirement:** 81-REQ-1.5
**Type:** unit
**Description:** Verify that the hunt scan fires immediately when the timer
elapses and no `af:fix` issues exist.

**Preconditions:**
- Mock platform returns 0 `af:fix` issues.
- Hunt interval set to 2 seconds.

**Input:**
- Run engine past the hunt interval.

**Expected:**
- `_run_hunt_scan` is called after the interval elapses.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform)
run engine for 3 seconds
ASSERT _run_hunt_scan.call_count >= 1
```

### TS-81-6: ProgressDisplay created and started in CLI

**Requirement:** 81-REQ-2.1
**Type:** integration
**Description:** Verify that night_shift_cmd creates a ProgressDisplay,
starts it, and registers the LiveAwareHandler.

**Preconditions:**
- Mock platform, engine, and asyncio.run.

**Input:**
- Invoke `night_shift_cmd` via Click test runner.

**Expected:**
- ProgressDisplay.start() is called.
- ProgressDisplay.stop() is called (in finally block).

**Assertion pseudocode:**
```
with mock ProgressDisplay as pd_mock:
    runner = CliRunner()
    result = runner.invoke(night_shift_cmd, ...)
    ASSERT pd_mock.start.called
    ASSERT pd_mock.stop.called
```

### TS-81-7: Summary printed on exit

**Requirement:** 81-REQ-2.2
**Type:** unit
**Description:** Verify that the exit summary includes scans, issues fixed,
cost, and status.

**Preconditions:**
- Engine returns state with known values.

**Input:**
- Run night_shift_cmd to completion.

**Expected:**
- Output contains "Scans completed: 2", "Issues fixed: 3", cost value.

**Assertion pseudocode:**
```
state = NightShiftState(hunt_scans_completed=2, issues_fixed=3, total_cost=1.5)
# mock engine.run to return state
result = runner.invoke(night_shift_cmd, ...)
ASSERT "Scans completed: 2" in result.output
ASSERT "Issues fixed: 3" in result.output
ASSERT "$1.5" in result.output
```

### TS-81-8: ActivityEvent forwarded during fix session

**Requirement:** 81-REQ-2.3
**Type:** unit
**Description:** Verify that ActivityEvents from the session runner reach
the activity_callback during a fix session.

**Preconditions:**
- Engine constructed with a recording activity_callback.
- Mock run_session to emit ActivityEvent.

**Input:**
- Process one issue through the fix pipeline.

**Expected:**
- activity_callback receives at least one ActivityEvent with correct fields.

**Assertion pseudocode:**
```
events = []
engine = NightShiftEngine(config, platform, activity_callback=events.append)
process one issue
ASSERT len(events) >= 1
ASSERT events[0].archetype in ("skeptic", "coder", "verifier")
```

### TS-81-9: TaskEvent emitted on archetype completion

**Requirement:** 81-REQ-2.4
**Type:** unit
**Description:** Verify that a TaskEvent is emitted for each archetype
session (3 per issue: skeptic, coder, verifier).

**Preconditions:**
- Engine constructed with a recording task_callback.
- Mock run_session to return successfully.

**Input:**
- Process one issue through the fix pipeline.

**Expected:**
- task_callback receives exactly 3 TaskEvents with archetypes
  "skeptic", "coder", "verifier" and status "completed".

**Assertion pseudocode:**
```
events = []
pipeline = FixPipeline(config, platform, task_callback=events.append)
await pipeline.process_issue(issue, body="fix this")
ASSERT len(events) == 3
ASSERT [e.archetype for e in events] == ["skeptic", "coder", "verifier"]
ASSERT all(e.status == "completed" for e in events)
```

### TS-81-10: Phase line emitted on issue check start

**Requirement:** 81-REQ-3.1
**Type:** unit
**Description:** Verify that a status line is emitted when the engine
starts an issue check.

**Preconditions:**
- Engine constructed with a recording status_callback.

**Input:**
- Trigger one issue check cycle.

**Expected:**
- status_callback called with text containing "af:fix" or "issue".

**Assertion pseudocode:**
```
lines = []
engine = NightShiftEngine(config, platform, status_callback=lines.append)
await engine._run_issue_check()
ASSERT any("af:fix" in line or "issue" in line.lower() for line, _ in lines)
```

### TS-81-11: Phase line emitted on hunt scan start

**Requirement:** 81-REQ-3.2
**Type:** unit
**Description:** Verify that a status line is emitted when the engine
starts a hunt scan.

**Preconditions:**
- Engine constructed with a recording status_callback.
- No open issues (gate passes).

**Input:**
- Trigger one hunt scan.

**Expected:**
- status_callback called with text containing "hunt" or "scan".

**Assertion pseudocode:**
```
lines = []
engine = NightShiftEngine(config, platform, status_callback=lines.append)
await engine._run_hunt_scan()
ASSERT any("hunt" in line.lower() or "scan" in line.lower() for line, _ in lines)
```

### TS-81-12: Phase line on hunt scan complete with counts

**Requirement:** 81-REQ-3.3
**Type:** unit
**Description:** Verify that a status line with finding/issue counts is
emitted after a hunt scan completes.

**Preconditions:**
- Hunt scan produces 3 findings, 2 issues created.

**Input:**
- Run one hunt scan.

**Expected:**
- status_callback receives a line containing the issue count.

**Assertion pseudocode:**
```
lines = []
# mock scan to produce 2 issues
await engine._run_hunt_scan()
ASSERT any("2" in line for line, _ in lines)
```

### TS-81-13: Phase line on successful fix

**Requirement:** 81-REQ-3.4
**Type:** unit
**Description:** Verify that a permanent line is emitted when an issue fix
completes successfully, showing issue number and duration.

**Preconditions:**
- Fix pipeline succeeds for issue #42.

**Input:**
- Process issue #42.

**Expected:**
- status_callback receives a line containing "#42" and a duration.

**Assertion pseudocode:**
```
lines = []
await engine._process_fix(issue_42)
ASSERT any("#42" in line for line, _ in lines)
```

### TS-81-14: Phase line on failed fix

**Requirement:** 81-REQ-3.5
**Type:** unit
**Description:** Verify that a permanent line is emitted when an issue fix
fails.

**Preconditions:**
- Fix pipeline raises an exception for issue #42.

**Input:**
- Process issue #42 (mock pipeline to fail).

**Expected:**
- status_callback receives a line containing "#42" and "failed" indication.

**Assertion pseudocode:**
```
lines = []
mock _process_fix to raise
await engine._process_fix(issue_42)
ASSERT any("#42" in line and "fail" in line.lower() for line, _ in lines)
```

### TS-81-15: Idle spinner shows next action time

**Requirement:** 81-REQ-4.1
**Type:** unit
**Description:** Verify that during idle periods the spinner shows the
next scheduled action time in local timezone.

**Preconditions:**
- Engine in idle state with known remaining times.
- Mock `datetime.now()` to a fixed time.

**Input:**
- Call `_update_idle_spinner(issue_remaining=300, hunt_remaining=600)`.

**Expected:**
- activity_callback or spinner update contains a time string in HH:MM format.

**Assertion pseudocode:**
```
engine._update_idle_spinner(300, 600)
ASSERT spinner text matches pattern "Waiting until HH:MM for next issue check"
```

### TS-81-16: Idle spinner clears on phase start

**Requirement:** 81-REQ-4.2
**Type:** unit
**Description:** Verify that the idle message is cleared when a phase starts.

**Preconditions:**
- Engine in idle state with spinner showing wait time.

**Input:**
- Trigger an issue check.

**Expected:**
- Spinner text is replaced with activity events (no stale idle message).

**Assertion pseudocode:**
```
engine._update_idle_spinner(10, 600)
ASSERT "Waiting" in spinner_text
await engine._run_issue_check()
# phase line replaces idle text
ASSERT "Waiting" not in current_spinner_text
```

### TS-81-17: Engine constructor accepts callbacks

**Requirement:** 81-REQ-5.1
**Type:** unit
**Description:** Verify that NightShiftEngine accepts and stores callback
parameters.

**Preconditions:**
- Callback functions defined.

**Input:**
- Construct engine with callbacks.

**Expected:**
- Callbacks are accessible as engine attributes.

**Assertion pseudocode:**
```
cb = lambda e: None
engine = NightShiftEngine(config, platform, activity_callback=cb, task_callback=cb)
ASSERT engine._activity_callback is cb
ASSERT engine._task_callback is cb
```

### TS-81-18: FixPipeline passes activity_callback to run_session

**Requirement:** 81-REQ-5.2
**Type:** unit
**Description:** Verify that FixPipeline passes the activity_callback
through to run_session.

**Preconditions:**
- Mock run_session to capture kwargs.

**Input:**
- Process one issue with a callback set.

**Expected:**
- run_session is called with `activity_callback` kwarg matching the
  provided callback.

**Assertion pseudocode:**
```
cb = lambda e: None
pipeline = FixPipeline(config, platform, activity_callback=cb)
mock run_session to capture call
await pipeline.process_issue(issue, body="fix")
ASSERT run_session_call.kwargs["activity_callback"] is cb
```

### TS-81-19: FixPipeline emits TaskEvent per archetype

**Requirement:** 81-REQ-5.3
**Type:** unit
**Description:** Verify that FixPipeline emits one TaskEvent per archetype
with correct fields.

**Preconditions:**
- Mock run_session to succeed quickly.

**Input:**
- Process one issue.

**Expected:**
- 3 TaskEvents emitted with correct node_id, status, archetype, and
  positive duration.

**Assertion pseudocode:**
```
events = []
pipeline = FixPipeline(config, platform, task_callback=events.append)
await pipeline.process_issue(issue, body="fix")
ASSERT len(events) == 3
for e in events:
    ASSERT e.duration_s > 0
    ASSERT e.node_id.startswith("fix-issue-")
    ASSERT e.status == "completed"
```

## Property Test Cases

### TS-81-P1: Hunt gate invariant

**Property:** Property 1 from design.md
**Validates:** 81-REQ-1.1, 81-REQ-1.4
**Type:** property
**Description:** For any sequence of timer ticks and issue counts, the
engine never calls `_run_hunt_scan` while issues exist.

**For any:** Sequence of (tick_count: 1..100, issues_at_each_tick: 0..5)
generated by Hypothesis.
**Invariant:** If `list_issues_by_label("af:fix")` returns non-empty at the
moment `_run_hunt_scan` would fire, the hunt scan is not called.

**Assertion pseudocode:**
```
FOR ANY ticks IN st.lists(st.tuples(st.integers(1, 100), st.integers(0, 5))):
    platform = MockPlatform(issue_schedule=ticks)
    engine = NightShiftEngine(config, platform)
    mock _run_hunt_scan to record calls and assert platform has 0 issues
    run engine for len(ticks) ticks
    # assertion is inside the mock: _run_hunt_scan only called when issues == 0
```

### TS-81-P2: Post-hunt drain ordering

**Property:** Property 2 from design.md
**Validates:** 81-REQ-1.3, 81-REQ-1.E3
**Type:** property
**Description:** For any hunt scan completion, an issue check always
follows before the next hunt scan.

**For any:** Number of hunt scans (1..5), issues created per scan (0..3).
**Invariant:** Between any two consecutive `_run_hunt_scan` calls in the
call log, there is at least one `_run_issue_check` call.

**Assertion pseudocode:**
```
FOR ANY n_scans IN st.integers(1, 5), issues_per IN st.integers(0, 3):
    call_log = run_engine_recording_calls(n_scans, issues_per)
    hunt_indices = [i for i, c in enumerate(call_log) if c == "hunt_scan"]
    for a, b in zip(hunt_indices, hunt_indices[1:]):
        between = call_log[a+1:b]
        ASSERT "issue_check" in between
```

### TS-81-P3: Startup order invariant

**Property:** Property 3 from design.md
**Validates:** 81-REQ-1.2
**Type:** property
**Description:** For any initial issue count, the first call is always
`_run_issue_check`, never `_run_hunt_scan`.

**For any:** Initial issue count (0..10).
**Invariant:** `call_log[0] == "issue_check"`.

**Assertion pseudocode:**
```
FOR ANY n_issues IN st.integers(0, 10):
    call_log = run_engine_startup(n_issues)
    ASSERT call_log[0] == "issue_check"
```

### TS-81-P4: Callback propagation

**Property:** Property 4 from design.md
**Validates:** 81-REQ-5.1, 81-REQ-5.2, 81-REQ-5.3
**Type:** property
**Description:** For any number of issues processed, the task_callback
receives exactly 3 events per successfully processed issue.

**For any:** Number of issues (1..5), each with non-empty body.
**Invariant:** `len(task_events) == 3 * n_successful_issues`.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(1, 5):
    events = []
    pipeline = FixPipeline(config, platform, task_callback=events.append)
    for issue in issues[:n]:
        await pipeline.process_issue(issue, body="fix")
    ASSERT len(events) == 3 * n
```

### TS-81-P5: Idle display accuracy

**Property:** Property 5 from design.md
**Validates:** 81-REQ-4.1, 81-REQ-4.E1
**Type:** property
**Description:** For any pair of remaining times, the spinner displays the
earlier time.

**For any:** issue_remaining (60..3600), hunt_remaining (60..14400).
**Invariant:** The displayed time equals `now + min(issue_remaining, hunt_remaining)`.

**Assertion pseudocode:**
```
FOR ANY ir IN st.integers(60, 3600), hr IN st.integers(60, 14400):
    engine._update_idle_spinner(ir, hr)
    expected_time = now + timedelta(seconds=min(ir, hr))
    ASSERT spinner_text contains expected_time.strftime("%H:%M")
```

### TS-81-P6: Display lifecycle

**Property:** Property 6 from design.md
**Validates:** 81-REQ-2.1, 81-REQ-2.2
**Type:** property
**Description:** For any engine exit path (clean, signal, exception), the
ProgressDisplay is started before and stopped after.

**For any:** Exit mode in ("clean", "signal", "exception").
**Invariant:** `start()` is called exactly once and `stop()` is called exactly
once, with `start` before `stop`.

**Assertion pseudocode:**
```
FOR ANY exit_mode IN st.sampled_from(["clean", "signal", "exception"]):
    progress = MockProgressDisplay()
    run night_shift_cmd with exit_mode
    ASSERT progress.start_count == 1
    ASSERT progress.stop_count == 1
    ASSERT progress.start_time < progress.stop_time
```

### TS-81-P7: Backward compatibility

**Property:** Property 7 from design.md
**Validates:** 81-REQ-5.E1
**Type:** property
**Description:** For any engine run with None callbacks, no display methods
are invoked.

**For any:** Issue count (0..5), hunt scan count (0..2).
**Invariant:** No exceptions raised, no display output produced.

**Assertion pseudocode:**
```
FOR ANY n_issues IN st.integers(0, 5):
    engine = NightShiftEngine(config, platform)  # no callbacks
    state = run engine
    # no assertion on display — just verify no exception
    ASSERT state is not None
```

### TS-81-P8: Phase line emission completeness

**Property:** Property 8 from design.md
**Validates:** 81-REQ-3.1, 81-REQ-3.2, 81-REQ-3.3, 81-REQ-3.4, 81-REQ-3.5
**Type:** property
**Description:** For any engine run that includes both issue checks and
hunt scans, every phase transition produces exactly one status line.

**For any:** Sequence of phases: issue_check(n_issues: 0..3),
hunt_scan(n_findings: 0..5).
**Invariant:** Number of status lines == number of phase transitions.

**Assertion pseudocode:**
```
FOR ANY phases IN st.lists(st.tuples(st.sampled_from(["issue", "hunt"]), st.integers(0, 5))):
    lines = []
    engine = NightShiftEngine(config, platform, status_callback=lines.append)
    run phases
    ASSERT len(lines) == expected_phase_transitions(phases)
```

## Edge Case Tests

### TS-81-E1: Platform API failure during pre-hunt issue check

**Requirement:** 81-REQ-1.E1
**Type:** unit
**Description:** Verify that if the platform API fails during the pre-hunt
issue check, the engine logs a warning and proceeds with the hunt scan.

**Preconditions:**
- Mock `list_issues_by_label` to raise an exception.

**Input:**
- Trigger a hunt scan cycle (timer elapses, drain_issues called).

**Expected:**
- Hunt scan still runs despite the issue check failure.
- Warning is logged.

**Assertion pseudocode:**
```
platform.list_issues_by_label = raises(PlatformError)
call_log = []
await engine._drain_issues()  # fails
await engine._run_hunt_scan()  # should still run
ASSERT "hunt_scan" in call_log
ASSERT warning logged
```

### TS-81-E2: Issue fix failure does not block hunt scan

**Requirement:** 81-REQ-1.E2
**Type:** unit
**Description:** Verify that if an issue fix fails, remaining issues are
processed and the hunt scan runs afterward.

**Preconditions:**
- 2 issues: first fails, second succeeds.

**Input:**
- Process both issues, then run hunt scan.

**Expected:**
- Both issues attempted.
- Hunt scan runs after.

**Assertion pseudocode:**
```
platform returns [issue1, issue2]
mock _process_fix to fail on issue1, succeed on issue2
await engine._drain_issues()
ASSERT _process_fix called for both issues
await engine._run_hunt_scan()
ASSERT hunt scan ran
```

### TS-81-E3: Auto mode post-hunt issue creation triggers drain

**Requirement:** 81-REQ-1.E3
**Type:** unit
**Description:** Verify that in --auto mode, issues created during a hunt
scan are processed in the post-hunt drain.

**Preconditions:**
- Engine in auto_fix mode.
- Hunt scan creates 2 issues with `af:fix` label.
- Post-hunt `list_issues_by_label` returns those 2 issues, then 0.

**Input:**
- Run one full cycle: startup drain → hunt scan → post-hunt drain.

**Expected:**
- Post-hunt `_run_issue_check` processes the 2 newly created issues.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform, auto_fix=True)
run full cycle
ASSERT state.issues_fixed == 2  # the auto-created ones
```

### TS-81-E4: Non-TTY disables spinner

**Requirement:** 81-REQ-2.E1
**Type:** unit
**Description:** Verify that ProgressDisplay disables Live spinner on
non-TTY stdout.

**Preconditions:**
- Console with `is_terminal = False`.

**Input:**
- Create and start ProgressDisplay, emit a task event.

**Expected:**
- No Live started. Task events still printed as plain text.

**Assertion pseudocode:**
```
console = Console(file=StringIO())  # non-TTY
progress = ProgressDisplay(theme_with(console))
progress.start()
ASSERT progress._live is None
progress.on_task_event(event)
ASSERT output contains event text
```

### TS-81-E5: Quiet mode suppresses all output

**Requirement:** 81-REQ-2.E2
**Type:** unit
**Description:** Verify that quiet mode suppresses all display output.

**Preconditions:**
- ProgressDisplay created with `quiet=True`.

**Input:**
- Start display, emit activity and task events, call print_status.

**Expected:**
- No output produced.

**Assertion pseudocode:**
```
progress = ProgressDisplay(theme, quiet=True)
progress.start()
progress.on_activity(event)
progress.on_task_event(event)
progress.print_status("test", "bold")
ASSERT output is empty
```

### TS-81-E6: None callbacks produce no display output

**Requirement:** 81-REQ-5.E1
**Type:** unit
**Description:** Verify that omitting callbacks produces no display output
and no exceptions.

**Preconditions:**
- Engine constructed without callbacks.

**Input:**
- Process one issue.

**Expected:**
- No exceptions. No display calls.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform)  # no callbacks
await engine._process_fix(issue)
# no exception raised
ASSERT engine.state.issues_fixed == 1
```

### TS-81-E7: Quiet mode suppresses phase lines

**Requirement:** 81-REQ-3.E1
**Type:** unit
**Description:** Verify that phase lines are suppressed in quiet mode.

**Preconditions:**
- ProgressDisplay with quiet=True, its print_status used as status_callback.

**Input:**
- Engine runs issue check and hunt scan.

**Expected:**
- No phase lines printed.

**Assertion pseudocode:**
```
progress = ProgressDisplay(theme, quiet=True)
engine = NightShiftEngine(config, platform, status_callback=progress.print_status)
await engine._run_issue_check()
ASSERT no output produced
```

### TS-81-E8: Earlier timer shown in idle display

**Requirement:** 81-REQ-4.E1
**Type:** unit
**Description:** Verify that when both timers are pending, the spinner
shows the earlier one.

**Preconditions:**
- Issue check fires in 5 minutes, hunt scan fires in 2 hours.

**Input:**
- Call `_update_idle_spinner(300, 7200)`.

**Expected:**
- Spinner shows "next issue check" (the earlier one), not "next hunt scan".

**Assertion pseudocode:**
```
engine._update_idle_spinner(300, 7200)
ASSERT "issue check" in spinner_text
ASSERT "hunt scan" not in spinner_text
```

## Integration Smoke Tests

### TS-81-SMOKE-1: Full startup with issue-first gate and display

**Execution Path:** Path 1 from design.md
**Description:** Verify the full startup sequence: CLI creates display,
engine drains issues before hunt scan, display shows phase lines and
activity events in correct order.

**Setup:**
- Mock platform with 1 `af:fix` issue (body: "fix linter warning").
- Mock `run_session` to return a canned `SessionOutcome` and emit one
  `ActivityEvent`.
- Mock harvest/push to succeed.
- Real `NightShiftEngine` (not mocked).
- Real `ProgressDisplay` (with StringIO console for capture).

**Trigger:**
- Call `engine.run()` with shutdown requested after startup completes.

**Expected side effects:**
- Phase line "Checking for af:fix issues…" appears in output.
- ActivityEvents from fix session appear in output.
- TaskEvents for skeptic/coder/verifier appear in output.
- Phase line for fix completion appears.
- Hunt scan phase line appears after issues are drained.
- Call order: issue_check → fix pipeline → hunt scan.

**Must NOT satisfy with:**
- NightShiftEngine mocked (must be real to test gate logic).
- `_run_issue_check` or `_run_hunt_scan` mocked (must run real methods).

**Assertion pseudocode:**
```
platform = MockPlatform(issues=[issue1])
console_output = StringIO()
theme = create_theme_with(console_output)
progress = ProgressDisplay(theme)
progress.start()

engine = NightShiftEngine(
    config, platform,
    activity_callback=progress.activity_callback,
    task_callback=progress.task_callback,
    status_callback=progress.print_status,
)
# shutdown after startup
engine.state.is_shutting_down = True  # after first cycle
state = await engine.run()

progress.stop()
output = console_output.getvalue()
ASSERT "af:fix" in output or "issue" in output.lower()
ASSERT "hunt" in output.lower() or "scan" in output.lower()
ASSERT state.issues_fixed >= 1
```

### TS-81-SMOKE-2: Fix session activity display end-to-end

**Execution Path:** Path 2 from design.md
**Description:** Verify that a fix session produces ActivityEvents and
TaskEvents that render correctly through ProgressDisplay.

**Setup:**
- Mock `run_session` to emit 2 ActivityEvents (Read, Edit) and return
  a SessionOutcome.
- Real FixPipeline with callbacks.
- Real ProgressDisplay (StringIO console).

**Trigger:**
- Call `pipeline.process_issue(issue, body="fix this")`.

**Expected side effects:**
- Console output contains tool verbs ("Reading", "Editing").
- Console output contains archetype labels ("[skeptic]", "[coder]", "[verifier]").
- Console output contains completion icons (✔).

**Must NOT satisfy with:**
- FixPipeline mocked (must be real to test callback wiring).
- ProgressDisplay mocked (must render to verify formatting).

**Assertion pseudocode:**
```
console_output = StringIO()
progress = ProgressDisplay(theme_with(console_output))
progress.start()

pipeline = FixPipeline(
    config, platform,
    activity_callback=progress.activity_callback,
    task_callback=progress.task_callback,
)
await pipeline.process_issue(issue, body="fix this")

progress.stop()
output = console_output.getvalue()
ASSERT "skeptic" in output
ASSERT "coder" in output
ASSERT "verifier" in output
ASSERT "✔" in output or "done" in output
```

### TS-81-SMOKE-3: Idle state display end-to-end

**Execution Path:** Path 3 from design.md
**Description:** Verify that during idle periods the spinner shows the
next action time and clears when a phase starts.

**Setup:**
- Mock platform returns 0 issues.
- Real engine with short intervals (2s issue, 5s hunt).
- Real ProgressDisplay (StringIO console).
- Mock datetime.now for deterministic time.

**Trigger:**
- Run engine for 1 tick (idle state), capture spinner text.
- Then let issue timer fire, verify spinner clears.

**Expected side effects:**
- Spinner text contains "Waiting until" and a time in HH:MM format.
- After phase starts, spinner text changes to phase activity.

**Must NOT satisfy with:**
- Engine event loop mocked.
- `_update_idle_spinner` mocked.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform,
    activity_callback=progress.activity_callback,
    status_callback=progress.print_status)
# run 1 tick
await asyncio.sleep(0)  # let one tick execute
spinner = engine._get_idle_text()  # or capture from progress
ASSERT re.search(r"Waiting until \d{2}:\d{2}", spinner)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 81-REQ-1.1 | TS-81-1 | unit |
| 81-REQ-1.2 | TS-81-2 | unit |
| 81-REQ-1.3 | TS-81-3 | unit |
| 81-REQ-1.4 | TS-81-4 | unit |
| 81-REQ-1.5 | TS-81-5 | unit |
| 81-REQ-1.E1 | TS-81-E1 | unit |
| 81-REQ-1.E2 | TS-81-E2 | unit |
| 81-REQ-1.E3 | TS-81-E3 | unit |
| 81-REQ-2.1 | TS-81-6 | integration |
| 81-REQ-2.2 | TS-81-7 | unit |
| 81-REQ-2.3 | TS-81-8 | unit |
| 81-REQ-2.4 | TS-81-9 | unit |
| 81-REQ-2.E1 | TS-81-E4 | unit |
| 81-REQ-2.E2 | TS-81-E5 | unit |
| 81-REQ-3.1 | TS-81-10 | unit |
| 81-REQ-3.2 | TS-81-11 | unit |
| 81-REQ-3.3 | TS-81-12 | unit |
| 81-REQ-3.4 | TS-81-13 | unit |
| 81-REQ-3.5 | TS-81-14 | unit |
| 81-REQ-3.E1 | TS-81-E7 | unit |
| 81-REQ-4.1 | TS-81-15 | unit |
| 81-REQ-4.2 | TS-81-16 | unit |
| 81-REQ-4.E1 | TS-81-E8 | unit |
| 81-REQ-5.1 | TS-81-17 | unit |
| 81-REQ-5.2 | TS-81-18 | unit |
| 81-REQ-5.3 | TS-81-19 | unit |
| 81-REQ-5.E1 | TS-81-E6 | unit |
| Property 1 | TS-81-P1 | property |
| Property 2 | TS-81-P2 | property |
| Property 3 | TS-81-P3 | property |
| Property 4 | TS-81-P4 | property |
| Property 5 | TS-81-P5 | property |
| Property 6 | TS-81-P6 | property |
| Property 7 | TS-81-P7 | property |
| Property 8 | TS-81-P8 | property |
| Path 1 | TS-81-SMOKE-1 | integration |
| Path 2 | TS-81-SMOKE-2 | integration |
| Path 3 | TS-81-SMOKE-3 | integration |
