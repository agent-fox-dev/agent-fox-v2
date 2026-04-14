# Test Specification: Agent Conversation Trace

## Overview

Tests validate that the `AgentTraceSink` correctly captures conversation-level
events to a JSONL file, that tool input truncation works correctly, that the
old `JsonlSink` is fully removed, and that audit retention does not touch
agent trace files. Test cases map 1:1 to acceptance criteria and correctness
properties.

## Test Cases

### TS-103-1: AgentTraceSink creates file on first write

**Requirement:** 103-REQ-1.2
**Type:** unit
**Description:** Verify the trace file is created at the correct path on first event.

**Preconditions:**
- Temporary directory exists, no trace file present.

**Input:**
- `AgentTraceSink(audit_dir=tmp_dir, run_id="20260414_120000_abc123")`
- Call `record_session_init(...)` with minimal valid arguments.

**Expected:**
- File `tmp_dir/agent_20260414_120000_abc123.jsonl` exists.
- File contains exactly one JSON line.

**Assertion pseudocode:**
```
sink = AgentTraceSink(tmp_dir, "20260414_120000_abc123")
sink.record_session_init(run_id="20260414_120000_abc123", node_id="n1",
    model_id="claude-sonnet-4-6", archetype="coder",
    system_prompt="sys", task_prompt="task")
path = tmp_dir / "agent_20260414_120000_abc123.jsonl"
ASSERT path.exists()
lines = path.read_text().strip().split("\n")
ASSERT len(lines) == 1
```

### TS-103-2: JSONL format — one JSON object per line, flushed

**Requirement:** 103-REQ-1.3
**Type:** unit
**Description:** Verify each event is a valid JSON object on its own line.

**Preconditions:**
- `AgentTraceSink` created with a temporary directory.

**Input:**
- Emit 3 events: `session.init`, `assistant.message`, `session.result`.

**Expected:**
- File contains exactly 3 lines.
- Each line parses as valid JSON.
- `event_type` fields are `"session.init"`, `"assistant.message"`,
  `"session.result"` respectively.

**Assertion pseudocode:**
```
sink = AgentTraceSink(tmp_dir, run_id)
sink.record_session_init(...)
sink.record_assistant_message(...)
sink.record_session_result(...)
lines = read_lines(trace_file)
ASSERT len(lines) == 3
FOR line IN lines:
    ASSERT json.loads(line) is valid
ASSERT [json.loads(l)["event_type"] for l in lines] == [
    "session.init", "assistant.message", "session.result"]
```

### TS-103-3: Audit directory created if missing

**Requirement:** 103-REQ-1.E1
**Type:** unit
**Description:** Verify the sink creates the audit directory on first write.

**Preconditions:**
- `audit_dir` path does not exist.

**Input:**
- Create `AgentTraceSink` with non-existent `audit_dir`.
- Emit one event.

**Expected:**
- `audit_dir` directory now exists.
- Trace file exists within it.

**Assertion pseudocode:**
```
audit_dir = tmp_path / "nonexistent" / "audit"
ASSERT NOT audit_dir.exists()
sink = AgentTraceSink(audit_dir, run_id)
sink.record_session_init(...)
ASSERT audit_dir.exists()
ASSERT (audit_dir / f"agent_{run_id}.jsonl").exists()
```

### TS-103-4: Write failure is logged, not raised

**Requirement:** 103-REQ-1.E2
**Type:** unit
**Description:** Verify I/O errors during write are swallowed with a warning log.

**Preconditions:**
- `AgentTraceSink` created with a read-only directory (or mock that raises
  `OSError` on write).

**Input:**
- Attempt to emit an event.

**Expected:**
- No exception raised.
- Warning logged.

**Assertion pseudocode:**
```
sink = AgentTraceSink(read_only_dir, run_id)
sink.record_session_init(...)  # must not raise
ASSERT "Failed to write" IN captured_warnings
```

### TS-103-5: session.init captures prompts verbatim

**Requirement:** 103-REQ-2.1, 103-REQ-2.2
**Type:** unit
**Description:** Verify session.init event contains full system and task prompts.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `system_prompt = "You are a coding agent. " * 5000` (large prompt)
- `task_prompt = "Implement feature X based on..."`

