# Implementation Plan: Coding Session Prompt Overhaul

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec modifies `agent_fox/session/context.py` (add test_spec.md) and
rewrites `agent_fox/session/prompt.py` (template-based prompts). Task group 1
writes failing tests, task group 2 implements the context change, task group 3
implements the prompt builder rewrite, and task group 4 is a checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/session/test_context.py tests/unit/session/test_prompt.py tests/property/session/test_prompt_props.py -q`
- Unit tests: `uv run pytest tests/unit/session/ -q`
- Property tests: `uv run pytest tests/property/session/ -q`
- All tests: `uv run pytest tests/ -q`
- Linter: `uv run ruff check agent_fox/session/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Update context assembly tests
    - Add tests to `tests/unit/session/test_context.py`
    - Implement TS-15-1: context includes test_spec.md content
    - Implement TS-15-2: test_spec appears between design and tasks
    - Implement TS-15-E1: missing test_spec.md skipped with warning
    - Update the `tmp_spec_dir` fixture to include a `test_spec.md` file
    - _Test Spec: TS-15-1, TS-15-2, TS-15-E1_

  - [x] 1.2 Update prompt builder tests
    - Rewrite `tests/unit/session/test_prompt.py` for new signatures
    - Implement TS-15-3: coding role loads coding.md + git-flow.md
    - Implement TS-15-4: coordinator role loads coordinator.md
    - Implement TS-15-5: role defaults to coding
    - Implement TS-15-6: context appended to system prompt
    - Implement TS-15-7: placeholder interpolation
    - Implement TS-15-8: frontmatter stripped
    - Implement TS-15-9: task prompt contains spec name
    - Implement TS-15-10: task prompt contains quality instructions
    - _Test Spec: TS-15-3, TS-15-4, TS-15-5, TS-15-6, TS-15-7, TS-15-8, TS-15-9, TS-15-10_

  - [x] 1.3 Write prompt builder edge case tests
    - Add to `tests/unit/session/test_prompt.py`
    - Implement TS-15-E2: missing template raises ConfigError
    - Implement TS-15-E3: unknown role raises ValueError
    - Implement TS-15-E4: literal braces preserved (coordinator JSON)
    - Implement TS-15-E5: task_group < 1 raises ValueError
    - Implement TS-15-E6: template without frontmatter unchanged
    - _Test Spec: TS-15-E2, TS-15-E3, TS-15-E4, TS-15-E5, TS-15-E6_

  - [x] 1.4 Write property tests
    - Create `tests/property/session/test_prompt_props.py`
    - Implement TS-15-P1: test spec always in context when present
    - Implement TS-15-P2: template content always present for valid roles
    - Implement TS-15-P3: interpolation never crashes
    - Implement TS-15-P4: frontmatter never leaks
    - Implement TS-15-P5: task prompt completeness
    - _Test Spec: TS-15-P1, TS-15-P2, TS-15-P3, TS-15-P4, TS-15-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Add test_spec.md to context assembly
  - [x] 2.1 Update `_SPEC_FILES` in `agent_fox/session/context.py`
    - Add `("test_spec.md", "## Test Specification")` after `design.md`
      and before `tasks.md`
    - _Requirements: 15-REQ-1.1, 15-REQ-1.2_

  - [x] 2.2 Update `tmp_spec_dir` fixture if needed
    - Ensure the fixture in `tests/unit/session/conftest.py` creates a
      `test_spec.md` file so existing context tests continue to pass
    - _Requirements: 15-REQ-1.E1_

  - [x] 2.V Verify task group 2
    - [x] Context tests pass: `uv run pytest tests/unit/session/test_context.py -q`
    - [x] All existing tests still pass: `uv run pytest tests/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/session/context.py`
    - [x] Requirements 15-REQ-1.* acceptance criteria met

