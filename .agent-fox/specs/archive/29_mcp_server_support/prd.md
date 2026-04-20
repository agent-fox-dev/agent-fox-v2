# PRD: Token-Efficient File Tools & MCP Server

**Origin:** [GitHub Issue #108 — investigate: alternative edit tool](https://github.com/agent-fox-dev/agent-fox-v2/issues/108)

## Problem

Agent-fox sessions rely on built-in file tools (Read, Write, Edit) provided by
the underlying agent SDK. These tools work but are token-inefficient in ways
that compound across long sessions:

1. **Full-file reads waste input tokens.** To inspect one function in a
   500-line file, the agent reads all 500 lines. Most content is irrelevant
   noise that fills the context window.

2. **Edits echo old text, wasting output tokens.** The built-in Edit tool
   requires the agent to output the old text being replaced (`old_string`)
   alongside the new text. The old text is pure overhead — output tokens are
   the most expensive token class.

3. **String-matching edits risk silent corruption.** The `old_string` →
   `new_string` pattern can silently corrupt code when reads are stale, the
   model hallucinates anchors, or the match is ambiguous (multiple occurrences
   of the same string).

4. **No way to share tools externally.** Agent-fox has no mechanism to expose
   its capabilities (file tools or otherwise) to other agents or IDEs via a
   standard protocol.

## Proposed Solution

Build a set of **token-efficient file tools** native to agent-fox, with two
distinct consumption paths: direct in-process injection for agent-fox's own
sessions, and an MCP server for external consumers.

### Part 1: Token-Efficient File Tools (Core Library)

A new `agent_fox.tools` module implementing four file tools as plain Python
functions designed for minimal token usage:

1. **`fox_outline`** — Returns a compact structural outline of a file: function
   and class declarations with their line ranges, collapsed import blocks, and
   symbol counts. An agent sees the full structure in ~10-15 lines instead of
   reading hundreds.

2. **`fox_read`** — Reads specific line ranges from a file (one or more
   disjoint ranges in a single call). Each returned line carries a content
   hash. The agent reads only what it needs.

3. **`fox_edit`** — Applies edits by referencing line ranges and content hashes
   instead of echoing old text. The agent outputs only the new content. Hash
   verification ensures the file hasn't changed since it was read — if hashes
   don't match, the edit is rejected before any bytes hit disk. Multiple edits
   can be batched in a single call and applied atomically.

4. **`fox_search`** — Regex search within a file, returning matching lines with
   surrounding context and content hashes. Enables a search → edit workflow
   without a separate read step.

These tools are **pure Python with no AST or tree-sitter dependency**. The
outline tool uses a lightweight heuristic parser (regex-based detection of
function/class/const declarations) that works across common languages without
requiring language-specific grammars. Accuracy is good-enough for navigation;
the model handles semantic understanding.

Each tool function has a clean signature that takes typed inputs and returns
structured output. These functions are the single source of truth — both the
backend integration and the MCP server are thin wrappers around them.

### Part 2: Backend Protocol Extension (In-Process Tools)

Extend the `AgentBackend` protocol with the ability to register **custom
tools** — agent-fox-defined tool schemas and handler functions that run
in-process alongside the SDK's built-in tools. No subprocess, no MCP protocol
overhead, no stdio piping. The tools execute as direct Python function calls
within the session process.

Each backend implementation maps these custom tool definitions to its SDK's
native mechanism for registering additional tools (e.g., the Claude backend
uses the SDK's tool registration API; a future backend would use its own
equivalent).

A new `ToolDefinition` dataclass in the protocol module captures each tool's
name, description, input schema (JSON Schema), and handler function. The
`AgentBackend.execute()` method accepts an optional list of these definitions.

A `[tools]` config section in `fox.toml` controls whether the built-in
fox tools are enabled for sessions. When enabled, the session runner constructs
`ToolDefinition` objects from the core library functions and passes them to
the backend.

### Part 3: MCP Server (External Consumption)

An MCP server (`agent_fox.tools.server`) that wraps the same core library
functions from Part 1 and exposes them over the Model Context Protocol (stdio
transport). This is **only for external consumers** — other agents, IDEs, and
tools that want to use agent-fox's file tools without being agent-fox sessions.

The server is launched via a new CLI command: `agent-fox serve-tools`.

Any MCP-compatible client (Claude Code, Cursor, Gemini CLI, VS Code Copilot,
etc.) can connect to the server and use the tools. The MCP server is a thin
adapter: it translates MCP tool-call requests into calls to the core library
functions from Part 1 and returns the results.

Agent-fox's own sessions never go through the MCP server. They use the
in-process path from Part 2.

## User Stories

1. **As an agent-fox operator**, I want agent-fox sessions to use
   token-efficient file tools so that sessions consume fewer tokens and stay
   within context limits on large codebases.

2. **As a developer using Claude Code or Cursor**, I want to run
   `agent-fox serve-tools` and connect it as an MCP server so I get
   hash-verified, compact file editing in my IDE.

3. **As a platform integrator**, I want agent-fox's file tools exposed via a
   standard protocol (MCP) so I can compose them with other tools and agents
   without coupling to agent-fox internals.

## Clarifications

1. **Q: Should the outline tool use tree-sitter or AST parsing?**
   A: No. A lightweight regex-based heuristic parser is sufficient and avoids
   a heavy dependency. It detects `def`, `class`, `function`, `const`,
   `export`, `struct`, `impl`, etc. across Python, JS/TS, Rust, Go, and Java.
   It doesn't need to be perfect — the model handles semantics.

2. **Q: What hash algorithm for content verification?**
   A: Use xxhash (xxh3_64) for speed. Content hashes are ephemeral (valid
   only until the file changes) and not security-sensitive.

3. **Q: Should the MCP server support resources or prompts?**
   A: No. Tools only for v1. Resources and prompts can be added later.

4. **Q: Should agent-fox sessions use these tools by default?**
   A: No. The tools are opt-in via configuration. A `[tools]` config section
   enables the built-in fox tools for sessions.

5. **Q: How does this interact with archetype permissions?**
   A: The existing `can_use_tool` callback gates all tool use, including
   custom tools. Read-only archetypes (Skeptic) will be denied write-capable
   tools (`fox_edit`) automatically. No new permission mechanism is needed —
   the existing callback handles it.

6. **Q: What transports does the MCP server support?**
   A: Stdio only for v1. The MCP Python SDK handles the transport layer.

7. **Q: What happens if `fox_edit` hashes don't match?**
   A: The edit is rejected atomically. No partial writes. The tool returns an
   error indicating which lines have stale hashes, prompting the agent to
   re-read those ranges.

8. **Q: Why two consumption paths instead of one?**
   A: In-process tools (Part 2) avoid the overhead and fragility of spawning
   a subprocess and communicating over stdio/MCP just to call Python functions
   that are already loaded in the same process. The MCP server (Part 3) exists
   solely for external consumers who are not agent-fox sessions.

## Out of Scope

- SSE or HTTP MCP transports (stdio only for v1).
- MCP resource or prompt capabilities (tools only).
- Tree-sitter or language-specific AST parsing.
- Marketplace or plugin discovery.
- Automatic migration of sessions from built-in tools to fox tools.
- Consuming external MCP servers from agent-fox sessions (this spec only
  adds the ability to register in-process tools and serve them externally).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 26_agent_archetypes | 5 | 4 | Per-archetype allowlist resolution (group 5) gates custom tool permissions via existing `can_use_tool` callback |
| 26_agent_archetypes | 2 | 3 | AgentBackend protocol (group 2) is extended with custom tool registration |
