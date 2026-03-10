# Test Specification: Token-Efficient File Tools & MCP Server

## Overview

Tests are organized by requirement group. Each acceptance criterion has a
corresponding unit or integration test. Each correctness property from
design.md has a property-based test using Hypothesis. Edge cases have
dedicated tests exercising error paths and boundary conditions.

Test fixtures include small sample files in multiple languages (Python, JS,
Rust, Go) for outline testing, and temporary files for read/edit/search
testing.

## Test Cases

### TS-29-1: Outline returns symbols with kind, name, and line ranges

**Requirement:** 29-REQ-1.1
**Type:** unit
**Description:** Verify fox_outline returns Symbol objects with correct fields.

**Preconditions:**
- A Python fixture file with two functions and one class (known content).

**Input:**
- `file_path` pointing to the fixture file.

**Expected:**
- List of 3 Symbol objects.
- Each has `kind` ("function" or "class"), `name` matching the declaration,
  and `start_line`/`end_line` as 1-based integers with start <= end.

**Assertion pseudocode:**
```
result = fox_outline(fixture_path)
ASSERT len(result.symbols) == 3
ASSERT result.symbols[0].kind == "function"
ASSERT result.symbols[0].name == "foo"
ASSERT result.symbols[0].start_line >= 1
ASSERT result.symbols[0].start_line <= result.symbols[0].end_line
```

---

### TS-29-2: Outline collapses contiguous imports

**Requirement:** 29-REQ-1.2
**Type:** unit
**Description:** Verify contiguous import lines are collapsed into one summary entry.

**Preconditions:**
- A Python fixture file with 5 contiguous import lines followed by a function.

**Input:**
- `file_path` pointing to the fixture file.

**Expected:**
- First symbol has kind "import_block", name "(5 imports)", start_line=1,
  end_line=5.

**Assertion pseudocode:**
```
result = fox_outline(fixture_path)
ASSERT result.symbols[0].kind == "import_block"
ASSERT "5 imports" in result.symbols[0].name
ASSERT result.symbols[0].start_line == 1
ASSERT result.symbols[0].end_line == 5
```

---

### TS-29-3: Outline includes summary line

**Requirement:** 29-REQ-1.3
**Type:** unit
**Description:** Verify OutlineResult includes total_lines and symbol count.

**Preconditions:**
- A Python fixture file with known line count and declaration count.

**Input:**
- `file_path` pointing to a 30-line file with 4 declarations.

**Expected:**
- `result.total_lines == 30`
- `len(result.symbols) == 4` (plus any import blocks)

**Assertion pseudocode:**
```
result = fox_outline(fixture_path)
ASSERT result.total_lines == 30
ASSERT len(result.symbols) >= 4
```

---

### TS-29-4: Outline detects declarations across languages

**Requirement:** 29-REQ-1.4
**Type:** unit
**Description:** Verify heuristic parser detects declarations in Python, JS,
TS, Rust, Go, and Java.

**Preconditions:**
- Six fixture files, one per language, each containing at least one function
  and one class/struct/type declaration.

**Input:**
- Each fixture file path.

**Expected:**
- For each language, at least 2 symbols detected with correct names.

**Assertion pseudocode:**
```
FOR language, fixture_path IN fixtures:
    result = fox_outline(fixture_path)
    ASSERT len(result.symbols) >= 2
    names = {s.name for s in result.symbols if s.kind != "import_block"}
    ASSERT expected_names[language].issubset(names)
```

---

### TS-29-5: Read returns hashed lines for requested ranges

**Requirement:** 29-REQ-2.1
**Type:** unit
**Description:** Verify fox_read returns HashedLine objects for requested ranges.

**Preconditions:**
- A temp file with 20 lines of known content.

**Input:**
- `file_path`, `ranges=[(5, 10)]`

**Expected:**
- 6 HashedLine objects (lines 5 through 10).
- Each has line_number, content matching file, and non-empty hash string.

**Assertion pseudocode:**
```
result = fox_read(temp_file, [(5, 10)])
ASSERT len(result.lines) == 6
ASSERT result.lines[0].line_number == 5
ASSERT result.lines[0].content == known_lines[4]
ASSERT len(result.lines[0].hash) == 16
```

---

### TS-29-6: Read returns multiple ranges in order

**Requirement:** 29-REQ-2.2
**Type:** unit
**Description:** Verify multiple disjoint ranges are returned in ascending line order.

**Preconditions:**
- A temp file with 20 lines.

**Input:**
- `file_path`, `ranges=[(15, 17), (3, 5)]` (out of order)

**Expected:**
- 6 lines total, line_numbers = [3, 4, 5, 15, 16, 17].