**Expected:**
- Trace event has `event_type == "session.init"`.
- `system_prompt` and `task_prompt` fields match input exactly (no truncation).
- `model_id`, `archetype`, `node_id`, `run_id` fields present.

**Assertion pseudocode:**
```
sink.record_session_init(run_id=rid, node_id="n1", model_id="claude-sonnet-4-6",
    archetype="coder", system_prompt=system_prompt, task_prompt=task_prompt)
event = json.loads(read_last_line(trace_file))
ASSERT event["event_type"] == "session.init"
ASSERT event["system_prompt"] == system_prompt
ASSERT event["task_prompt"] == task_prompt
ASSERT event["model_id"] == "claude-sonnet-4-6"
ASSERT event["archetype"] == "coder"
```

### TS-103-6: assistant.message captures full content

**Requirement:** 103-REQ-3.1, 103-REQ-3.2
**Type:** unit
**Description:** Verify assistant message content is captured verbatim.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `content = "[thinking] Let me analyze... I'll start by reading the file."`

**Expected:**
- Trace event has `event_type == "assistant.message"`.
- `content` field matches input exactly.

**Assertion pseudocode:**
```
sink.record_assistant_message(run_id=rid, node_id="n1", content=content)
event = json.loads(read_last_line(trace_file))
ASSERT event["event_type"] == "assistant.message"
ASSERT event["content"] == content
```

### TS-103-7: tool.use captures name and truncated input

**Requirement:** 103-REQ-4.1, 103-REQ-4.2
**Type:** unit
**Description:** Verify tool use events include name and truncated input.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `tool_name = "Write"`
- `tool_input = {"file_path": "/short.py", "content": "x" * 20000}`

**Expected:**
- Trace event has `event_type == "tool.use"`.
- `tool_name == "Write"`.
- `tool_input["file_path"] == "/short.py"` (short, not truncated).
- `tool_input["content"]` is 10000 chars + `" [truncated]"`.

**Assertion pseudocode:**
```
sink.record_tool_use(run_id=rid, node_id="n1", tool_name="Write",
    tool_input={"file_path": "/short.py", "content": "x" * 20000})
event = json.loads(read_last_line(trace_file))
ASSERT event["tool_name"] == "Write"
ASSERT event["tool_input"]["file_path"] == "/short.py"
ASSERT len(event["tool_input"]["content"]) == 10000 + len(" [truncated]")
ASSERT event["tool_input"]["content"].endswith(" [truncated]")
```

### TS-103-8: tool.use with non-string values preserved

**Requirement:** 103-REQ-4.3
**Type:** unit
**Description:** Verify non-string values in tool_input are passed through.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `tool_input = {"timeout": 5000, "force": True, "tags": ["a", "b"]}`

**Expected:**
- All values unchanged in trace event.

**Assertion pseudocode:**
```
sink.record_tool_use(run_id=rid, node_id="n1", tool_name="Bash",
    tool_input={"timeout": 5000, "force": True, "tags": ["a", "b"]})
event = json.loads(read_last_line(trace_file))
ASSERT event["tool_input"]["timeout"] == 5000
ASSERT event["tool_input"]["force"] == True
ASSERT event["tool_input"]["tags"] == ["a", "b"]
```

### TS-103-9: tool.use with empty tool_input

**Requirement:** 103-REQ-4.E1
**Type:** unit
**Description:** Verify empty tool_input is emitted unchanged.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `tool_input = {}`

**Expected:**
- Trace event has `tool_input == {}`.

**Assertion pseudocode:**
```
sink.record_tool_use(run_id=rid, node_id="n1", tool_name="Bash", tool_input={})
event = json.loads(read_last_line(trace_file))
ASSERT event["tool_input"] == {}
```

### TS-103-10: tool.error event emitted on session failure

**Requirement:** 103-REQ-5.1
**Type:** unit
**Description:** Verify tool error trace event is emitted with correct fields.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `tool_name = "Bash"`, `error_message = "Command failed with exit code 1"`

**Expected:**
- Trace event has `event_type == "tool.error"`.
- `tool_name` and `error_message` match input.

