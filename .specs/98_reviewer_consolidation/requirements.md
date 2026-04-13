# Requirements Document

## Introduction

This specification consolidates the separate review archetypes (skeptic, oracle,
auditor, fix_reviewer) into a single **reviewer** archetype with named modes,
folds fix_coder into coder as a mode, updates the verifier to single-instance
STANDARD tier, and cleans up the registry and configuration.

## Glossary

- **Reviewer**: The consolidated archetype replacing skeptic, oracle, auditor,
  and fix_reviewer. Operates in one of four modes.
- **Pre-review mode**: Review mode that examines specs before coding (replaces
  skeptic).
- **Drift-review mode**: Review mode that compares spec design against existing
  codebase (replaces oracle).
- **Audit-review mode**: Review mode that validates test coverage against
  test_spec contracts (replaces auditor).
- **Fix-review mode**: Review mode for nightshift fix proposals (replaces
  fix_reviewer).
- **Fix mode (coder)**: Coder mode for nightshift fix implementation (replaces
  fix_coder).
- **Convergence**: The process of combining results from multiple instances of
  the same archetype/mode into a single verdict.
- **Injection**: Automatic insertion of archetype nodes into the task graph at
  specific timing points.
- **Oracle gating**: Skipping drift-review when the spec references no
  existing code.

## Requirements

### Requirement 1: Reviewer Archetype With Modes

**User Story:** As a project operator, I want a single reviewer archetype with
modes so that review configuration is unified and coherent.

#### Acceptance Criteria

[98-REQ-1.1] THE `ARCHETYPE_REGISTRY` SHALL contain a `"reviewer"` entry with
modes `"pre-review"`, `"drift-review"`, `"audit-review"`, and `"fix-review"`,
each with mode-specific templates, allowlist, injection timing, and model tier.

[98-REQ-1.2] THE reviewer's pre-review mode SHALL have no shell access
(empty allowlist), `auto_pre` injection, and STANDARD model tier.

[98-REQ-1.3] THE reviewer's drift-review mode SHALL have a read-only analysis
allowlist (`ls`, `cat`, `git`, `grep`, `find`, `head`, `tail`, `wc`),
`auto_pre` injection, and STANDARD model tier.

[98-REQ-1.4] THE reviewer's audit-review mode SHALL have an extended analysis
allowlist (including `uv`), `auto_mid` injection, STANDARD model tier, and
`retry_predecessor=True`.

[98-REQ-1.5] THE reviewer's fix-review mode SHALL have an analysis allowlist
(including `uv`, `make`), no injection (manual only), and ADVANCED model tier.

#### Edge Cases

[98-REQ-1.E1] IF a config references the old archetype name `"skeptic"`,
`"oracle"`, `"auditor"`, or `"fix_reviewer"`, THEN THE system SHALL raise a
configuration error with a message explaining the new reviewer mode names.

### Requirement 2: Coder Fix Mode

**User Story:** As the nightshift fix pipeline, I need a coder fix mode that
behaves like the former fix_coder.

#### Acceptance Criteria

[98-REQ-2.1] THE `ARCHETYPE_REGISTRY` coder entry SHALL include a `"fix"` mode
with the same configuration as the former `fix_coder` entry (STANDARD tier,
300 max turns, adaptive thinking with 64k budget, no injection, not
task-assignable via mode).

[98-REQ-2.2] WHEN the engine creates a coder session with `mode="fix"`, THE
system SHALL use the fix mode's template (`fix_coding.md`) instead of the
default coder template.

#### Edge Cases

[98-REQ-2.E1] IF the coder is invoked without a mode (mode=None), THEN THE
system SHALL behave identically to the current coder archetype — no
regression.

### Requirement 3: Template Consolidation

**User Story:** As a developer, I want review templates merged into a single
file so that shared guidance is centralized and mode-specific sections are
clearly delineated.

#### Acceptance Criteria

[98-REQ-3.1] THE system SHALL provide a `reviewer.md` template that contains
shared review identity and rules, plus mode-specific sections for pre-review,
drift-review, audit-review, and fix-review.

[98-REQ-3.2] WHEN building a system prompt for the reviewer archetype with a
specific mode, THE system SHALL load `reviewer.md` AND the prompt SHALL
contain the mode-specific section relevant to the active mode.

[98-REQ-3.3] THE system SHALL retain `fix_coding.md` as a separate template
file referenced by the coder's fix mode.

### Requirement 4: Injection Update

**User Story:** As the graph builder, I need injection logic to create
reviewer-mode nodes instead of separate archetype nodes.

