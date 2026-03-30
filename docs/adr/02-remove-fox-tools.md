# ADR 02: Remove Fox Tools

## Status

Accepted

## Context

agent-fox shipped four custom file tools (fox_outline, fox_read, fox_edit,
fox_search) as an MCP server registered with every coding session. The
original rationale (ADR in hack/adr/token-efficient-file-tools.md) argued
they would:

1. Save input tokens by reading only needed line ranges.
2. Save output tokens by avoiding the old-string echo in edits.
3. Prevent silent corruption via per-line content hash verification.

After running in production, audit log data tells a different story.

### Actual usage (from .agent-fox/audit/ logs)

| Tool | Invocations | % of total |
|------|:-----------:|:----------:|
| fox_read | 45 | 78% |
| fox_search | 11 | 19% |
| fox_outline | 2 | 3% |
| fox_edit | 0 | 0% |

**fox_edit -- the centrepiece of the design -- was never used.** The model
consistently chose Claude's built-in Edit tool over fox_edit, because the
built-in tool is part of the model's training data and requires no hash
management workflow.

### Why the tools cost more than they save

- **Hash overhead on every read.** fox_read appends a 16-char hex hash to
  every line. Since fox_edit is never used, those hashes are pure waste --
  extra output tokens that no downstream tool consumes.

- **Schema overhead per session.** Four tool JSON schemas (~800-1000 tokens)
  are injected into the system context of every session, whether or not the
  agent uses them.

- **Claude's built-in tools already cover the same ground.** Claude's Read
  tool supports offset/limit for partial reads. Grep handles regex search.
  Edit handles string-replacement edits natively.

- **Maintenance burden.** ~1,300 lines of production code, an MCP server,
  an xxhash dependency, and 13 test files -- all supporting tools the model
  largely ignores.

## Decision

Remove the entire fox tools system:

- Delete the `agent_fox/tools/` package (read, edit, outline, search,
  registry, server, types, utilities).
- Remove `ToolDefinition` and the `tools` parameter from the
  `AgentBackend` protocol and `ClaudeBackend` implementation.
- Remove `ToolsConfig` and `fox_tools` from configuration.
- Remove the `xxhash` direct dependency.
- Delete all associated tests (unit, property, integration).
- Update documentation to remove fox tools references.

## Consequences

### Positive

- **~1,300 fewer lines** of production code to maintain.
- **13 fewer test files** (~600 lines of test code removed).
- **One fewer direct dependency** (xxhash).
- **~800-1000 fewer input tokens** per session (no tool schemas injected).
- **Simpler backend protocol** -- `AgentBackend.execute()` no longer
  carries a tools parameter or MCP server wiring.
- **Simpler config** -- one fewer config section to document and validate.

### Negative

- If a future model learns to use fox_edit effectively, the hash-verified
  editing capability would need to be re-implemented. This is unlikely
  given that model providers are converging on their own built-in file
  tools.

### Risks

- None identified. The tools were opt-in (config flag) and the model was
  already not using them in practice.
