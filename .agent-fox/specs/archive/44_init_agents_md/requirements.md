# Requirements Document

## Introduction

This specification extends the `agent-fox init` command to scaffold an
`AGENTS.md` template file in the project root. The template provides
project-specific instructions for coding agents (Claude Code, Cursor, Codex,
etc.) and follows the same idempotent pattern as the existing
`.claude/settings.local.json` creation.

## Glossary

- **AGENTS.md**: A markdown file at the project root containing instructions
  and conventions for coding agents working on the repository.
- **Template**: A static file bundled in the agent-fox package at
  `agent_fox/_templates/agents_md.md` that serves as the initial content for
  `AGENTS.md`. Contains placeholder markers for project-specific values.
- **Placeholder marker**: An angle-bracketed token (e.g., `<main_package>`)
  in the template that users replace with project-specific values.
- **Fresh init**: Running `agent-fox init` on a project that has no
  `.agent-fox/` directory or `config.toml`.
- **Re-init**: Running `agent-fox init` on a project that already has an
  `.agent-fox/config.toml`.
- **JSON mode**: The `--json` output flag that causes commands to emit
  structured JSON instead of human-readable text.
- **Project root**: The current working directory (`Path.cwd()`) where
  `agent-fox init` is executed.

## Requirements

### Requirement 1: Bundle AGENTS.md Template

**User Story:** As a maintainer, I want a well-structured AGENTS.md template
bundled with agent-fox, so that users get a useful starting point without
writing instructions from scratch.

#### Acceptance Criteria

1. [44-REQ-1.1] THE agent-fox package SHALL include a static template file
   at `agent_fox/_templates/agents_md.md`.
2. [44-REQ-1.2] THE template file SHALL be valid UTF-8 encoded markdown.
3. [44-REQ-1.3] THE template file SHALL contain placeholder markers in
   angle-bracket format (e.g., `<main_package>`) for project-specific values
   that users customize.

#### Edge Cases

1. [44-REQ-1.E1] IF the template file is missing from the package, THEN THE
   init command SHALL raise a clear error message identifying the missing
   template path.

### Requirement 2: Create AGENTS.md on Fresh Init

**User Story:** As a user running `agent-fox init` for the first time, I want
an `AGENTS.md` file created automatically, so that coding agents have
project instructions from day one.

#### Acceptance Criteria

1. [44-REQ-2.1] WHEN `agent-fox init` runs in a project without an existing
   `AGENTS.md`, THE init command SHALL write the template content to
   `{project_root}/AGENTS.md` using UTF-8 encoding.
2. [44-REQ-2.2] WHEN `AGENTS.md` is created, THE init command SHALL display
   the message `Created AGENTS.md.` to the user via `click.echo`.
3. [44-REQ-2.3] WHEN `AGENTS.md` is created in JSON mode, THE init command
   SHALL include `"agents_md": "created"` in the JSON output object.

#### Edge Cases

1. [44-REQ-2.E1] IF the project root directory is read-only or the write
   fails, THEN THE init command SHALL raise an appropriate OS error (no
   special handling beyond what `Path.write_text` provides).

### Requirement 3: Skip AGENTS.md on Re-Init

**User Story:** As a user re-running `agent-fox init`, I want my customized
`AGENTS.md` to be preserved, so that my project-specific instructions are
never overwritten.

#### Acceptance Criteria

1. [44-REQ-3.1] WHEN `agent-fox init` runs in a project where `AGENTS.md`
   already exists, THE init command SHALL NOT overwrite, modify, or read the
   existing file.
2. [44-REQ-3.2] WHEN `AGENTS.md` already exists, THE init command SHALL NOT
   display any message about `AGENTS.md` (silent skip).
3. [44-REQ-3.3] WHEN `AGENTS.md` already exists in JSON mode, THE init
   command SHALL include `"agents_md": "skipped"` in the JSON output object.

#### Edge Cases

1. [44-REQ-3.E1] IF `AGENTS.md` exists but is empty (zero bytes), THEN THE
   init command SHALL still skip it (existence check only, no content
   inspection).

### Requirement 4: Coexistence with CLAUDE.md

**User Story:** As a user who already has a `CLAUDE.md`, I want `AGENTS.md`
to be created independently, so that both files can coexist.

#### Acceptance Criteria

1. [44-REQ-4.1] WHEN `CLAUDE.md` exists in the project root, THE init
   command SHALL still create `AGENTS.md` if it does not exist.
2. [44-REQ-4.2] WHEN `CLAUDE.md` does not exist in the project root, THE
   init command SHALL still create `AGENTS.md`.

### Requirement 5: Git Tracking

**User Story:** As a user, I want `AGENTS.md` to be git-tracked by default,
so that all team members and agents share the same instructions.

#### Acceptance Criteria

1. [44-REQ-5.1] THE init command SHALL NOT add `AGENTS.md` to `.gitignore`.