**Assertion pseudocode:**
```
sink.record_tool_error_trace(run_id=rid, node_id="n1",
    tool_name="Bash", error_message="Command failed with exit code 1")
event = json.loads(read_last_line(trace_file))
ASSERT event["event_type"] == "tool.error"
ASSERT event["tool_name"] == "Bash"
ASSERT event["error_message"] == "Command failed with exit code 1"
```

### TS-103-11: session.result captures terminal metrics

**Requirement:** 103-REQ-6.1
**Type:** unit
**Description:** Verify session result event contains all metric fields.

**Preconditions:**
- `AgentTraceSink` created.

**Input:**
- `status="completed"`, `input_tokens=15000`, `output_tokens=3200`,
  `cache_read_input_tokens=8000`, `cache_creation_input_tokens=2000`,
  `duration_ms=30000`, `is_error=False`, `error_message=None`

**Expected:**
- Trace event has `event_type == "session.result"`.
- All metric fields match input values.

**Assertion pseudocode:**
```
sink.record_session_result(run_id=rid, node_id="n1", status="completed",
    input_tokens=15000, output_tokens=3200, cache_read_input_tokens=8000,
    cache_creation_input_tokens=2000, duration_ms=30000,
    is_error=False, error_message=None)
event = json.loads(read_last_line(trace_file))
ASSERT event["event_type"] == "session.result"
ASSERT event["status"] == "completed"
ASSERT event["input_tokens"] == 15000
ASSERT event["output_tokens"] == 3200
ASSERT event["duration_ms"] == 30000
ASSERT event["is_error"] == False
ASSERT event["error_message"] == None
```

### TS-103-12: JsonlSink module removed

**Requirement:** 103-REQ-7.1
**Type:** unit
**Description:** Verify the old JsonlSink module no longer exists.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Check for file `agent_fox/knowledge/jsonl_sink.py`.

**Expected:**
- File does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/knowledge/jsonl_sink.py").exists()
```

### TS-103-13: No imports of JsonlSink remain

**Requirement:** 103-REQ-7.E1
**Type:** unit
**Description:** Verify no module imports JsonlSink.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Search all `.py` files for `from agent_fox.knowledge.jsonl_sink import`
  or `import jsonl_sink`.

**Expected:**
- Zero matches (excluding test files that specifically test removal).

**Assertion pseudocode:**
```
matches = grep("jsonl_sink", "agent_fox/**/*.py")
ASSERT len(matches) == 0
```

### TS-103-14: Audit retention preserves agent trace files

**Requirement:** 103-REQ-8.1, 103-REQ-8.2, 103-REQ-8.E1
**Type:** unit
**Description:** Verify enforce_audit_retention does not delete agent trace files.

**Preconditions:**
- DuckDB connection with audit_events table containing entries for runs
  `run_A` and `run_B`.
- Audit directory contains `audit_run_A.jsonl`, `agent_run_A.jsonl`,
  `audit_run_B.jsonl`, `agent_run_B.jsonl`.
- `max_runs=1` (so `run_A` should be pruned).

**Input:**
- Call `enforce_audit_retention(audit_dir, conn, max_runs=1)`.

**Expected:**
- `audit_run_A.jsonl` deleted.
- `agent_run_A.jsonl` still exists.
- `audit_run_B.jsonl` still exists.
- `agent_run_B.jsonl` still exists.

**Assertion pseudocode:**
```
enforce_audit_retention(audit_dir, conn, max_runs=1)
ASSERT NOT (audit_dir / "audit_run_A.jsonl").exists()
ASSERT (audit_dir / "agent_run_A.jsonl").exists()
ASSERT (audit_dir / "audit_run_B.jsonl").exists()
ASSERT (audit_dir / "agent_run_B.jsonl").exists()
```

## Property Test Cases

### TS-103-P1: Event completeness — every record call produces a line

**Property:** Property 1 from design.md
**Validates:** 103-REQ-2.1, 103-REQ-3.1, 103-REQ-4.1, 103-REQ-6.1
**Type:** property
**Description:** For any sequence of trace method calls, the file contains
exactly that many JSON lines.

**For any:** Sequence of 1..20 calls to any mix of `record_session_init`,
`record_assistant_message`, `record_tool_use`, `record_session_result`.

**Invariant:** Number of lines in the trace file equals the number of record
calls made.

**Assertion pseudocode:**
```
FOR ANY calls IN list(st.sampled_from(record_methods), min_size=1, max_size=20):
    sink = AgentTraceSink(tmp_dir, run_id)
    FOR call IN calls:
        call(sink, ...)
    lines = read_lines(trace_file)
    ASSERT len(lines) == len(calls)
    FOR line IN lines:
        ASSERT json.loads(line) is valid