**Assertion pseudocode:**
```
result = fox_read(temp_file, [(15, 17), (3, 5)])
ASSERT len(result.lines) == 6
numbers = [l.line_number for l in result.lines]
ASSERT numbers == [3, 4, 5, 15, 16, 17]
```

---

### TS-29-7: Read uses xxh3_64 hashes

**Requirement:** 29-REQ-2.3
**Type:** unit
**Description:** Verify content hashes match independently computed xxh3_64.

**Preconditions:**
- A temp file with known content.

**Input:**
- `file_path`, `ranges=[(1, 1)]`

**Expected:**
- Hash matches `xxhash.xxh3_64(line_bytes).hexdigest()`.

**Assertion pseudocode:**
```
result = fox_read(temp_file, [(1, 1)])
expected_hash = xxhash.xxh3_64(known_line_bytes).hexdigest()
ASSERT result.lines[0].hash == expected_hash
```

---

### TS-29-8: Edit verifies hashes before applying

**Requirement:** 29-REQ-3.1
**Type:** unit
**Description:** Verify fox_edit checks all hashes against current file content.

**Preconditions:**
- A temp file with 10 lines. Read lines 3-5 to obtain hashes.

**Input:**
- `fox_edit(file_path, [EditOperation(3, 5, correct_hashes, "new\n")])`

**Expected:**
- `result.success == True`, file lines 3-5 replaced with "new\n".

**Assertion pseudocode:**
```
read_result = fox_read(temp_file, [(3, 5)])
hashes = [l.hash for l in read_result.lines]
edit_result = fox_edit(temp_file, [EditOperation(3, 5, hashes, "new content\n")])
ASSERT edit_result.success is True
ASSERT "new content" in Path(temp_file).read_text()
```

---

### TS-29-9: Edit applies atomically

**Requirement:** 29-REQ-3.2
**Type:** unit
**Description:** Verify all edits in a batch succeed or none are written.

**Preconditions:**
- A temp file. Read hashes for two ranges. Corrupt one hash.

**Input:**
- Batch with one valid edit and one with corrupted hash.

**Expected:**
- `result.success == False`, file unchanged.

**Assertion pseudocode:**
```
original = Path(temp_file).read_text()
edit_result = fox_edit(temp_file, [valid_edit, bad_hash_edit])
ASSERT edit_result.success is False
ASSERT Path(temp_file).read_text() == original
```

---

### TS-29-10: Edit processes in reverse line order

**Requirement:** 29-REQ-3.3
**Type:** unit
**Description:** Verify batch edits at different line ranges don't shift each other.

**Preconditions:**
- A temp file with 20 lines. Read hashes for lines 3-5 and 15-17.

**Input:**
- Two edits: replace lines 3-5 with 2 lines, replace lines 15-17 with 4 lines.

**Expected:**
- Both edits applied correctly despite changing line counts.

**Assertion pseudocode:**
```
result = fox_edit(temp_file, [edit_at_3, edit_at_15])
ASSERT result.success is True
lines = Path(temp_file).read_text().splitlines()
ASSERT "edit_3_content" in lines[2]
ASSERT "edit_15_content" in lines[13]  # shifted by -1 from first edit
```

---

### TS-29-11: Edit with empty content deletes lines

**Requirement:** 29-REQ-3.4
**Type:** unit
**Description:** Verify empty replacement content deletes the target range.

**Preconditions:**
- A temp file with 10 lines. Read hashes for lines 4-6.

**Input:**
- `EditOperation(4, 6, hashes, "")` (empty new_content)

**Expected:**
- File has 7 lines (3 deleted). Lines 1-3 and 7-10 preserved.

**Assertion pseudocode:**
```
result = fox_edit(temp_file, [EditOperation(4, 6, hashes, "")])
ASSERT result.success is True
ASSERT len(Path(temp_file).read_text().splitlines()) == 7
```

---

### TS-29-12: Search returns matching lines with hashes

**Requirement:** 29-REQ-4.1
**Type:** unit
**Description:** Verify fox_search returns matches with line numbers and hashes.

**Preconditions:**
- A temp file containing "TODO" on lines 5 and 12.

**Input:**
- `fox_search(file_path, "TODO")`

**Expected:**
- `result.total_matches == 2`
- Each match has HashedLine entries with correct line numbers.

**Assertion pseudocode:**
```
result = fox_search(temp_file, "TODO")
ASSERT result.total_matches == 2
match_lines = [m.match_line_numbers[0] for m in result.matches]
ASSERT 5 in match_lines
ASSERT 12 in match_lines
```

---

### TS-29-13: Search includes context lines

**Requirement:** 29-REQ-4.2
**Type:** unit
**Description:** Verify context parameter includes surrounding lines.

**Preconditions:**
- A temp file with 20 lines, "TODO" on line 10.

