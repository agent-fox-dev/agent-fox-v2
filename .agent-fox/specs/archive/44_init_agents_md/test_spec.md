# Test Specification: Init AGENTS.md Template

## Overview

This test specification defines test contracts for the `_ensure_agents_md()`
function and its integration into the `init_cmd()` command. Tests map
directly to acceptance criteria in `requirements.md` and correctness
properties in `design.md`.

## Test Cases

### TS-44-1: Template File Exists in Package

**Requirement:** 44-REQ-1.1
**Type:** unit
**Description:** Verify the bundled template file exists at the expected path.

**Preconditions:**
- The agent-fox package is installed.

**Input:**
- Resolve `agent_fox/_templates/agents_md.md` via `Path(__file__)`.

**Expected:**
- The file exists and is non-empty.

**Assertion pseudocode:**
```
template_path = Path(agent_fox.__file__).parent / "_templates" / "agents_md.md"
ASSERT template_path.exists()
ASSERT template_path.stat().st_size > 0
```

### TS-44-2: Template Is Valid UTF-8

**Requirement:** 44-REQ-1.2
**Type:** unit
**Description:** Verify the template can be read as UTF-8 without errors.

**Preconditions:**
- Template file exists.

**Input:**
- Read the template file with UTF-8 encoding.

**Expected:**
- No `UnicodeDecodeError` is raised.

**Assertion pseudocode:**
```
content = template_path.read_text(encoding="utf-8")
ASSERT len(content) > 0
```

### TS-44-3: Template Contains Placeholder Markers

**Requirement:** 44-REQ-1.3
**Type:** unit
**Description:** Verify the template contains at least one placeholder marker.

**Preconditions:**
- Template file exists.

**Input:**
- Read the template content.

**Expected:**
- Content contains at least one angle-bracketed placeholder (e.g., `<main_package>`).

**Assertion pseudocode:**
```
content = template_path.read_text()
ASSERT "<main_package>" IN content OR "<test_directory>" IN content
```

### TS-44-4: Creates AGENTS.md When Absent

**Requirement:** 44-REQ-2.1
**Type:** unit
**Description:** Verify `_ensure_agents_md` creates the file when it does not exist.

**Preconditions:**
- Temporary directory with no `AGENTS.md` file.

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- `AGENTS.md` exists in `tmp_dir`.
- Content matches the bundled template.

**Assertion pseudocode:**
```
result = _ensure_agents_md(tmp_dir)
agents_md = tmp_dir / "AGENTS.md"
ASSERT agents_md.exists()
ASSERT agents_md.read_text() == template_content
ASSERT result == "created"
```

### TS-44-5: Displays Creation Message

**Requirement:** 44-REQ-2.2
**Type:** integration
**Description:** Verify `init_cmd` displays "Created AGENTS.md." when the file is created.

**Preconditions:**
- Temporary git repository with no `AGENTS.md`.

**Input:**
- Invoke `agent-fox init` via Click test runner.

**Expected:**
- stdout contains `Created AGENTS.md.`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(init_cmd)
ASSERT "Created AGENTS.md." IN result.output
```

### TS-44-6: JSON Output Contains agents_md Created

**Requirement:** 44-REQ-2.3
**Type:** integration
**Description:** Verify JSON output includes `"agents_md": "created"` on fresh init.

**Preconditions:**
- Temporary git repository with no `AGENTS.md`.
- JSON mode enabled.

**Input:**
- Invoke `agent-fox --json init` via Click test runner.

**Expected:**
- JSON output contains `"agents_md": "created"`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(cli, ["--json", "init"])
data = json.loads(result.output)
ASSERT data["agents_md"] == "created"
```

### TS-44-7: Skips When AGENTS.md Exists

**Requirement:** 44-REQ-3.1
**Type:** unit
**Description:** Verify `_ensure_agents_md` does not overwrite an existing file.

**Preconditions:**
- Temporary directory with an existing `AGENTS.md` containing custom content.

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- `AGENTS.md` content is unchanged.
- Return value is `"skipped"`.

**Assertion pseudocode:**
```
agents_md = tmp_dir / "AGENTS.md"
agents_md.write_text("custom content")
result = _ensure_agents_md(tmp_dir)
ASSERT agents_md.read_text() == "custom content"
ASSERT result == "skipped"
```

### TS-44-8: Silent Skip — No Message

**Requirement:** 44-REQ-3.2
**Type:** integration
**Description:** Verify no AGENTS.md message is displayed on re-init when file exists.

