# Requirements Document

## Introduction

This specification defines comprehensive token tracking and cost reporting for
agent-fox. Every LLM call — whether through the Claude Code SDK or direct
Anthropic API — must contribute to reported totals. Model pricing is
configurable via `config.toml` with current Claude values as defaults. Reporting
includes per-archetype and per-spec cost breakdowns.

## Glossary

- **Auxiliary LLM call**: A direct `client.messages.create()` call to the
  Anthropic API, outside the Claude Code SDK session flow. Used for memory
  extraction, causal link analysis, spec validation, and other supporting tasks.
- **Token accumulator**: A module-level counter that collects token usage from
  auxiliary LLM calls during an orchestration run.
- **Session tokens**: Input and output tokens reported by the Claude Code SDK's
  `ResultMessage` at the end of a coding/archetype session.
- **ExecutionState**: The persistent state object (`engine/state.py`) tracking
  cumulative token/cost totals and session history.
- **SessionRecord**: A dataclass capturing the outcome of a single session,
  including tokens, cost, status, and (now) archetype.
- **StatusReport**: The data structure rendered by `agent-fox status`.
- **Pricing config**: The `[pricing]` section in `config.toml` defining
  per-model input and output token prices.
- **MODEL_REGISTRY**: The dictionary in `core/models.py` mapping model IDs to
  `ModelEntry` instances (tier, pricing removed → moved to config).

## Requirements

### Requirement 1: Auxiliary Token Accumulation

**User Story:** As a developer, I want all LLM token usage tracked regardless
of call site, so that reported costs reflect actual consumption.

#### Acceptance Criteria

[34-REQ-1.1] THE system SHALL provide a token accumulator that records
`input_tokens`, `output_tokens`, and `model` for each auxiliary LLM call.

[34-REQ-1.2] WHEN an auxiliary LLM call completes, THE system SHALL add the
call's token counts to the accumulator immediately.

[34-REQ-1.3] WHEN a session completes and the orchestrator updates
`ExecutionState`, THE system SHALL include accumulated auxiliary tokens in the
`total_input_tokens` and `total_output_tokens` fields.

[34-REQ-1.4] WHEN a session completes and the orchestrator updates
`ExecutionState`, THE system SHALL include auxiliary token cost in the
`total_cost` field.

[34-REQ-1.5] THE system SHALL instrument all existing auxiliary LLM call sites
to report to the accumulator: memory fact extraction, causal link extraction,
AI spec validation, fix clusterer, routing complexity assessment, and knowledge
query synthesis.

#### Edge Cases

[34-REQ-1.E1] IF an auxiliary LLM call fails before returning a response, THEN
THE system SHALL record zero tokens for that call and not raise an error in
the accumulator.

[34-REQ-1.E2] IF the Anthropic API response lacks `usage` data, THEN THE
system SHALL record zero tokens for that call and log a warning.

### Requirement 2: Configurable Pricing

**User Story:** As a developer, I want to configure model pricing in
`config.toml`, so that cost calculations stay accurate when pricing changes
without code modifications.

#### Acceptance Criteria

[34-REQ-2.1] THE system SHALL support a `[pricing]` section in `config.toml`
with per-model `input_price_per_m` and `output_price_per_m` fields (USD per
million tokens).

[34-REQ-2.2] THE system SHALL provide default pricing values matching current
Claude API rates for all models in `MODEL_REGISTRY`.

[34-REQ-2.3] WHEN `calculate_cost()` is called, THE system SHALL use pricing
from the loaded config rather than hardcoded `ModelEntry` fields.

[34-REQ-2.4] WHEN a model ID used in a session is not found in the pricing
config, THE system SHALL fall back to a zero-cost estimate and log a warning.

#### Edge Cases

[34-REQ-2.E1] IF the `[pricing]` section is absent from `config.toml`, THEN
THE system SHALL use the built-in default prices without error.

[34-REQ-2.E2] IF a pricing value is negative or non-numeric, THEN THE system
SHALL clamp it to zero and log a warning.

### Requirement 3: Per-Archetype Tracking

**User Story:** As a developer, I want to see token usage broken down by
archetype, so that I can understand which agent roles consume the most tokens.

#### Acceptance Criteria

[34-REQ-3.1] THE `SessionRecord` dataclass SHALL include an `archetype` field
of type `str` with default value `"coder"`.

[34-REQ-3.2] WHEN creating a `SessionRecord`, THE system SHALL populate the
`archetype` field with the archetype name used for that session.

[34-REQ-3.3] WHEN `agent-fox status` renders its output, THE system SHALL
include a per-archetype cost breakdown showing total tokens and cost for each
archetype that has recorded sessions.

#### Edge Cases

[34-REQ-3.E1] IF a `SessionRecord` loaded from `state.jsonl` lacks the
`archetype` field (backward compatibility), THEN THE system SHALL default it
to `"coder"`.

### Requirement 4: Per-Spec Cost Aggregation

**User Story:** As a developer, I want to see cost broken down by spec, so
that I can understand which features are most expensive to implement.

#### Acceptance Criteria

[34-REQ-4.1] WHEN `agent-fox status` renders its output, THE system SHALL
include a per-spec cost breakdown showing total tokens and cost for each spec
that has recorded sessions.

[34-REQ-4.2] THE system SHALL derive the spec name from the `node_id` field
of `SessionRecord` by extracting the prefix before the last colon separator.

#### Edge Cases

[34-REQ-4.E1] IF a `node_id` does not contain a colon separator, THEN THE
system SHALL use the full `node_id` as the spec name for aggregation.

### Requirement 5: Pricing Accuracy

**User Story:** As a developer, I want the default pricing to match current
Anthropic rates, so that costs are accurate out of the box.

#### Acceptance Criteria

[34-REQ-5.1] THE system SHALL ship with default pricing matching the current
published Anthropic API rates for claude-haiku-4-5, claude-sonnet-4-6, and
claude-opus-4-6.

[34-REQ-5.2] THE system SHALL remove the `input_price_per_m` and
`output_price_per_m` fields from the `ModelEntry` dataclass, as pricing is
now managed via config.
