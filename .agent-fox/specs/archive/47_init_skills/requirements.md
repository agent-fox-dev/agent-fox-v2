# Requirements Document

## Introduction

This specification defines the `--skills` flag for the `agent-fox init`
command. When provided, the flag triggers installation of bundled Claude Code
skill files into the project's `.claude/skills/` directory, enabling users to
invoke agent-fox skills (e.g., `/af-spec`, `/af-fix`) from interactive Claude
Code sessions.

## Glossary

- **Skill**: A Claude Code slash command defined by a `SKILL.md` file in a
  `.claude/skills/{name}/` directory. Contains YAML frontmatter (name,
  description, optional argument-hint) followed by markdown instructions.
- **Bundled template**: A skill file shipped inside the `agent_fox` Python
  package at `agent_fox/_templates/skills/{name}`.
- **YAML frontmatter**: A metadata block delimited by `---` lines at the top
  of a SKILL.md file, containing fields like `name`, `description`, and
  `argument-hint`.
- **Project root**: The current working directory where `agent-fox init` is
  invoked (must be a git repository).

## Requirements

### Requirement 1: Bundled Skill Templates Include Frontmatter

**User Story:** As a developer packaging agent-fox, I want the bundled skill
templates to include valid YAML frontmatter, so that they can be installed
directly as SKILL.md files without post-processing.

#### Acceptance Criteria

1. [47-REQ-1.1] THE bundled skill templates in `agent_fox/_templates/skills/`
   SHALL each contain YAML frontmatter with at least `name` and `description`
   fields, delimited by `---` lines.

2. [47-REQ-1.2] THE `name` field in each bundled template's frontmatter SHALL
   match the template's filename (directory name).

3. [47-REQ-1.3] THE bundled skill templates SHALL be complete, valid SKILL.md
   files that can be copied directly to `.claude/skills/{name}/SKILL.md`
   without modification.

#### Edge Cases

1. [47-REQ-1.E1] IF a bundled template file cannot be read (e.g., missing or
   corrupt), THEN THE system SHALL skip that skill and log a warning rather
   than aborting the entire installation.

### Requirement 2: `--skills` Flag on Init Command

**User Story:** As a user, I want to pass `--skills` to `agent-fox init`, so
that Claude Code skills are installed into my project automatically.

#### Acceptance Criteria

1. [47-REQ-2.1] WHEN the user runs `agent-fox init --skills`, THE system SHALL
   copy each bundled skill template to
   `{project_root}/.claude/skills/{skill-name}/SKILL.md`.

2. [47-REQ-2.2] WHEN the user runs `agent-fox init` without `--skills`, THE
   system SHALL NOT install any skills.

3. [47-REQ-2.3] WHEN `--skills` is provided, THE system SHALL create the
   `.claude/skills/` directory and any required subdirectories if they do not
   exist.

4. [47-REQ-2.4] WHEN `--skills` is provided and skill files already exist at
   the target location, THE system SHALL overwrite them with the latest bundled
   versions.

5. [47-REQ-2.5] WHEN `--skills` is provided, THE system SHALL report the
   number of skills installed in its output.

#### Edge Cases

1. [47-REQ-2.E1] IF the `_templates/skills/` directory is empty or missing,
   THEN THE system SHALL log a warning and report zero skills installed rather
   than failing.

2. [47-REQ-2.E2] IF the `.claude/skills/` directory cannot be created (e.g.,
   permission error), THEN THE system SHALL report an error and continue with
   the rest of init.

### Requirement 3: JSON Output Includes Skills Status

**User Story:** As a tool consuming `agent-fox init --json`, I want the JSON
output to include skills installation status, so that I can programmatically
verify the result.

#### Acceptance Criteria

1. [47-REQ-3.1] WHEN the user runs `agent-fox init --skills --json`, THE
   system SHALL include a `skills_installed` integer field in the JSON output
   indicating the number of skills installed.

2. [47-REQ-3.2] WHEN the user runs `agent-fox init --json` without `--skills`,
   THE JSON output SHALL NOT include a `skills_installed` field.

### Requirement 4: Skills Work on Both Fresh and Re-Init

**User Story:** As a user, I want `--skills` to work whether I'm initializing
a new project or re-initializing an existing one, so that I can install or
update skills at any time.

#### Acceptance Criteria

1. [47-REQ-4.1] WHEN the user runs `agent-fox init --skills` on a fresh
   project, THE system SHALL install skills as part of the initial setup.

2. [47-REQ-4.2] WHEN the user runs `agent-fox init --skills` on an
   already-initialized project, THE system SHALL install (or update) skills
   and continue with the normal re-init behavior.
