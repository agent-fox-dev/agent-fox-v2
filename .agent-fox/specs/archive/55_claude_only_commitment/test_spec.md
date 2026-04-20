# Test Specification: Claude-Only Commitment

## Overview

Tests validate that the backend factory is simplified, the protocol is
preserved, and documentation artifacts exist. Most tests are unit-level
(import checks, signature inspection). Property tests cover factory
invariants. One integration test verifies no stale call sites remain.

## Test Cases

### TS-55-1: ADR File Exists

**Requirement:** 55-REQ-1.1
**Type:** integration
**Description:** Verify that an ADR file for the Claude-only decision exists
in `docs/adr/`.

**Preconditions:**
- The `docs/adr/` directory exists.

**Input:**
- Glob pattern `docs/adr/*use-claude-exclusively*`.

**Expected:**
- Exactly one file matches the pattern.

**Assertion pseudocode:**
```
matches = glob("docs/adr/*use-claude-exclusively*")
ASSERT len(matches) == 1
```

### TS-55-2: ADR Contains Alternatives Section

**Requirement:** 55-REQ-1.2
**Type:** unit
**Description:** Verify the ADR lists considered alternatives.

**Preconditions:**
- ADR file exists (TS-55-1 passes).

**Input:**
- Contents of the ADR file.

**Expected:**
- File contains headings or text referencing "Alternatives" or
  "Considered Options" and mentions OpenAI, Gemini, and multi-provider.

**Assertion pseudocode:**
```
content = read_file(adr_path)
ASSERT "OpenAI" in content
ASSERT "Gemini" in content
ASSERT "multi-provider" in content OR "multiple providers" in content
```

### TS-55-3: ADR Mentions Future Non-Coding Use

**Requirement:** 55-REQ-1.3
**Type:** unit
**Description:** Verify the ADR acknowledges future non-coding provider use.

**Preconditions:**
- ADR file exists.

**Input:**
- Contents of the ADR file.

**Expected:**
- File contains text about non-coding tasks and future providers.

**Assertion pseudocode:**
```
content = read_file(adr_path)
ASSERT "non-coding" in content.lower() OR "embeddings" in content.lower()
```

### TS-55-4: get_backend Returns ClaudeBackend Without Arguments

**Requirement:** 55-REQ-2.1
**Type:** unit
**Description:** Verify `get_backend()` returns a `ClaudeBackend` with no
arguments.

**Preconditions:**
- `agent_fox.session.backends` is importable.

**Input:**
- Call `get_backend()` with no arguments.

**Expected:**
- Returns an instance of `ClaudeBackend`.

**Assertion pseudocode:**
```
from agent_fox.session.backends import get_backend
from agent_fox.session.backends.claude import ClaudeBackend
result = get_backend()
ASSERT isinstance(result, ClaudeBackend)
```

### TS-55-5: get_backend Accepts No Name Parameter

**Requirement:** 55-REQ-2.2
**Type:** unit
**Description:** Verify `get_backend()` signature has no parameters.

**Preconditions:**
- `get_backend` is importable.

**Input:**
- Inspect the function signature.

**Expected:**
- The function has zero parameters (excluding `self` if applicable).

**Assertion pseudocode:**
```
import inspect
sig = inspect.signature(get_backend)
params = [p for p in sig.parameters if p != "self"]
ASSERT len(params) == 0
```

### TS-55-6: No Call Sites Pass Name Argument

**Requirement:** 55-REQ-2.3
**Type:** integration
**Description:** Verify no Python file in `agent_fox/` calls `get_backend`
with an argument.

**Preconditions:**
- Source tree is available.

**Input:**
- Grep for `get_backend(` with a non-empty argument.

**Expected:**
- No matches found (all calls use `get_backend()` with no args).

**Assertion pseudocode:**
```
import re, pathlib
pattern = re.compile(r'get_backend\([^)]+\)')
matches = []
for f in pathlib.Path("agent_fox").rglob("*.py"):
    if pattern.search(f.read_text()):
        matches.append(f)
ASSERT len(matches) == 0
```

### TS-55-7: AgentBackend Protocol Still Exported

**Requirement:** 55-REQ-3.1
**Type:** unit
**Description:** Verify `AgentBackend` is importable from the backends package.

**Preconditions:**
- Package is importable.

**Input:**
- Import `AgentBackend` from `agent_fox.session.backends`.

**Expected:**
- Import succeeds, `AgentBackend` is a runtime-checkable Protocol.

**Assertion pseudocode:**
```
from agent_fox.session.backends import AgentBackend
ASSERT hasattr(AgentBackend, '__protocol_attrs__') OR is Protocol subclass
```

### TS-55-8: AgentBackend Docstring Mentions Claude-Only

**Requirement:** 55-REQ-3.2
**Type:** unit
**Description:** Verify `AgentBackend` docstring states ClaudeBackend is
the only production implementation.

**Preconditions:**
- `AgentBackend` is importable.

**Input:**
- Read `AgentBackend.__doc__`.

**Expected:**
- Docstring contains "ClaudeBackend" and "production" or "only".

