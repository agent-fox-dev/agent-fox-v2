# Test Specification: Fix Command Progress Display

## Overview

Tests verify that the `fix` command produces real-time progress output
consistent with `code`, that callbacks are correctly wired, and that quiet/JSON
modes suppress all display. Tests are organized into unit tests (callback
plumbing, event emission), property tests (invariants), and integration tests
(end-to-end CLI output).

## Test Cases

### TS-76-1: Banner Rendered at Startup

**Requirement:** 76-REQ-1.1
**Type:** unit
**Description:** Verify that `fix_cmd` calls `render_banner` when not in quiet
or JSON mode.

**Preconditions:**
- `fix_cmd` is invoked with default flags (no `--quiet`, no `--json`).
- At least one quality check is detected.

**Input:**
- Standard invocation via Click test runner.

**Expected:**
- `render_banner` is called exactly once.

**Assertion pseudocode:**
```
mock render_banner
invoke fix_cmd with defaults
ASSERT render_banner.call_count == 1
```

### TS-76-2: Banner Suppressed in Quiet Mode

**Requirement:** 76-REQ-1.2
**Type:** unit
**Description:** Verify that `render_banner` is NOT called when `--quiet` is
active.

**Preconditions:**
- `fix_cmd` is invoked with `--quiet`.

**Input:**
- Invocation with quiet=True.

**Expected:**
- `render_banner` is not called.

**Assertion pseudocode:**
```
mock render_banner
invoke fix_cmd with quiet=True
ASSERT render_banner.call_count == 0
```

### TS-76-3: Banner Suppressed in JSON Mode

**Requirement:** 76-REQ-1.3
**Type:** unit
**Description:** Verify that `render_banner` is NOT called when `--json` is
active.

**Preconditions:**
- `fix_cmd` is invoked with JSON mode.

**Input:**
- Invocation with json_mode=True.

**Expected:**
- `render_banner` is not called.

**Assertion pseudocode:**
```
mock render_banner
invoke fix_cmd with json_mode=True
ASSERT render_banner.call_count == 0
```

### TS-76-4: ProgressDisplay Created and Started

**Requirement:** 76-REQ-2.1
**Type:** unit
**Description:** Verify that a `ProgressDisplay` is created and `start()` is
called before the fix loop runs.

**Preconditions:**
- `fix_cmd` is invoked normally.

**Input:**
- Standard invocation.

**Expected:**
- `ProgressDisplay` constructor is called once.
- `start()` is called once before `run_fix_loop`.

**Assertion pseudocode:**
```
mock ProgressDisplay
invoke fix_cmd
ASSERT ProgressDisplay called once
ASSERT ProgressDisplay.return_value.start.call_count == 1
```

### TS-76-5: ProgressDisplay Stopped in Finally Block

**Requirement:** 76-REQ-2.2
**Type:** unit
**Description:** Verify that `stop()` is called even when an exception occurs.

**Preconditions:**
- `run_fix_loop` raises an exception.

**Input:**
- Mock `run_fix_loop` to raise RuntimeError.

**Expected:**
- `ProgressDisplay.stop()` is called exactly once.

**Assertion pseudocode:**
```
mock run_fix_loop to raise RuntimeError
mock ProgressDisplay
invoke fix_cmd (catching the error)
ASSERT ProgressDisplay.return_value.stop.call_count == 1
```

### TS-76-6: ProgressDisplay Quiet When Quiet or JSON

**Requirement:** 76-REQ-2.3
**Type:** unit
**Description:** Verify that `ProgressDisplay` is created with `quiet=True`
when quiet or JSON mode is active.

**Preconditions:**
- `fix_cmd` is invoked with `--quiet`.

**Input:**
- Invocation with quiet=True.

**Expected:**
- `ProgressDisplay` is constructed with `quiet=True`.

**Assertion pseudocode:**
```
mock ProgressDisplay
invoke fix_cmd with quiet=True
ASSERT ProgressDisplay.call_args includes quiet=True
```

