# Requirements Document

## Introduction

This specification adds archetype profiles to the prompt assembly pipeline.
Profiles are human-readable markdown files that define archetype behavior
(identity, rules, focus areas, output format). They replace the current
template-based prompt building with a 3-layer system: project context +
archetype profile + task context.

## Glossary

- **Profile**: A markdown file defining an archetype's behavioral guidance
  (identity, rules, focus areas, output format). Lives in
  `.agent-fox/profiles/<archetype>.md` (project-level) or is embedded in
  the package (default).
- **3-layer prompt assembly**: The prompt construction approach where project
  context (CLAUDE.md), archetype profile, and task context are concatenated
  as distinct blocks.
- **Project context**: The content of `CLAUDE.md` — project-wide instructions
  applicable to all agents.
- **Task context**: Spec artifacts, knowledge injection, findings, and
  mode-specific guidance assembled per-session by the engine.
- **Default profile**: The package-embedded profile used when no project
  override exists.
- **Permission preset**: An existing archetype's permission configuration
  (allowlist, sandbox) reused by a custom archetype.
- **Custom archetype**: A team-defined archetype beyond the 4 built-in ones,
  created via a profile + permission preset mapping.

## Requirements

### Requirement 1: 3-Layer Prompt Assembly

**User Story:** As an operator, I want system prompts assembled from three
clearly separated layers so that I can reason about what each agent is told.

#### Acceptance Criteria

[99-REQ-1.1] WHEN building a system prompt, THE system SHALL concatenate three
layers in order: (1) project context from CLAUDE.md, (2) archetype profile,
(3) task context (spec artifacts, findings, knowledge) AND return the combined
prompt with clear delineation between layers.

[99-REQ-1.2] THE system SHALL load the archetype profile from
`.agent-fox/profiles/<archetype>.md` if the file exists in the project
directory AND fall back to the package-embedded default profile otherwise.

[99-REQ-1.3] WHEN a project-level profile exists, THE system SHALL use it as
a full replacement for the default — no merging of sections.

#### Edge Cases

[99-REQ-1.E1] IF `CLAUDE.md` does not exist, THEN THE system SHALL omit the
project context layer and proceed with only the profile and task context.

[99-REQ-1.E2] IF neither a project profile nor a default profile exists for
the archetype, THEN THE system SHALL log a warning and use an empty string
for the profile layer.

### Requirement 2: Default Profiles

**User Story:** As a developer, I want sensible default profiles shipped with
the package so that the system works without any project configuration.

#### Acceptance Criteria

[99-REQ-2.1] THE system SHALL ship default profile files for each built-in
archetype (`coder`, `reviewer`, `verifier`, `maintainer`) embedded in the
`agent_fox._templates.profiles` package directory.

[99-REQ-2.2] EACH default profile SHALL contain four sections: Identity,
Rules, Focus areas, and Output format.

[99-REQ-2.3] THE default profiles SHALL incorporate the content from the
current prompt templates (coding.md, reviewer.md, verifier.md) reorganized
into the 4-section profile structure.

### Requirement 3: Init Profiles Command

**User Story:** As a project maintainer, I want a CLI command to scaffold
profile files in my project so that I can customize archetype behavior.

#### Acceptance Criteria

[99-REQ-3.1] WHEN the user runs `agent-fox init --profiles`, THE system SHALL
copy all default profile files into `.agent-fox/profiles/` in the project
directory AND return the list of created file paths.

[99-REQ-3.2] WHEN a profile file already exists in the project directory,
THE `init --profiles` command SHALL skip that file and log a message
indicating it was preserved.

[99-REQ-3.3] THE `init --profiles` command SHALL create the
`.agent-fox/profiles/` directory if it does not exist.

#### Edge Cases

[99-REQ-3.E1] IF the `.agent-fox/` directory does not exist, THEN THE system
SHALL create it along with the `profiles/` subdirectory.

### Requirement 4: Custom Archetype Extensibility

**User Story:** As a team lead, I want to define project-specific archetypes
beyond the built-in four so that I can support deployment, research, or
other workflows.

#### Acceptance Criteria

[99-REQ-4.1] WHEN a profile exists at `.agent-fox/profiles/<name>.md` for a
name not in the built-in registry, THE system SHALL treat it as a custom
archetype.

[99-REQ-4.2] THE config SHALL support `archetype.<name>.permissions` mapping
a custom archetype to a built-in archetype's permission profile (allowlist,
sandbox settings) AND the system SHALL enforce that preset's permissions.

[99-REQ-4.3] WHEN a task group uses `[archetype: <name>]` for a custom
archetype, THE system SHALL load the custom profile, apply the permission
preset, and execute the session.

[99-REQ-4.4] THE `get_archetype()` function SHALL check for custom archetype
profiles as a fallback before falling back to `"coder"`, AND return an
`ArchetypeEntry` constructed from the permission preset.

#### Edge Cases

[99-REQ-4.E1] IF a custom archetype has a profile but no permission preset
in config, THEN THE system SHALL default to the `"coder"` permission profile
with a warning.

[99-REQ-4.E2] IF a custom archetype's permission preset references a
non-existent built-in archetype, THEN THE system SHALL raise a
configuration error.

### Requirement 5: Profile Loading

**User Story:** As the engine, I need a reliable profile loading mechanism
that resolves profiles from the correct location.

#### Acceptance Criteria

[99-REQ-5.1] THE system SHALL provide a `load_profile(archetype: str,
project_dir: Path | None)` function that returns the profile content as a
string.

[99-REQ-5.2] THE `load_profile()` function SHALL check
`<project_dir>/.agent-fox/profiles/<archetype>.md` first, then fall back to
the package-embedded default.

[99-REQ-5.3] THE `load_profile()` function SHALL strip any YAML frontmatter
from the profile file before returning content.

#### Edge Cases

[99-REQ-5.E1] WHEN `project_dir` is `None`, THE system SHALL use only the
package default profile.
