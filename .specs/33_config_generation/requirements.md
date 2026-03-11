# Requirements Document

## Introduction

This specification defines the config generation and merge system for
agent-fox. The `init` command must produce a complete, documented `config.toml`
derived programmatically from the Pydantic configuration models. Re-running
`init` on an existing project must merge the config intelligently: preserving
user values, surfacing new fields as comments, and marking removed fields as
deprecated.

## Glossary

- **Config model**: A Pydantic `BaseModel` subclass in `agent_fox/core/config.py`
  that defines the schema for a configuration section.
- **Root model**: `AgentFoxConfig` — the top-level Pydantic model containing all
  config sections as nested fields.
- **Config template**: The generated `config.toml` content written by `init`,
  with all fields commented out and annotated with descriptions and defaults.
- **Config merge**: The process of updating an existing `config.toml` to match
  the current schema without losing user-set values or comments.
- **Commented field**: A config field that appears in the TOML file prefixed
  with `#`, showing its default value and description but not active.
- **Active field**: A config field whose line is not commented out — its value
  is loaded by `load_config`.
- **Deprecated field**: A field present in the user's TOML but no longer
  recognized by the current Pydantic models, marked with `# DEPRECATED`.
- **tomlkit**: A Python library for TOML manipulation that preserves comments,
  formatting, and ordering during round-trip read/write.

## Requirements

### Requirement 1: Config Template Generation

**User Story:** As a developer, I want `agent-fox init` to produce a
`config.toml` that documents every available configuration option, so that I
can discover and customize settings without reading source code.

#### Acceptance Criteria

[33-REQ-1.1] WHEN `init` creates a new `config.toml`, THE system SHALL
generate the file content by introspecting every field of `AgentFoxConfig` and
its nested models, producing one commented entry per field.

[33-REQ-1.2] WHEN generating a config template, THE system SHALL include for
each field: a comment with a brief description, the valid range (if the field
has clamping bounds), and the default value as a commented-out TOML key-value
pair.

[33-REQ-1.3] WHEN generating a config template, THE system SHALL emit proper
TOML section headers for each top-level config section (e.g., `# [orchestrator]`)
and sub-table headers for nested models (e.g., `# [archetypes.instances]`).

[33-REQ-1.4] WHEN generating a config template, THE system SHALL produce
output that, when all comment prefixes are removed, is valid TOML that
`load_config` accepts without errors or warnings.

[33-REQ-1.5] WHEN generating a config template, THE system SHALL order
sections and fields in the same order as they appear in the Pydantic model
definitions.

#### Edge Cases

[33-REQ-1.E1] IF a field's default value is `None`, THEN THE system SHALL
represent it as a commented-out entry with the comment `# not set by default`.

[33-REQ-1.E2] IF a field's default value is an empty list, THEN THE system
SHALL represent it as a commented-out entry with value `[]`.

[33-REQ-1.E3] IF a field's default value is an empty dict, THEN THE system
SHALL represent it as a commented-out entry with value `{}`.

### Requirement 2: Config Merge on Re-init

**User Story:** As a developer, I want re-running `init` to update my
`config.toml` with new options without losing my customizations, so that I stay
current with schema changes.

#### Acceptance Criteria

[33-REQ-2.1] WHEN `init` runs and `config.toml` already exists, THE system
SHALL preserve all active (uncommented) field values set by the user.

[33-REQ-2.2] WHEN `init` runs and `config.toml` already exists, THE system
SHALL add any fields present in the current schema but missing from the file
as commented-out entries with defaults and descriptions.

[33-REQ-2.3] WHEN `init` runs and `config.toml` already exists, THE system
SHALL preserve all user comments and formatting that are not part of
managed config entries.

[33-REQ-2.4] WHEN `init` runs and `config.toml` contains active fields not
recognized by the current schema, THE system SHALL prefix those fields with
`# DEPRECATED: '<field_name>' is no longer recognized` and comment out the
value.

[33-REQ-2.5] WHEN `init` runs and `config.toml` already exists with no
schema changes needed, THE system SHALL leave the file unchanged (byte-for-byte
identical).

#### Edge Cases

[33-REQ-2.E1] IF the existing `config.toml` contains invalid TOML syntax, THEN
THE system SHALL log a warning, skip the merge, and leave the file untouched.

[33-REQ-2.E2] IF the existing `config.toml` is empty or whitespace-only, THEN
THE system SHALL treat it as a fresh generation (same as no file existing).

### Requirement 3: Round-Trip Integrity

**User Story:** As a developer, I want generated configs to load without
warnings, so that I can trust the generation is correct.

#### Acceptance Criteria

[33-REQ-3.1] THE system SHALL ensure that a freshly generated `config.toml`
(with all fields commented out) loads via `load_config` and returns an
`AgentFoxConfig` with all documented default values.

[33-REQ-3.2] WHEN a generated `config.toml` has all comment prefixes removed,
THE system SHALL ensure `load_config` accepts it without errors or warnings
and returns an `AgentFoxConfig` with all documented default values.

#### Edge Cases

[33-REQ-3.E1] IF a Pydantic model field has an alias (e.g., `skeptic_settings`
for `skeptic_config`), THEN THE system SHALL use the alias in the generated
TOML to match what `load_config` expects.

### Requirement 4: Schema Introspection API

**User Story:** As a maintainer, I want a centralized function that extracts
the full config schema from Pydantic models, so that the template generator,
merge logic, and documentation can all use the same source of truth.

#### Acceptance Criteria

[33-REQ-4.1] THE system SHALL provide a function that, given the root
`AgentFoxConfig` model, returns a structured representation of all sections,
fields, types, defaults, descriptions, and constraints.

[33-REQ-4.2] WHEN a new field is added to any config model, THE system SHALL
automatically include it in the generated template and merge logic without
any manual updates to the generator.

#### Edge Cases

[33-REQ-4.E1] IF a config model uses `Field(default_factory=...)` for mutable
defaults, THEN THE system SHALL invoke the factory to obtain the default value
for template generation.

### Requirement 5: Dead Code Cleanup

**User Story:** As a maintainer, I want unused config definitions removed, so
that the config schema only contains fields that are actually used.

#### Acceptance Criteria

[33-REQ-5.1] THE system SHALL remove the `MemoryConfig` class and the
`memory` field from `AgentFoxConfig` since no code accesses `config.memory`.

[33-REQ-5.2] WHEN `load_config` encounters a `[memory]` section in an existing
TOML file, THE system SHALL ignore it without error (via Pydantic's
`extra="ignore"` on the root model).
