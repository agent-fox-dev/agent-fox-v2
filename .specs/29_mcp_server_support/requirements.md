# Requirements Document

## Introduction

This specification defines token-efficient file tools for agent-fox and two
consumption paths: in-process injection for agent-fox sessions (via the
`AgentBackend` protocol) and an MCP server for external consumers (other agents,
IDEs). The core tool implementations are plain Python functions shared by both
paths.

## Glossary

| Term | Definition |
|------|-----------|
| Content Hash | A per-line xxh3_64 hash of the line's content, used to detect stale reads and prevent silent file corruption during edits. |
| Disjoint Range | A pair of 1-based line numbers `[start, end]` (inclusive) specifying a contiguous block of lines within a file. Multiple disjoint ranges may be requested in a single tool call. |
| Fox Tools | The four token-efficient file tools defined in this spec: `fox_outline`, `fox_read`, `fox_edit`, `fox_search`. |
| Heuristic Parser | A regex-based scanner that identifies structural declarations (functions, classes, constants) across multiple languages without requiring AST or tree-sitter grammars. |
| In-Process Tool | A custom tool registered with the `AgentBackend` as a Python callable, executed within the session process without subprocess or protocol overhead. |
| MCP | Model Context Protocol — a standard protocol for exposing tools to AI agents and IDEs. |
| MCP Server | A process that implements the MCP protocol and serves tool definitions to connected clients. |
| Stdio Transport | MCP communication over standard input/output streams of a subprocess. |
| Symbol | A structural declaration detected by the heuristic parser: function, class, method, constant, or similar top-level construct. |
| ToolDefinition | A dataclass capturing a custom tool's name, description, JSON Schema input definition, and handler function, used to register in-process tools with the backend. |

## Requirements

### Requirement 1: File Outline Tool

**User Story:** As an agent, I want to see a compact structural outline of a
file so that I can navigate large files without reading every line.

#### Acceptance Criteria

1. [29-REQ-1.1] WHEN `fox_outline` is called with a file path, THE tool SHALL
   return a list of symbols found in the file, where each symbol includes the
   declaration kind (e.g. function, class, constant), name, and start/end line
   numbers.

2. [29-REQ-1.2] WHEN `fox_outline` is called on a file containing import
   statements, THE tool SHALL collapse contiguous import lines into a single
   summary entry showing the line range and count (e.g. "1-10: (10 imports)").

3. [29-REQ-1.3] THE tool SHALL include a trailing summary line with the total
   symbol count and total source line count.

4. [29-REQ-1.4] THE tool SHALL detect declarations in at least Python, JavaScript,
   TypeScript, Rust, Go, and Java using regex-based heuristic matching, without
   requiring AST or tree-sitter dependencies.

#### Edge Cases

1. [29-REQ-1.E1] IF the file path does not exist or is not readable, THEN THE
   tool SHALL return an error message identifying the path and the failure reason.

2. [29-REQ-1.E2] IF the file is empty (zero bytes), THEN THE tool SHALL return
   a summary with zero symbols and zero lines.

3. [29-REQ-1.E3] IF the file is binary (contains null bytes in the first 8192
   bytes), THEN THE tool SHALL return an error indicating it is not a text file.

---

### Requirement 2: Line-Range Read Tool

**User Story:** As an agent, I want to read specific line ranges from a file
with content hashes so that I can inspect only what I need and later verify
edits against the actual content.

#### Acceptance Criteria

1. [29-REQ-2.1] WHEN `fox_read` is called with a file path and one or more
   disjoint ranges, THE tool SHALL return the lines within those ranges, each
   annotated with its 1-based line number and content hash.

2. [29-REQ-2.2] WHEN `fox_read` is called with multiple disjoint ranges, THE
   tool SHALL return all requested ranges in a single response, ordered by
   ascending line number.

3. [29-REQ-2.3] THE tool SHALL compute content hashes using the xxh3_64
   algorithm applied to the raw line content (including trailing newline if
   present).

#### Edge Cases

1. [29-REQ-2.E1] IF the file path does not exist or is not readable, THEN THE
   tool SHALL return an error message identifying the path and the failure reason.

2. [29-REQ-2.E2] IF a requested range extends beyond the file's line count,
   THEN THE tool SHALL return lines up to the end of the file and include a
   warning indicating the truncation.

3. [29-REQ-2.E3] IF a range has start > end, THEN THE tool SHALL return an error
   indicating the invalid range.

---

### Requirement 3: Hash-Verified Edit Tool

**User Story:** As an agent, I want to apply edits by specifying line ranges
and new content, verified against content hashes, so that I avoid echoing old
text and prevent silent corruption from stale reads.

#### Acceptance Criteria

1. [29-REQ-3.1] WHEN `fox_edit` is called with a file path, one or more edit
   operations (each specifying a start line, end line, content hashes for the
   target lines, and the new replacement content), THE tool SHALL verify that
   every provided content hash matches the current file content before applying
   any changes.

2. [29-REQ-3.2] WHEN all hashes verify successfully, THE tool SHALL apply all
   edit operations atomically: either all edits succeed or none are written.

3. [29-REQ-3.3] WHEN multiple edits are provided in a single call, THE tool
   SHALL process them in reverse line-number order so that earlier edits do not
   shift the line numbers of later ones.

4. [29-REQ-3.4] WHEN an edit operation has empty replacement content, THE tool
   SHALL delete the specified line range (line deletion).

#### Edge Cases

1. [29-REQ-3.E1] IF any content hash does not match the current file content,
   THEN THE tool SHALL reject the entire batch and return an error listing
   each mismatched line number with its expected and actual hashes.

2. [29-REQ-3.E2] IF the file path does not exist or is not writable, THEN THE
   tool SHALL return an error message identifying the path and the failure reason.

