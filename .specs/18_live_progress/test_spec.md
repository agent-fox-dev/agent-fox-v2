# Test Specification: Live Progress Line

## Overview

Tests validate the live progress display components: event types,
argument abbreviation, spinner line rendering, permanent line output,
quiet/non-TTY behavior, and callback wiring. Property tests cover
truncation invariants and display safety.

## Test Cases

### TS-18-1: Progress display starts and stops

**Requirement:** 18-REQ-1.1, 18-REQ-1.3
**Type:** unit
**Description:** ProgressDisplay start/stop lifecycle works cleanly.

**Preconditions:**
- ProgressDisplay created with a StringIO-backed console.

**Input:**
- Call `start()` then `stop()`.

**Expected:**
- No exceptions raised.
- After `stop()`, no spinner content remains on the console.

**Assertion pseudocode:**
```
display = ProgressDisplay(theme, quiet=False)
display.start()
display.stop()
ASSERT no exception raised
```

---

### TS-18-2: Activity event updates spinner line

**Requirement:** 18-REQ-2.1, 18-REQ-3.1, 18-REQ-3.4
**Type:** unit
**Description:** Calling on_activity updates the displayed text.

**Preconditions:**
- ProgressDisplay created and started.

**Input:**
- `ActivityEvent(node_id="03_session:2", tool_name="Read", argument="config.py")`

**Expected:**
- Spinner line contains `[03_session:2] Read config.py`.

**Assertion pseudocode:**
```
display.on_activity(ActivityEvent("03_session:2", "Read", "config.py"))
output = capture_display()
ASSERT "[03_session:2] Read config.py" IN output
```

---

### TS-18-3: Thinking state shown when no tool use

**Requirement:** 18-REQ-2.2
**Type:** unit
**Description:** When model is thinking, spinner shows "thinking...".

**Preconditions:**
- ProgressDisplay created and started.

**Input:**
- `ActivityEvent(node_id="03_session:2", tool_name="thinking...", argument="")`

**Expected:**
- Spinner line contains `[03_session:2] thinking...`.

**Assertion pseudocode:**
```
display.on_activity(ActivityEvent("03_session:2", "thinking...", ""))
output = capture_display()
ASSERT "[03_session:2] thinking..." IN output
```

---

### TS-18-4: Task completion prints permanent line

**Requirement:** 18-REQ-4.1, 18-REQ-4.3
**Type:** unit
**Description:** Completed task emits a styled permanent line.

**Preconditions:**
- ProgressDisplay created with a StringIO-backed console (non-live mode).

**Input:**
- `TaskEvent(node_id="03_session:2", status="completed", duration_s=45.0)`

**Expected:**
- Output contains check mark, node ID, "done", and duration.

**Assertion pseudocode:**
```
display.on_task_event(TaskEvent("03_session:2", "completed", 45.0))
output = capture_output()
ASSERT "\u2714" IN output
ASSERT "03_session:2" IN output
ASSERT "done" IN output
ASSERT "45s" IN output
```

---

### TS-18-5: Task failure prints permanent line

**Requirement:** 18-REQ-4.2
**Type:** unit
**Description:** Failed task emits a permanent error line.

**Preconditions:**
- ProgressDisplay created with a StringIO-backed console.

**Input:**
- `TaskEvent(node_id="03_session:2", status="failed", duration_s=12.0, error_message="test error")`

**Expected:**
- Output contains cross mark, node ID, and "failed".

**Assertion pseudocode:**
```
display.on_task_event(TaskEvent("03_session:2", "failed", 12.0, "test error"))
output = capture_output()
ASSERT "\u2718" IN output
ASSERT "03_session:2" IN output
ASSERT "failed" IN output
```

---

### TS-18-6: Abbreviate file path to basename

**Requirement:** 18-REQ-2.E2
**Type:** unit
**Description:** File paths are abbreviated to basename only.

**Preconditions:** None.

**Input:**
- `"/Users/dev/workspace/project/src/agent_fox/core/config.py"`

**Expected:**
- `"config.py"`

**Assertion pseudocode:**
```
result = abbreviate_arg("/Users/dev/workspace/project/src/agent_fox/core/config.py")
ASSERT result == "config.py"
```

---

### TS-18-7: Abbreviate long string with ellipsis

**Requirement:** 18-REQ-2.E3
**Type:** unit
**Description:** Non-path strings exceeding max_len are truncated.

**Preconditions:** None.

**Input:**
- `"This is a very long argument that exceeds thirty characters easily"`
- `max_len=30`

**Expected:**
- Result is 30 characters ending with "...".

**Assertion pseudocode:**
```
result = abbreviate_arg("This is a very long argument that exceeds thirty characters easily", max_len=30)
ASSERT len(result) == 30
ASSERT result.endswith("...")
```

---

### TS-18-8: Session runner activity callback invoked

**Requirement:** 18-REQ-2.1, 18-REQ-2.3
**Type:** integration
**Description:** run_session invokes the activity callback for SDK tool-use messages.

**Preconditions:**
- Mock SDK client yielding a tool-use message then a ResultMessage.

