# Requirements Document

## Introduction

This specification defines prompt caching behavior for agent-fox's auxiliary
API calls to Anthropic's Messages API. A configurable cache policy controls
whether and how `cache_control` markers are injected into API requests,
reducing input token costs on cache hits.

## Glossary

- **Cache policy**: One of NONE, DEFAULT, or EXTENDED — controls whether
  `cache_control` is added to API requests and with which TTL.
- **TTL**: Time-to-live for cached content on Anthropic's servers (5 minutes
  for DEFAULT, 1 hour for EXTENDED).
- **Auxiliary call**: A direct `client.messages.create()` invocation outside
  the main Agent SDK session path.
- **Cache control marker**: A `cache_control` dict (e.g.,
  `{"type": "ephemeral"}`) attached to a content block or system prompt block
  in an Anthropic Messages API request.
- **Token threshold**: The minimum number of tokens required by Anthropic for
  prompt caching to take effect (model-dependent).
- **Cached message helper**: The shared function in `core/client.py` that
  wraps `messages.create()` and injects cache control markers.

## Requirements

### Requirement 1: Cache Policy Configuration

**User Story:** As an operator, I want to configure the prompt caching
strategy in `config.toml`, so that I can control cost/latency trade-offs.

#### Acceptance Criteria

1. [77-REQ-1.1] THE system SHALL support a `cache_policy` field in the
   `[caching]` section of `config.toml` accepting values `"NONE"`,
   `"DEFAULT"`, and `"EXTENDED"` (case-insensitive).

2. [77-REQ-1.2] WHEN no `[caching]` section is present in `config.toml`,
   THE system SHALL default `cache_policy` to `"DEFAULT"`.

3. [77-REQ-1.3] WHEN `cache_policy` is `"NONE"`, THE system SHALL not
   add any `cache_control` markers to API requests.

4. [77-REQ-1.4] WHEN `cache_policy` is `"DEFAULT"`, THE system SHALL use
   `cache_control` with `{"type": "ephemeral"}` (5-minute TTL).

5. [77-REQ-1.5] WHEN `cache_policy` is `"EXTENDED"`, THE system SHALL use
   `cache_control` with `{"type": "ephemeral", "ttl": "1h"}` (1-hour TTL).

#### Edge Cases

1. [77-REQ-1.E1] IF `cache_policy` contains an unrecognized value, THEN
   THE system SHALL raise a validation error at config load time.

### Requirement 2: Cached Message Helper

**User Story:** As a developer, I want a single helper function that adds
caching to API calls, so that caching logic is not duplicated across modules.

#### Acceptance Criteria

1. [77-REQ-2.1] THE system SHALL provide a helper function in
   `core/client.py` that accepts the same parameters as
   `client.messages.create()` plus a `cache_policy` parameter.

2. [77-REQ-2.2] WHEN the helper is called with a `system` parameter, THE
   system SHALL attach the active `cache_control` marker to the last block
   of the system prompt.

3. [77-REQ-2.3] WHEN the helper is called without a `system` parameter, THE
   system SHALL not add any `cache_control` markers.

4. [77-REQ-2.4] WHEN `cache_policy` is `NONE`, THE system SHALL pass the
   request through to `client.messages.create()` without modification.

#### Edge Cases

1. [77-REQ-2.E1] IF the `system` parameter is a plain string, THEN THE
   system SHALL convert it to a single-element content-block list before
   attaching `cache_control`.

2. [77-REQ-2.E2] IF the API returns an error related to `cache_control`,
   THEN THE system SHALL log a warning and retry the request without
   `cache_control`.

### Requirement 3: Auxiliary Call Migration

**User Story:** As a developer, I want all auxiliary API calls to use the
cached message helper, so that caching is applied consistently.

#### Acceptance Criteria

1. [77-REQ-3.1] WHEN any auxiliary module makes an API call, THE system
   SHALL route it through the cached message helper.

2. [77-REQ-3.2] THE system SHALL migrate all 10 call sites across the 9
   auxiliary modules to use the cached message helper.

3. [77-REQ-3.3] WHEN an auxiliary module does not currently use a `system`
   parameter, THE system SHALL refactor the call to pass stable instruction
   content via the `system` parameter where the instructions are separable
   from the per-call data.

#### Edge Cases

1. [77-REQ-3.E1] IF a module's prompt is entirely dynamic with no stable
   prefix, THEN THE system SHALL still use the helper but caching will
   have no effect (no system block to cache).

### Requirement 4: Token Threshold Awareness

**User Story:** As an operator, I want the system to skip caching on
prompts too small to benefit, so that unnecessary cache-write costs
are avoided.

#### Acceptance Criteria

1. [77-REQ-4.1] THE system SHALL define per-model minimum token thresholds
   for caching (2,048 for Sonnet-class, 4,096 for Opus/Haiku-class).

2. [77-REQ-4.2] WHEN the system prompt content is estimated to be below
   the model's minimum token threshold, THE system SHALL skip adding
   `cache_control` markers.

3. [77-REQ-4.3] THE system SHALL estimate token count using a simple
   heuristic (characters ÷ 4) rather than calling a tokenizer.

#### Edge Cases

1. [77-REQ-4.E1] IF the model is not recognized in the threshold table,
   THEN THE system SHALL default to the highest threshold (4,096 tokens)
   and log a debug message.

### Requirement 5: Behavioral Compatibility

**User Story:** As an operator, I want existing behavior and cost tracking
to remain unchanged when caching is disabled.

#### Acceptance Criteria

1. [77-REQ-5.1] WHEN `cache_policy` is `NONE`, THE system SHALL produce
   identical API requests to the current (pre-change) behavior.

2. [77-REQ-5.2] THE system SHALL not alter the existing cache token
   tracking or cost calculation logic in `core/models.py`.