3. [29-REQ-3.E3] IF two edit operations in the same batch have overlapping line
   ranges, THEN THE tool SHALL return an error identifying the conflicting
   ranges.

---

### Requirement 4: File Search Tool

**User Story:** As an agent, I want to search a file by regex and get matching
lines with context and content hashes so that I can find and edit code in a
single workflow without a separate read step.

#### Acceptance Criteria

1. [29-REQ-4.1] WHEN `fox_search` is called with a file path and a regex
   pattern, THE tool SHALL return all matching lines with their 1-based line
   numbers, content, and content hashes.

2. [29-REQ-4.2] WHEN a context parameter is provided (integer N), THE tool
   SHALL include N lines before and after each match, each with line numbers
   and content hashes.

3. [29-REQ-4.3] WHEN multiple matches have overlapping context ranges, THE tool
   SHALL merge them into a single contiguous block (no duplicate lines).

#### Edge Cases

1. [29-REQ-4.E1] IF the file path does not exist or is not readable, THEN THE
   tool SHALL return an error message identifying the path and the failure reason.

2. [29-REQ-4.E2] IF the regex pattern is syntactically invalid, THEN THE tool
   SHALL return an error identifying the pattern and the parse failure.

3. [29-REQ-4.E3] IF no lines match the pattern, THEN THE tool SHALL return an
   empty result set with no error.

---

### Requirement 5: Content Hashing

**User Story:** As an agent, I want content hashes to reliably detect file
changes so that edits against stale reads are caught before writing.

#### Acceptance Criteria

1. [29-REQ-5.1] THE system SHALL compute content hashes using the xxh3_64
   algorithm, producing a 16-character lowercase hexadecimal string per line.

2. [29-REQ-5.2] WHEN the same line content (byte-identical) is hashed at
   different times, THE system SHALL produce the same hash value
   (deterministic).

3. [29-REQ-5.3] WHEN a line's content changes by even one byte, THE system
   SHALL produce a different hash value (collision resistance within practical
   bounds).

#### Edge Cases

1. [29-REQ-5.E1] IF the xxhash library is not available at runtime, THEN THE
   system SHALL fall back to the standard library's `hashlib` (e.g.
   `hashlib.blake2b` with 8-byte digest) and log a warning on first use.

---

### Requirement 6: Backend Custom Tool Registration

**User Story:** As a session runner, I want to register custom tools with the
backend so that agents can use fox tools in-process without subprocess overhead.

#### Acceptance Criteria

1. [29-REQ-6.1] THE `AgentBackend` protocol SHALL accept an optional list of
   `ToolDefinition` objects on `execute()`, where each `ToolDefinition`
   specifies a tool name, description, JSON Schema for inputs, and a callable
   handler.

2. [29-REQ-6.2] WHEN a backend implementation receives `ToolDefinition` objects,
   THE backend SHALL make them available to the agent alongside the SDK's
   built-in tools.

3. [29-REQ-6.3] WHEN the agent invokes a custom tool, THE backend SHALL call
   the corresponding handler function in-process and return the result to the
   agent.

4. [29-REQ-6.4] THE existing `permission_callback` SHALL gate custom tool
   invocations using the same mechanism as built-in tools (the callback
   receives the custom tool's name and input).

#### Edge Cases

1. [29-REQ-6.E1] IF no `ToolDefinition` list is provided (None or empty), THEN
   THE backend SHALL behave identically to the current implementation (no
   change in behavior).

2. [29-REQ-6.E2] IF a `ToolDefinition` handler raises an exception, THEN THE
   backend SHALL catch the exception, return the error message to the agent as
   a tool error result, and continue the session.

---

### Requirement 7: MCP Server

**User Story:** As an external developer, I want to connect to agent-fox's file
tools via MCP so that I can use them from any MCP-compatible client.

#### Acceptance Criteria

1. [29-REQ-7.1] THE system SHALL provide an MCP server that exposes
   `fox_outline`, `fox_read`, `fox_edit`, and `fox_search` as MCP tools over
   stdio transport.

2. [29-REQ-7.2] WHEN an MCP client calls a tool, THE server SHALL delegate to
   the same core library function used by in-process tool registration (single
   source of truth).

3. [29-REQ-7.3] THE server SHALL be launchable via the CLI command
   `agent-fox serve-tools`.

4. [29-REQ-7.4] WHEN launched, THE server SHALL accept an optional
   `--allowed-dirs` argument that restricts file operations to the specified
   directories and their descendants.

#### Edge Cases

1. [29-REQ-7.E1] IF `--allowed-dirs` is specified and a tool call references
   a path outside the allowed directories, THEN THE server SHALL return an
   error without performing any file operation.

2. [29-REQ-7.E2] IF the MCP client disconnects unexpectedly, THEN THE server
   SHALL terminate cleanly without leaving orphan processes or open file
   handles.

---

### Requirement 8: Configuration

**User Story:** As an operator, I want to enable or disable fox tools for
agent-fox sessions via configuration so that I can opt in when ready.

#### Acceptance Criteria

1. [29-REQ-8.1] THE system SHALL support a `[tools]` section in the
   `config.toml` file with a boolean `fox_tools` field (default: false).

2. [29-REQ-8.2] WHEN `tools.fox_tools` is true, THE session runner SHALL
   construct `ToolDefinition` objects for all four fox tools and pass them to
   `AgentBackend.execute()`.

3. [29-REQ-8.3] WHEN `tools.fox_tools` is false or the `[tools]` section is
   absent, THE session runner SHALL not register any fox tools (existing
   behavior preserved).

#### Edge Cases

1. [29-REQ-8.E1] IF `tools.fox_tools` is set to a non-boolean value, THEN THE
   system SHALL raise a `ConfigError` with a clear message identifying the
   field and expected type.
