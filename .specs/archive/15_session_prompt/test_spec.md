# Test Specification: Coding Session Prompt Overhaul

## Overview

Tests verify that the context assembler includes `test_spec.md`, the prompt
builder loads and composes templates correctly, placeholders are interpolated,
frontmatter is stripped, and error cases are handled. Unit tests check
function output directly. Property tests fuzz inputs to verify robustness.

## Test Cases

### TS-15-1: Context Includes Test Spec

**Requirement:** 15-REQ-1.1
**Type:** unit
**Description:** Verify that `assemble_context` output includes test_spec.md
content.

**Preconditions:**
- Temp spec directory with `requirements.md`, `design.md`, `test_spec.md`,
  and `tasks.md`.

**Input:**
- `assemble_context(spec_dir, task_group=2)`.

**Expected:**
- Output contains the test_spec.md file content.

**Assertion pseudocode:**
```
spec_dir = create_temp_spec_dir(
    test_spec_content="Test spec content here"
)
ctx = assemble_context(spec_dir, task_group=2)
ASSERT "Test spec content here" IN ctx
```

---

### TS-15-2: Test Spec Ordering

**Requirement:** 15-REQ-1.2
**Type:** unit
**Description:** Verify `test_spec.md` appears after design and before tasks
in the assembled context.

**Preconditions:**
- Temp spec directory with all four spec files.

**Input:**
- `assemble_context(spec_dir, task_group=1)`.

**Expected:**
- The `## Test Specification` section header appears after `## Design` and
  before `## Tasks` in the output.

**Assertion pseudocode:**
```
ctx = assemble_context(spec_dir, task_group=1)
design_pos = ctx.index("## Design")
test_spec_pos = ctx.index("## Test Specification")
tasks_pos = ctx.index("## Tasks")
ASSERT design_pos < test_spec_pos < tasks_pos
```

---

### TS-15-3: System Prompt Loads Coding Template

**Requirement:** 15-REQ-2.1, 15-REQ-2.2
**Type:** unit
**Description:** Verify that `build_system_prompt` with `role="coding"`
includes content from `coding.md` and `git-flow.md`.

**Preconditions:**
- Template files exist at `agent_fox/_templates/prompts/`.

**Input:**
- `build_system_prompt("context", 2, "my_spec", role="coding")`.

**Expected:**
- Output contains recognizable text from `coding.md` (e.g., "CODING AGENT").
- Output contains recognizable text from `git-flow.md` (e.g., "Git Workflow").

**Assertion pseudocode:**
```
result = build_system_prompt("context", 2, "my_spec", role="coding")
ASSERT "CODING AGENT" IN result
ASSERT "Git Workflow" IN result
```

---

### TS-15-4: System Prompt Loads Coordinator Template

**Requirement:** 15-REQ-2.3
**Type:** unit
**Description:** Verify that `build_system_prompt` with `role="coordinator"`
includes content from `coordinator.md`.

**Preconditions:**
- Template files exist at `agent_fox/_templates/prompts/`.

**Input:**
- `build_system_prompt("context", 1, "my_spec", role="coordinator")`.

**Expected:**
- Output contains recognizable text from `coordinator.md`
  (e.g., "COORDINATOR AGENT").

**Assertion pseudocode:**
```
result = build_system_prompt("context", 1, "my_spec", role="coordinator")
ASSERT "COORDINATOR AGENT" IN result
```

---

### TS-15-5: Role Parameter Defaults to Coding

**Requirement:** 15-REQ-2.4
**Type:** unit
**Description:** Verify that omitting the `role` parameter defaults to
the coding template.

**Preconditions:**
- Template files exist.

**Input:**
- `build_system_prompt("context", 2, "my_spec")` (no role argument).

**Expected:**
- Output contains coding template content.

**Assertion pseudocode:**
```
result = build_system_prompt("context", 2, "my_spec")
ASSERT "CODING AGENT" IN result
```