```

### TS-103-P2: Truncation preserves keys and respects max_len

**Property:** Property 2 from design.md
**Validates:** 103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1
**Type:** property
**Description:** truncate_tool_input preserves all keys, truncates only string
values exceeding max_len, and leaves non-string values unchanged.

**For any:** Dict of 0..10 keys with values that are strings (0..20000 chars),
ints, bools, or lists; `max_len` in range 100..20000.

**Invariant:** Output dict has same keys as input. String values ≤ max_len
are unchanged. String values > max_len are exactly max_len chars +
`" [truncated]"`. Non-string values are identical.

**Assertion pseudocode:**
```
FOR ANY tool_input IN dicts(str_keys, mixed_values):
    FOR ANY max_len IN integers(100, 20000):
        result = truncate_tool_input(tool_input, max_len=max_len)
        ASSERT set(result.keys()) == set(tool_input.keys())
        FOR key IN tool_input:
            IF isinstance(tool_input[key], str):
                IF len(tool_input[key]) <= max_len:
                    ASSERT result[key] == tool_input[key]
                ELSE:
                    ASSERT result[key] == tool_input[key][:max_len] + " [truncated]"
            ELSE:
                ASSERT result[key] == tool_input[key]
```

### TS-103-P3: File location matches run_id

**Property:** Property 3 from design.md
**Validates:** 103-REQ-1.2, 103-REQ-7.3
**Type:** property
**Description:** The trace file is always created at the canonical path.

**For any:** run_id string matching the format `YYYYMMDD_HHMMSS_{hex6}`.

**Invariant:** After any write, the only file in audit_dir matching `agent_*`
is `agent_{run_id}.jsonl`.

**Assertion pseudocode:**
```
FOR ANY run_id IN run_id_strategy():
    sink = AgentTraceSink(tmp_dir, run_id)
    sink.record_session_init(...)
    agent_files = glob(tmp_dir / "agent_*.jsonl")
    ASSERT len(agent_files) == 1
    ASSERT agent_files[0].name == f"agent_{run_id}.jsonl"
```

## Edge Case Tests

### TS-103-E1: Non-existent audit directory is created

**Requirement:** 103-REQ-1.E1
**Type:** unit
**Description:** Verify missing parent directories are created.

(Covered by TS-103-3 above — same test.)

### TS-103-E2: Write failure isolation

**Requirement:** 103-REQ-1.E2
**Type:** unit
**Description:** Verify I/O errors don't crash the session.

(Covered by TS-103-4 above — same test.)

### TS-103-E3: Empty tool_input passthrough

**Requirement:** 103-REQ-4.E1
**Type:** unit
**Description:** Verify empty dict is handled.

(Covered by TS-103-9 above — same test.)

### TS-103-E4: Retention preserves agent files

**Requirement:** 103-REQ-8.E1
**Type:** unit
**Description:** Verify agent files survive audit cleanup.

(Covered by TS-103-14 above — same test.)

## Integration Smoke Tests

### TS-103-SMOKE-1: Full session trace end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Verify a complete coding session with debug=True produces
a trace file containing session.init, assistant.message, tool.use, and
session.result events in correct order.

**Setup:**
- Mock `AgentBackend` that yields: `AssistantMessage("thinking")`,
  `ToolUseMessage("Read", {"file_path": "/f.py"})`,
  `AssistantMessage("done")`,
  `ResultMessage(status="completed", ...)`.
- Real `AgentTraceSink` writing to a temporary audit directory.
- Real `SinkDispatcher` with the trace sink registered.
- Real `_execute_query` called with mock backend.

**Trigger:** Call `_execute_query(...)` with all required arguments.

**Expected side effects:**
- Trace file exists at `audit_dir/agent_{run_id}.jsonl`.
- File contains events in order: `session.init`, `assistant.message`,
  `tool.use`, `assistant.message`, `session.result`.
- `session.init` contains the system_prompt and task_prompt passed to
  `_execute_query`.
- `tool.use` event has `tool_name == "Read"`.

**Must NOT satisfy with:**
- Mocking `AgentTraceSink` (must be the real implementation).
- Mocking `_execute_query` (must run the real message loop).

**Assertion pseudocode:**
```
backend = MockBackend(messages=[
    AssistantMessage("thinking"),
    ToolUseMessage("Read", {"file_path": "/f.py"}),
    AssistantMessage("done"),
    ResultMessage(status="completed", input_tokens=100, output_tokens=50,
                  duration_ms=1000, error_message=None, is_error=False),
])
sink = AgentTraceSink(audit_dir, run_id)
dispatcher = SinkDispatcher([DuckDBSink(conn), sink])