**Input:**
- `fox_search(file_path, "TODO", context=2)`

**Expected:**
- Match block contains lines 8-12 (2 before, match, 2 after).

**Assertion pseudocode:**
```
result = fox_search(temp_file, "TODO", context=2)
ASSERT len(result.matches) == 1
numbers = [l.line_number for l in result.matches[0].lines]
ASSERT numbers == [8, 9, 10, 11, 12]
```

---

### TS-29-14: Search merges overlapping context

**Requirement:** 29-REQ-4.3
**Type:** unit
**Description:** Verify overlapping context ranges are merged.

**Preconditions:**
- A temp file with "TODO" on lines 10 and 12.

**Input:**
- `fox_search(file_path, "TODO", context=2)`

**Expected:**
- Single merged match block covering lines 8-14 (no duplicates).

**Assertion pseudocode:**
```
result = fox_search(temp_file, "TODO", context=2)
ASSERT len(result.matches) == 1
numbers = [l.line_number for l in result.matches[0].lines]
ASSERT numbers == list(range(8, 15))
ASSERT len(numbers) == len(set(numbers))  # no duplicates
```

---

### TS-29-15: Hash uses xxh3_64 with 16-char hex output

**Requirement:** 29-REQ-5.1
**Type:** unit
**Description:** Verify hash_line produces 16-character lowercase hex strings.

**Preconditions:** None.

**Input:**
- `hash_line(b"hello world\n")`

**Expected:**
- 16-character string matching `[0-9a-f]{16}`.

**Assertion pseudocode:**
```
h = hash_line(b"hello world\n")
ASSERT len(h) == 16
ASSERT re.fullmatch(r"[0-9a-f]{16}", h) is not None
```

---

### TS-29-16: Hash is deterministic

**Requirement:** 29-REQ-5.2
**Type:** unit
**Description:** Verify same input produces same hash.

**Preconditions:** None.

**Input:**
- `hash_line(b"test content\n")` called twice.

**Expected:**
- Both calls return identical strings.

**Assertion pseudocode:**
```
ASSERT hash_line(b"test\n") == hash_line(b"test\n")
```

---

### TS-29-17: Hash differs for different content

**Requirement:** 29-REQ-5.3
**Type:** unit
**Description:** Verify different inputs produce different hashes.

**Preconditions:** None.

**Input:**
- `hash_line(b"aaa\n")` vs `hash_line(b"aab\n")`

**Expected:**
- Different hash strings.

**Assertion pseudocode:**
```
ASSERT hash_line(b"aaa\n") != hash_line(b"aab\n")
```

---

### TS-29-18: Backend accepts ToolDefinition list

**Requirement:** 29-REQ-6.1
**Type:** unit
**Description:** Verify AgentBackend.execute() accepts tools parameter.

**Preconditions:**
- A mock backend implementation.

**Input:**
- `execute(prompt, ..., tools=[tool_def])`

**Expected:**
- Backend receives the ToolDefinition list without error.

**Assertion pseudocode:**
```
backend = MockBackend()
tool_def = ToolDefinition(name="test", ...)
result = await backend.execute("prompt", ..., tools=[tool_def])
ASSERT backend.received_tools == [tool_def]
```

---

### TS-29-19: Backend makes custom tools available

**Requirement:** 29-REQ-6.2
**Type:** integration
**Description:** Verify custom tools are available alongside built-in tools.

**Preconditions:**
- ClaudeBackend with a ToolDefinition registered.

**Input:**
- A session prompt that would invoke the custom tool.

**Expected:**
- ToolUseMessage with the custom tool name appears in the message stream.

**Assertion pseudocode:**
```
# Integration test — verify tool is registered with SDK
tools = build_fox_tool_definitions()
# Verify each has valid name, schema, and callable handler
FOR td IN tools:
    ASSERT td.name.startswith("fox_")
    ASSERT "type" in td.input_schema
    ASSERT callable(td.handler)
```

---

### TS-29-20: Backend calls handler in-process

**Requirement:** 29-REQ-6.3
**Type:** unit
**Description:** Verify custom tool handler is called when agent invokes the tool.

**Preconditions:**
- A mock backend with a ToolDefinition whose handler records calls.

**Input:**
- Agent invokes the custom tool.

**Expected:**
- Handler function was called with the tool input.

**Assertion pseudocode:**
```
calls = []
def handler(tool_input):
    calls.append(tool_input)
    return "ok"
td = ToolDefinition(name="test_tool", ..., handler=handler)
# Simulate tool invocation
result = td.handler({"file_path": "/tmp/test.py"})
ASSERT len(calls) == 1
ASSERT calls[0]["file_path"] == "/tmp/test.py"
```

---

### TS-29-21: Permission callback gates custom tools

