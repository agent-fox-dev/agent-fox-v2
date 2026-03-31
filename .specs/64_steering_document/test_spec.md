# Test Specification: Steering Document

## Overview

Tests cover five areas: init-time creation, runtime loading with placeholder
detection, context assembly ordering, skill template references, and AGENTS.md
template reference. Test cases map 1:1 to acceptance criteria and correctness
properties.

## Test Cases

### TS-64-1: Init creates steering file when absent

**Requirement:** 64-REQ-1.1
**Type:** unit
**Description:** Verify that `_ensure_steering_md()` creates the file when it
does not exist.

**Preconditions:**
- `tmp_path / ".specs"` directory does not contain `steering.md`.

**Input:**
- `project_root = tmp_path`

**Expected:**
- `tmp_path / ".specs" / "steering.md"` exists after the call.
- Return value is `"created"`.
- File content contains the sentinel marker `<!-- steering:placeholder -->`.

**Assertion pseudocode:**
```
result = _ensure_steering_md(tmp_path)
ASSERT result == "created"
path = tmp_path / ".specs" / "steering.md"
ASSERT path.exists()
ASSERT "<!-- steering:placeholder -->" IN path.read_text()
```

### TS-64-2: Init skips existing steering file

**Requirement:** 64-REQ-1.2
**Type:** unit
**Description:** Verify that `_ensure_steering_md()` does not overwrite an
existing file.

**Preconditions:**
- `tmp_path / ".specs" / "steering.md"` exists with custom content.

**Input:**
- `project_root = tmp_path`

**Expected:**
- Return value is `"skipped"`.
- File content is unchanged.

**Assertion pseudocode:**
```
(tmp_path / ".specs").mkdir()
(tmp_path / ".specs" / "steering.md").write_text("my directives")
result = _ensure_steering_md(tmp_path)
ASSERT result == "skipped"
ASSERT (tmp_path / ".specs" / "steering.md").read_text() == "my directives"
```

### TS-64-3: Placeholder contains sentinel and instructional comments

**Requirement:** 64-REQ-1.3
**Type:** unit
**Description:** Verify placeholder content structure.

**Preconditions:**
- None.

**Input:**
- Call `_ensure_steering_md(tmp_path)`.

**Expected:**
- File contains `<!-- steering:placeholder -->`.
- File contains instructional text inside HTML comments.
- No text outside comments is actionable (only whitespace/sentinel).

**Assertion pseudocode:**
```
_ensure_steering_md(tmp_path)
content = (tmp_path / ".specs" / "steering.md").read_text()
ASSERT "<!-- steering:placeholder -->" IN content
ASSERT "<!--" IN content
ASSERT load_steering(tmp_path) IS None  # placeholder is not loaded
```

### TS-64-4: Init creates .specs directory if needed

**Requirement:** 64-REQ-1.4
**Type:** unit
**Description:** Verify `.specs/` is created when absent.

**Preconditions:**
- `tmp_path / ".specs"` does not exist.

**Input:**
- `project_root = tmp_path`

**Expected:**
- `.specs/` directory is created.
- `steering.md` is created inside it.

**Assertion pseudocode:**
```
ASSERT NOT (tmp_path / ".specs").exists()
_ensure_steering_md(tmp_path)
ASSERT (tmp_path / ".specs").is_dir()
ASSERT (tmp_path / ".specs" / "steering.md").exists()
```

### TS-64-5: load_steering returns content for non-placeholder file

**Requirement:** 64-REQ-2.1
**Type:** unit
**Description:** Verify steering content is returned when file has real
directives.

**Preconditions:**
- `.specs/steering.md` contains user-authored directives.

**Input:**
- File content: `"Always use type hints.\n"`

**Expected:**
- `load_steering()` returns the content string.

**Assertion pseudocode:**
```
(tmp_path / ".specs" / "steering.md").write_text("Always use type hints.\n")
result = load_steering(tmp_path)
ASSERT result == "Always use type hints."
```

### TS-64-6: Steering placement in assembled context

**Requirement:** 64-REQ-2.2
**Type:** integration
**Description:** Verify steering section appears after spec files and before
memory facts.

**Preconditions:**
- Spec directory with at least `requirements.md`.
- `.specs/steering.md` with real content.
- Memory facts provided.