#### Acceptance Criteria

[98-REQ-4.1] WHEN `collect_enabled_auto_pre()` is called, THE system SHALL
return reviewer entries with modes `"pre-review"` and `"drift-review"` instead
of separate skeptic and oracle entries AND return the mode alongside the
archetype name.

[98-REQ-4.2] WHEN `ensure_graph_archetypes()` injects auto_pre nodes, THE
system SHALL create `Node(archetype="reviewer", mode="pre-review")` and
`Node(archetype="reviewer", mode="drift-review")` instead of separate skeptic
and oracle nodes.

[98-REQ-4.3] WHEN `ensure_graph_archetypes()` injects auto_mid nodes, THE
system SHALL create `Node(archetype="reviewer", mode="audit-review")` instead
of auditor nodes.

[98-REQ-4.4] THE oracle gating logic SHALL apply to the drift-review mode:
WHEN a spec has no existing code to validate, THE system SHALL skip
drift-review injection.

[98-REQ-4.5] THE `is_archetype_enabled()` function SHALL check
`archetypes.reviewer` for all reviewer modes AND return the appropriate
mode-specific enable state.

#### Edge Cases

[98-REQ-4.E1] IF `archetypes.reviewer = false` in config, THEN THE system
SHALL skip all reviewer mode injections (pre-review, drift-review,
audit-review).

### Requirement 5: Convergence Dispatch

**User Story:** As the convergence system, I need to dispatch by reviewer
mode rather than archetype name.

#### Acceptance Criteria

[98-REQ-5.1] WHEN convergence is invoked for `archetype="reviewer"`,
`mode="pre-review"`, THE system SHALL use the current skeptic convergence
algorithm (majority-gated blocking).

[98-REQ-5.2] WHEN convergence is invoked for `archetype="reviewer"`,
`mode="drift-review"`, THE system SHALL use the current skeptic convergence
algorithm (same as pre-review).

[98-REQ-5.3] WHEN convergence is invoked for `archetype="reviewer"`,
`mode="audit-review"`, THE system SHALL use the current auditor convergence
algorithm (union/worst-verdict-wins per TS entry).

#### Edge Cases

[98-REQ-5.E1] IF convergence is invoked with an unknown reviewer mode, THEN
THE system SHALL raise a `ValueError` indicating the unknown mode.

### Requirement 6: Verifier Changes

**User Story:** As a project operator, I want the verifier to default to
STANDARD tier and single-instance to reduce cost without sacrificing
correctness.

#### Acceptance Criteria

[98-REQ-6.1] THE verifier archetype's `default_model_tier` SHALL be
`"STANDARD"`.

[98-REQ-6.2] THE `ArchetypeInstancesConfig` SHALL default verifier instances
to 1 AND clamp the maximum to 1.

[98-REQ-6.3] THE verifier SHALL retain `retry_predecessor=True` and
escalation ladder support for model tier escalation on retry.

### Requirement 7: Registry Cleanup

**User Story:** As a developer, I want the old archetype entries removed so
that there is a single source of truth.

#### Acceptance Criteria

[98-REQ-7.1] THE `ARCHETYPE_REGISTRY` SHALL NOT contain entries for
`"skeptic"`, `"oracle"`, `"auditor"`, `"fix_reviewer"`, or `"fix_coder"`.

[98-REQ-7.2] WHEN `get_archetype()` is called with a removed name, THE system
SHALL log a warning and fall back to the `"coder"` entry (existing behavior).

### Requirement 8: Config Schema Update

**User Story:** As a project maintainer, I want config keys to reflect the
consolidated archetypes so that configuration is coherent.

#### Acceptance Criteria

[98-REQ-8.1] THE `ArchetypesConfig` SHALL replace the boolean toggles
`skeptic`, `oracle`, `auditor` with a single `reviewer` boolean toggle
(default `True`).

[98-REQ-8.2] THE `ArchetypesConfig` SHALL replace `skeptic_config`,
`oracle_settings`, and `auditor_config` with a single `reviewer_config`
containing mode-specific settings (block thresholds, min_ts_entries,
max_retries) AND return these settings keyed by mode name.

[98-REQ-8.3] THE `ArchetypeInstancesConfig` SHALL replace `skeptic`,
`verifier`, `auditor` fields with `reviewer` (default 1) and `verifier`
(default 1, max 1).

#### Edge Cases

[98-REQ-8.E1] IF config contains the old key `archetypes.skeptic`, THEN THE
system SHALL raise a validation error with migration guidance.