---

### TS-15-6: Context Appended to System Prompt

**Requirement:** 15-REQ-2.5
**Type:** unit
**Description:** Verify the assembled context appears in the system prompt.

**Preconditions:**
- None.

**Input:**
- `build_system_prompt("unique_context_xyz", 2, "my_spec")`.

**Expected:**
- Output contains `"unique_context_xyz"`.

**Assertion pseudocode:**
```
result = build_system_prompt("unique_context_xyz", 2, "my_spec")
ASSERT "unique_context_xyz" IN result
```

---

### TS-15-7: Placeholder Interpolation

**Requirement:** 15-REQ-3.1
**Type:** unit
**Description:** Verify that `{spec_name}` and `{task_group}` placeholders
in templates are replaced with actual values.

**Preconditions:**
- Template files containing placeholder patterns.

**Input:**
- `build_system_prompt("ctx", 3, "05_my_feature")`.

**Expected:**
- Output contains `"05_my_feature"` where spec_name placeholders were.
- Output contains `"3"` where task_group placeholders were.

**Assertion pseudocode:**
```
result = build_system_prompt("ctx", 3, "05_my_feature")
ASSERT "05_my_feature" IN result
ASSERT "3" IN result
```

---

### TS-15-8: Frontmatter Stripped

**Requirement:** 15-REQ-4.1
**Type:** unit
**Description:** Verify that YAML frontmatter is stripped from templates.

**Preconditions:**
- `git-flow.md` has YAML frontmatter (`---\ninclusion: always\n---`).

**Input:**
- `build_system_prompt("ctx", 1, "spec")` with coding role.

**Expected:**
- Output does NOT contain `"inclusion: always"`.

**Assertion pseudocode:**
```
result = build_system_prompt("ctx", 1, "spec", role="coding")
ASSERT "inclusion: always" NOT IN result
```

---

### TS-15-9: Task Prompt Contains Spec Name

**Requirement:** 15-REQ-5.1
**Type:** unit
**Description:** Verify the task prompt includes the spec name and task group.

**Preconditions:**
- None.

**Input:**
- `build_task_prompt(3, "05_my_feature")`.

**Expected:**
- Output contains `"05_my_feature"` and `"3"`.

**Assertion pseudocode:**
```
result = build_task_prompt(3, "05_my_feature")
ASSERT "05_my_feature" IN result
ASSERT "3" IN result
```

---

### TS-15-10: Task Prompt Contains Quality Instructions

**Requirement:** 15-REQ-5.2, 15-REQ-5.3
**Type:** unit
**Description:** Verify the task prompt includes checkbox, commit, and quality
gate instructions.

**Preconditions:**
- None.

**Input:**
- `build_task_prompt(2, "my_spec")`.

**Expected:**
- Output mentions checkbox/task status updates.
- Output mentions committing changes.
- Output mentions running tests or quality gates.

**Assertion pseudocode:**
```
result = build_task_prompt(2, "my_spec")
ASSERT "checkbox" IN result.lower() OR "task" IN result.lower()
ASSERT "commit" IN result.lower()
ASSERT "test" IN result.lower() OR "quality" IN result.lower()
```

## Property Test Cases

### TS-15-P1: Context Always Includes Test Spec When Present

**Property:** Property 1 from design.md
**Validates:** 15-REQ-1.1, 15-REQ-1.2
**Type:** property
**Description:** When test_spec.md exists, it always appears in context
between design and tasks.

**For any:** Task group in [1..20], spec directory with all four files.
**Invariant:** Context output contains `## Test Specification` header between
`## Design` and `## Tasks`.

**Assertion pseudocode:**
```
FOR ANY task_group IN integers(1, 20):
    ctx = assemble_context(spec_dir, task_group)
    design_pos = ctx.index("## Design")
    test_spec_pos = ctx.index("## Test Specification")
    tasks_pos = ctx.index("## Tasks")
    ASSERT design_pos < test_spec_pos < tasks_pos
```