**Assertion pseudocode:**
```
from agent_fox.session.backends.protocol import AgentBackend
doc = AgentBackend.__doc__
ASSERT "ClaudeBackend" in doc
ASSERT "production" in doc.lower() OR "only" in doc.lower()
```

### TS-55-9: README Mentions Claude-Only

**Requirement:** 55-REQ-5.1
**Type:** integration
**Description:** Verify README.md states agent-fox is built for Claude.

**Preconditions:**
- `README.md` exists at project root.

**Input:**
- Contents of `README.md`.

**Expected:**
- Contains "Claude" in a context indicating exclusivity.

**Assertion pseudocode:**
```
content = read_file("README.md")
ASSERT "claude" in content.lower()
ASSERT "built" in content.lower() OR "exclusively" in content.lower() OR "powered by" in content.lower()
```

## Property Test Cases

### TS-55-P1: Factory Always Returns AgentBackend

**Property:** Property 1 from design.md
**Validates:** 55-REQ-2.1, 55-REQ-3.1
**Type:** property
**Description:** `get_backend()` always returns an object satisfying
`AgentBackend`.

**For any:** N calls to `get_backend()` (N in 1..100)
**Invariant:** Every returned object is an instance of both `ClaudeBackend`
and `AgentBackend`.

**Assertion pseudocode:**
```
FOR ANY n IN range(1, 100):
    result = get_backend()
    ASSERT isinstance(result, ClaudeBackend)
    ASSERT isinstance(result, AgentBackend)
```

### TS-55-P2: Factory Has No Parameters

**Property:** Property 2 from design.md
**Validates:** 55-REQ-2.1, 55-REQ-2.2
**Type:** property
**Description:** The factory function signature has zero parameters.

**For any:** inspection of `get_backend`
**Invariant:** Parameter count is exactly zero.

**Assertion pseudocode:**
```
sig = inspect.signature(get_backend)
ASSERT len(sig.parameters) == 0
```

### TS-55-P3: Protocol Is Runtime Checkable

**Property:** Property 3 from design.md
**Validates:** 55-REQ-3.1, 55-REQ-3.E1
**Type:** property
**Description:** `AgentBackend` is a runtime-checkable Protocol.

**For any:** mock object implementing the AgentBackend interface
**Invariant:** `isinstance(mock, AgentBackend)` returns True.

**Assertion pseudocode:**
```
from typing import runtime_checkable, Protocol
ASSERT issubclass(AgentBackend, Protocol)
ASSERT getattr(AgentBackend, '__protocol_attrs__', None) is not None OR runtime_checkable applied
```

## Edge Case Tests

### TS-55-E1: ADR Number Non-Collision

**Requirement:** 55-REQ-1.E1
**Type:** unit
**Description:** Verify that the ADR file uses a non-conflicting number.

**Preconditions:**
- `docs/adr/` contains existing ADR files.

**Input:**
- List all ADR files and extract their numeric prefixes.

**Expected:**
- The new ADR's number does not collide with any existing ADR.

**Assertion pseudocode:**
```
adrs = glob("docs/adr/[0-9]*.md")
numbers = [extract_number(f) for f in adrs]
ASSERT len(numbers) == len(set(numbers))  # no duplicates
```

### TS-55-E2: Test Mock Satisfies Protocol

**Requirement:** 55-REQ-3.E1
**Type:** unit
**Description:** Verify a mock backend passes isinstance check.

**Preconditions:**
- `AgentBackend` is importable.

**Input:**
- Create a mock implementing all AgentBackend methods.

**Expected:**
- `isinstance(mock, AgentBackend)` returns True.

**Assertion pseudocode:**
```
class MockBackend:
    @property
    def name(self): return "mock"
    async def execute(self, prompt, *, system_prompt, model, cwd, **kw): yield
    async def close(self): pass

ASSERT isinstance(MockBackend(), AgentBackend)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 55-REQ-1.1 | TS-55-1 | integration |
| 55-REQ-1.2 | TS-55-2 | unit |
| 55-REQ-1.3 | TS-55-3 | unit |
| 55-REQ-1.E1 | TS-55-E1 | unit |
| 55-REQ-2.1 | TS-55-4, TS-55-P1 | unit, property |
| 55-REQ-2.2 | TS-55-5, TS-55-P2 | unit, property |
| 55-REQ-2.3 | TS-55-6 | integration |
| 55-REQ-2.E1 | TS-55-6 | integration |
| 55-REQ-3.1 | TS-55-7, TS-55-P1, TS-55-P3 | unit, property |
| 55-REQ-3.2 | TS-55-8 | unit |
| 55-REQ-3.E1 | TS-55-E2, TS-55-P3 | unit, property |
| 55-REQ-4.1 | (no code change; verified by TS-55-4) | — |
| 55-REQ-4.2 | (no code change; visual inspection) | — |
| 55-REQ-5.1 | TS-55-9 | integration |
| Property 1 | TS-55-P1 | property |
| Property 2 | TS-55-P2 | property |
| Property 3 | TS-55-P3 | property |
| Property 4 | TS-55-1 | integration |
