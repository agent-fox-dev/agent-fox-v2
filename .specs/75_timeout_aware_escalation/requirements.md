# Requirements Document

## Introduction

This specification adds timeout-aware handling to the escalation ladder.
Instead of escalating to a more expensive model tier when a session times out,
the system retries at the same tier with extended time and turn limits. Timeout
retries use a separate counter from the escalation ladder's failure retries.

## Glossary

- **Timeout**: A session that exceeds `session_timeout` minutes, caught as
  `TimeoutError` by `asyncio.wait_for()`. Session status is `"timeout"`.
- **Escalation ladder**: The retry/escalation state machine in
  `EscalationLadder` that tracks failures and escalates model tiers.
- **Timeout retry**: A retry triggered by timeout, using the same model tier
  with increased `max_turns` and `session_timeout`. Tracked separately from
  escalation ladder failures.
- **Logical failure**: A session failure that is NOT a timeout (status
  `"failed"`, error message, SDK error, etc.).
- **max_turns**: Maximum number of conversation turns the agent may take.
- **session_timeout**: Maximum wall-clock time in minutes before a session
  is killed.
- **Timeout multiplier**: Factor by which max_turns and session_timeout are
  increased on each timeout retry. Default 1.5.
- **Timeout ceiling**: Maximum session_timeout as a factor of the original
  configured value. Default 2.0x.

## Requirements

### Requirement 1: Timeout Detection in Result Handler

**User Story:** As a system operator, I want timeout failures to be handled
differently from logical failures, so that the system doesn't waste budget
on model escalation when more time is what's needed.

#### Acceptance Criteria

[75-REQ-1.1] WHEN a session completes with status `"timeout"`, THE result
handler SHALL route the failure to timeout-specific retry logic instead of
the escalation ladder's `record_failure()`.

[75-REQ-1.2] WHEN a session completes with a non-timeout failure status
(e.g., `"failed"`), THE result handler SHALL continue to use the escalation
ladder as before.

[75-REQ-1.3] THE result handler SHALL distinguish timeout from logical
failure by checking `record.status == "timeout"`.

#### Edge Cases

[75-REQ-1.E1] IF a session fails with status `"failed"` AND the error
message contains the word "timeout", THE system SHALL still treat it as a
logical failure (only status `"timeout"` triggers timeout handling).

### Requirement 2: Timeout Retry Counter

**User Story:** As a system operator, I want timeout retries tracked
separately from escalation retries, so that timeouts don't consume the
failure retry budget.

#### Acceptance Criteria

[75-REQ-2.1] THE system SHALL maintain a per-node timeout retry counter
that is separate from the escalation ladder's failure counter.

[75-REQ-2.2] WHEN a timeout occurs, THE system SHALL increment the timeout
retry counter for that node without affecting the escalation ladder state.

[75-REQ-2.3] WHEN the timeout retry counter is below `max_timeout_retries`,
THE system SHALL retry at the same model tier with extended parameters.

[75-REQ-2.4] WHEN the timeout retry counter reaches `max_timeout_retries`,
THE system SHALL fall through to the escalation ladder and call
`record_failure()`.

#### Edge Cases

[75-REQ-2.E1] IF a node experiences a mix of timeouts and logical failures,
THE timeout retry counter and escalation ladder failure counter SHALL be
independent — consuming one SHALL NOT affect the other.

[75-REQ-2.E2] IF `max_timeout_retries` is configured as 0, THE system SHALL
skip timeout-specific handling entirely and fall through to the escalation
ladder immediately on timeout.

### Requirement 3: Extended Parameters on Timeout Retry

**User Story:** As a system operator, I want timed-out sessions to retry
with more time and turns, so that tasks that need more compute can complete.

#### Acceptance Criteria

[75-REQ-3.1] WHEN retrying after a timeout, THE system SHALL increase the
node's effective `max_turns` by `timeout_multiplier` (default 1.5), rounded
up to the nearest integer.

[75-REQ-3.2] WHEN retrying after a timeout, THE system SHALL increase the
node's effective `session_timeout` by `timeout_multiplier` (default 1.5),
rounded up to the nearest integer.

[75-REQ-3.3] THE extended `session_timeout` SHALL NOT exceed
`timeout_ceiling_factor` (default 2.0) times the original configured
`session_timeout`.

[75-REQ-3.4] WHEN `max_turns` is None (unlimited), THE system SHALL NOT
apply the timeout multiplier to max_turns — only session_timeout SHALL be
extended.

[75-REQ-3.5] THE extended parameters SHALL be applied per-node — other
nodes' parameters SHALL NOT be affected.

#### Edge Cases

[75-REQ-3.E1] IF the extended `session_timeout` would exceed the ceiling,
THEN THE system SHALL clamp it to the ceiling value.

[75-REQ-3.E2] IF `max_turns` is already at its maximum practical value,
THEN THE system SHALL apply the multiplier without special casing (the
backend handles any SDK limits).

### Requirement 4: Configuration

**User Story:** As a system operator, I want to configure timeout retry
behavior, so that I can tune it for my workload.

#### Acceptance Criteria

[75-REQ-4.1] THE `RoutingConfig` SHALL include a `max_timeout_retries`
field with type `int` and default value `2`.

[75-REQ-4.2] THE `RoutingConfig` SHALL include a `timeout_multiplier`
field with type `float` and default value `1.5`.

[75-REQ-4.3] THE `RoutingConfig` SHALL include a `timeout_ceiling_factor`
field with type `float` and default value `2.0`.

[75-REQ-4.4] THE system SHALL validate that `max_timeout_retries` is >= 0.

[75-REQ-4.5] THE system SHALL validate that `timeout_multiplier` is >= 1.0.

[75-REQ-4.6] THE system SHALL validate that `timeout_ceiling_factor` is
>= 1.0.

#### Edge Cases

[75-REQ-4.E1] IF `timeout_multiplier` equals 1.0, THEN timeout retries
SHALL use the same parameters as the original attempt (no extension).

### Requirement 5: Observability

**User Story:** As a system operator, I want to see when timeout retries
occur and how parameters are extended, so that I can diagnose and tune
timeout behavior.

#### Acceptance Criteria

[75-REQ-5.1] WHEN a timeout retry is initiated, THE system SHALL emit an
audit event of type `SESSION_TIMEOUT_RETRY` with the node_id, retry count,
extended max_turns, and extended session_timeout in the payload.

[75-REQ-5.2] WHEN timeout retries are exhausted and the failure falls through
to the escalation ladder, THE system SHALL log a warning indicating that
timeout retries were exhausted and escalation is being attempted.

[75-REQ-5.3] THE `SESSION_TIMEOUT_RETRY` audit event payload SHALL include
the original and extended values for both max_turns and session_timeout.