**Preconditions:**
- Temporary git repository with an existing `AGENTS.md`.

**Input:**
- Invoke `agent-fox init` via Click test runner.

**Expected:**
- stdout does NOT contain `AGENTS.md`.

**Assertion pseudocode:**
```
(tmp_dir / "AGENTS.md").write_text("existing")
result = cli_runner.invoke(init_cmd)
ASSERT "AGENTS.md" NOT IN result.output
```

### TS-44-9: JSON Output Contains agents_md Skipped

**Requirement:** 44-REQ-3.3
**Type:** integration
**Description:** Verify JSON output includes `"agents_md": "skipped"` on re-init.

**Preconditions:**
- Temporary git repository with existing `AGENTS.md`.
- JSON mode enabled.

**Input:**
- Invoke `agent-fox --json init` via Click test runner.

**Expected:**
- JSON output contains `"agents_md": "skipped"`.

**Assertion pseudocode:**
```
(tmp_dir / "AGENTS.md").write_text("existing")
result = cli_runner.invoke(cli, ["--json", "init"])
data = json.loads(result.output)
ASSERT data["agents_md"] == "skipped"
```

### TS-44-10: Created Regardless of CLAUDE.md Presence

**Requirement:** 44-REQ-4.1
**Type:** unit
**Description:** Verify AGENTS.md is created even when CLAUDE.md exists.

**Preconditions:**
- Temporary directory with a `CLAUDE.md` file but no `AGENTS.md`.

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- `AGENTS.md` is created.

**Assertion pseudocode:**
```
(tmp_dir / "CLAUDE.md").write_text("# Instructions")
result = _ensure_agents_md(tmp_dir)
ASSERT (tmp_dir / "AGENTS.md").exists()
ASSERT result == "created"
```

### TS-44-11: Created When CLAUDE.md Absent

**Requirement:** 44-REQ-4.2
**Type:** unit
**Description:** Verify AGENTS.md is created when CLAUDE.md does not exist.

**Preconditions:**
- Temporary directory with no `CLAUDE.md` and no `AGENTS.md`.

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- `AGENTS.md` is created.

**Assertion pseudocode:**
```
result = _ensure_agents_md(tmp_dir)
ASSERT (tmp_dir / "AGENTS.md").exists()
ASSERT result == "created"
```

### TS-44-12: Not Added to Gitignore

**Requirement:** 44-REQ-5.1
**Type:** integration
**Description:** Verify AGENTS.md is not added to .gitignore by init.

**Preconditions:**
- Temporary git repository.

**Input:**
- Invoke `agent-fox init` via Click test runner.

**Expected:**
- `.gitignore` does not contain `AGENTS.md`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(init_cmd)
gitignore = (tmp_dir / ".gitignore").read_text()
ASSERT "AGENTS.md" NOT IN gitignore
```

## Edge Case Tests

### TS-44-E1: Missing Template File

**Requirement:** 44-REQ-1.E1
**Type:** unit
**Description:** Verify a clear error when the template file is missing.

**Preconditions:**
- The template path is monkeypatched to a non-existent file.

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- `FileNotFoundError` is raised.

**Assertion pseudocode:**
```
monkeypatch _AGENTS_MD_TEMPLATE to Path("/nonexistent/agents_md.md")
ASSERT RAISES FileNotFoundError:
    _ensure_agents_md(tmp_dir)
```

### TS-44-E2: Empty Existing AGENTS.md

**Requirement:** 44-REQ-3.E1
**Type:** unit
**Description:** Verify an empty AGENTS.md is not overwritten.

**Preconditions:**
- Temporary directory with an empty `AGENTS.md` (zero bytes).

**Input:**
- Call `_ensure_agents_md(tmp_dir)`.

**Expected:**
- File is unchanged (still empty).
- Return value is `"skipped"`.

**Assertion pseudocode:**
```
agents_md = tmp_dir / "AGENTS.md"
agents_md.write_text("")
result = _ensure_agents_md(tmp_dir)
ASSERT agents_md.read_text() == ""
ASSERT result == "skipped"
```

## Property Test Cases

### TS-44-P1: Idempotent Creation

**Property:** Property 1 from design.md
**Validates:** 44-REQ-2.1, 44-REQ-3.1
**Type:** property
**Description:** Calling `_ensure_agents_md` twice produces the same result as calling it once.

**For any:** empty temporary directory
**Invariant:** After two calls, the file content equals the template and the
second call returns `"skipped"`.

**Assertion pseudocode:**
```
FOR ANY tmp_dir IN empty_directories:
    result1 = _ensure_agents_md(tmp_dir)
    content1 = (tmp_dir / "AGENTS.md").read_text()
    result2 = _ensure_agents_md(tmp_dir)
    content2 = (tmp_dir / "AGENTS.md").read_text()
    ASSERT result1 == "created"
    ASSERT result2 == "skipped"
    ASSERT content1 == content2
