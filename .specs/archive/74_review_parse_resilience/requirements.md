# Requirements Document

## Introduction

This specification addresses the 57% parse failure rate observed across review
archetype sessions (skeptic, verifier, auditor, oracle). Two complementary
strategies are applied: stricter prompt instructions to reduce output format
variance, and a more tolerant parser with a single-retry fallback to recover
from remaining failures. Multi-instance convergence is updated to handle
partial parse results.

## Glossary

- **Review archetype**: An agent archetype whose output is structured JSON
  ingested by the harvester. Includes skeptic, verifier, auditor, and oracle.
- **Harvester**: The post-session pipeline that extracts structured findings
  from review archetype output text (`persist_review_findings()`).
- **Parse failure**: The harvester's inability to extract valid structured
  findings from a review session's output. Emits `REVIEW_PARSE_FAILURE`.
- **Wrapper key**: The JSON object key that wraps an array of findings
  (e.g., `"findings"`, `"verdicts"`, `"drift_findings"`, `"audit"`).
- **Fuzzy field matching**: Accepting common variants of expected field names
  (e.g., `"finding"` for `"findings"`).
- **Format retry**: Re-prompting the agent within the same session when
  parsing fails, requesting corrected JSON output.
- **Convergence**: Post-processing that merges results from multi-instance
  archetype runs (union, majority vote, worst-verdict).

## Requirements

### Requirement 1: Stricter Prompt Format Instructions

**User Story:** As a system operator, I want review archetypes to produce
consistently parseable JSON, so that blocking and retry mechanisms work
reliably.

#### Acceptance Criteria

[74-REQ-1.1] THE skeptic prompt template SHALL include an instruction stating
that the JSON block must be output without surrounding prose, markdown fences,
or commentary.

[74-REQ-1.2] THE verifier prompt template SHALL include an instruction stating
that the JSON block must be output without surrounding prose, markdown fences,
or commentary.

[74-REQ-1.3] THE auditor prompt template SHALL include an instruction stating
that the JSON block must be output without surrounding prose, markdown fences,
or commentary.

[74-REQ-1.4] THE oracle prompt template SHALL include an instruction stating
that the JSON block must be output without surrounding prose, markdown fences,
or commentary.

[74-REQ-1.5] WHEN a review archetype template specifies an output schema,
THE template SHALL repeat the critical format constraints (bare JSON, exact
field names) in a final "CRITICAL REMINDERS" section at the end of the prompt.

[74-REQ-1.6] THE review archetype templates SHALL include a negative example
showing a common formatting mistake (e.g., JSON wrapped in markdown fences
with prose) and explicitly labeling it as incorrect.

#### Edge Cases

[74-REQ-1.E1] IF the review archetype template already contains format
instructions, THEN THE system SHALL replace them with the stricter version
rather than duplicating instructions.

### Requirement 2: Tolerant JSON Extraction

**User Story:** As a system operator, I want the harvester to extract valid
findings even when the JSON output has minor format deviations, so that
fewer sessions result in parse failures.

#### Acceptance Criteria

[74-REQ-2.1] WHEN extracting JSON from review output, THE `_unwrap_items()`
function SHALL accept case-insensitive wrapper keys (e.g., `"Findings"` and
`"FINDINGS"` treated as `"findings"`).

[74-REQ-2.2] WHEN extracting JSON from review output, THE `_unwrap_items()`
function SHALL accept common singular/plural variants of wrapper keys (e.g.,
`"finding"` for `"findings"`, `"verdict"` for `"verdicts"`,
`"drift_finding"` for `"drift_findings"`).

[74-REQ-2.3] WHEN a JSON object contains a key matching a known wrapper key
variant, THE system SHALL extract the array value even if the key does not
exactly match the canonical wrapper key.

[74-REQ-2.4] WHEN individual finding objects contain keys with non-standard
casing (e.g., `"Severity"`, `"DESCRIPTION"`), THE field-level parsers SHALL
normalize keys to lowercase before validation.

