# Claude Agent SDK Improvement Opportunities

Opportunities to improve agent-fox by adopting Claude Agent SDK features that
go beyond replacing existing code. These are new capabilities that the SDK
enables which agent-fox does not use today.

Investigated 2026-04-09 against claude-agent-sdk-python and
https://code.claude.com/docs/en/agent-sdk/overview.

## 1. In-Process MCP Tools for Knowledge DB

**Value: High | Effort: High**

### Background

ADR-02 removed external MCP-based fox tools because: (a) models preferred
built-in tools, (b) subprocess MCP servers added IPC overhead, and (c) four
tool schemas cost ~800-1000 tokens per session.

The SDK now supports **in-process MCP tools** -- Python functions decorated
with `@tool` that run inside the same process with zero IPC overhead:

```python
from claude_agent_sdk import create_sdk_mcp_server

@tool("query_findings", "Retrieve prior review findings for a spec", {"spec_name": str})
async def query_findings(args):
    # Query DuckDB directly -- same process, no IPC
    rows = knowledge_store.get_findings(args["spec_name"])
    return {"content": [{"type": "text", "text": format_findings(rows)}]}

server = create_sdk_mcp_server(name="knowledge", version="1.0.0", tools=[query_findings])
```

### Opportunity

Currently `session/context.py` assembles *all* potentially relevant context
(findings, facts, drift reports, verification verdicts) into the system prompt
upfront. This can be wasteful -- a coder working on task group 3 may never
need the drift report from task group 1.

In-process knowledge tools would let the agent pull context on demand:

- `query_findings(spec_name)` -- retrieve prior review/drift findings
- `query_facts(topic)` -- semantic search over causal facts via embeddings
- `query_audit(node_id)` -- look up execution history for a specific node

### Caveats

- ADR-02 demonstrated that models prefer built-in tools. These knowledge
  tools would need to be high-signal enough that the model actually invokes
  them. Requires empirical validation.
- Schema overhead is per-tool (~200-250 tokens each). Three tools add ~750
  tokens -- comparable to the old fox tools. Only worthwhile if they save
  more than that from reduced system prompt size.
- The `readOnlyHint` tool annotation should be set to enable SDK
  parallelization.

### Next Steps

1. Prototype a single `query_findings` in-process tool
2. Run A/B comparison: system-prompt injection vs. on-demand tool
3. Measure token savings and model utilization rate
4. If positive, expand to facts and audit queries


## 2. Session Resume for Retries

**Value: High | Effort: Medium**

### Background

When a task fails and the orchestrator retries (`engine/result_handler.py`),
it creates a brand-new `ClaudeSDKClient` session. The agent starts from
scratch with no memory of what it tried or why it failed.

The SDK supports session resume via `ClaudeAgentOptions(resume=session_id)`.
A resumed session continues from where the previous one left off -- the agent
retains full conversation history including its failed attempts.

### Opportunity

- **Smarter retries**: The agent knows what it already tried and can take a
  different approach instead of repeating the same failing strategy.
- **Session forking**: `fork_session=True` creates a branch from the failed
  session without modifying the original. The orchestrator could fork on
  retry, preserving the original attempt's audit trail.
- **Error context**: The retry session sees the exact error that caused the
  previous failure, not just a re-injected error summary in the prompt.

### Integration Points

- `ClaudeBackend.execute()` would need to accept an optional `session_id`
  parameter and pass it as `resume` in `ClaudeAgentOptions`.
- `ResultMessage` from the SDK includes a `session_id` field -- the backend
  should capture and return this in the canonical `ResultMessage`.
- The orchestrator's retry logic in `result_handler.py` would pass the
  failed session's ID to the retry dispatch.
- Session storage lives in `~/.claude/projects/` -- no custom persistence
  needed.

### Caveats

- Resumed sessions carry the full prior conversation, which may push
  against context limits on already-long sessions. The `PreCompact` hook
  (see item 4) mitigates this.
- The worktree may have changed between retries (e.g., git reset). The
  resumed session's file references may be stale.
- Transport-layer retries in `claude.py` (connection errors) should NOT
  use session resume -- those are invisible retries, not orchestrator-level
  retries.


## 3. Structured Output for Fact/Review Extraction

**Value: Medium | Effort: Medium**

### Background

Agent-fox extracts structured data from free-text LLM responses in several
places:

- **Fact extraction** (`knowledge/knowledge_harvest.py`): Parses facts from
  coder session transcripts for the knowledge DB.
- **Review finding parsing**: Skeptic and oracle session responses are parsed
  to extract finding IDs, severities, and descriptions.
- **Complexity assessment** (`routing/core.py`): The routing assessor
  predicts a model tier from task descriptions.

All of these rely on prompt-engineering the output format and then parsing
free text, which is fragile.

### Opportunity

The SDK's `output_format` parameter accepts a JSON schema and guarantees
that the response conforms to it:

```python
options = ClaudeAgentOptions(
    output_format={
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "severity": {"enum": ["critical", "high", "medium", "low"]},
                        "category": {"enum": ["security", "spec_drift", "quality"]},
                        "description": {"type": "string"}
                    }
                }
            }
        }
    }
)
```

