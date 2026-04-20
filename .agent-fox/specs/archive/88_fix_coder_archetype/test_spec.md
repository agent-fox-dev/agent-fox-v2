# Test Specification: Fix-Coder Archetype

## Overview

Tests verify that the `fix_coder` archetype is correctly registered, its
template is issue-focused (no spec artifacts), the fix pipeline uses it, and
SDK parameters resolve correctly. Tests use the project's existing pytest
framework with mocking for session execution.

## Test Cases

### TS-88-1: fix_coding.md template exists and loads

**Requirement:** 88-REQ-1.1
**Type:** unit
**Description:** The fix_coding.md template file exists and can be loaded.

**Preconditions:**
- Template directory exists at `agent_fox/_templates/prompts/`

**Input:**
- Template name: `"fix_coding.md"`

**Expected:**
- `_load_template("fix_coding.md")` returns a non-empty string
- No `ConfigError` raised

**Assertion pseudocode:**
```
result = _load_template("fix_coding.md")
ASSERT isinstance(result, str)
ASSERT len(result) > 0
```

### TS-88-2: fix_coding.md contains no .specs/ references

**Requirement:** 88-REQ-1.2
**Type:** unit
**Description:** The template text does not reference .specs/ paths.

**Preconditions:**
- `fix_coding.md` exists and loads successfully

**Input:**
- Raw template content from `_load_template("fix_coding.md")`

**Expected:**
- The string `.specs/` does not appear anywhere in the template
- The string `tasks.md` does not appear in the context of spec paths

**Assertion pseudocode:**
```
content = _load_template("fix_coding.md")
ASSERT ".specs/" not in content
ASSERT "tasks.md" not in content
```

### TS-88-3: fix_coding.md includes nightshift commit format

**Requirement:** 88-REQ-1.3
**Type:** unit
**Description:** The template instructs the agent to use the nightshift commit
format.

**Preconditions:**
- `fix_coding.md` exists

**Input:**
- Raw template content

**Expected:**
- Template contains the string `fix(#` (commit format pattern)
- Template contains the string `nightshift` in the commit format context

**Assertion pseudocode:**
```
content = _load_template("fix_coding.md")
ASSERT "fix(#" in content
ASSERT "nightshift" in content
```

### TS-88-4: fix_coding.md includes git workflow instructions

**Requirement:** 88-REQ-1.4
**Type:** unit
**Description:** The template includes standard git workflow constraints.

**Preconditions:**
- `fix_coding.md` exists

**Input:**
- Raw template content

**Expected:**
- Template contains instructions about not switching branches
- Template contains instructions about conventional commits
- Template contains instructions about not adding Co-Authored-By

**Assertion pseudocode:**
```
content = _load_template("fix_coding.md")
ASSERT "Do not" in content and "branch" in content
ASSERT "conventional commit" in content.lower() or "conventional commits" in content.lower()
ASSERT "Co-Authored-By" in content
```

### TS-88-5: fix_coding.md includes quality gate instructions

**Requirement:** 88-REQ-1.5
**Type:** unit
**Description:** The template instructs the agent to run quality checks.

**Preconditions:**
- `fix_coding.md` exists

**Input:**
- Raw template content

**Expected:**
- Template references running tests and/or linter before committing

**Assertion pseudocode:**
```
content = _load_template("fix_coding.md")
ASSERT "quality" in content.lower() or "test" in content.lower()
ASSERT "linter" in content.lower() or "lint" in content.lower()
```

### TS-88-6: fix_coding.md omits session artifact instructions

**Requirement:** 88-REQ-1.6
**Type:** unit
**Description:** The template does not instruct the agent to create session
summary or learnings files.

**Preconditions:**
- `fix_coding.md` exists

**Input:**
- Raw template content

**Expected:**
- Template does not contain `.session-summary.json`
- Template does not contain `.session-learnings.md`

**Assertion pseudocode:**
```
content = _load_template("fix_coding.md")
ASSERT ".session-summary.json" not in content
ASSERT ".session-learnings.md" not in content
```

### TS-88-7: fix_coder archetype is registered

**Requirement:** 88-REQ-2.1
**Type:** unit
**Description:** The archetype registry contains a fix_coder entry with the
correct template.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is imported

**Input:**
- Lookup key: `"fix_coder"`