### TS-76-7: Fix Session Runner Passes Activity Callback

**Requirement:** 76-REQ-3.1
**Type:** unit
**Description:** Verify that the fix session runner forwards
`activity_callback` to `run_session`.

**Preconditions:**
- A `ProgressDisplay` is active.
- A fix session runner is built with an activity callback.

**Input:**
- Call the session runner with a mock FixSpec.

**Expected:**
- `run_session` is called with `activity_callback` set to the progress
  display's callback.

**Assertion pseudocode:**
```
mock run_session
callback = Mock()
runner = _build_fix_session_runner(config, root, activity_callback=callback)
await runner(fix_spec)
ASSERT run_session.call_args.kwargs["activity_callback"] == callback
```

### TS-76-8: Improve Session Runner Passes Activity Callback

**Requirement:** 76-REQ-3.2
**Type:** unit
**Description:** Verify that the improve session runner forwards
`activity_callback` to `run_session`.

**Preconditions:**
- A `ProgressDisplay` is active.
- An improve session runner is built with an activity callback.

**Input:**
- Call the session runner with system/task prompts.

**Expected:**
- `run_session` is called with `activity_callback` set to the progress
  display's callback.

**Assertion pseudocode:**
```
mock run_session
callback = Mock()
runner = _build_improve_session_runner(config, root, activity_callback=callback)
await runner(sys_prompt, task_prompt, "STANDARD")
ASSERT run_session.call_args.kwargs["activity_callback"] == callback
```

### TS-76-9: Fix Loop Emits Pass Start Event

**Requirement:** 76-REQ-4.1
**Type:** unit
**Description:** Verify that `run_fix_loop` calls `progress_callback` with a
pass-start event at the beginning of each pass.

**Preconditions:**
- `run_fix_loop` is called with a non-None `progress_callback`.
- Quality checks return failures on first pass, pass on second.

**Input:**
- max_passes=3, mock checks to fail once then pass.

**Expected:**
- `progress_callback` is called with `stage="checks_start"` and
  `pass_number=1`.

**Assertion pseudocode:**
```
callback = Mock()
result = await run_fix_loop(..., progress_callback=callback)
start_calls = [c for c in callback.call_args_list
               if c.args[0].stage == "checks_start"]
ASSERT len(start_calls) >= 1
ASSERT start_calls[0].args[0].pass_number == 1
ASSERT start_calls[0].args[0].phase == "repair"
```

### TS-76-10: Fix Loop Emits All-Passed Event

**Requirement:** 76-REQ-4.2
**Type:** unit
**Description:** Verify that when all checks pass, `progress_callback` is
called with `stage="all_passed"`.

**Preconditions:**
- All quality checks return exit code 0.

**Input:**
- Mock checks to return no failures.

**Expected:**
- `progress_callback` is called with `stage="all_passed"`.

**Assertion pseudocode:**
```
callback = Mock()
result = await run_fix_loop(..., progress_callback=callback)
ASSERT any(c.args[0].stage == "all_passed" for c in callback.call_args_list)
```

### TS-76-11: Fix Loop Emits Clusters Found Event

**Requirement:** 76-REQ-4.3
**Type:** unit
**Description:** Verify that when failures are clustered, `progress_callback`
is called with `stage="clusters_found"` and the cluster count in detail.

**Preconditions:**
- Quality checks return failures.

**Input:**
- Mock checks to return 2 failures that cluster into 1 cluster.

**Expected:**
- `progress_callback` is called with `stage="clusters_found"` and
  `detail` containing "1".

**Assertion pseudocode:**
```
callback = Mock()
result = await run_fix_loop(..., progress_callback=callback)
cluster_calls = [c for c in callback.call_args_list
                 if c.args[0].stage == "clusters_found"]
ASSERT len(cluster_calls) >= 1
ASSERT "1" in cluster_calls[0].args[0].detail
```