**Input:**
- `run_session(config, workspace, system_prompt, task_prompt, activity_callback=mock_cb)`

**Expected:**
- `mock_cb` called at least once with an `ActivityEvent`.

**Assertion pseudocode:**
```
events = []
await run_session(..., activity_callback=lambda e: events.append(e))
ASSERT len(events) >= 1
ASSERT isinstance(events[0], ActivityEvent)
```

---

### TS-18-9: Session runner works without callback

**Requirement:** 18-REQ-2.3
**Type:** unit
**Description:** run_session without activity_callback behaves identically.

**Preconditions:**
- Mock SDK client yielding a ResultMessage.

**Input:**
- `run_session(config, workspace, system_prompt, task_prompt)` (no callback)

**Expected:**
- Returns SessionOutcome without error.

**Assertion pseudocode:**
```
outcome = await run_session(config, workspace, system_prompt, task_prompt)
ASSERT outcome.status == "completed"
```

---

### TS-18-10: Orchestrator emits task callback

**Requirement:** 18-REQ-5.4
**Type:** integration
**Description:** Orchestrator calls task_callback on task completion.

**Preconditions:**
- Orchestrator with a mock session runner that completes immediately.
- task_callback provided.

**Input:**
- Run orchestrator with a single-task plan.

**Expected:**
- task_callback called with a TaskEvent for the completed task.

**Assertion pseudocode:**
```
events = []
orchestrator = Orchestrator(..., task_callback=lambda e: events.append(e))
await orchestrator.run()
ASSERT len(events) >= 1
ASSERT events[0].status == "completed"
```

## Edge Case Tests

### TS-18-E1: Quiet mode suppresses all output

**Requirement:** 18-REQ-1.E1
**Type:** unit
**Description:** ProgressDisplay with quiet=True produces no output.

**Preconditions:**
- ProgressDisplay created with `quiet=True` and StringIO-backed console.

**Input:**
- Call `start()`, `on_activity(...)`, `on_task_event(...)`, `stop()`.

**Expected:**
- Console buffer is empty.

**Assertion pseudocode:**
```
display = ProgressDisplay(theme, quiet=True)
display.start()
display.on_activity(ActivityEvent("x:1", "Read", "foo.py"))
display.on_task_event(TaskEvent("x:1", "completed", 1.0))
display.stop()
ASSERT buf.getvalue() == ""
```

---

### TS-18-E2: Non-TTY disables spinner, prints permanent lines

**Requirement:** 18-REQ-1.E2, 18-REQ-4.E1
**Type:** unit
**Description:** Non-TTY console prints task events as plain text.

**Preconditions:**
- Console created with `force_terminal=False` (non-TTY).

**Input:**
- Call `on_task_event(TaskEvent("x:1", "completed", 10.0))`.

**Expected:**
- Output contains node ID and "done" without ANSI escapes.

**Assertion pseudocode:**
```
display = ProgressDisplay(theme_non_tty)
display.start()
display.on_task_event(TaskEvent("x:1", "completed", 10.0))
output = buf.getvalue()
ASSERT "x:1" IN output
ASSERT "done" IN output
ASSERT "\x1b[" NOT IN output
```

---

### TS-18-E3: Activity callback exception does not crash session

**Requirement:** 18-REQ-2.E1
**Type:** unit
**Description:** Exceptions in activity_callback are caught.

**Preconditions:**
- Mock SDK client yielding a tool-use message then ResultMessage.

**Input:**
- `run_session(..., activity_callback=lambda e: 1/0)` (raises ZeroDivisionError)

**Expected:**
- Session completes normally despite callback exception.

**Assertion pseudocode:**
```
outcome = await run_session(..., activity_callback=raising_cb)
ASSERT outcome.status == "completed"
```

---

### TS-18-E4: Default terminal width fallback

**Requirement:** 18-REQ-3.E1
**Type:** unit
**Description:** When terminal width is unavailable, default to 80.

**Preconditions:**
- Console with width detection mocked to raise.

**Input:**
- Activity event with long text.

**Expected:**
- Spinner line truncated to 80 characters.

**Assertion pseudocode:**
```
display = ProgressDisplay(theme_no_width)
display.on_activity(ActivityEvent("x:1", "Read", "a" * 200))
line = get_spinner_line(display)
ASSERT len(line) <= 80
```

---

### TS-18-E5: Progress display stopped on orchestrator exception

**Requirement:** 18-REQ-5.E1
**Type:** integration
**Description:** If orchestrator raises, progress display is still stopped.

**Preconditions:**
- Orchestrator that raises during execution.

**Input:**
- Run code command with failing orchestrator.

**Expected:**
- Progress display is stopped (no dangling spinner).

**Assertion pseudocode:**
```
# progress.stop() called in finally block
ASSERT display.is_stopped == True
```

## Property Test Cases

### TS-18-P1: Spinner Line Never Exceeds Terminal Width

**Property:** Property 1 from design.md
**Validates:** 18-REQ-3.3
**Type:** property
**Description:** For any text and terminal width, spinner line fits.