**Expected:**
- Entry exists with `templates == ["fix_coding.md"]`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["fix_coder"]
ASSERT entry.templates == ["fix_coding.md"]
```

### TS-88-8: fix_coder defaults match coder

**Requirement:** 88-REQ-2.2
**Type:** unit
**Description:** The fix_coder entry has the same default model tier, max
turns, thinking mode, and thinking budget as coder.

**Preconditions:**
- Both `coder` and `fix_coder` exist in `ARCHETYPE_REGISTRY`

**Input:**
- Both entries

**Expected:**
- `default_model_tier` matches
- `default_max_turns` matches
- `default_thinking_mode` matches
- `default_thinking_budget` matches

**Assertion pseudocode:**
```
coder = ARCHETYPE_REGISTRY["coder"]
fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
ASSERT fix_coder.default_model_tier == coder.default_model_tier
ASSERT fix_coder.default_max_turns == coder.default_max_turns
ASSERT fix_coder.default_thinking_mode == coder.default_thinking_mode
ASSERT fix_coder.default_thinking_budget == coder.default_thinking_budget
```

### TS-88-9: fix_coder is not task-assignable

**Requirement:** 88-REQ-2.3
**Type:** unit
**Description:** The fix_coder entry has task_assignable=False.

**Preconditions:**
- `fix_coder` exists in `ARCHETYPE_REGISTRY`

**Input:**
- fix_coder entry

**Expected:**
- `task_assignable` is `False`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["fix_coder"]
ASSERT entry.task_assignable is False
```

### TS-88-10: _build_coder_prompt uses fix_coder archetype

**Requirement:** 88-REQ-3.1
**Type:** unit
**Description:** The fix pipeline's coder prompt is built with
archetype="fix_coder".

**Preconditions:**
- FixPipeline is instantiated with a mock config and platform
- An InMemorySpec and TriageResult are available

**Input:**
- Call `_build_coder_prompt(spec, triage)`

**Expected:**
- `build_system_prompt` is called with `archetype="fix_coder"`

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, platform)
with patch("...build_system_prompt") as mock_bsp:
    mock_bsp.return_value = "prompt"
    pipeline._build_coder_prompt(spec, triage)
    ASSERT mock_bsp.call_args.kwargs["archetype"] == "fix_coder"
```

### TS-88-11: _build_coder_prompt does not append commit format

**Requirement:** 88-REQ-3.3
**Type:** unit
**Description:** The task prompt returned by _build_coder_prompt does not
contain hardcoded commit format lines appended by the method.

**Preconditions:**
- FixPipeline is instantiated
- spec.task_prompt is a known string

**Input:**
- Call `_build_coder_prompt(spec, triage)` with no review feedback

**Expected:**
- The returned task prompt equals `spec.task_prompt` exactly (no appended
  commit format)

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, platform)
with patch("...build_system_prompt", return_value="prompt"):
    _, task_prompt = pipeline._build_coder_prompt(spec, triage)
    ASSERT task_prompt == spec.task_prompt
```

### TS-88-12: _run_coder_session passes fix_coder archetype

**Requirement:** 88-REQ-3.2
**Type:** unit
**Description:** The coder session runner uses fix_coder as the archetype.

**Preconditions:**
- FixPipeline is instantiated with mocks

**Input:**
- Call `_run_coder_session(workspace, spec, system_prompt, task_prompt)`

**Expected:**
- `_run_session` is called with `"fix_coder"` as the first argument

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, platform)
with patch.object(pipeline, "_run_session") as mock_rs:
    mock_rs.return_value = mock_outcome
    await pipeline._run_coder_session(workspace, spec, "sys", "task")
    ASSERT mock_rs.call_args[0][0] == "fix_coder"
```

## Property Test Cases

### TS-88-P1: Template isolation under interpolation

**Property:** Property 1 from design.md
**Validates:** 88-REQ-1.2, 88-REQ-1.E1
**Type:** property
**Description:** For any spec_name, the interpolated fix_coding.md template
never contains `.specs/`.

**For any:** `spec_name` generated from `st.text(min_size=1, max_size=100,
alphabet=st.characters(whitelist_categories=("L", "N", "Pd")))`
**Invariant:** The interpolated template does not contain `.specs/`.

**Assertion pseudocode:**
```
FOR ANY spec_name IN strategy:
    variables = {"spec_name": spec_name, "task_group": "0",
                 "number": spec_name, "specification": spec_name}
    template = _load_template("fix_coding.md")
    result = _interpolate(template, variables)
    ASSERT ".specs/" not in result