**Input:**
- spec_dir with requirements.md, steering.md with content, memory_facts list.

**Expected:**
- Assembled context contains `## Steering Directives` section.
- The steering section appears after `## Requirements` and before
  `## Memory Facts`.

**Assertion pseudocode:**
```
context = assemble_context(spec_dir, 1, ["fact1"], conn=conn, project_root=root)
req_pos = context.index("## Requirements")
steer_pos = context.index("## Steering Directives")
mem_pos = context.index("## Memory Facts")
ASSERT req_pos < steer_pos < mem_pos
```

### TS-64-7: Missing steering file skipped silently

**Requirement:** 64-REQ-2.3
**Type:** unit
**Description:** Verify no error when steering file is absent.

**Preconditions:**
- `.specs/steering.md` does not exist.

**Input:**
- `project_root = tmp_path` (no steering.md)

**Expected:**
- `load_steering()` returns `None`.
- No exception raised.

**Assertion pseudocode:**
```
result = load_steering(tmp_path)
ASSERT result IS None
```

### TS-64-8: Placeholder-only file returns None

**Requirement:** 64-REQ-2.4
**Type:** unit
**Description:** Verify placeholder content is detected and skipped.

**Preconditions:**
- `.specs/steering.md` contains only the placeholder template.

**Input:**
- File content: the exact placeholder template from init.

**Expected:**
- `load_steering()` returns `None`.

**Assertion pseudocode:**
```
_ensure_steering_md(tmp_path)
result = load_steering(tmp_path)
ASSERT result IS None
```

### TS-64-9: Skill templates contain steering reference

**Requirement:** 64-REQ-3.1, 64-REQ-3.2
**Type:** unit
**Description:** Verify every bundled skill template references steering.md.

**Preconditions:**
- All skill template files in `agent_fox/_templates/skills/`.

**Input:**
- Read each skill template file.

**Expected:**
- Each file contains a reference to `.specs/steering.md`.

**Assertion pseudocode:**
```
FOR EACH template IN skills_dir.iterdir():
    content = template.read_text()
    ASSERT ".specs/steering.md" IN content
```

### TS-64-10: AGENTS.md template contains steering reference

**Requirement:** 64-REQ-4.1, 64-REQ-4.2
**Type:** unit
**Description:** Verify AGENTS.md template references steering.md in the
orientation section.

**Preconditions:**
- `agent_fox/_templates/agents_md.md` exists.

**Input:**
- Read the template file.

**Expected:**
- File contains a reference to `.specs/steering.md`.
- The reference appears after "Read `README.md`" and before "Explore the
  codebase".

**Assertion pseudocode:**
```
content = agents_md_template.read_text()
ASSERT ".specs/steering.md" IN content
readme_pos = content.index("README.md")
steering_pos = content.index("steering.md")
explore_pos = content.index("Explore the codebase")
ASSERT readme_pos < steering_pos < explore_pos
```

### TS-64-11: Sentinel marker present in placeholder

**Requirement:** 64-REQ-5.1
**Type:** unit
**Description:** Verify the placeholder contains the sentinel marker.

**Preconditions:**
- None (tests the constant).

**Input:**
- The `_STEERING_PLACEHOLDER` constant.

**Expected:**
- Contains `<!-- steering:placeholder -->`.

**Assertion pseudocode:**
```
ASSERT "<!-- steering:placeholder -->" IN _STEERING_PLACEHOLDER
```

## Property Test Cases

### TS-64-P1: Idempotent initialization

**Property:** Property 1 from design.md
**Validates:** 64-REQ-1.1, 64-REQ-1.2
**Type:** property
**Description:** Creating the steering file is idempotent — calling init
twice never changes an existing file.

**For any:** file content string (text strategy, min_size=1)
**Invariant:** If `.specs/steering.md` exists with content C before calling
`_ensure_steering_md()`, then after the call the file still contains C and
the return value is `"skipped"`.

**Assertion pseudocode:**
```
FOR ANY content IN text(min_size=1):
    (tmp_path / ".specs").mkdir(exist_ok=True)
    (tmp_path / ".specs" / "steering.md").write_text(content)
    result = _ensure_steering_md(tmp_path)
    ASSERT result == "skipped"
    ASSERT (tmp_path / ".specs" / "steering.md").read_text() == content
```