```

### TS-44-P2: Content Fidelity

**Property:** Property 2 from design.md
**Validates:** 44-REQ-1.1, 44-REQ-2.1
**Type:** property
**Description:** Created file always matches the template exactly.

**For any:** empty temporary directory
**Invariant:** The written file is byte-identical to the bundled template.

**Assertion pseudocode:**
```
FOR ANY tmp_dir IN empty_directories:
    _ensure_agents_md(tmp_dir)
    written = (tmp_dir / "AGENTS.md").read_bytes()
    template = _AGENTS_MD_TEMPLATE.read_bytes()
    ASSERT written == template
```

### TS-44-P3: Existing File Preservation

**Property:** Property 3 from design.md
**Validates:** 44-REQ-3.1, 44-REQ-3.E1
**Type:** property
**Description:** Existing AGENTS.md content is never modified.

**For any:** text content (including empty strings)
**Invariant:** If AGENTS.md exists with that content before the call, it has
the same content after.

**Assertion pseudocode:**
```
FOR ANY content IN text(min_size=0, max_size=10000):
    agents_md = tmp_dir / "AGENTS.md"
    agents_md.write_text(content)
    _ensure_agents_md(tmp_dir)
    ASSERT agents_md.read_text() == content
```

### TS-44-P4: CLAUDE.md Independence

**Property:** Property 4 from design.md
**Validates:** 44-REQ-4.1, 44-REQ-4.2
**Type:** property
**Description:** Behavior is identical with or without CLAUDE.md.

**For any:** boolean indicating CLAUDE.md presence
**Invariant:** The return value and resulting AGENTS.md content are the same
regardless of CLAUDE.md existence.

**Assertion pseudocode:**
```
FOR ANY claude_present IN booleans():
    tmp1 = make_temp_dir()
    tmp2 = make_temp_dir()
    IF claude_present:
        (tmp1 / "CLAUDE.md").write_text("# Instructions")
    result1 = _ensure_agents_md(tmp1)
    result2 = _ensure_agents_md(tmp2)
    ASSERT result1 == result2
    ASSERT (tmp1 / "AGENTS.md").read_text() == (tmp2 / "AGENTS.md").read_text()
```

### TS-44-P5: Return Value Correctness

**Property:** Property 5 from design.md
**Validates:** 44-REQ-2.3, 44-REQ-3.3
**Type:** property
**Description:** Return value accurately reflects whether the file was created.

**For any:** boolean indicating prior AGENTS.md existence
**Invariant:** Returns `"created"` iff file did not exist before call,
`"skipped"` iff it did.

**Assertion pseudocode:**
```
FOR ANY exists_before IN booleans():
    IF exists_before:
        (tmp_dir / "AGENTS.md").write_text("existing")
    result = _ensure_agents_md(tmp_dir)
    IF exists_before:
        ASSERT result == "skipped"
    ELSE:
        ASSERT result == "created"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 44-REQ-1.1 | TS-44-1 | unit |
| 44-REQ-1.2 | TS-44-2 | unit |
| 44-REQ-1.3 | TS-44-3 | unit |
| 44-REQ-1.E1 | TS-44-E1 | unit |
| 44-REQ-2.1 | TS-44-4 | unit |
| 44-REQ-2.2 | TS-44-5 | integration |
| 44-REQ-2.3 | TS-44-6 | integration |
| 44-REQ-2.E1 | (implicit — OS error propagation) | — |
| 44-REQ-3.1 | TS-44-7 | unit |
| 44-REQ-3.2 | TS-44-8 | integration |
| 44-REQ-3.3 | TS-44-9 | integration |
| 44-REQ-3.E1 | TS-44-E2 | unit |
| 44-REQ-4.1 | TS-44-10 | unit |
| 44-REQ-4.2 | TS-44-11 | unit |
| 44-REQ-5.1 | TS-44-12 | integration |
| Property 1 | TS-44-P1 | property |
| Property 2 | TS-44-P2 | property |
| Property 3 | TS-44-P3 | property |
| Property 4 | TS-44-P4 | property |
| Property 5 | TS-44-P5 | property |