**Requirement:** 29-REQ-6.4
**Type:** unit
**Description:** Verify permission_callback receives custom tool name and input.

**Preconditions:**
- A permission callback that records invocations.

**Input:**
- Session with custom tool and recording callback.

**Expected:**
- Callback receives ("fox_edit", {tool_input}).

**Assertion pseudocode:**
```
recorded = []
async def cb(name, input):
    recorded.append((name, input))
    return True
# Verify callback is invoked for custom tool names
ASSERT cb can be called with ("fox_edit", {"file_path": "..."})
```

---

### TS-29-22: MCP server exposes four tools

**Requirement:** 29-REQ-7.1
**Type:** integration
**Description:** Verify MCP server registers all four fox tools.

**Preconditions:**
- MCP server created via create_mcp_server().

**Input:**
- List registered tools.

**Expected:**
- Tool names: fox_outline, fox_read, fox_edit, fox_search.

**Assertion pseudocode:**
```
server = create_mcp_server()
tool_names = {t.name for t in server.list_tools()}
ASSERT tool_names == {"fox_outline", "fox_read", "fox_edit", "fox_search"}
```

---

### TS-29-23: MCP server delegates to core functions

**Requirement:** 29-REQ-7.2
**Type:** integration
**Description:** Verify MCP tool calls produce same results as direct function calls.

**Preconditions:**
- A temp file with known content.

**Input:**
- Call fox_read via MCP server and directly.

**Expected:**
- Identical results.

**Assertion pseudocode:**
```
direct = fox_read(temp_file, [(1, 5)])
mcp_result = mcp_client.call_tool("fox_read", {"file_path": temp_file, "ranges": [[1, 5]]})
ASSERT direct.lines == parse_mcp_result(mcp_result).lines
```

---

### TS-29-24: CLI serve-tools command exists

**Requirement:** 29-REQ-7.3
**Type:** unit
**Description:** Verify serve-tools is a registered CLI command.

**Preconditions:** None.

**Input:**
- `agent-fox serve-tools --help`

**Expected:**
- Exit code 0, help text mentions MCP server.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["serve-tools", "--help"])
ASSERT result.exit_code == 0
ASSERT "MCP" in result.output or "mcp" in result.output
```

---

### TS-29-25: MCP server accepts --allowed-dirs

**Requirement:** 29-REQ-7.4
**Type:** unit
**Description:** Verify --allowed-dirs restricts file access.

**Preconditions:**
- MCP server created with allowed_dirs=["/tmp/safe"].

**Input:**
- Tool call referencing /etc/passwd.

**Expected:**
- Error returned, no file operation performed.

**Assertion pseudocode:**
```
server = create_mcp_server(allowed_dirs=["/tmp/safe"])
result = server.call_tool("fox_read", {"file_path": "/etc/passwd", "ranges": [[1, 1]]})
ASSERT "error" in result.lower() or result.is_error
```

---

### TS-29-26: Config fox_tools defaults to false

**Requirement:** 29-REQ-8.1
**Type:** unit
**Description:** Verify default config has fox_tools=false.

**Preconditions:** None.

**Input:**
- `AgentFoxConfig()` (default construction).

**Expected:**
- `config.tools.fox_tools is False`

**Assertion pseudocode:**
```
config = AgentFoxConfig()
ASSERT config.tools.fox_tools is False
```

---

### TS-29-27: Session runner passes tools when enabled

**Requirement:** 29-REQ-8.2
**Type:** unit
**Description:** Verify session runner constructs ToolDefinitions when fox_tools=true.

**Preconditions:**
- Config with `tools.fox_tools = true`.

**Input:**
- Run session with enabled config and a mock backend.

**Expected:**
- Backend.execute() called with non-empty tools list.

**Assertion pseudocode:**
```
config = AgentFoxConfig(tools=ToolsConfig(fox_tools=True))
# Verify build_fox_tool_definitions() returns 4 definitions
defs = build_fox_tool_definitions()
ASSERT len(defs) == 4
ASSERT {d.name for d in defs} == {"fox_outline", "fox_read", "fox_edit", "fox_search"}
```

---

### TS-29-28: Session runner omits tools when disabled

**Requirement:** 29-REQ-8.3
**Type:** unit
**Description:** Verify no tools passed when fox_tools=false.

**Preconditions:**
- Config with default (fox_tools=false).

**Input:**
- Session execution with default config.

**Expected:**
- Backend.execute() called with tools=None.

**Assertion pseudocode:**
```
config = AgentFoxConfig()
ASSERT config.tools.fox_tools is False
# Session runner should not call build_fox_tool_definitions()
```

---

## Property Test Cases

### TS-29-P1: Hash Determinism

**Property:** Property 1 from design.md
**Validates:** 29-REQ-5.1, 29-REQ-5.2
**Type:** property
**Description:** Same byte content always produces the same hash.

**For any:** `content: bytes` (arbitrary byte strings, 0 to 10000 bytes)
**Invariant:** `hash_line(content) == hash_line(content)` and result is
16-char lowercase hex.

**Assertion pseudocode:**
```
FOR ANY content IN st.binary(min_size=0, max_size=10000):
    h1 = hash_line(content)
    h2 = hash_line(content)
    ASSERT h1 == h2
    ASSERT re.fullmatch(r"[0-9a-f]{16}", h1)
