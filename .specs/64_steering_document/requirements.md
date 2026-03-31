# Requirements Document

## Introduction

This spec adds a project-level steering document (`.specs/steering.md`) that
lets users provide persistent, manually-maintained directives to all agents and
skills. The document is injected into runtime prompts and referenced by skill
templates and AGENTS.md.

## Glossary

- **Steering document**: A Markdown file at `.specs/steering.md` containing
  user-authored directives that influence agent behavior across all sessions.
- **Placeholder content**: The initial template text written by `init` when
  creating the steering document. Contains instructional text but no actual
  directives.
- **Prompt assembly**: The process in `prompt.py` that composes spec documents,
  memory facts, and other context into a system prompt for an archetype session.

## Requirements

### Requirement 1: Initialization

**User Story:** As a project maintainer, I want the `init` command to create
a steering document placeholder so that the file exists and is tracked in git
from the start.

#### Acceptance Criteria

1. [64-REQ-1.1] WHEN the `init` command runs AND `.specs/steering.md` does not
   exist, THE system SHALL create `.specs/steering.md` with placeholder content.
2. [64-REQ-1.2] WHEN the `init` command runs AND `.specs/steering.md` already
   exists, THE system SHALL leave the file unchanged.
3. [64-REQ-1.3] THE placeholder content SHALL contain instructional text
   explaining the file's purpose, wrapped in HTML comments or clearly marked
   as non-directive, so that agents do not treat it as actionable directives.
4. [64-REQ-1.4] WHEN the `init` command runs, THE system SHALL ensure the
   `.specs/` directory exists before writing the steering document.

#### Edge Cases

1. [64-REQ-1.E1] IF the `.specs/` directory cannot be created due to a
   permission error, THEN THE system SHALL log a warning and continue
   initialization without creating the steering document.

### Requirement 2: Runtime Prompt Inclusion

**User Story:** As a project maintainer, I want steering directives injected
into every agent's system prompt so that all archetypes respect my directives.

#### Acceptance Criteria

1. [64-REQ-2.1] WHEN assembling context for any archetype session AND
   `.specs/steering.md` exists AND contains content beyond the placeholder,
   THE system SHALL include the steering content in the assembled context.
2. [64-REQ-2.2] THE system SHALL place steering content after spec documents
   and before memory facts in the assembled context.
3. [64-REQ-2.3] WHEN `.specs/steering.md` does not exist, THE system SHALL
   skip steering inclusion without warning or error.
4. [64-REQ-2.4] WHEN `.specs/steering.md` contains only placeholder content
   (no user-authored directives), THE system SHALL skip steering inclusion.

#### Edge Cases

1. [64-REQ-2.E1] IF `.specs/steering.md` exists but cannot be read (e.g.,
   permission error), THEN THE system SHALL log a warning and skip steering
   inclusion.

### Requirement 3: Skill Template Reference

**User Story:** As a project maintainer, I want every bundled skill to read
my steering document so that skill-based agents respect my directives.

#### Acceptance Criteria

1. [64-REQ-3.1] THE system SHALL include an instruction in every bundled skill
   template directing the agent to read and follow `.specs/steering.md` if the
   file exists.
2. [64-REQ-3.2] THE instruction SHALL appear early in the skill template
   (before the main skill workflow steps) so it is processed before
   task-specific instructions.

### Requirement 4: AGENTS.md Reference

**User Story:** As a project maintainer, I want AGENTS.md to reference the
steering document so that agents using AGENTS.md directly (e.g., Cursor, Codex)
also follow my directives.

#### Acceptance Criteria

1. [64-REQ-4.1] THE AGENTS.md template SHALL include a reference instructing
   agents to read and follow `.specs/steering.md` if the file exists.
2. [64-REQ-4.2] THE reference SHALL appear in the "Understand Before You Code"
   section, after existing orientation steps.

### Requirement 5: Placeholder Detection

**User Story:** As a developer, I want the system to reliably distinguish
placeholder content from real directives so that empty steering files don't
pollute prompts.

#### Acceptance Criteria

1. [64-REQ-5.1] THE system SHALL define a sentinel marker in the placeholder
   content that can be checked programmatically.
2. [64-REQ-5.2] WHEN the steering document contains the sentinel marker AND
   no other non-whitespace content outside HTML comments, THE system SHALL
   treat the file as placeholder-only.
