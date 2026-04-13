# PRD: Archetype Profiles

## Problem Statement

Agent behavior is currently defined by templates embedded in the
`agent_fox._templates.prompts` package. These templates are invisible to
project teams — when an agent misbehaves, diagnosing "what was it told?"
requires reading Python source. There is no way for a team to customize
archetype behavior per project (e.g., "our reviewers should always check
accessibility" or "our coders must run `make lint` before committing")
without modifying the package itself.

The v3 architecture introduces **archetype profiles** — readable, editable
files that define how each archetype behaves. Profiles live in
`.agent-fox/profiles/` and participate in a 3-layer prompt assembly:
project context (CLAUDE.md) + archetype profile + task context.

Additionally, profiles enable **custom archetype extensibility** — teams
can define project-specific archetypes beyond the 4 built-in ones by
creating a profile and mapping it to a permission preset.

## Goals

1. Implement 3-layer prompt assembly: project context → archetype profile →
   task context.
2. Ship default profiles embedded in the package for all built-in archetypes.
3. Support project-level profile overrides at `.agent-fox/profiles/<archetype>.md`.
4. Override semantics: full replacement (project profile replaces package
   default entirely).
5. Add `af init --profiles` command to copy default profiles into the project.
6. Support custom archetypes via profiles + permission presets in config.

## Non-Goals

- Section-level merge of profiles (too complex, makes effective prompt hard
  to reason about).
- Mode-specific profiles (profiles are per archetype, not per mode).
- Profile templating or variable substitution within profiles.

## Design Decisions

1. **Full replacement override.** If a team creates `.agent-fox/profiles/coder.md`,
   they own the entire profile — including Identity and Rules sections.
   No section-level merging.
2. **Profiles are per archetype, not per mode.** A single `reviewer.md`
   profile covers all reviewer modes. Mode-specific guidance belongs in
   the task context layer, not the profile.
3. **Profile structure is advisory.** The engine doesn't parse profile
   sections (Identity, Rules, Focus areas, Output format). The structure
   is a convention for human authors — the engine treats the profile as
   an opaque text block inserted into the prompt.
4. **Custom archetypes use permission presets.** A custom archetype maps
   to an existing archetype's permission profile (allowlist, sandbox).
   This keeps security enforcement centralized.
5. **`af init --profiles` is additive.** It copies default profiles into
   the project directory, creating `.agent-fox/profiles/` if needed.
   Existing files are NOT overwritten.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 97_archetype_modes | 2 | 2 | Uses ArchetypeEntry.modes and get_archetype() from group 2 where registry is updated |
| 98_reviewer_consolidation | 2 | 2 | Uses consolidated registry (reviewer, coder with modes) from group 2 to generate correct default profiles |