### Integration Points

- Review archetypes (skeptic, oracle, auditor) would use `output_format` to
  guarantee structured findings output.
- `knowledge_harvest.py` would use structured output for fact extraction.
- `routing/core.py` assessor would use structured output for tier prediction.
- The parsing code in `engine/result_handler.py` that extracts findings from
  free text could be replaced with direct JSON deserialization.

### Caveats

- Structured output constrains the model's response format, which may reduce
  the quality of analysis if the schema is too rigid.
- The coder archetype should NOT use structured output -- it needs free-form
  tool-calling behavior.
- Structured output may not be compatible with extended thinking in all
  configurations. Requires testing.


## 4. PreCompact Hook for Context Preservation

**Value: Medium | Effort: Low**

### Background

When a session's conversation history approaches context limits, the SDK
automatically compacts (summarizes) prior messages. This can silently
discard critical information -- spec requirements, review findings, or
task constraints that the agent needs to complete its work.

### Opportunity

The SDK's `PreCompact` hook fires before compaction and can return a
`systemMessage` that gets injected to preserve key context:

```python
async def preserve_context(input_data, tool_use_id, context):
    return {
        "hookSpecificOutput": {
            "systemMessage": (
                "IMPORTANT: The following requirements MUST be preserved "
                "across compaction:\n"
                f"{critical_requirements}\n"
                f"Review findings to address:\n{active_findings}"
            )
        }
    }

options = ClaudeAgentOptions(
    hooks={"PreCompact": [HookMatcher(hooks=[preserve_context])]}
)
```

### Integration Points

- The hook function would need access to the current session's spec
  context (requirements, active findings). This could come from the same
  data that `session/context.py` already assembles.
- Minimal code change: add a hook factory in `hooks/` and wire it into
  `ClaudeAgentOptions` in `claude.py`.

### Caveats

- The injected system message itself consumes tokens. Keep it concise --
  only truly critical constraints, not the full spec.
- Only relevant for long-running coder sessions. Short review/verification
  sessions are unlikely to trigger compaction.


## 5. SDK Subagents for Intra-Session Delegation

**Value: Low | Effort: High**

### Background

Agent-fox orchestrates multi-agent workflows at the graph level: each
archetype (coder, skeptic, verifier, oracle) runs as a separate graph
node with its own `ClaudeSDKClient` session. This provides deterministic
scheduling, independent audit trails, and clear failure boundaries.

The SDK now supports lightweight subagents via `AgentDefinition` that run
within a single parent session:

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Bash", "Agent"],
    agents={
        "test-checker": AgentDefinition(
            description="Runs tests and reports results",
            tools=["Bash", "Read"],
            model="haiku"
        )
    }
)
```

### Opportunity

For lightweight, well-defined subtasks within a coder session, intra-session
subagents would be cheaper than full graph nodes:

- "Run the test suite and summarize failures"
- "Read these 5 files and check for pattern X"
- "Verify the import graph is acyclic"

The coder agent would decide when to delegate, reducing orchestrator
complexity for simple verification steps.

### Caveats

- **Conflicts with deterministic scheduling**: The orchestrator can't
  predict or control when subagents run. This makes audit trails harder
  to follow and retry behavior less predictable.
- **Overlaps with existing archetypes**: The verifier and auditor
  archetypes already handle post-coder verification. Adding intra-session
  subagents creates two paths for the same purpose.
- **Context isolation trade-off**: Subagents don't inherit the parent's
  conversation history. For tasks requiring deep context (e.g., "check if
  this change satisfies requirement X from our earlier discussion"), they'd
  need explicit briefing.
- Best suited for tasks that are too trivial for a graph node but too
  complex for a single tool call.


## 6. Effort Levels for Thinking Configuration

**Value: Low | Effort: Low**

### Background

Agent-fox manages extended thinking via `resolve_thinking()` in
`engine/sdk_params.py`, which resolves `thinking_mode` ("enabled",
"adaptive", "disabled") and `budget_tokens` (default 10,000) from a
three-level config hierarchy.

The SDK now supports a simpler `effort` parameter:
`"low"` | `"medium"` | `"high"` | `"max"`.

### Opportunity

For users who don't need fine-grained control over thinking budget tokens,
effort levels provide a simpler configuration surface:

```toml
[archetypes.overrides.coder]
effort = "high"

[archetypes.overrides.skeptic]
effort = "medium"
```

### Integration Points

- Add an optional `effort` field to `ArchetypeOverride` in config.
- When `effort` is set, pass it directly to `ClaudeAgentOptions(effort=...)`
  instead of constructing a `thinking` dict.
- Keep the existing `thinking_mode` / `thinking_budget` path for users who
  want precise control.

### Caveats

- Less precise than manual budget tokens. For archetypes where thinking
  budget has been tuned, effort levels may over- or under-allocate.
- Both `effort` and `thinking` cannot be set simultaneously. Config
  validation needs to enforce mutual exclusivity.
