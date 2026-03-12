# PRD: Coding Session Prompt Overhaul

> Source: [GitHub Issue #2](https://github.com/agent-fox-dev/agent-fox-v2/issues/2)

## Problem

The coding session system has two issues that prevent effective autonomous
coding:

1. **Missing context**: `session/context.py` does not include `test_spec.md`
   in the assembled context. The `_SPEC_FILES` list only covers
   `requirements.md`, `design.md`, and `tasks.md`, so the coding agent never
   sees the test specification — which is critical for writing and validating
   tests.

2. **Simplistic prompts**: `session/prompt.py` builds system and task prompts
   from short inline f-strings (~10 lines). The agent-fox v1 prompt builder
   used rich, multi-section templates that included a detailed workflow
   (session contract, 9-step process, documentation policy, failure policy,
   git workflow, session summary/learnings format). These templates have
   already been copied to `agent_fox/_templates/prompts/` but are not loaded
   or used by the prompt builder.

## Requirements

### 1. Include test_spec.md in Context

Add `("test_spec.md", "## Test Specification")` to `_SPEC_FILES` in
`agent_fox/session/context.py` so that the test specification is included in
every coding session's assembled context.

### 2. Template-Based Prompt Builder

Rewrite `agent_fox/session/prompt.py` to load prompts from the template files
in `agent_fox/_templates/prompts/` instead of using inline f-strings.

The builder must support two prompt roles:
- **Coding** (`coding.md` + `git-flow.md` embedded inline)
- **Coordinator** (`coordinator.md`)

### 3. Template Interpolation

The templates contain placeholders like `{number}_{specification}` and
`{task_group}`. The prompt builder SHALL perform string interpolation to
replace these with actual spec name and task group values.

### 4. Updated Task Prompt

The `build_task_prompt()` function should also be enriched with template
content or made more descriptive than the current minimal implementation.

## Clarifications

1. **Git-flow embedding**: The `git-flow.md` template SHALL be embedded inline
   into the system prompt alongside `coding.md`. The builder should verify
   the template content supports the coded behavior (trust but verify).
2. **Frontmatter handling**: `git-flow.md` has YAML frontmatter
   (`---\ninclusion: always\n---`). The builder SHALL strip frontmatter
   before embedding.
3. **Template loading**: Use `importlib.resources` or `Path(__file__).parent`
   relative loading to access templates as package data.
4. **Coordinator support**: `build_system_prompt()` SHALL accept a `role`
   parameter to select between coding and coordinator templates.
5. **Backward compatibility**: The function signatures may change, but callers
   (tests, any future orchestrator code) must be updated accordingly.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 03_session_and_workspace | 3 | 2 | Modifies context.py and prompt.py created in group 3 |
