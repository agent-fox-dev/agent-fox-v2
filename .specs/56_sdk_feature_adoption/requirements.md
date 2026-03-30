# Requirements Document

## Introduction

This specification adds four Claude SDK features to agent-fox's session
execution layer: per-archetype turn limits, per-session budget caps, fallback
model configuration, and extended thinking support. All features are
configurable via `config.toml` with sensible defaults.

## Glossary

- **Turn** — A single request-response cycle between the SDK client and the
  Claude model, including any tool use within that cycle.
- **Budget cap** — A maximum USD spend limit enforced by the SDK during
  session execution via the `max_budget_usd` parameter.
- **Fallback model** — A secondary model ID used by the SDK when the primary
  model is unavailable (rate-limited, capacity issues).
- **Extended thinking** — A Claude SDK feature that allocates a token budget
  for chain-of-thought reasoning before the model produces its response.
  Modes: `enabled` (always think), `adaptive` (model decides), `disabled`.
- **Archetype** — A named agent configuration (coder, oracle, skeptic,
  verifier, auditor, librarian, cartographer, coordinator) with specific
  model tier, tool allowlist, and behavioral template.
- **ClaudeCodeOptions** — The SDK configuration object passed to
  `ClaudeSDKClient` that controls model, permissions, tools, and execution
  parameters.

## Requirements

### Requirement 1: Per-Archetype Turn Limits

**User Story:** As an operator, I want to limit the number of turns per
archetype, so that read-only agents don't run indefinitely.

#### Acceptance Criteria

[56-REQ-1.1] THE system SHALL accept a `max_turns` configuration per
archetype in `config.toml` under `[archetypes.max_turns]`.

[56-REQ-1.2] WHEN a `max_turns` value is configured for an archetype, THE
system SHALL pass it to `ClaudeCodeOptions` when constructing the SDK options.

[56-REQ-1.3] THE system SHALL use the following default `max_turns` values
when no override is configured: coder=200, oracle=50, skeptic=50,
verifier=75, auditor=50, librarian=100, cartographer=100, coordinator=30.

[56-REQ-1.4] WHEN `max_turns` is set to 0, THE system SHALL treat it as
unlimited (no `max_turns` passed to SDK).

#### Edge Cases

[56-REQ-1.E1] IF `max_turns` is negative, THEN THE system SHALL raise a
configuration validation error at startup.

### Requirement 2: Per-Session Budget Cap

**User Story:** As an operator, I want to set a maximum USD spend per session,
so that runaway sessions don't burn excessive tokens.

#### Acceptance Criteria

[56-REQ-2.1] THE system SHALL accept a `max_budget_usd` configuration in
`config.toml` under `[orchestrator]`.

[56-REQ-2.2] WHEN `max_budget_usd` is configured, THE system SHALL pass it
to `ClaudeCodeOptions` when constructing the SDK options.

[56-REQ-2.3] THE system SHALL default `max_budget_usd` to 2.0 (USD) when
no override is configured.

[56-REQ-2.4] THE `max_budget_usd` parameter SHALL be independent of the
post-hoc `calculate_cost()` function — both may coexist.

#### Edge Cases

[56-REQ-2.E1] IF `max_budget_usd` is set to 0, THEN THE system SHALL treat
it as unlimited (no `max_budget_usd` passed to SDK).

[56-REQ-2.E2] IF `max_budget_usd` is negative, THEN THE system SHALL raise
a configuration validation error at startup.

### Requirement 3: Fallback Model

**User Story:** As an operator, I want sessions to degrade to a secondary
model when the primary is unavailable, so that work continues.

#### Acceptance Criteria

[56-REQ-3.1] THE system SHALL accept a `fallback_model` configuration in
`config.toml` under `[models]`.

[56-REQ-3.2] WHEN `fallback_model` is configured, THE system SHALL pass it
to `ClaudeCodeOptions` when constructing the SDK options.

[56-REQ-3.3] THE system SHALL default `fallback_model` to `claude-sonnet-4-6`
when no override is configured.

[56-REQ-3.4] WHEN `fallback_model` is set to an empty string, THE system
SHALL treat it as no fallback (no `fallback_model` passed to SDK).

#### Edge Cases

[56-REQ-3.E1] IF `fallback_model` is set to a model ID not in the model
registry, THEN THE system SHALL log a warning but still pass it to the SDK
(the SDK may know models not in the local registry).

### Requirement 4: Extended Thinking

**User Story:** As an operator, I want to enable extended thinking for complex
coding tasks, so that the model reasons more deeply before acting.

#### Acceptance Criteria

[56-REQ-4.1] THE system SHALL accept a `thinking` configuration per archetype
in `config.toml` under `[archetypes.thinking]`, with fields `mode`
(`enabled`, `adaptive`, `disabled`) and `budget_tokens` (integer).

[56-REQ-4.2] WHEN a thinking configuration is set for an archetype, THE system
SHALL pass the corresponding `thinking` dict to `ClaudeCodeOptions`.

[56-REQ-4.3] THE system SHALL default to `mode=adaptive, budget_tokens=10000`
for the `coder` archetype and `mode=disabled` for all other archetypes when
no override is configured.

[56-REQ-4.4] WHILE extended thinking is enabled, THE system SHALL include
`ThinkingBlock` content in `AssistantMessage` mapping when present in SDK
responses.

#### Edge Cases

[56-REQ-4.E1] IF `mode` is set to an unrecognised value, THEN THE system
SHALL raise a configuration validation error at startup.

[56-REQ-4.E2] IF `budget_tokens` is zero or negative while `mode` is
`enabled`, THEN THE system SHALL raise a configuration validation error
at startup.

### Requirement 5: Configuration Integration

**User Story:** As a developer, I want all new SDK features to be wired
through the existing config model, so that they follow established patterns.

#### Acceptance Criteria

[56-REQ-5.1] THE `AgentFoxConfig` model SHALL include new fields for
`max_turns` (per-archetype dict), `max_budget_usd` (float),
`fallback_model` (string), and `thinking` (per-archetype dict).

[56-REQ-5.2] THE `ClaudeBackend.execute()` method SHALL accept the new
parameters and forward them to `ClaudeCodeOptions`.

[56-REQ-5.3] THE `AgentBackend` protocol SHALL be extended with optional
keyword parameters for `max_turns`, `max_budget_usd`, `fallback_model`,
and `thinking` to maintain protocol alignment.

#### Edge Cases

[56-REQ-5.E1] IF the SDK version does not support a parameter (e.g.,
`thinking`), THEN THE system SHALL catch the resulting `TypeError` and
log a warning, falling back to execution without the unsupported parameter.