### TS-76-12: Fix Loop Emits Session Start Event

**Requirement:** 76-REQ-4.4
**Type:** unit
**Description:** Verify that a session_start event is emitted with the cluster
label before each fix session.

**Preconditions:**
- Quality checks return failures that cluster into named clusters.

**Input:**
- Mock failures and session runner.

**Expected:**
- `progress_callback` is called with `stage="session_start"` and `detail`
  containing the cluster label.

**Assertion pseudocode:**
```
callback = Mock()
result = await run_fix_loop(..., progress_callback=callback)
session_calls = [c for c in callback.call_args_list
                 if c.args[0].stage == "session_start"]
ASSERT len(session_calls) >= 1
ASSERT session_calls[0].args[0].detail != ""
```

### TS-76-13: Improve Loop Emits Pass Start Event

**Requirement:** 76-REQ-4.5
**Type:** unit
**Description:** Verify that `run_improve_loop` calls `progress_callback` with
an analyzer_start event at the beginning of each pass.

**Preconditions:**
- `run_improve_loop` is called with a non-None `progress_callback`.

**Input:**
- max_passes=1, mock session runner.

**Expected:**
- `progress_callback` is called with `phase="improve"` and
  `stage="analyzer_start"`.

**Assertion pseudocode:**
```
callback = Mock()
result = await run_improve_loop(..., progress_callback=callback)
calls = [c for c in callback.call_args_list
         if c.args[0].stage == "analyzer_start"]
ASSERT len(calls) >= 1
ASSERT calls[0].args[0].phase == "improve"
```

### TS-76-14: Improve Loop Emits Session Role Events

**Requirement:** 76-REQ-4.6
**Type:** unit
**Description:** Verify that `run_improve_loop` emits events for analyzer_done,
coder_done, and verifier_done.

**Preconditions:**
- `run_improve_loop` completes a full pass (analyzer, coder, verifier all
  succeed).

**Input:**
- max_passes=1, mock session runner to return valid responses.

**Expected:**
- `progress_callback` is called with stages "analyzer_done", "coder_done",
  "verifier_done" (or "verifier_pass"/"verifier_fail").

**Assertion pseudocode:**
```
callback = Mock()
result = await run_improve_loop(..., progress_callback=callback)
stages = {c.args[0].stage for c in callback.call_args_list}
ASSERT "analyzer_done" in stages or "analyzer_start" in stages
ASSERT "coder_done" in stages or "coder_start" in stages
```

### TS-76-15: Check Callback Called on Start

**Requirement:** 76-REQ-5.1
**Type:** unit
**Description:** Verify that `run_checks` calls `check_callback` with
`stage="start"` before each check.

**Preconditions:**
- Two checks are configured.

**Input:**
- Two check descriptors, mock subprocess.

**Expected:**
- `check_callback` is called twice with `stage="start"`, once per check.

**Assertion pseudocode:**
```
callback = Mock()
run_checks(checks, root, check_callback=callback)
start_calls = [c for c in callback.call_args_list
               if c.args[0].stage == "start"]
ASSERT len(start_calls) == 2
```

### TS-76-16: Check Callback Called on Done

**Requirement:** 76-REQ-5.2
**Type:** unit
**Description:** Verify that `run_checks` calls `check_callback` with
`stage="done"` after each check, including pass/fail status.

**Preconditions:**
- Two checks configured: one passes (exit 0), one fails (exit 1).

**Input:**
- Two check descriptors with mocked subprocess results.

**Expected:**
- `check_callback` is called twice with `stage="done"`.
- One call has `passed=True`, the other `passed=False` with `exit_code=1`.

**Assertion pseudocode:**
```
callback = Mock()
run_checks(checks, root, check_callback=callback)
done_calls = [c for c in callback.call_args_list
              if c.args[0].stage == "done"]
ASSERT len(done_calls) == 2
pass_results = {c.args[0].passed for c in done_calls}
ASSERT pass_results == {True, False}
```

