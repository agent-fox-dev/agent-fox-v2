# PRD: Config Generation

> Source: [GitHub Issue #140](https://github.com/agent-fox-dev/agent-fox-v2/issues/140)

## Problem

The `agent-fox init` command generates a `config.toml` that is severely
incomplete. The current `_DEFAULT_CONFIG` is a hand-maintained string literal
covering only 9 of 71+ config fields defined in the Pydantic models. This means
users are unaware of most configuration options and must read source code to
discover them.

Additionally, when the config schema evolves (fields added, removed, or
renamed), existing `config.toml` files become stale with no mechanism to bring
them up to date.

## Goals

1. **Generate the config template programmatically** from the Pydantic models in
   `agent_fox/core/config.py` so the template never drifts from the schema.
2. **Make `init` idempotent with smart merging** — re-running `init` on an
   existing project merges the config: preserving user values, adding new fields
   as comments, and marking removed fields as deprecated.
3. **Centralize configuration definitions** — the Pydantic models are the single
   source of truth. The generated template, documentation, and merge logic all
   derive from the models.
4. **Clean up dead config code** — remove `memory.model` (defined but never
   accessed).

## Scope

### In Scope

- Replace the static `_DEFAULT_CONFIG` string in `init.py` with a generator
  that introspects `AgentFoxConfig` and its nested models.
- Add `tomlkit` as a dependency for comment-preserving TOML read/write
  (round-trip without losing user comments or formatting).
- Implement config merge logic in `init`: when `config.toml` already exists,
  read it with `tomlkit`, compare against the current schema, add missing
  fields as commented-out entries with defaults and descriptions, and mark
  removed fields with a `# DEPRECATED` prefix.
- Each generated commented field includes: the default value, a brief
  description, and valid range (where applicable).
- Nested config sections (e.g., `[archetypes.instances]`,
  `[archetypes.skeptic_settings]`) use proper TOML sub-table syntax.
- Remove the unused `MemoryConfig.model` field and the `MemoryConfig` /
  `[memory]` section if no other fields remain.
- Round-trip test: generate → load → no warnings/errors.
- Update `load_config` to use `tomlkit` instead of `tomllib` for consistency
  (or keep `tomllib` for loading if preferred — but generation must use
  `tomlkit`).

### Out of Scope

- Config migration across major versions (semantic versioning of config schema).
- GUI or interactive config editor.
- Config validation CLI command (already covered by `load_config`).

## Clarifications

1. **Generate from models:** The template is derived programmatically from
   Pydantic model introspection. No more hand-maintained string literals.
2. **Detecting removed fields:** Compare keys in the existing TOML against
   field names in the current Pydantic models. Keys not in the models are
   candidates for deprecation marking.
3. **tomlkit for round-trip:** Use `tomlkit` (not `tomli-w`) because it
   preserves comments, formatting, and ordering — critical for the merge use
   case.
4. **Commented field format:** Each commented field includes default value,
   brief description, and valid range where applicable. Example:
   ```toml
   # Maximum parallel sessions (1-8, default: 1)
   # parallel = 1
   ```
5. **Deprecated field format:** Fields no longer in the schema get prefixed:
   ```toml
   # DEPRECATED: 'old_field' is no longer recognized
   # old_field = "value"
   ```
6. **Nested config:** Use full TOML section syntax:
   ```toml
   # [archetypes.instances]
   # skeptic = 1
   # verifier = 1
   ```
7. **Dead code removal:** `memory.model` field and `MemoryConfig` class removed
   since no code reads it. If the `[memory]` section gains new fields in the
   future, recreate the class then.
8. **`load_config` stays with `tomllib`** for loading (stdlib, no extra
   dependency for the read path). `tomlkit` is used only for generation and
   merging in `init`.
