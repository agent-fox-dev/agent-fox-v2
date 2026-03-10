# ADR: Token-Efficient File Tools

## Status

Accepted

## Context

AI coding agents spend a large portion of their token budgets reading and
writing files. Standard approaches (reading entire files, echoing old content
in edits) are wasteful and error-prone:

- **Token waste:** Agents read full files when they only need a few lines.
- **Silent corruption:** Edits based on stale reads can silently overwrite
  concurrent changes.
- **No structural navigation:** Without an outline tool, agents scan files
  line-by-line to find declarations.

agent-fox needs a set of file tools that are token-efficient, hash-verified,
and available through two consumption paths: in-process for agent-fox sessions
and via MCP for external consumers (other agents, IDEs).

## Decision

Implement four token-efficient file tools as a core library and expose them
through two paths:

### Tools

1. **`fox_outline`** — Structural file outline using regex-based heuristic
   parsing. Returns functions, classes, constants with line ranges. Collapses
   import blocks.
2. **`fox_read`** — Line-range file reading with per-line xxh3_64 content
   hashes. Supports multiple disjoint ranges in a single call.
3. **`fox_edit`** — Hash-verified atomic batch editing. Verifies content
   hashes before applying changes, processes edits in reverse line order,
   supports line deletion.
4. **`fox_search`** — Regex search with configurable context lines and
   content hashes. Merges overlapping context ranges.

### Architecture

Three-layer architecture:

- **Core library** (`agent_fox.tools`) — Pure Python functions with no I/O
  protocol awareness. Shared by both consumption paths.
- **Backend integration** — `ToolDefinition` dataclass and protocol extension
  on `AgentBackend.execute()`. Session runner wraps core functions when config
  enables them.
- **MCP server** (`agent_fox.tools.server`) — Thin adapter exposing core
  functions as MCP tools over stdio transport.

### Key design choices

1. **Regex heuristics over tree-sitter (for outline):** We use regex-based
   pattern matching to detect declarations across Python, JavaScript,
   TypeScript, Rust, Go, and Java. This avoids the tree-sitter dependency
   (C extension, grammar files per language) while providing sufficient
   accuracy for navigation. The outline is approximate and intended for
   navigation — the AI model handles semantic understanding.

2. **xxh3_64 content hashing:** We use xxhash's xxh3_64 algorithm for
   per-line content hashing. It is fast (non-cryptographic), produces compact
   16-character hex strings, and provides sufficient collision resistance for
   detecting stale reads. A blake2b fallback is available when xxhash is not
   installed.

3. **Dual consumption path (in-process vs MCP):** In-process tools avoid
   subprocess overhead for agent-fox sessions. The MCP server enables external
   consumers without code coupling. Both paths call the same core functions
   (single source of truth).

4. **Opt-in via config:** Fox tools are disabled by default
   (`tools.fox_tools = false`). This allows gradual rollout without affecting
   existing users.

5. **`ToolDefinition` protocol extension:** The `AgentBackend.execute()`
   method accepts an optional `tools` parameter. This keeps the protocol
   backward-compatible — backends that don't support custom tools ignore the
   parameter.

## Alternatives Considered

### Tree-sitter for outline parsing

Tree-sitter provides accurate AST parsing but requires C extensions and
per-language grammar files. The maintenance burden and dependency weight are
not justified for a navigation tool where approximate results are acceptable.

### Full-file hashing instead of per-line hashing

Hashing entire files is simpler but doesn't enable line-level edit
verification. Per-line hashing lets agents verify that specific lines haven't
changed, enabling targeted edits without re-reading the entire file.

### MCP-only (no in-process path)

Routing all tool calls through MCP adds subprocess and protocol overhead for
every invocation within agent-fox sessions. The in-process path eliminates
this overhead while MCP remains available for external consumers.

### Always-on tools (no config flag)

Registering tools unconditionally would change agent behavior for all users.
The opt-in flag allows operators to enable tools when ready and revert
without side effects.

## Consequences

### Positive

- Agents use fewer tokens for file operations (read only needed lines, no
  echo in edits).
- Hash verification prevents silent corruption from stale reads.
- External tools and IDEs can use fox tools via MCP without agent-fox
  coupling.
- Backward-compatible — no behavior change for existing users until opt-in.

### Negative

- Regex-based outline parsing may miss or misidentify declarations in complex
  or unconventional code.
- xxhash is an additional dependency (mitigated by blake2b fallback).
- Two consumption paths (in-process + MCP) increase surface area for testing.

### Risks

- Heuristic end-line detection is approximate. It may produce incorrect
  line ranges for deeply nested or unusual code structures.
- The `mcp` SDK is a relatively new dependency; API changes in future
  versions may require updates.