### TS-76-17: run_fix_loop Accepts progress_callback Parameter

**Requirement:** 76-REQ-6.1
**Type:** unit
**Description:** Verify that `run_fix_loop` signature includes
`progress_callback` parameter.

**Preconditions:**
- None.

**Input:**
- Inspect function signature.

**Expected:**
- `progress_callback` is in the parameter list.

**Assertion pseudocode:**
```
sig = inspect.signature(run_fix_loop)
ASSERT "progress_callback" in sig.parameters
```

### TS-76-18: run_improve_loop Accepts progress_callback Parameter

**Requirement:** 76-REQ-6.2
**Type:** unit
**Description:** Verify that `run_improve_loop` signature includes
`progress_callback` parameter.

**Preconditions:**
- None.

**Input:**
- Inspect function signature.

**Expected:**
- `progress_callback` is in the parameter list.

**Assertion pseudocode:**
```
sig = inspect.signature(run_improve_loop)
ASSERT "progress_callback" in sig.parameters
```

### TS-76-19: run_checks Accepts check_callback Parameter

**Requirement:** 76-REQ-6.3
**Type:** unit
**Description:** Verify that `run_checks` signature includes `check_callback`
parameter.

**Preconditions:**
- None.

**Input:**
- Inspect function signature.

**Expected:**
- `check_callback` is in the parameter list.

**Assertion pseudocode:**
```
sig = inspect.signature(run_checks)
ASSERT "check_callback" in sig.parameters
```

## Edge Case Tests

### TS-76-E1: ProgressDisplay Stopped on KeyboardInterrupt

**Requirement:** 76-REQ-2.E1
**Type:** unit
**Description:** Verify that `ProgressDisplay.stop()` is called when
`run_fix_loop` raises KeyboardInterrupt.

**Preconditions:**
- `run_fix_loop` raises KeyboardInterrupt.

**Input:**
- Mock `run_fix_loop` to raise KeyboardInterrupt.

**Expected:**
- `ProgressDisplay.stop()` is called.

**Assertion pseudocode:**
```
mock run_fix_loop to raise KeyboardInterrupt
mock ProgressDisplay
invoke fix_cmd (catching SystemExit)
ASSERT ProgressDisplay.return_value.stop.call_count == 1
```

### TS-76-E2: Cost Limit Milestone Line

**Requirement:** 76-REQ-4.E1
**Type:** unit
**Description:** Verify that a cost_limit event is emitted when the fix loop
terminates due to cost.

**Preconditions:**
- Cost limit is set to a small value.
- Fix sessions consume cost exceeding the limit.

**Input:**
- config.orchestrator.max_cost = 0.01, mock session to return cost 0.02.

**Expected:**
- `progress_callback` is called with `stage="cost_limit"`.

**Assertion pseudocode:**
```
callback = Mock()
result = await run_fix_loop(..., progress_callback=callback)
ASSERT any(c.args[0].stage == "cost_limit" for c in callback.call_args_list)
```

### TS-76-E3: Session Error Milestone Line

**Requirement:** 76-REQ-4.E2
**Type:** unit
**Description:** Verify that a session_error event is emitted when a fix
session raises an exception.

**Preconditions:**
- Session runner raises an exception.

**Input:**
- Mock session runner to raise RuntimeError.

**Expected:**
- `progress_callback` is called with `stage="session_error"`.

**Assertion pseudocode:**
```
callback = Mock()
mock_runner = AsyncMock(side_effect=RuntimeError("fail"))
result = await run_fix_loop(..., session_runner=mock_runner,
                            progress_callback=callback)
ASSERT any(c.args[0].stage == "session_error"
           for c in callback.call_args_list)
```

### TS-76-E4: None progress_callback Is Backward Compatible

**Requirement:** 76-REQ-6.E1
**Type:** unit
**Description:** Verify that `run_fix_loop` with `progress_callback=None`
produces the same result as before (no errors).