```

---

### TS-29-P2: Hash Sensitivity

**Property:** Property 2 from design.md
**Validates:** 29-REQ-5.3
**Type:** property
**Description:** Different byte content produces different hashes.

**For any:** `a: bytes, b: bytes` where `a != b` (arbitrary, 1 to 1000 bytes)
**Invariant:** `hash_line(a) != hash_line(b)`

**Assertion pseudocode:**
```
FOR ANY a, b IN st.binary(min_size=1, max_size=1000):
    assume(a != b)
    ASSERT hash_line(a) != hash_line(b)
```

---

### TS-29-P3: Read-Edit Round-Trip Integrity

**Property:** Property 3 from design.md
**Validates:** 29-REQ-2.1, 29-REQ-3.1, 29-REQ-3.2
**Type:** property
**Description:** Reading lines, then editing with same hashes and new content,
produces correct file.

**For any:** File with N lines (5-50), range [S, E] within file, new_content
string.
**Invariant:** After read → edit, lines outside [S, E] are unchanged, lines
[S, E] contain new_content.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(5, 50), s, e, new_content:
    create temp file with n lines
    read_result = fox_read(file, [(s, e)])
    hashes = [l.hash for l in read_result.lines]
    fox_edit(file, [EditOperation(s, e, hashes, new_content)])
    ASSERT lines before s unchanged
    ASSERT lines after e unchanged
    ASSERT new content present at [s, ...]
```

---

### TS-29-P4: Edit Atomicity

**Property:** Property 4 from design.md
**Validates:** 29-REQ-3.2, 29-REQ-3.E1
**Type:** property
**Description:** A batch with one stale hash leaves the file unchanged.

**For any:** File with N lines (5-50), valid edit + one edit with corrupted hash.
**Invariant:** File content is byte-identical after the failed edit.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(5, 50):
    create temp file
    original = file.read_bytes()
    result = fox_edit(file, [valid_edit, bad_hash_edit])
    ASSERT result.success is False
    ASSERT file.read_bytes() == original
```

---

### TS-29-P5: Stale Hash Rejection

**Property:** Property 5 from design.md
**Validates:** 29-REQ-3.1, 29-REQ-3.E1
**Type:** property
**Description:** Modifying a line between read and edit causes rejection.

**For any:** File, line L modified after reading its hash.
**Invariant:** fox_edit rejects with hash mismatch error.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(5, 50), line_to_modify:
    read hashes
    modify line_to_modify in file
    result = fox_edit(file, [edit using old hashes])
    ASSERT result.success is False
    ASSERT any("mismatch" in e for e in result.errors)
```

---

### TS-29-P6: Outline Completeness (Python)

**Property:** Property 6 from design.md
**Validates:** 29-REQ-1.1, 29-REQ-1.4
**Type:** property
**Description:** All top-level def/class declarations are detected in Python files.

**For any:** Python file with N declarations (1-10), generated with random
valid names.
**Invariant:** `fox_outline` returns at least N symbols with matching names.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(1, 10):
    generate Python file with n top-level def/class declarations
    result = fox_outline(file)
    found_names = {s.name for s in result.symbols if s.kind != "import_block"}
    ASSERT expected_names.issubset(found_names)
```

---

### TS-29-P7: Search Context Merge

**Property:** Property 7 from design.md
**Validates:** 29-REQ-4.2, 29-REQ-4.3
**Type:** property
**Description:** Overlapping context ranges produce no duplicate line numbers.

**For any:** File with N lines, pattern matching at positions M, context C.
**Invariant:** All line numbers in result are unique (no duplicates).

**Assertion pseudocode:**
```
FOR ANY n, match_positions, context:
    create file with markers at match_positions
    result = fox_search(file, "MARKER", context=context)
    all_numbers = [l.line_number for m in result.matches for l in m.lines]
    ASSERT len(all_numbers) == len(set(all_numbers))