**For any:** `text: str` (length 0..200), `width: int` (20..200)
**Invariant:** `len(render_spinner_line(text, width)) <= width`

**Assertion pseudocode:**
```
FOR ANY text IN text(0..200), width IN integers(20..200):
    line = render_spinner_line(text, width)
    ASSERT len(line) <= width
```

---

### TS-18-P2: Abbreviation Idempotence

**Property:** Property 2 from design.md
**Validates:** 18-REQ-2.E2, 18-REQ-2.E3
**Type:** property
**Description:** Abbreviating twice gives the same result as once.

**For any:** `s: str` (length 0..500)
**Invariant:** `abbreviate_arg(abbreviate_arg(s)) == abbreviate_arg(s)`

**Assertion pseudocode:**
```
FOR ANY s IN text(0..500):
    ASSERT abbreviate_arg(abbreviate_arg(s)) == abbreviate_arg(s)
```

---

### TS-18-P3: Quiet Produces No Output

**Property:** Property 3 from design.md
**Validates:** 18-REQ-1.E1
**Type:** property
**Description:** Quiet display never writes to the console.

**For any:** sequence of 1..20 `ActivityEvent`s and 0..5 `TaskEvent`s
**Invariant:** Console buffer is empty after all events.

**Assertion pseudocode:**
```
FOR ANY events IN lists(activity_events, 1..20), task_events IN lists(task_events, 0..5):
    display = ProgressDisplay(theme, quiet=True)
    display.start()
    for e in events: display.on_activity(e)
    for t in task_events: display.on_task_event(t)
    display.stop()
    ASSERT buf.getvalue() == ""
```

---

### TS-18-P4: Permanent Lines Contain Node ID

**Property:** Property 4 from design.md
**Validates:** 18-REQ-4.1, 18-REQ-4.2
**Type:** property
**Description:** Every permanent line includes the node ID and status.

**For any:** `node_id: str` (non-empty), `status` in {"completed", "failed", "blocked"}
**Invariant:** Output contains `node_id`.

**Assertion pseudocode:**
```
FOR ANY node_id IN text(1..50), status IN sampled_from(["completed", "failed", "blocked"]):
    display.on_task_event(TaskEvent(node_id, status, 1.0))
    ASSERT node_id IN buf.getvalue()
```

---

### TS-18-P5: Session Outcome Unchanged By Callback

**Property:** Property 5 from design.md
**Validates:** 18-REQ-2.3
**Type:** property
**Description:** Presence of activity callback does not alter session outcome.

**For any:** valid session configuration
**Invariant:** `run_session(cb=None)` and `run_session(cb=noop)` produce equivalent outcomes.

**Assertion pseudocode:**
```
outcome_without = await run_session(...)
outcome_with = await run_session(..., activity_callback=lambda e: None)
ASSERT outcome_without.status == outcome_with.status
ASSERT outcome_without.input_tokens == outcome_with.input_tokens
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 18-REQ-1.1 | TS-18-1 | unit |
| 18-REQ-1.2 | TS-18-1 | unit |
| 18-REQ-1.3 | TS-18-1 | unit |
| 18-REQ-1.E1 | TS-18-E1 | unit |
| 18-REQ-1.E2 | TS-18-E2 | unit |
| 18-REQ-2.1 | TS-18-2, TS-18-8 | unit, integration |
| 18-REQ-2.2 | TS-18-3 | unit |
| 18-REQ-2.3 | TS-18-9 | unit |
| 18-REQ-2.E1 | TS-18-E3 | unit |
| 18-REQ-2.E2 | TS-18-6 | unit |
| 18-REQ-2.E3 | TS-18-7 | unit |
| 18-REQ-3.1 | TS-18-2 | unit |
| 18-REQ-3.2 | TS-18-2 | unit |
| 18-REQ-3.3 | TS-18-P1 | property |
| 18-REQ-3.4 | TS-18-2 | unit |
| 18-REQ-3.E1 | TS-18-E4 | unit |
| 18-REQ-4.1 | TS-18-4 | unit |
| 18-REQ-4.2 | TS-18-5 | unit |
| 18-REQ-4.3 | TS-18-4 | unit |
| 18-REQ-4.4 | TS-18-4 | unit |
| 18-REQ-4.E1 | TS-18-E2 | unit |
| 18-REQ-5.1 | TS-18-10 | integration |
| 18-REQ-5.2 | TS-18-10 | integration |
| 18-REQ-5.3 | TS-18-8 | integration |
| 18-REQ-5.4 | TS-18-10 | integration |
| 18-REQ-5.E1 | TS-18-E5 | integration |
| 18-REQ-6.1 | TS-18-2 | unit |
| 18-REQ-6.2 | TS-18-2 | unit |
| 18-REQ-6.E1 | TS-18-4 | unit |
| Property 1 | TS-18-P1 | property |
| Property 2 | TS-18-P2 | property |
| Property 3 | TS-18-P3 | property |
| Property 4 | TS-18-P4 | property |
| Property 5 | TS-18-P5 | property |