```

### TS-88-P2: Registry parity between fix_coder and coder

**Property:** Property 2 from design.md
**Validates:** 88-REQ-2.1, 88-REQ-2.2, 88-REQ-2.3
**Type:** property
**Description:** The fix_coder entry always has the same numeric defaults as
coder but different template and task_assignable flag.

**For any:** (single check — registry is static)
**Invariant:** Numeric defaults match; templates and task_assignable differ.

**Assertion pseudocode:**
```
coder = ARCHETYPE_REGISTRY["coder"]
fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
ASSERT fix_coder.templates == ["fix_coding.md"]
ASSERT fix_coder.templates != coder.templates
ASSERT fix_coder.task_assignable is False
ASSERT fix_coder.default_model_tier == coder.default_model_tier
ASSERT fix_coder.default_max_turns == coder.default_max_turns
ASSERT fix_coder.default_thinking_mode == coder.default_thinking_mode
ASSERT fix_coder.default_thinking_budget == coder.default_thinking_budget
```

### TS-88-P3: SDK parameter parity without overrides

**Property:** Property 4 from design.md
**Validates:** 88-REQ-4.1
**Type:** property
**Description:** Without config overrides, SDK param resolution for fix_coder
returns the same values as for coder.

**For any:** default config (no archetype overrides)
**Invariant:** `resolve_model_tier`, `resolve_max_turns`, `resolve_thinking`
return equal values for `"fix_coder"` and `"coder"`.

**Assertion pseudocode:**
```
config = default_config_with_no_overrides()
ASSERT resolve_model_tier(config, "fix_coder") == resolve_model_tier(config, "coder")
ASSERT resolve_max_turns(config, "fix_coder") == resolve_max_turns(config, "coder")
ASSERT resolve_thinking(config, "fix_coder") == resolve_thinking(config, "coder")
```

## Edge Case Tests

### TS-88-E1: Interpolation with adversarial spec_name

**Requirement:** 88-REQ-1.E1
**Type:** unit
**Description:** Even a spec_name containing ".specs/" does not cause the
template to reference spec paths (the template itself has no such references).

**Preconditions:**
- `fix_coding.md` is loaded

**Input:**
- `spec_name = ".specs/malicious"`

**Expected:**
- The interpolated template does not contain `.specs/` from the template
  itself (any occurrence comes solely from the `{spec_name}` variable
  substitution in non-path contexts)

**Assertion pseudocode:**
```
template = _load_template("fix_coding.md")
ASSERT ".specs/" not in template  # raw template has no such reference
```

### TS-88-E2: get_archetype fallback for fix_coder

**Requirement:** 88-REQ-3.E1
**Type:** unit
**Description:** If fix_coder were removed from registry, get_archetype falls
back to coder.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is temporarily modified to remove `fix_coder`

**Input:**
- `get_archetype("fix_coder")`

**Expected:**
- Returns the `coder` entry
- Logs a warning

**Assertion pseudocode:**
```
saved = ARCHETYPE_REGISTRY.pop("fix_coder")
try:
    entry = get_archetype("fix_coder")
    ASSERT entry.name == "coder"
finally:
    ARCHETYPE_REGISTRY["fix_coder"] = saved
```

## Integration Smoke Tests

### TS-88-SMOKE-1: Fix pipeline coder session uses fix_coding.md

**Execution Path:** Path 1 from design.md
**Description:** A fix pipeline coder session receives a system prompt built
from `fix_coding.md`, not `coding.md`.

**Setup:** Mock `run_session` to capture args. Real `FixPipeline`,
`build_system_prompt`, `get_archetype`, `_load_template`. Mock platform.

**Trigger:** Call `pipeline._build_coder_prompt(spec, triage)` and then
`pipeline._run_coder_session(workspace, spec, system_prompt, task_prompt)`.

**Expected side effects:**
- The system prompt contains text from `fix_coding.md` (e.g., "FIX CODER"
  or equivalent role header)
- The system prompt does NOT contain `coding.md`-specific text (e.g.,
  "Choose exactly one task group")
- `_run_session` is called with `"fix_coder"`

**Must NOT satisfy with:** Mocking `build_system_prompt` (it must run for
real), mocking `get_archetype`, or mocking `_load_template`.

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, mock_platform)
system_prompt, task_prompt = pipeline._build_coder_prompt(spec, triage)
ASSERT "task group" not in system_prompt.lower()
ASSERT ".specs/" not in system_prompt
ASSERT "nightshift" in system_prompt.lower()

with patch.object(pipeline, "_run_session", return_value=mock_outcome) as mock:
    await pipeline._run_coder_session(workspace, spec, system_prompt, task_prompt)
    ASSERT mock.call_args[0][0] == "fix_coder"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 88-REQ-1.1 | TS-88-1 | unit |
| 88-REQ-1.2 | TS-88-2, TS-88-P1 | unit, property |
| 88-REQ-1.3 | TS-88-3 | unit |
| 88-REQ-1.4 | TS-88-4 | unit |
| 88-REQ-1.5 | TS-88-5 | unit |
| 88-REQ-1.6 | TS-88-6 | unit |
| 88-REQ-1.E1 | TS-88-E1, TS-88-P1 | unit, property |
| 88-REQ-2.1 | TS-88-7, TS-88-P2 | unit, property |
| 88-REQ-2.2 | TS-88-8, TS-88-P2 | unit, property |
| 88-REQ-2.3 | TS-88-9, TS-88-P2 | unit, property |
| 88-REQ-2.E1 | TS-88-E2 | unit |
| 88-REQ-3.1 | TS-88-10 | unit |
| 88-REQ-3.2 | TS-88-12 | unit |
| 88-REQ-3.3 | TS-88-11 | unit |
| 88-REQ-3.E1 | TS-88-E2 | unit |
| 88-REQ-4.1 | TS-88-P3 | property |
| 88-REQ-4.2 | TS-88-P3 | property |
| Path 1 | TS-88-SMOKE-1 | integration |
