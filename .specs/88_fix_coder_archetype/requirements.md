# Requirements Document

## Introduction

The night-shift fix pipeline runs a coder agent session to implement fixes for
GitHub issues. Currently it reuses the spec-driven `coder` archetype, whose
template instructs the agent to create and update `.specs/` artifacts. This
spec introduces a dedicated `fix_coder` archetype with an issue-focused
template that eliminates spec artifact creation and provides clear fix-oriented
instructions.

## Glossary

- **Archetype**: A named configuration bundle (template files, model tier,
  max turns, thinking mode) that defines an agent session's behavior.
- **Archetype registry**: The `ARCHETYPE_REGISTRY` dict in `archetypes.py`
  mapping archetype names to `ArchetypeEntry` instances.
- **Fix pipeline**: The night-shift subsystem that processes `af:fix`-labelled
  GitHub issues through triage, coder, and reviewer sessions.
- **Template**: A markdown file in `agent_fox/_templates/prompts/` that provides
  the system prompt instructions for an archetype.
- **SDK params**: Session configuration values (model tier, max turns, thinking
  mode, security config) resolved per-archetype from config overrides and
  registry defaults.

## Requirements

### Requirement 1: Fix-Coder Template

**User Story:** As the night-shift fix pipeline, I want a coder template
designed for issue-driven fixes, so that the agent focuses on implementing
the fix rather than creating spec artifacts.

#### Acceptance Criteria

[88-REQ-1.1] THE `fix_coding.md` template SHALL exist at
`agent_fox/_templates/prompts/fix_coding.md`.

[88-REQ-1.2] THE `fix_coding.md` template SHALL NOT contain any references to
`.specs/`, `tasks.md`, task groups, or spec-driven workflow instructions.

[88-REQ-1.3] THE `fix_coding.md` template SHALL instruct the agent to use the
conventional commit format `fix(#<N>, nightshift): <description>` where `<N>`
is the issue number from the task prompt.

[88-REQ-1.4] THE `fix_coding.md` template SHALL include git workflow
instructions consistent with `coding.md`: stay on the current branch, do not
switch branches or merge, use conventional commits, never add Co-Authored-By
lines, never push to remote.

[88-REQ-1.5] THE `fix_coding.md` template SHALL include quality gate
instructions: run tests and linter before committing, fix failures before
proceeding, no regressions allowed.

[88-REQ-1.6] THE `fix_coding.md` template SHALL NOT instruct the agent to
create `.session-summary.json` or `.session-learnings.md`.

#### Edge Cases

[88-REQ-1.E1] IF the `fix_coding.md` template is loaded and interpolated with
any `spec_name` value, THEN THE resulting prompt text SHALL NOT contain the
literal string `.specs/`.

### Requirement 2: Fix-Coder Archetype Registration

**User Story:** As the archetype registry, I want a `fix_coder` entry, so that
the fix pipeline can resolve it to the correct template and defaults.

#### Acceptance Criteria

[88-REQ-2.1] WHEN the archetype name `"fix_coder"` is looked up, THE archetype
registry SHALL return an `ArchetypeEntry` with `templates=["fix_coding.md"]`.

[88-REQ-2.2] THE `fix_coder` archetype entry SHALL have the same default
values as `coder`: `default_model_tier="STANDARD"`,
`default_max_turns=300`, `default_thinking_mode="adaptive"`,
`default_thinking_budget=64000`.

[88-REQ-2.3] THE `fix_coder` archetype entry SHALL have
`task_assignable=False` since it is not used in the spec-driven task graph.

#### Edge Cases

[88-REQ-2.E1] IF an unknown archetype name is looked up, THEN THE registry
SHALL fall back to `coder` (existing behavior, unchanged).

### Requirement 3: Fix Pipeline Integration

**User Story:** As the fix pipeline, I want to use the `fix_coder` archetype
for coder sessions, so that agents receive issue-focused instructions.

#### Acceptance Criteria

[88-REQ-3.1] WHEN `_build_coder_prompt()` builds the system prompt, THE fix
pipeline SHALL pass `archetype="fix_coder"` to `build_system_prompt()`.

[88-REQ-3.2] WHEN `_run_coder_session()` invokes `_run_session()`, THE fix
pipeline SHALL pass `"fix_coder"` as the archetype argument.

[88-REQ-3.3] THE `_build_coder_prompt()` method SHALL NOT append any hardcoded
commit format instructions to the task prompt (the template handles this).

#### Edge Cases

[88-REQ-3.E1] IF `fix_coder` is not found in the registry (e.g., due to a
code error), THEN THE system SHALL fall back to the `coder` archetype and log
a warning (existing `get_archetype` behavior).

### Requirement 4: SDK Parameter Resolution

**User Story:** As a user, I want `fix_coder` sessions to use the same model
and configuration as `coder` by default, with the option to override
independently.

#### Acceptance Criteria

[88-REQ-4.1] WHEN no config override exists for `fix_coder`, THE SDK parameter
resolution functions (`resolve_model_tier`, `resolve_max_turns`,
`resolve_thinking`, `resolve_security_config`) SHALL return the `fix_coder`
registry defaults, which match `coder` defaults.

[88-REQ-4.2] WHERE `archetypes.overrides.fix_coder` is configured, THE SDK
parameter resolution functions SHALL use the override values for `fix_coder`
sessions independently of `coder` overrides.