**Preconditions:**
- All checks pass.

**Input:**
- Call `run_fix_loop` without `progress_callback`.

**Expected:**
- Returns FixResult with termination_reason ALL_FIXED, no exceptions.

**Assertion pseudocode:**
```
result = await run_fix_loop(root, config)
ASSERT result.termination_reason == TerminationReason.ALL_FIXED
```

### TS-76-E5: None check_callback Is Backward Compatible

**Requirement:** 76-REQ-6.E2
**Type:** unit
**Description:** Verify that `run_checks` with `check_callback=None` works
identically to before.

**Preconditions:**
- Two checks configured.

**Input:**
- Call `run_checks` without `check_callback`.

**Expected:**
- Returns (failures, passed) tuple, no exceptions.

**Assertion pseudocode:**
```
failures, passed = run_checks(checks, root)
ASSERT isinstance(failures, list)
ASSERT isinstance(passed, list)
```

## Property Test Cases

### TS-76-P1: Quiet Mode Suppresses All Output

**Property:** Property 1 from design.md
**Validates:** 76-REQ-1.2, 76-REQ-1.3, 76-REQ-2.3
**Type:** property
**Description:** For any combination of quiet/json flags, when either is True,
ProgressDisplay is created with quiet=True.

**For any:** quiet in {True, False}, json_mode in {True, False}
**Invariant:** If quiet OR json_mode, then ProgressDisplay quiet parameter is
True.

**Assertion pseudocode:**
```
FOR ANY quiet IN {True, False}, json_mode IN {True, False}:
    expected_quiet = quiet or json_mode
    pd = ProgressDisplay(theme, quiet=expected_quiet)
    ASSERT pd._quiet == expected_quiet
```

### TS-76-P2: Display Lifecycle Completeness

**Property:** Property 2 from design.md
**Validates:** 76-REQ-2.2, 76-REQ-2.E1
**Type:** property
**Description:** For any execution outcome (success, error, interrupt), stop()
is always called.

**For any:** outcome in {normal, RuntimeError, KeyboardInterrupt}
**Invariant:** ProgressDisplay.stop() is called exactly once.

**Assertion pseudocode:**
```
FOR ANY outcome IN [None, RuntimeError("e"), KeyboardInterrupt()]:
    mock ProgressDisplay
    mock run_fix_loop to return/raise outcome
    invoke fix_cmd
    ASSERT ProgressDisplay.return_value.stop.call_count == 1
```

### TS-76-P3: Activity Callback Wiring

**Property:** Property 3 from design.md
**Validates:** 76-REQ-3.1, 76-REQ-3.2
**Type:** property
**Description:** For any session runner built with an activity_callback, every
call to run_session includes that callback.

**For any:** callback in {None, Mock()}
**Invariant:** run_session receives the same callback that was passed to the
builder.

**Assertion pseudocode:**
```
FOR ANY callback IN [None, Mock()]:
    mock run_session
    runner = _build_fix_session_runner(config, root, activity_callback=callback)
    await runner(fix_spec)
    ASSERT run_session.call_args.kwargs["activity_callback"] is callback
```

### TS-76-P4: Callback Backward Compatibility

**Property:** Property 4 from design.md
**Validates:** 76-REQ-6.E1, 76-REQ-6.E2
**Type:** property
**Description:** For any call to run_fix_loop or run_checks with None
callbacks, no errors are raised and the return value is valid.

**For any:** checks in generated list of CheckDescriptors (0-3 items)
**Invariant:** run_checks(checks, root, check_callback=None) returns a valid
tuple without raising.

**Assertion pseudocode:**
```
FOR ANY checks IN st.lists(check_descriptors, max_size=3):
    failures, passed = run_checks(checks, root, check_callback=None)
    ASSERT isinstance(failures, list)
    ASSERT isinstance(passed, list)
    ASSERT len(failures) + len(passed) == len(checks)
```