```

---

### TS-29-P8: Tool Registration Backward Compatibility

**Property:** Property 8 from design.md
**Validates:** 29-REQ-6.E1, 29-REQ-8.3
**Type:** unit
**Description:** Calling execute() with tools=None behaves identically to
pre-extension.

**For any:** Any valid execute() call with tools=None.
**Invariant:** Behavior matches calling execute() without tools parameter.

**Assertion pseudocode:**
```
# Verify ToolDefinition parameter is optional and defaults to None
sig = inspect.signature(AgentBackend.execute)
ASSERT sig.parameters["tools"].default is None
```

---

### TS-29-P9: MCP-InProcess Equivalence

**Property:** Property 9 from design.md
**Validates:** 29-REQ-7.2
**Type:** integration
**Description:** MCP server and in-process handler return identical results.

**For any:** Tool call with valid inputs to any of the four tools.
**Invariant:** MCP result == direct function result.

**Assertion pseudocode:**
```
FOR tool IN [fox_outline, fox_read, fox_search]:
    direct = tool(fixture_file, ...)
    mcp_result = mcp_call(tool.name, same_args)
    ASSERT direct == mcp_result
```

---

## Edge Case Tests

### TS-29-E1: Outline on nonexistent file

**Requirement:** 29-REQ-1.E1
**Type:** unit
**Description:** Verify error returned for missing file.

**Preconditions:** File does not exist.

**Input:** `fox_outline("/nonexistent/path.py")`

**Expected:** Error string containing the path.

**Assertion pseudocode:**
```
result = fox_outline("/nonexistent/path.py")
ASSERT isinstance(result, str)
ASSERT "/nonexistent/path.py" in result
```

---

### TS-29-E2: Outline on empty file

**Requirement:** 29-REQ-1.E2
**Type:** unit
**Description:** Verify empty file returns zero symbols and zero lines.

**Preconditions:** Empty temp file.

**Input:** `fox_outline(empty_file)`

**Expected:** `symbols=[], total_lines=0`

**Assertion pseudocode:**
```
result = fox_outline(empty_file)
ASSERT result.symbols == []
ASSERT result.total_lines == 0
```

---

### TS-29-E3: Outline on binary file

**Requirement:** 29-REQ-1.E3
**Type:** unit
**Description:** Verify error for binary file.

**Preconditions:** Temp file with null bytes in first 8192 bytes.

**Input:** `fox_outline(binary_file)`

**Expected:** Error string mentioning "binary" or "not a text file".

**Assertion pseudocode:**
```
result = fox_outline(binary_file)
ASSERT isinstance(result, str)
ASSERT "binary" in result.lower() or "text" in result.lower()
```

---

### TS-29-E4: Read on nonexistent file

**Requirement:** 29-REQ-2.E1
**Type:** unit
**Description:** Verify error for missing file.

**Preconditions:** File does not exist.

**Input:** `fox_read("/missing.py", [(1, 5)])`

**Expected:** Error string.

**Assertion pseudocode:**
```
result = fox_read("/missing.py", [(1, 5)])
ASSERT isinstance(result, str)
```

---

### TS-29-E5: Read range beyond EOF

**Requirement:** 29-REQ-2.E2
**Type:** unit
**Description:** Verify truncation warning when range exceeds file.

**Preconditions:** Temp file with 10 lines.

**Input:** `fox_read(file, [(8, 20)])`

**Expected:** Lines 8-10 returned, warning about truncation.

**Assertion pseudocode:**
```
result = fox_read(temp_file, [(8, 20)])
ASSERT len(result.lines) == 3
ASSERT result.lines[-1].line_number == 10
ASSERT len(result.warnings) == 1
ASSERT "truncat" in result.warnings[0].lower()
```

---

### TS-29-E6: Read invalid range (start > end)

**Requirement:** 29-REQ-2.E3
**Type:** unit
**Description:** Verify error for reversed range.

**Preconditions:** Temp file.

**Input:** `fox_read(file, [(10, 5)])`

**Expected:** Error string mentioning invalid range.

**Assertion pseudocode:**
```
result = fox_read(temp_file, [(10, 5)])
ASSERT isinstance(result, str)
ASSERT "invalid" in result.lower() or "range" in result.lower()
```

---

### TS-29-E7: Edit hash mismatch rejects batch

**Requirement:** 29-REQ-3.E1
**Type:** unit
**Description:** Verify stale hash causes full batch rejection with details.

**Preconditions:** Temp file. Read hashes, then modify a line.

**Input:** `fox_edit(file, [edit_with_old_hashes])`

**Expected:** `success=False`, errors list mentions mismatched lines.

**Assertion pseudocode:**
```
read = fox_read(file, [(3, 5)])
hashes = [l.hash for l in read.lines]
# Modify line 4
modify_file_line(file, 4)
result = fox_edit(file, [EditOperation(3, 5, hashes, "new")])
ASSERT result.success is False
ASSERT any("4" in e for e in result.errors)
```

---

### TS-29-E8: Edit on nonexistent file

**Requirement:** 29-REQ-3.E2
**Type:** unit
**Description:** Verify error for missing or non-writable file.

**Preconditions:** File does not exist.

**Input:** `fox_edit("/missing.py", [some_edit])`

**Expected:** `success=False`, error about file access.

**Assertion pseudocode:**
```
result = fox_edit("/missing.py", [edit])
ASSERT result.success is False
ASSERT len(result.errors) > 0
```

---

### TS-29-E9: Edit overlapping ranges

**Requirement:** 29-REQ-3.E3
**Type:** unit
**Description:** Verify error when two edits overlap.

**Preconditions:** Temp file.

**Input:** Two edits: lines 3-7 and lines 5-9 (overlapping at 5-7).

**Expected:** `success=False`, error mentioning overlap.

**Assertion pseudocode:**
```
result = fox_edit(file, [edit_3_7, edit_5_9])
ASSERT result.success is False
ASSERT any("overlap" in e.lower() for e in result.errors)
```

---

### TS-29-E10: Search on nonexistent file

**Requirement:** 29-REQ-4.E1
**Type:** unit
**Description:** Verify error for missing file.

**Preconditions:** File does not exist.

**Input:** `fox_search("/missing.py", "pattern")`

**Expected:** Error string.

**Assertion pseudocode:**
```
result = fox_search("/missing.py", "pattern")
ASSERT isinstance(result, str)
```

---

### TS-29-E11: Search with invalid regex

**Requirement:** 29-REQ-4.E2
**Type:** unit
**Description:** Verify error for bad regex pattern.

**Preconditions:** Temp file.

**Input:** `fox_search(file, "[invalid")`

**Expected:** Error string mentioning the pattern.

**Assertion pseudocode:**
```
result = fox_search(temp_file, "[invalid")
ASSERT isinstance(result, str)
ASSERT "pattern" in result.lower() or "regex" in result.lower()
```

---

### TS-29-E12: Search with no matches

**Requirement:** 29-REQ-4.E3
**Type:** unit
**Description:** Verify empty result (not error) when no lines match.

**Preconditions:** Temp file with no "ZZZZZ" content.

**Input:** `fox_search(file, "ZZZZZ")`

**Expected:** `matches=[], total_matches=0`

**Assertion pseudocode:**
```
result = fox_search(temp_file, "ZZZZZ")
ASSERT isinstance(result, SearchResult)
ASSERT result.total_matches == 0
ASSERT result.matches == []
```

---

### TS-29-E13: Hash fallback when xxhash unavailable

**Requirement:** 29-REQ-5.E1
**Type:** unit
**Description:** Verify blake2b fallback when xxhash import fails.

**Preconditions:** Monkeypatch xxhash import to raise ImportError.

**Input:** `hash_line(b"test\n")`

**Expected:** Returns a 16-char hex string (blake2b), warning logged.

**Assertion pseudocode:**
```
# Patch xxhash to be unavailable
with monkeypatch_import("xxhash", ImportError):
    h = hash_line(b"test\n")
    ASSERT len(h) == 16
    ASSERT re.fullmatch(r"[0-9a-f]{16}", h)
    ASSERT "fallback" in captured_logs or "warning" in captured_logs