await _execute_query(task_prompt="task", system_prompt="sys",
    model_id="claude-sonnet-4-6", cwd="/tmp", config=config,
    backend=backend, state=state, node_id="n1",
    sink_dispatcher=dispatcher, run_id=run_id)

events = [json.loads(l) for l in read_lines(trace_file)]
ASSERT events[0]["event_type"] == "session.init"
ASSERT events[0]["system_prompt"] == "sys"
ASSERT events[0]["task_prompt"] == "task"
ASSERT events[1]["event_type"] == "assistant.message"
ASSERT events[2]["event_type"] == "tool.use"
ASSERT events[2]["tool_name"] == "Read"
ASSERT events[3]["event_type"] == "assistant.message"
ASSERT events[4]["event_type"] == "session.result"
ASSERT events[4]["status"] == "completed"
```

### TS-103-SMOKE-2: No legacy trace files produced

**Execution Path:** Path 2 from design.md
**Description:** Verify that with debug=True, no files are created at the
old `.agent-fox/{timestamp}_{session_id}.jsonl` location.

**Setup:**
- Real `_setup_infrastructure` called with `debug=True`.
- Mock backend that yields a simple session.

**Trigger:** Run a session via the infrastructure setup path.

**Expected side effects:**
- No files matching `*.jsonl` exist in `.agent-fox/` root (only in
  `.agent-fox/audit/`).

**Must NOT satisfy with:**
- Mocking `_setup_infrastructure` (must run real registration logic).

**Assertion pseudocode:**
```
infra = _setup_infrastructure(config, debug=True)
# ... run a session ...
legacy_files = glob(".agent-fox/*.jsonl")
ASSERT len(legacy_files) == 0
agent_files = glob(".agent-fox/audit/agent_*.jsonl")
ASSERT len(agent_files) >= 1
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 103-REQ-1.1 | TS-103-SMOKE-1 | integration |
| 103-REQ-1.2 | TS-103-1 | unit |
| 103-REQ-1.3 | TS-103-2 | unit |
| 103-REQ-1.E1 | TS-103-3 | unit |
| 103-REQ-1.E2 | TS-103-4 | unit |
| 103-REQ-2.1 | TS-103-5 | unit |
| 103-REQ-2.2 | TS-103-5 | unit |
| 103-REQ-3.1 | TS-103-6 | unit |
| 103-REQ-3.2 | TS-103-6 | unit |
| 103-REQ-4.1 | TS-103-7 | unit |
| 103-REQ-4.2 | TS-103-7 | unit |
| 103-REQ-4.3 | TS-103-8 | unit |
| 103-REQ-4.E1 | TS-103-9 | unit |
| 103-REQ-5.1 | TS-103-10 | unit |
| 103-REQ-6.1 | TS-103-11 | unit |
| 103-REQ-7.1 | TS-103-12 | unit |
| 103-REQ-7.2 | TS-103-SMOKE-1 | integration |
| 103-REQ-7.3 | TS-103-SMOKE-2 | integration |
| 103-REQ-7.E1 | TS-103-13 | unit |
| 103-REQ-8.1 | TS-103-14 | unit |
| 103-REQ-8.2 | TS-103-14 | unit |
| 103-REQ-8.E1 | TS-103-14 | unit |
| Property 1 | TS-103-P1 | property |
| Property 2 | TS-103-P2 | property |
| Property 3 | TS-103-P3 | property |
