# PRD: Archetype Model v3 — Mode Infrastructure

## Problem Statement

The current archetype system defines archetypes as flat entries in a static
registry (`ARCHETYPE_REGISTRY` in `agent_fox/archetypes.py`). Each of the 8
archetypes (coder, skeptic, oracle, auditor, verifier, triage, fix_reviewer,
fix_coder) is a standalone `ArchetypeEntry` with fixed templates, permissions,
model tier, and injection timing.

This prevents expressing that skeptic, oracle, and auditor are conceptually
*modes* of a single "reviewer" archetype — they share review semantics but
differ in focus, permissions, and injection timing. Similarly, triage is
conceptually a mode of a "maintainer" archetype, and fix_coder is a mode of
"coder".

The v3 architecture consolidates 8 archetypes into 4 mode-bearing archetypes
(Coder, Reviewer, Verifier, Maintainer). This spec adds the **mode
infrastructure** — data model, configuration schema, resolution logic, and
security integration — without performing the actual archetype consolidation.

## Goals

1. Add a `ModeConfig` dataclass for mode-specific configuration overrides.
2. Add a `modes` dict field to `ArchetypeEntry` mapping mode names to
   `ModeConfig` instances.
3. Add a `resolve_effective_config()` function that merges mode overrides onto
   base archetype config.
4. Add a `mode` field to `Node` in the task graph.
5. Extend the configuration schema (`PerArchetypeConfig`) with per-mode
   override support.
6. Update all SDK parameter resolution functions to accept a `mode` parameter.
7. Update the security hook to resolve allowlists by `(archetype, mode)` pair.

## Non-Goals

- Consolidating existing archetypes into reviewer/maintainer (Spec 98, 100).
- Implementing archetype profiles (Spec 99).
- Adaptive model routing (removed from v3 scope).
- Database migration tooling.
- Backward compatibility with v2 config keys (clean break).

## Design Decisions

1. **Clean break from v2 config keys.** No backward compatibility shims.
   Users must update their `config.toml` when mode-aware keys are introduced.
2. **Breaking DB changes accepted.** Session and convergence records may
   reference new archetype/mode pairs. No migration tooling required.
3. **No adaptive routing.** The Coder uses static tier assignment with
   escalation ladder on retry, not heuristic-based initial tier selection.
4. **Allowlist sentinel values.** In `ModeConfig`, `None` means "inherit from
   base archetype", `[]` (empty list) means "no shell commands allowed"
   (blocks all Bash). This distinction is critical for modes like
   reviewer:pre-review that must have no shell access at all.
5. **Modeless archetypes work unchanged.** Archetypes without modes (e.g.,
   verifier) work exactly as before. `mode=None` is the default and
   resolution skips mode lookup.
6. **Mode overrides are opt-in.** Every field in `ModeConfig` defaults to
   `None` (inherit). Only explicitly set fields override the base.