### TS-64-P2: Placeholder detection accuracy

**Property:** Property 2 from design.md
**Validates:** 64-REQ-5.1, 64-REQ-5.2, 64-REQ-2.4
**Type:** property
**Description:** Placeholder-only content is always detected; content with
real directives is never mistakenly treated as placeholder.

**For any:** directive string (text strategy, min_size=1, alphabet excluding
`<`, `>`, `-` to avoid generating comment-like content)
**Invariant:** A file containing the placeholder template plus the directive
string appended returns non-None from `load_steering()`.

**Assertion pseudocode:**
```
FOR ANY directive IN text(min_size=1, alphabet=alphanumeric+spaces):
    content = _STEERING_PLACEHOLDER + "\n" + directive
    (tmp_path / ".specs" / "steering.md").write_text(content)
    result = load_steering(tmp_path)
    ASSERT result IS NOT None
```

### TS-64-P3: Context ordering invariant

**Property:** Property 3 from design.md
**Validates:** 64-REQ-2.2
**Type:** property
**Description:** Steering always appears between specs and memory in
assembled context.

**For any:** steering content string (text strategy, min_size=1), list of
memory fact strings (lists of text, min_size=1)
**Invariant:** In the assembled context, the index of "## Steering Directives"
is greater than the index of any spec section header and less than the index
of "## Memory Facts".

**Assertion pseudocode:**
```
FOR ANY steering IN text(min_size=1), facts IN lists(text, min_size=1):
    write steering to .specs/steering.md
    context = assemble_context(spec_dir, 1, facts, conn=conn, project_root=root)
    IF "## Steering Directives" IN context AND "## Memory Facts" IN context:
        steer_pos = context.index("## Steering Directives")
        mem_pos = context.index("## Memory Facts")
        ASSERT steer_pos < mem_pos
```

## Edge Case Tests

### TS-64-E1: Permission error creating .specs directory

**Requirement:** 64-REQ-1.E1
**Type:** unit
**Description:** Init handles permission errors gracefully.

**Preconditions:**
- `.specs/` parent directory is read-only (simulated via monkeypatch).

**Input:**
- `project_root = tmp_path` with mkdir patched to raise `OSError`.

**Expected:**
- No exception raised.
- Return value is `"skipped"` or similar non-error indicator.
- Warning is logged.

**Assertion pseudocode:**
```
monkeypatch Path.mkdir to raise OSError
result = _ensure_steering_md(tmp_path)
ASSERT result == "skipped"
ASSERT warning logged
```

### TS-64-E2: Unreadable steering file at runtime

**Requirement:** 64-REQ-2.E1
**Type:** unit
**Description:** Runtime handles unreadable steering file gracefully.

**Preconditions:**
- `.specs/steering.md` exists but `read_text` raises `PermissionError`.

**Input:**
- `project_root = tmp_path` with file read patched to raise.

**Expected:**
- `load_steering()` returns `None`.
- Warning is logged.

**Assertion pseudocode:**
```
create .specs/steering.md
monkeypatch read_text to raise PermissionError
result = load_steering(tmp_path)
ASSERT result IS None
ASSERT warning logged
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 64-REQ-1.1 | TS-64-1 | unit |
| 64-REQ-1.2 | TS-64-2 | unit |
| 64-REQ-1.3 | TS-64-3 | unit |
| 64-REQ-1.4 | TS-64-4 | unit |
| 64-REQ-1.E1 | TS-64-E1 | unit |
| 64-REQ-2.1 | TS-64-5 | unit |
| 64-REQ-2.2 | TS-64-6 | integration |
| 64-REQ-2.3 | TS-64-7 | unit |
| 64-REQ-2.4 | TS-64-8 | unit |
| 64-REQ-2.E1 | TS-64-E2 | unit |
| 64-REQ-3.1 | TS-64-9 | unit |
| 64-REQ-3.2 | TS-64-9 | unit |
| 64-REQ-4.1 | TS-64-10 | unit |
| 64-REQ-4.2 | TS-64-10 | unit |
| 64-REQ-5.1 | TS-64-11 | unit |
| 64-REQ-5.2 | TS-64-8 | unit |
| Property 1 | TS-64-P1 | property |
| Property 2 | TS-64-P2 | property |
| Property 3 | TS-64-P3 | property |
