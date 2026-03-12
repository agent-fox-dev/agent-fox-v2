# Requirements Document

## Introduction

This document specifies enhancements to the coding session context assembly
and prompt building system. The context assembler gains `test_spec.md`
coverage, and the prompt builder is rewritten to load rich, multi-section
templates from `agent_fox/_templates/prompts/` with placeholder interpolation.

## Glossary

| Term | Definition |
|------|-----------|
| Context assembler | The `assemble_context()` function that gathers spec documents and memory facts for a session |
| Prompt builder | The module that constructs system and task prompts from templates |
| System prompt | The instruction prompt sent to the claude-code-sdk as `system_prompt` |
| Task prompt | The user-facing prompt that tells the agent which task group to implement |
| Template | A Markdown file in `agent_fox/_templates/prompts/` containing prompt instructions |
| Frontmatter | YAML metadata block between `---` delimiters at the top of a Markdown file |
| Interpolation | String substitution replacing `{placeholder}` with actual values |
| Coding role | The prompt role for coding sessions, composed from `coding.md` + `git-flow.md` |
| Coordinator role | The prompt role for cross-spec dependency analysis, loaded from `coordinator.md` |

## Requirements

### Requirement 1: Test Specification in Context

**User Story:** As the orchestrator, I want `test_spec.md` included in the
assembled context, so that the coding agent can reference test contracts when
writing and validating tests.

#### Acceptance Criteria

1. [15-REQ-1.1] THE context assembler SHALL include `test_spec.md` in the
   list of spec files read during context assembly, with the section header
   `## Test Specification`.
2. [15-REQ-1.2] THE context assembler SHALL read `test_spec.md` after
   `design.md` and before `tasks.md` in the assembled output.

#### Edge Cases

1. [15-REQ-1.E1] IF `test_spec.md` does not exist in the spec directory, THEN
   THE context assembler SHALL skip it and log a warning (existing behavior
   from 03-REQ-4.E1).

---

### Requirement 2: Template-Based System Prompt

**User Story:** As the orchestrator, I want the system prompt built from rich
template files, so that the coding agent receives detailed workflow
instructions that produce effective autonomous coding sessions.

#### Acceptance Criteria

1. [15-REQ-2.1] THE prompt builder SHALL load prompt templates from
   `agent_fox/_templates/prompts/` using package-relative path resolution.
2. [15-REQ-2.2] WHEN building a coding system prompt, THE prompt builder
   SHALL compose the template from `coding.md` with `git-flow.md` content
   embedded inline.
3. [15-REQ-2.3] WHEN building a coordinator system prompt, THE prompt builder
   SHALL load the template from `coordinator.md`.
4. [15-REQ-2.4] THE prompt builder SHALL accept a `role` parameter
   (defaulting to `"coding"`) to select between prompt templates.
5. [15-REQ-2.5] THE prompt builder SHALL append the assembled context
   (spec documents + memory facts) to the system prompt.

#### Edge Cases

1. [15-REQ-2.E1] IF a template file does not exist at the expected path, THEN
   THE prompt builder SHALL raise a `ConfigError` with the missing file path.
2. [15-REQ-2.E2] IF an unknown role is specified, THEN THE prompt builder
   SHALL raise a `ValueError` identifying the invalid role and listing valid
   options.

---

### Requirement 3: Template Interpolation

**User Story:** As the orchestrator, I want template placeholders replaced
with actual values, so that the coding agent sees concrete spec names and
task group numbers in its instructions.

#### Acceptance Criteria

1. [15-REQ-3.1] THE prompt builder SHALL interpolate the following
   placeholders in template content: `{spec_name}`, `{task_group}`.
2. [15-REQ-3.2] THE prompt builder SHALL leave unrecognized placeholders
   unchanged (no `KeyError` on unknown placeholders).

#### Edge Cases

1. [15-REQ-3.E1] IF a template contains a literal brace (e.g., JSON
   examples), THEN THE prompt builder SHALL preserve them without
   raising an interpolation error.

---

### Requirement 4: Frontmatter Stripping

**User Story:** As the prompt builder, I need to strip YAML frontmatter from
templates, so that metadata like `inclusion: always` does not appear in the
agent's prompt.

#### Acceptance Criteria

1. [15-REQ-4.1] THE prompt builder SHALL strip YAML frontmatter (content
   between leading `---` delimiters) from template files before embedding.
2. [15-REQ-4.2] WHEN a template has no frontmatter, THE prompt builder SHALL
   return its content unchanged.

---

### Requirement 5: Updated Task Prompt

**User Story:** As the orchestrator, I want an enriched task prompt, so that
the coding agent has clear, actionable instructions for each session.

#### Acceptance Criteria

1. [15-REQ-5.1] THE task prompt builder SHALL include the spec name, task
   group number, and a reference to the tasks.md subtask list.
2. [15-REQ-5.2] THE task prompt builder SHALL include instructions to update
   checkbox states and commit changes on the feature branch.
3. [15-REQ-5.3] THE task prompt builder SHALL include a reminder to run
   quality gates (tests, linter) before committing.

#### Edge Cases

1. [15-REQ-5.E1] IF `task_group` is less than 1, THEN THE task prompt builder
   SHALL raise a `ValueError`.