---

### TS-15-P2: Template Content Present

**Property:** Property 2 from design.md
**Validates:** 15-REQ-2.1, 15-REQ-2.2, 15-REQ-2.3
**Type:** property
**Description:** For any valid role, the system prompt contains recognizable
template content.

**For any:** role in ["coding", "coordinator"], any spec name, any task group.
**Invariant:** System prompt is non-empty and contains role-specific keywords.

**Assertion pseudocode:**
```
FOR ANY role IN ["coding", "coordinator"]:
    FOR ANY spec_name IN text(min_size=1, max_size=30):
        result = build_system_prompt("ctx", 1, spec_name, role=role)
        ASSERT len(result) > 100
        IF role == "coding":
            ASSERT "CODING AGENT" IN result
        ELSE:
            ASSERT "COORDINATOR AGENT" IN result
```

---

### TS-15-P3: Interpolation Never Crashes

**Property:** Property 3 from design.md, Property 4
**Validates:** 15-REQ-3.1, 15-REQ-3.E1
**Type:** property
**Description:** build_system_prompt never raises on any spec name or task
group combination.

**For any:** spec_name as arbitrary text, task_group as positive integer.
**Invariant:** No exception is raised and the result contains the spec name.

**Assertion pseudocode:**
```
FOR ANY spec_name IN text(min_size=1, max_size=50,
                          alphabet=characters(whitelist_categories=("L", "N", "P"))):
    FOR ANY task_group IN integers(1, 100):
        result = build_system_prompt("ctx", task_group, spec_name)
        ASSERT spec_name IN result
```

---

### TS-15-P4: Frontmatter Never Leaks

**Property:** Property 5 from design.md
**Validates:** 15-REQ-4.1, 15-REQ-4.2
**Type:** property
**Description:** Frontmatter content never appears in the final prompt.

**For any:** Any valid role and spec name.
**Invariant:** Output does not contain `inclusion:` (frontmatter key from
git-flow.md).

**Assertion pseudocode:**
```
FOR ANY spec_name IN text(min_size=1, max_size=20):
    result = build_system_prompt("ctx", 1, spec_name, role="coding")
    ASSERT "inclusion:" NOT IN result
```

---

### TS-15-P5: Task Prompt Completeness

**Property:** Property 6 from design.md
**Validates:** 15-REQ-5.1, 15-REQ-5.2, 15-REQ-5.3
**Type:** property
**Description:** Task prompt always contains required elements.

**For any:** task_group in [1..50], spec_name as text.
**Invariant:** Output contains spec name, task group number, and instruction
keywords.

**Assertion pseudocode:**
```
FOR ANY task_group IN integers(1, 50):
    FOR ANY spec_name IN text(min_size=1, max_size=30):
        result = build_task_prompt(task_group, spec_name)
        ASSERT spec_name IN result
        ASSERT str(task_group) IN result
        ASSERT "commit" IN result.lower()
```

## Edge Case Tests

### TS-15-E1: Missing Test Spec File

**Requirement:** 15-REQ-1.E1
**Type:** unit
**Description:** Context assembly skips missing test_spec.md with a warning.

**Preconditions:**
- Spec dir with requirements.md, design.md, tasks.md but no test_spec.md.

**Input:**
- `assemble_context(spec_dir, task_group=1)`.

**Expected:**
- Output does NOT contain `## Test Specification`.
- No exception raised.
- Warning logged.

**Assertion pseudocode:**
```
spec_dir = create_temp_spec_dir(include_test_spec=False)
ctx = assemble_context(spec_dir, task_group=1)
ASSERT "## Test Specification" NOT IN ctx
ASSERT warning_logged("test_spec.md")
```

---

### TS-15-E2: Missing Template File

