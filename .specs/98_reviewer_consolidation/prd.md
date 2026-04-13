# PRD: Reviewer Consolidation

## Problem Statement

The current archetype system has three separate review archetypes (skeptic,
oracle, auditor) and a separate fix_reviewer, each with their own registry
entry, template, convergence logic, config keys, and injection rules. This
duplication makes the system harder to reason about and configure. The v3
architecture consolidates them into a single **Reviewer** archetype with named
modes:

- **pre-review** (replaces skeptic): Examines specs before coding for
  ambiguity, contradictions, and missing edge cases.
- **drift-review** (replaces oracle): Compares spec design against existing
  codebase for architectural divergence.
- **audit-review** (replaces auditor): Validates test coverage against
  test_spec contracts.
- **fix-review** (replaces fix_reviewer): Reviews nightshift fix proposals.

Additionally, `fix_coder` is folded into `coder` as a `fix` mode.

## Goals

1. Define a single `reviewer` archetype in the registry with 4 modes.
2. Fold `fix_coder` into `coder` as mode `fix`.
3. Merge the 4 review templates into one `reviewer.md` with mode-specific
   sections.
4. Update injection logic to inject `reviewer(pre-review)`,
   `reviewer(drift-review)`, etc. instead of skeptic, oracle, auditor.
5. Update convergence dispatch to route by mode rather than archetype name.
6. Enforce single-instance verifier (remove multi-instance support).
7. Update verifier default model tier from ADVANCED to STANDARD.
8. Remove old archetype entries (skeptic, oracle, auditor, fix_reviewer,
   fix_coder) from the registry.
9. Update config schema to use reviewer mode keys instead of per-archetype keys.

## Non-Goals

- Changing convergence algorithms (keep current skeptic/auditor/verifier
  logic as-is, just dispatch by mode).
- Implementing archetype profiles (Spec 99).
- Creating the Maintainer archetype (Spec 100).

## Design Decisions

1. **Keep current convergence logic.** Pre-review and drift-review use the
   current majority-gated blocking (skeptic convergence). Audit-review uses
   the current union/worst-verdict-wins (auditor convergence). This avoids
   over-blocking and preserves tested behavior.
2. **Verifier: STANDARD tier with escalation.** The verifier model tier
   changes from ADVANCED to STANDARD, with the existing escalation ladder
   available on retry.
3. **Verifier: single-instance only.** The `ArchetypeInstancesConfig.verifier`
   default changes from 2 to 1. Clamping enforces max 1.
4. **Template merging.** skeptic.md, oracle.md, auditor.md, and
   fix_reviewer.md merge into a single reviewer.md. Mode-specific guidance
   uses conditional sections. fix_coding.md merges into coding.md with a
   fix-mode section.
5. **Config clean break.** Config keys like `archetypes.skeptic`,
   `archetypes.skeptic_config`, `archetypes.oracle_settings` are replaced
   by `archetypes.reviewer` (enable toggle) and
   `archetypes.overrides.reviewer.modes.<mode>` (per-mode config).
   Old keys are removed with no deprecation shim.
6. **Triage stays.** The triage archetype remains unchanged in this spec.
   It will be absorbed into the Maintainer in Spec 100.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 97_archetype_modes | 4 | 2 | Uses mode infrastructure (ModeConfig, resolve_effective_config, mode-aware SDK resolution) from group 4 where resolution functions are updated |