[74-REQ-2.5] WHEN a JSON block is wrapped in markdown fences AND contains
additional prose outside the fences, THE `extract_json_array()` function
SHALL extract the JSON from within the fences (this is existing behavior
that must be preserved).

#### Edge Cases

[74-REQ-2.E1] IF the extracted JSON contains no recognizable wrapper key
AND is not a bare array, THEN THE system SHALL attempt to treat the entire
object as a single finding/verdict if it contains the required fields.

[74-REQ-2.E2] IF multiple JSON blocks are found in the output, THEN THE
system SHALL merge findings from all valid blocks rather than using only the
first.

### Requirement 3: Format Retry on Parse Failure

**User Story:** As a system operator, I want the system to re-prompt a
review agent when its output can't be parsed, so that transient format
issues don't cause permanent data loss.

#### Acceptance Criteria

[74-REQ-3.1] WHEN all extraction strategies fail for a review archetype
session, THE system SHALL re-prompt the agent with a short message requesting
the structured JSON output in the correct format.

[74-REQ-3.2] THE format retry message SHALL include the expected JSON schema
and a statement that the previous output could not be parsed.

[74-REQ-3.3] THE system SHALL attempt at most 1 format retry per review
session.

[74-REQ-3.4] WHEN the format retry produces parseable output, THE system
SHALL use those findings and SHALL NOT emit a `REVIEW_PARSE_FAILURE` event.

[74-REQ-3.5] THE format retry SHALL reuse the existing session (append a
user message) rather than creating a new session.

#### Edge Cases

[74-REQ-3.E1] IF the format retry also fails to produce parseable output,
THEN THE system SHALL emit a `REVIEW_PARSE_FAILURE` event and continue
without findings, as it does today.

[74-REQ-3.E2] IF the session has already been terminated (e.g., timeout or
backend error), THEN THE system SHALL NOT attempt a format retry.

### Requirement 4: Convergence with Partial Results

**User Story:** As a system operator, I want multi-instance convergence to
use whatever parseable results are available, rather than failing entirely
when some instances can't be parsed.

#### Acceptance Criteria

[74-REQ-4.1] WHEN running multi-instance skeptic sessions, THE convergence
logic SHALL proceed with findings from instances that produced parseable
output, excluding instances that failed parsing.

[74-REQ-4.2] WHEN running multi-instance verifier sessions, THE convergence
logic SHALL proceed with verdicts from instances that produced parseable
output, excluding instances that failed parsing.

[74-REQ-4.3] WHEN running multi-instance auditor sessions, THE convergence
logic SHALL proceed with audit results from instances that produced parseable
output, excluding instances that failed parsing.

[74-REQ-4.4] WHEN at least one instance produces parseable output, THE
system SHALL NOT emit a `REVIEW_PARSE_FAILURE` event for the overall
convergence.

[74-REQ-4.5] WHEN some instances fail parsing, THE system SHALL log a
warning identifying which instances failed.

#### Edge Cases

[74-REQ-4.E1] IF ALL instances fail parsing, THEN THE system SHALL emit a
`REVIEW_PARSE_FAILURE` event and return empty results.

[74-REQ-4.E2] IF only a single instance is configured (instances = 1),
THEN partial-result handling SHALL NOT apply — the single instance's parse
result (or failure) is used directly.

### Requirement 5: Observability

**User Story:** As a system operator, I want to measure the impact of parse
resilience improvements, so that I can verify the parse failure rate has
decreased.

#### Acceptance Criteria

[74-REQ-5.1] WHEN a format retry succeeds, THE system SHALL emit an audit
event of type `REVIEW_PARSE_RETRY_SUCCESS` with the archetype and node_id.

[74-REQ-5.2] WHEN a format retry fails, THE system SHALL emit the existing
`REVIEW_PARSE_FAILURE` event with an additional `retry_attempted: true`
field in the payload.

[74-REQ-5.3] THE `REVIEW_PARSE_FAILURE` payload SHALL include a `strategy`
field indicating which extraction strategies were attempted (e.g.,
`"bracket_scan,fence,retry"`).
