# PRD: Agent Conversation Trace

## Problem

When debugging agent-fox sessions, operators cannot inspect the actual
conversation between the orchestrator and the LLM. The existing `--debug` flag
captures only operational telemetry — session outcomes, tool call metadata
(name + timestamp), and token counts — but none of the actual content:

- No system prompt or task prompt sent to the model.
- No assistant responses (only the last one, truncated).
- No tool invocation arguments.
- No per-turn visibility into the conversation flow.

This makes it impossible to diagnose prompt engineering issues, unexpected agent
behavior, or model-specific regressions without adding ad-hoc logging.

## Solution

Re-purpose the `--debug` flag to capture the full agent–model conversation as a
structured JSONL trace file. Each session produces events that record what was
sent to the model and what came back, in chronological order.

### Trace File Location

Write trace files to `.agent-fox/audit/agent_{run_id}.jsonl`, where `run_id`
matches the existing audit run ID. This enables direct correlation with the
operational audit log (`audit_{run_id}.jsonl`) and the execution state
(`state.jsonl`).

### Events Captured

| Event Type | Content |
|------------|---------|
| `session.init` | System prompt, task prompt, model ID, node_id, archetype |
| `assistant.message` | Full assistant text (including `[thinking]` blocks) |
| `tool.use` | Tool name + truncated tool_input dict |
| `tool.error` | Tool name + error attribution |
| `session.result` | Terminal ResultMessage metrics (tokens, duration, status) |

### Tool Input Truncation

Tool input values can be arbitrarily large (e.g., a `Write` call with a full
file). String values in `tool_input` are truncated to a configurable limit
(default 10,000 characters) with a `[truncated]` marker. Non-string values
are serialized as-is.

### Replaces Existing JsonlSink

The new agent trace replaces the current `JsonlSink` (which writes to
`.agent-fox/{timestamp}_{session_id}.jsonl`). The old sink is removed entirely.
The `DuckDBSink.debug` parameter is retained for API compatibility but remains
a no-op.

### Retention

Agent trace files are kept indefinitely — no automatic cleanup. Operators
manage retention manually. This is intentional: trace files are diagnostic
artifacts that may be needed long after a run completes.

## Non-Goals

- Capturing SDK-internal per-turn request/response payloads (the SDK manages
  its own conversation loop; we only trace what agent-fox controls).
- Adding a new CLI flag — the existing `--debug` flag is re-purposed.
- Changing DuckDB schema or the audit event system.

## Clarifications

1. **Scope of "all that goes in":** The initial system prompt and task prompt
   that agent-fox constructs and passes to `backend.execute()`. Not the
   per-turn payloads managed internally by the SDK.
2. **Tool results:** Capture what the canonical message stream provides —
   `ToolUseMessage.tool_name` and `ToolUseMessage.tool_input` (truncated).
   No tool output capture (not available in the current message model).
3. **Existing JSONL sink:** Replaced entirely by the new agent trace.
4. **Retention:** No automatic cleanup — keep all trace files.
5. **Size:** No per-file size cap. Tool input string values are truncated
   individually, but the trace file itself grows unbounded.
6. **Thinking blocks:** The current `[thinking] {text}` flattening into
   `AssistantMessage.content` is sufficient — no separate event type needed.

## Dependencies

None. This spec modifies existing infrastructure without depending on
in-flight specs.