**Requirement:** 15-REQ-2.E1
**Type:** unit
**Description:** Prompt builder raises ConfigError for missing template.

**Preconditions:**
- Template directory exists but `coding.md` is removed.

**Input:**
- `build_system_prompt("ctx", 1, "spec", role="coding")` with missing
  template.

**Expected:**
- `ConfigError` raised with the missing file path.

**Assertion pseudocode:**
```
monkeypatch template_dir to temp dir without coding.md
ASSERT_RAISES ConfigError:
    build_system_prompt("ctx", 1, "spec", role="coding")
```

---

### TS-15-E3: Unknown Role

**Requirement:** 15-REQ-2.E2
**Type:** unit
**Description:** Prompt builder raises ValueError for unknown role.

**Preconditions:**
- None.

**Input:**
- `build_system_prompt("ctx", 1, "spec", role="invalid")`.

**Expected:**
- `ValueError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES ValueError:
    build_system_prompt("ctx", 1, "spec", role="invalid")
```

---

### TS-15-E4: Template with Literal Braces

**Requirement:** 15-REQ-3.E1
**Type:** unit
**Description:** Templates with JSON literal braces don't cause
interpolation errors.

**Preconditions:**
- `coordinator.md` contains JSON examples with literal `{` and `}`.

**Input:**
- `build_system_prompt("ctx", 1, "spec", role="coordinator")`.

**Expected:**
- No exception raised.
- JSON examples preserved in output.

**Assertion pseudocode:**
```
result = build_system_prompt("ctx", 1, "spec", role="coordinator")
ASSERT "inter_spec_edges" IN result  # JSON key from coordinator template
```

---

### TS-15-E5: Invalid Task Group

**Requirement:** 15-REQ-5.E1
**Type:** unit
**Description:** Task prompt raises ValueError for task_group < 1.

**Preconditions:**
- None.

**Input:**
- `build_task_prompt(0, "spec")`.

**Expected:**
- `ValueError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES ValueError:
    build_task_prompt(0, "spec")
```

---

### TS-15-E6: Template Without Frontmatter

**Requirement:** 15-REQ-4.2
**Type:** unit
**Description:** Templates without frontmatter are returned unchanged.

**Preconditions:**
- `coding.md` has no frontmatter (starts with `##`).

**Input:**
- `_strip_frontmatter(coding_content)`.

**Expected:**
- Output equals input.

**Assertion pseudocode:**
```
content = "## CODING AGENT\n\nContent here"
result = _strip_frontmatter(content)
ASSERT result == content
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 15-REQ-1.1 | TS-15-1 | unit |
| 15-REQ-1.2 | TS-15-2 | unit |
| 15-REQ-1.E1 | TS-15-E1 | unit |
| 15-REQ-2.1 | TS-15-3 | unit |
| 15-REQ-2.2 | TS-15-3 | unit |
| 15-REQ-2.3 | TS-15-4 | unit |
| 15-REQ-2.4 | TS-15-5 | unit |
| 15-REQ-2.5 | TS-15-6 | unit |
| 15-REQ-2.E1 | TS-15-E2 | unit |
| 15-REQ-2.E2 | TS-15-E3 | unit |
| 15-REQ-3.1 | TS-15-7 | unit |
| 15-REQ-3.E1 | TS-15-E4 | unit |
| 15-REQ-4.1 | TS-15-8 | unit |
| 15-REQ-4.2 | TS-15-E6 | unit |
| 15-REQ-5.1 | TS-15-9 | unit |
| 15-REQ-5.2 | TS-15-10 | unit |
| 15-REQ-5.3 | TS-15-10 | unit |
| 15-REQ-5.E1 | TS-15-E5 | unit |
| Property 1 | TS-15-P1 | property |
| Property 2 | TS-15-P2 | property |
| Property 3 | TS-15-P3 | property |
| Property 4 | TS-15-P4 | property |
| Property 5 | TS-15-P5 | property |