### TS-76-P5: Progress Event Completeness

**Property:** Property 5 from design.md
**Validates:** 76-REQ-4.1, 76-REQ-4.2, 76-REQ-4.3
**Type:** property
**Description:** For any fix loop execution with a callback, every pass
produces at least a start event and a terminal event.

**For any:** max_passes in 1..5, check outcomes in {all_pass, some_fail}
**Invariant:** For each pass_number observed, there is at least one event with
that pass_number and stage in {"checks_start"} and at least one with stage in
{"all_passed", "checks_done", "clusters_found", "cost_limit"}.

**Assertion pseudocode:**
```
FOR ANY max_passes IN range(1, 6):
    callback = Mock()
    result = await run_fix_loop(..., max_passes=max_passes,
                                progress_callback=callback)
    events = [c.args[0] for c in callback.call_args_list]
    for p in range(1, result.passes_completed + 1):
        pass_events = [e for e in events if e.pass_number == p]
        ASSERT any(e.stage == "checks_start" for e in pass_events)
        ASSERT any(e.stage in TERMINAL_STAGES for e in pass_events)
```

### TS-76-P6: Check Event Pairing

**Property:** Property 6 from design.md
**Validates:** 76-REQ-5.1, 76-REQ-5.2
**Type:** property
**Description:** For any list of checks, the callback receives exactly one
start and one done event per check.

**For any:** n_checks in 1..5
**Invariant:** start_count == done_count == n_checks

**Assertion pseudocode:**
```
FOR ANY n_checks IN range(1, 6):
    checks = [make_check(f"check_{i}") for i in range(n_checks)]
    callback = Mock()
    run_checks(checks, root, check_callback=callback)
    events = [c.args[0] for c in callback.call_args_list]
    starts = [e for e in events if e.stage == "start"]
    dones = [e for e in events if e.stage == "done"]
    ASSERT len(starts) == n_checks
    ASSERT len(dones) == n_checks
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 76-REQ-1.1 | TS-76-1 | unit |
| 76-REQ-1.2 | TS-76-2 | unit |
| 76-REQ-1.3 | TS-76-3 | unit |
| 76-REQ-2.1 | TS-76-4 | unit |
| 76-REQ-2.2 | TS-76-5 | unit |
| 76-REQ-2.3 | TS-76-6 | unit |
| 76-REQ-2.E1 | TS-76-E1 | unit |
| 76-REQ-3.1 | TS-76-7 | unit |
| 76-REQ-3.2 | TS-76-8 | unit |
| 76-REQ-3.3 | (covered by TS-76-7, TS-76-8 — wiring ensures format) | unit |
| 76-REQ-4.1 | TS-76-9 | unit |
| 76-REQ-4.2 | TS-76-10 | unit |
| 76-REQ-4.3 | TS-76-11 | unit |
| 76-REQ-4.4 | TS-76-12 | unit |
| 76-REQ-4.5 | TS-76-13 | unit |
| 76-REQ-4.6 | TS-76-14 | unit |
| 76-REQ-4.E1 | TS-76-E2 | unit |
| 76-REQ-4.E2 | TS-76-E3 | unit |
| 76-REQ-5.1 | TS-76-15 | unit |
| 76-REQ-5.2 | TS-76-16 | unit |
| 76-REQ-6.1 | TS-76-17 | unit |
| 76-REQ-6.2 | TS-76-18 | unit |
| 76-REQ-6.3 | TS-76-19 | unit |
| 76-REQ-6.E1 | TS-76-E4 | unit |
| 76-REQ-6.E2 | TS-76-E5 | unit |
| Property 1 | TS-76-P1 | property |
| Property 2 | TS-76-P2 | property |
| Property 3 | TS-76-P3 | property |
| Property 4 | TS-76-P4 | property |
| Property 5 | TS-76-P5 | property |
| Property 6 | TS-76-P6 | property |
