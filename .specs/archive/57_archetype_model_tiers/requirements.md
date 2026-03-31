# Requirements Document

## Introduction

This specification changes the default model tier assignments for agent
archetypes and fixes the escalation ladder's tier ceiling so that all
archetypes can escalate on retry. Review-oriented archetypes (Skeptic, Oracle,
Verifier) move to `ADVANCED` while execution-oriented archetypes (Coder and
others) move to or remain at `STANDARD`.

## Glossary

- **Model Tier**: One of `SIMPLE`, `STANDARD`, or `ADVANCED`, mapping to
  Claude Haiku, Sonnet, and Opus respectively.
- **Archetype**: A named agent role (Coder, Skeptic, Oracle, Verifier, Auditor,
  Librarian, Cartographer, Coordinator) with a specific prompt template, model
  tier default, and behavioral flags.
- **Tier Ceiling**: The maximum model tier an archetype can escalate to during
  retry. Currently derived from `default_model_tier`; this spec changes it to
  always be `ADVANCED`.
- **Escalation Ladder**: The mechanism that retries a failed task N times at the
  current tier, then promotes to the next higher tier, up to the ceiling.
- **Config Override**: A per-archetype model tier setting in `config.toml`
  (`archetypes.models`) that takes precedence over the registry default.

## Requirements

### Requirement 1: Registry Default Tier Changes

**User Story:** As a project operator, I want review archetypes to use the most
capable model by default, so that code reviews and verification are thorough
without manual configuration.

#### Acceptance Criteria

1. [57-REQ-1.1] THE archetype registry SHALL assign `default_model_tier = "ADVANCED"` to the Skeptic archetype.
2. [57-REQ-1.2] THE archetype registry SHALL assign `default_model_tier = "ADVANCED"` to the Oracle archetype.
3. [57-REQ-1.3] THE archetype registry SHALL assign `default_model_tier = "ADVANCED"` to the Verifier archetype.
4. [57-REQ-1.4] THE archetype registry SHALL assign `default_model_tier = "STANDARD"` to the Coder archetype.
5. [57-REQ-1.5] THE archetype registry SHALL assign `default_model_tier = "STANDARD"` to the Auditor, Librarian, Cartographer, and Coordinator archetypes.

#### Edge Cases

1. [57-REQ-1.E1] IF an archetype name is not found in the registry, THEN THE system SHALL fall back to the Coder entry (existing behavior, unchanged).

### Requirement 2: Tier Ceiling Always ADVANCED

**User Story:** As a project operator, I want any archetype to be able to
escalate to the most capable model on retry failures, so that difficult tasks
are not permanently blocked when a cheaper model fails.

#### Acceptance Criteria

1. [57-REQ-2.1] WHEN the orchestrator creates an escalation ladder for a node, THE system SHALL set the tier ceiling to `ADVANCED` regardless of the archetype's default model tier.
2. [57-REQ-2.2] WHEN a STANDARD-tier archetype exhausts retries at STANDARD, THE system SHALL escalate to ADVANCED before blocking.
3. [57-REQ-2.3] WHEN an ADVANCED-tier archetype exhausts retries at ADVANCED, THE system SHALL block the task (no further escalation possible).

#### Edge Cases

1. [57-REQ-2.E1] IF the assessment pipeline fails, THEN THE system SHALL use the archetype's default model tier as the starting tier and ADVANCED as the ceiling.

### Requirement 3: Config Override Precedence

**User Story:** As a project operator, I want to override model tier defaults
per archetype in config.toml, so that I can tune model selection for my
project's needs.

#### Acceptance Criteria

1. [57-REQ-3.1] WHEN `archetypes.models` contains an entry for an archetype, THE system SHALL use that entry's tier instead of the registry default.
2. [57-REQ-3.2] WHEN `archetypes.models` does not contain an entry for an archetype, THE system SHALL use the registry default tier.
3. [57-REQ-3.3] WHEN an assessed tier is provided by adaptive routing, THE system SHALL use the assessed tier instead of both the config override and the registry default.

#### Edge Cases

1. [57-REQ-3.E1] IF the config override specifies an invalid tier name, THEN THE system SHALL raise a ConfigError with the invalid value and valid options.

### Requirement 4: Documentation

**User Story:** As a project operator, I want the new default tiers documented,
so that I understand the model selection behavior without reading source code.

#### Acceptance Criteria

1. [57-REQ-4.1] THE archetypes documentation SHALL list the default model tier for each archetype.
2. [57-REQ-4.2] THE archetypes documentation SHALL describe how to override model tiers via `config.toml`.
3. [57-REQ-4.3] THE archetypes documentation SHALL explain the escalation behavior (retry at current tier, then escalate to ADVANCED).
