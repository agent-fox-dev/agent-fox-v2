# Requirements Document

## Introduction

This specification adds mode support to the archetype system. A mode is a named
variant of an archetype that overrides specific configuration fields (templates,
allowlist, model tier, injection timing, etc.) while inheriting all others from
the base archetype entry. This enables subsequent specs to consolidate multiple
flat archetypes (skeptic, oracle, auditor) into a single mode-bearing archetype
(reviewer) without changing the underlying infrastructure.

## Glossary

- **Archetype**: A named configuration bundle that defines how an agent session
  executes — its templates, model tier, permissions, and injection timing.
- **Mode**: A named variant of an archetype that overrides specific
  configuration fields while inheriting the rest from the base archetype.
- **ModeConfig**: A dataclass holding mode-specific override values.
- **ArchetypeEntry**: The frozen dataclass representing a single archetype in
  the registry.
- **Effective config**: The fully resolved configuration produced by merging
  mode overrides onto a base archetype entry.
- **Allowlist**: The set of shell commands an archetype is permitted to execute.
- **Injection**: The timing at which an archetype is auto-inserted into the
  task graph (`auto_pre`, `auto_post`, `auto_mid`, or `None`).
- **Resolution priority**: The ordered chain of configuration sources consulted
  when resolving a parameter value.

## Requirements

### Requirement 1: Mode-Bearing Archetype Entries

**User Story:** As a developer, I want archetypes to support named modes so
that I can express variants (e.g., reviewer:pre-review) within a single
archetype rather than defining separate top-level entries.

#### Acceptance Criteria

[97-REQ-1.1] THE system SHALL provide a `ModeConfig` frozen dataclass with
optional override fields: `templates`, `injection`, `allowlist`, `model_tier`,
`max_turns`, `thinking_mode`, `thinking_budget`, and `retry_predecessor`, all
defaulting to `None`.

[97-REQ-1.2] THE `ArchetypeEntry` dataclass SHALL include a `modes` field of
type `dict[str, ModeConfig]` defaulting to an empty dict.

[97-REQ-1.3] THE system SHALL provide a `resolve_effective_config()` function
that accepts an `ArchetypeEntry` and an optional mode name AND returns a new
`ArchetypeEntry` with mode overrides merged onto the base entry.

[97-REQ-1.4] WHEN `resolve_effective_config()` is called with `mode=None`,
THE system SHALL return the base `ArchetypeEntry` unchanged.

[97-REQ-1.5] WHEN `resolve_effective_config()` is called with a valid mode
name, THE system SHALL return a new `ArchetypeEntry` where each non-`None`
field from the `ModeConfig` overrides the corresponding base field, and all
`None` fields inherit the base value.

#### Edge Cases

[97-REQ-1.E1] IF `resolve_effective_config()` is called with a mode name that
does not exist in the entry's `modes` dict, THEN THE system SHALL log a
warning and return the base `ArchetypeEntry` unchanged.

[97-REQ-1.E2] WHEN an `ArchetypeEntry` has an empty `modes` dict, THE system
SHALL treat it identically to having no modes — `resolve_effective_config()`
returns the base entry for any mode argument.

### Requirement 2: Graph Node Mode Support

**User Story:** As the engine, I need to know which mode a task graph node
operates in so that I can pass the correct mode to session setup.

#### Acceptance Criteria

[97-REQ-2.1] THE `Node` dataclass SHALL include a `mode` field of type
`str | None` defaulting to `None`.

[97-REQ-2.2] WHEN a `TaskGraph` is serialized to JSON and deserialized back,
THE system SHALL preserve the `mode` field on every `Node`.

[97-REQ-2.3] WHEN a `Node` has a non-`None` mode, THE system SHALL include
the mode in the node's string representation (e.g., `"reviewer:pre-review"`).

#### Edge Cases

[97-REQ-2.E1] WHEN a `Node` has `mode=None`, THE system SHALL behave
identically to the current implementation — no mode information appears in
string representations or is passed to session setup.

### Requirement 3: Mode-Aware Configuration

**User Story:** As a project maintainer, I want to configure per-mode overrides
in `config.toml` so that I can tune model tier, allowlists, and thinking
settings for specific modes independently.

#### Acceptance Criteria

[97-REQ-3.1] THE `PerArchetypeConfig` model SHALL include a `modes` field of
type `dict[str, PerArchetypeConfig]` defaulting to an empty dict, enabling
nested per-mode overrides.

[97-REQ-3.2] WHEN config TOML contains a section like
`[archetypes.overrides.reviewer.modes.pre-review]`, THE system SHALL parse it
into the nested `modes` dict on `PerArchetypeConfig`.

[97-REQ-3.3] THE system SHALL resolve configuration with the following
priority chain (highest to lowest):
  1. `archetypes.overrides.<archetype>.modes.<mode>.<field>`
  2. `archetypes.overrides.<archetype>.<field>`
  3. Registry `ModeConfig` for the mode (if present)
  4. Registry `ArchetypeEntry` base default

#### Edge Cases

[97-REQ-3.E1] IF no mode-specific section exists in config for a given
archetype and mode, THEN THE system SHALL fall back to the archetype-level
override, then to registry defaults.

### Requirement 4: Mode-Aware Parameter Resolution

**User Story:** As the session lifecycle, I need all SDK parameter resolution
functions to accept a mode so that mode-specific configuration is applied
during session setup.

#### Acceptance Criteria

[97-REQ-4.1] THE `resolve_model_tier()` function SHALL accept an optional
`mode: str | None` parameter and resolve using the priority chain from
97-REQ-3.3.

[97-REQ-4.2] THE `resolve_max_turns()` function SHALL accept an optional
`mode: str | None` parameter and resolve using the priority chain from
97-REQ-3.3.

[97-REQ-4.3] THE `resolve_thinking()` function SHALL accept an optional
`mode: str | None` parameter and resolve using the priority chain from
97-REQ-3.3.

[97-REQ-4.4] THE `resolve_security_config()` function SHALL accept an optional
`mode: str | None` parameter and resolve using the priority chain from
97-REQ-3.3.

[97-REQ-4.5] THE `clamp_instances()` function SHALL accept an optional
`mode: str | None` parameter. WHEN archetype is `"coder"` regardless of mode,
THE system SHALL clamp instances to 1.

#### Edge Cases

[97-REQ-4.E1] WHEN `mode=None` is passed to any resolution function, THE
system SHALL produce results identical to the current modeless behavior.

### Requirement 5: Mode-Aware Security

**User Story:** As a security boundary, I need the command allowlist hook to
resolve by (archetype, mode) so that modes like reviewer:pre-review can have
no shell access while reviewer:drift-review has analysis commands.

#### Acceptance Criteria

[97-REQ-5.1] THE `make_pre_tool_use_hook()` function SHALL accept an optional
`mode: str | None` parameter AND use it when resolving the effective allowlist.

[97-REQ-5.2] WHEN a mode's resolved allowlist is an empty list, THE system
SHALL block all Bash tool invocations for that session.

[97-REQ-5.3] THE `NodeSessionRunner` SHALL pass the node's mode to
`resolve_security_config()` and `make_pre_tool_use_hook()` during session
setup.

#### Edge Cases

[97-REQ-5.E1] WHEN a mode has no allowlist override (`None` in ModeConfig),
THE system SHALL inherit the base archetype's allowlist.