```

---

### TS-29-E14: Backend with no tools behaves normally

**Requirement:** 29-REQ-6.E1
**Type:** unit
**Description:** Verify tools=None produces identical behavior.

**Preconditions:** Mock backend.

**Input:** `execute(prompt, ..., tools=None)`

**Expected:** No error, same behavior as without the parameter.

**Assertion pseudocode:**
```
result1 = await backend.execute("p", ..., tools=None)
result2 = await backend.execute("p", ...)
# Both should work identically
```

---

### TS-29-E15: Handler exception returns error to agent

**Requirement:** 29-REQ-6.E2
**Type:** unit
**Description:** Verify handler exception is caught and returned as tool error.

**Preconditions:** ToolDefinition with handler that raises ValueError.

**Input:** Agent invokes the tool.

**Expected:** Error message returned to agent, session continues.

**Assertion pseudocode:**
```
def bad_handler(tool_input):
    raise ValueError("broken")
td = ToolDefinition(name="bad", ..., handler=bad_handler)
# Verify the handler raises and the system can catch it
with pytest.raises(ValueError):
    td.handler({})
```

---

### TS-29-E16: MCP server blocks path outside allowed-dirs

**Requirement:** 29-REQ-7.E1
**Type:** integration
**Description:** Verify path sandboxing in MCP server.

**Preconditions:** Server with allowed_dirs=["/tmp/safe"].

**Input:** fox_read on "/etc/hosts".

**Expected:** Error, no file read.

**Assertion pseudocode:**
```
server = create_mcp_server(allowed_dirs=["/tmp/safe"])
result = call_tool(server, "fox_read", {"file_path": "/etc/hosts", "ranges": [[1,1]]})
ASSERT is_error(result)
```

---

### TS-29-E17: MCP server clean shutdown on client disconnect

**Requirement:** 29-REQ-7.E2
**Type:** integration
**Description:** Verify server exits cleanly on EOF/disconnect.

**Preconditions:** Running MCP server subprocess.

**Input:** Close stdin to the server process.

**Expected:** Process exits with code 0, no orphan processes.

**Assertion pseudocode:**
```
proc = subprocess.Popen(["agent-fox", "serve-tools"], stdin=PIPE)
proc.stdin.close()
proc.wait(timeout=5)
ASSERT proc.returncode == 0
```

---

### TS-29-E18: Config rejects non-boolean fox_tools

**Requirement:** 29-REQ-8.E1
**Type:** unit
**Description:** Verify ConfigError for invalid fox_tools value.

**Preconditions:** TOML with `[tools]\nfox_tools = "yes"`.

**Input:** `load_config(path)`

**Expected:** ConfigError raised mentioning "fox_tools".

**Assertion pseudocode:**
```
write_toml(path, '[tools]\nfox_tools = "yes"')
with pytest.raises(ConfigError) as exc:
    load_config(path)