- [ ] 3. Rewrite prompt builder with templates
  - [ ] 3.1 Implement template loading and frontmatter stripping
    - Add `_TEMPLATE_DIR`, `_ROLE_TEMPLATES` constants
    - Implement `_strip_frontmatter()` using regex
    - Implement `_load_template()` that reads file, strips frontmatter,
      raises `ConfigError` on missing file
    - _Requirements: 15-REQ-2.1, 15-REQ-4.1, 15-REQ-4.2, 15-REQ-2.E1_

  - [ ] 3.2 Implement placeholder interpolation
    - Implement `_interpolate()` that replaces known placeholders
      (`spec_name`, `task_group`, `number`, `specification`) while
      preserving literal braces
    - Use regex replacement targeting only known keys, not Python
      `str.format()` (which would choke on literal braces)
    - _Requirements: 15-REQ-3.1, 15-REQ-3.2, 15-REQ-3.E1_

  - [ ] 3.3 Rewrite `build_system_prompt()`
    - Add `role` parameter defaulting to `"coding"`
    - Validate role against `_ROLE_TEMPLATES`; raise `ValueError` if unknown
    - Load and compose templates for the role
    - For coding: concatenate coding.md + git-flow.md + context
    - For coordinator: coordinator.md + context
    - Interpolate placeholders in the composed template
    - _Requirements: 15-REQ-2.2, 15-REQ-2.3, 15-REQ-2.4, 15-REQ-2.5, 15-REQ-2.E2_

  - [ ] 3.4 Rewrite `build_task_prompt()`
    - Validate `task_group >= 1`; raise `ValueError` if invalid
    - Include spec name, task group, checkbox update instructions,
      commit instructions, and quality gate reminder
    - _Requirements: 15-REQ-5.1, 15-REQ-5.2, 15-REQ-5.3, 15-REQ-5.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Prompt tests pass: `uv run pytest tests/unit/session/test_prompt.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/session/test_prompt_props.py -q`
    - [ ] All existing tests still pass: `uv run pytest tests/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/session/prompt.py`
    - [ ] Requirements 15-REQ-2.*, 15-REQ-3.*, 15-REQ-4.*, 15-REQ-5.* met

- [ ] 4. Checkpoint — Session Prompt Complete
  - Ensure all tests pass: `uv run pytest tests/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/session/ tests/`
  - Ask the user if questions arise.

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 15-REQ-1.1 | TS-15-1 | 2.1 | tests/unit/session/test_context.py |
| 15-REQ-1.2 | TS-15-2 | 2.1 | tests/unit/session/test_context.py |
| 15-REQ-1.E1 | TS-15-E1 | 2.2 | tests/unit/session/test_context.py |
| 15-REQ-2.1 | TS-15-3 | 3.1 | tests/unit/session/test_prompt.py |
| 15-REQ-2.2 | TS-15-3 | 3.3 | tests/unit/session/test_prompt.py |
| 15-REQ-2.3 | TS-15-4 | 3.3 | tests/unit/session/test_prompt.py |
| 15-REQ-2.4 | TS-15-5 | 3.3 | tests/unit/session/test_prompt.py |
| 15-REQ-2.5 | TS-15-6 | 3.3 | tests/unit/session/test_prompt.py |
| 15-REQ-2.E1 | TS-15-E2 | 3.1 | tests/unit/session/test_prompt.py |
| 15-REQ-2.E2 | TS-15-E3 | 3.3 | tests/unit/session/test_prompt.py |
| 15-REQ-3.1 | TS-15-7 | 3.2 | tests/unit/session/test_prompt.py |
| 15-REQ-3.E1 | TS-15-E4 | 3.2 | tests/unit/session/test_prompt.py |
| 15-REQ-4.1 | TS-15-8 | 3.1 | tests/unit/session/test_prompt.py |
| 15-REQ-4.2 | TS-15-E6 | 3.1 | tests/unit/session/test_prompt.py |
| 15-REQ-5.1 | TS-15-9 | 3.4 | tests/unit/session/test_prompt.py |
| 15-REQ-5.2 | TS-15-10 | 3.4 | tests/unit/session/test_prompt.py |
| 15-REQ-5.3 | TS-15-10 | 3.4 | tests/unit/session/test_prompt.py |
| 15-REQ-5.E1 | TS-15-E5 | 3.4 | tests/unit/session/test_prompt.py |
| Property 1 | TS-15-P1 | 2.1 | tests/property/session/test_prompt_props.py |
| Property 2 | TS-15-P2 | 3.3 | tests/property/session/test_prompt_props.py |
| Property 3 | TS-15-P3 | 3.2 | tests/property/session/test_prompt_props.py |
| Property 4 | TS-15-P4 | 3.1 | tests/property/session/test_prompt_props.py |
| Property 5 | TS-15-P5 | 3.4 | tests/property/session/test_prompt_props.py |

## Notes

- The existing prompt tests in `tests/unit/session/test_prompt.py` will need
  to be rewritten since the function signatures change (added `role` parameter
  to `build_system_prompt`). Mark old tests that test the inline f-string
  behavior as superseded.
- Use `monkeypatch` or a fixture to override `_TEMPLATE_DIR` when testing
  missing template scenarios (TS-15-E2) to avoid modifying actual template files.
- For property tests, use `hypothesis.strategies.sampled_from` for the role
  parameter and `text()` with safe alphabets for spec names.
- The `coordinator.md` template contains JSON examples with literal braces —
  this is the primary test case for literal brace preservation (TS-15-E4).
- Template interpolation must NOT use Python's `str.format()` or f-strings on
  the template content, as the templates contain literal `{` and `}` characters
  in JSON examples and Markdown code blocks.