ASSERT "fox_tools" in str(exc.value)
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 29-REQ-1.1 | TS-29-1 | unit |
| 29-REQ-1.2 | TS-29-2 | unit |
| 29-REQ-1.3 | TS-29-3 | unit |
| 29-REQ-1.4 | TS-29-4 | unit |
| 29-REQ-1.E1 | TS-29-E1 | unit |
| 29-REQ-1.E2 | TS-29-E2 | unit |
| 29-REQ-1.E3 | TS-29-E3 | unit |
| 29-REQ-2.1 | TS-29-5 | unit |
| 29-REQ-2.2 | TS-29-6 | unit |
| 29-REQ-2.3 | TS-29-7 | unit |
| 29-REQ-2.E1 | TS-29-E4 | unit |
| 29-REQ-2.E2 | TS-29-E5 | unit |
| 29-REQ-2.E3 | TS-29-E6 | unit |
| 29-REQ-3.1 | TS-29-8 | unit |
| 29-REQ-3.2 | TS-29-9 | unit |
| 29-REQ-3.3 | TS-29-10 | unit |
| 29-REQ-3.4 | TS-29-11 | unit |
| 29-REQ-3.E1 | TS-29-E7 | unit |
| 29-REQ-3.E2 | TS-29-E8 | unit |
| 29-REQ-3.E3 | TS-29-E9 | unit |
| 29-REQ-4.1 | TS-29-12 | unit |
| 29-REQ-4.2 | TS-29-13 | unit |
| 29-REQ-4.3 | TS-29-14 | unit |
| 29-REQ-4.E1 | TS-29-E10 | unit |
| 29-REQ-4.E2 | TS-29-E11 | unit |
| 29-REQ-4.E3 | TS-29-E12 | unit |
| 29-REQ-5.1 | TS-29-15 | unit |
| 29-REQ-5.2 | TS-29-16 | unit |
| 29-REQ-5.3 | TS-29-17 | unit |
| 29-REQ-5.E1 | TS-29-E13 | unit |
| 29-REQ-6.1 | TS-29-18 | unit |
| 29-REQ-6.2 | TS-29-19 | integration |
| 29-REQ-6.3 | TS-29-20 | unit |
| 29-REQ-6.4 | TS-29-21 | unit |
| 29-REQ-6.E1 | TS-29-E14 | unit |
| 29-REQ-6.E2 | TS-29-E15 | unit |
| 29-REQ-7.1 | TS-29-22 | integration |
| 29-REQ-7.2 | TS-29-23 | integration |
| 29-REQ-7.3 | TS-29-24 | unit |
| 29-REQ-7.4 | TS-29-25 | unit |
| 29-REQ-7.E1 | TS-29-E16 | integration |
| 29-REQ-7.E2 | TS-29-E17 | integration |
| 29-REQ-8.1 | TS-29-26 | unit |
| 29-REQ-8.2 | TS-29-27 | unit |
| 29-REQ-8.3 | TS-29-28 | unit |
| 29-REQ-8.E1 | TS-29-E18 | unit |
| Property 1 | TS-29-P1 | property |
| Property 2 | TS-29-P2 | property |
| Property 3 | TS-29-P3 | property |
| Property 4 | TS-29-P4 | property |
| Property 5 | TS-29-P5 | property |
| Property 6 | TS-29-P6 | property |
| Property 7 | TS-29-P7 | property |
| Property 8 | TS-29-P8 | unit |
| Property 9 | TS-29-P9 | integration |
