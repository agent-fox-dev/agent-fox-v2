# Requirements Document

## Introduction

The test auditor is a new agent archetype that validates test code written by
the coder against `test_spec.md` contracts. It detects test-writing task groups,
injects itself into the task graph after them, and audits test quality across
five dimensions: coverage, assertion strength, precondition fidelity, edge case
rigor, and independence. On failure, it triggers a retry-predecessor loop with
a circuit breaker. When the circuit breaker trips, the pipeline halts for the
spec and a GitHub issue is filed, signaling that the specification itself may
need human attention.

## Glossary

- **Archetype**: A named agent configuration (prompt template, model tier,
  allowlist, injection mode) registered in the archetype registry.
- **Injection mode**: Determines when an archetype node is automatically
  inserted into the task graph. Existing modes: `auto_pre` (before first
  group), `auto_post` (after last group). This spec adds `auto_mid`.
- **auto_mid**: A new injection mode that inserts a node between a detected
  test-writing group and the next implementation group.
- **Test-writing group**: A task group whose description matches patterns
  indicating it writes tests (e.g., "Write failing spec tests").
- **TS entry**: A test case entry in `test_spec.md`, identified by an ID
  like `TS-05-1`, `TS-05-P1`, or `TS-05-E1`.
- **Convergence**: The process of merging results from multiple parallel
  instances of the same archetype into a single verdict.
- **Circuit breaker**: A configurable limit on auditor-coder retry iterations
  that prevents infinite loops.
- **Retry-predecessor**: A mechanism where a failing archetype node causes
  its predecessor node to be reset and re-executed.
- **Audit verdict**: One of PASS, WEAK, MISSING, or MISALIGNED, assigned
  per TS entry. The overall verdict is PASS or FAIL.

## Requirements

### Requirement 1: Archetype Registry Entry

**User Story:** As a system operator, I want the auditor to be a registered
archetype so that it integrates with existing archetype infrastructure.

#### Acceptance Criteria

1. [46-REQ-1.1] WHEN the archetype registry is loaded, THE system SHALL
   include an `auditor` entry with `injection="auto_mid"`,
   `retry_predecessor=True`, and `task_assignable=True`.

2. [46-REQ-1.2] THE `auditor` archetype entry SHALL specify a default model
   tier of `STANDARD`.

3. [46-REQ-1.3] THE `auditor` archetype entry SHALL specify a default
   allowlist containing `ls`, `cat`, `git`, `grep`, `find`, `head`, `tail`,
   `wc`, and `uv`.

4. [46-REQ-1.4] THE `auditor` archetype entry SHALL reference a template
   file `auditor.md`.

#### Edge Cases

1. [46-REQ-1.E1] IF `get_archetype("auditor")` is called, THEN THE system
   SHALL return the auditor entry (not fall back to coder).

### Requirement 2: Configuration

**User Story:** As a system operator, I want to configure the auditor via
config.toml so that I can enable it, set instance counts, and tune thresholds.

#### Acceptance Criteria

1. [46-REQ-2.1] THE `ArchetypesConfig` model SHALL include an `auditor`
   boolean field defaulting to `False`.

2. [46-REQ-2.2] THE `ArchetypeInstancesConfig` model SHALL include an
   `auditor` integer field defaulting to `1`, clamped to range 1-5.

3. [46-REQ-2.3] THE system SHALL provide an `AuditorConfig` model with
   `min_ts_entries` (integer, default 5, clamped >= 1) and `max_retries`
   (integer, default 2, clamped >= 0).

4. [46-REQ-2.4] THE `ArchetypesConfig` model SHALL include an
   `auditor_config` field of type `AuditorConfig`.

#### Edge Cases

1. [46-REQ-2.E1] IF the `[archetypes]` section omits `auditor`, THEN THE
   system SHALL default to `auditor=False` with no behavioral change.

2. [46-REQ-2.E2] IF `auditor_config.max_retries` is set to `0`, THEN THE
   system SHALL run the auditor once with no retry loop.

### Requirement 3: Test-Writing Group Detection

**User Story:** As a system operator, I want the auditor to automatically
detect test-writing groups so that injection does not depend on hardcoded
group numbers.

#### Acceptance Criteria

1. [46-REQ-3.1] WHEN building the task graph, THE system SHALL detect
   test-writing groups by matching the group title against a set of
   case-insensitive patterns including: "write failing spec tests",
   "write failing tests", "create unit test", "create test file",
   "spec tests".

2. [46-REQ-3.2] THE detection function SHALL accept a group title string
   and return a boolean indicating whether it is a test-writing group.

3. [46-REQ-3.3] WHEN multiple groups in a spec match the test-writing
   pattern, THE system SHALL inject an auditor node after each matching
   group.

#### Edge Cases

1. [46-REQ-3.E1] IF no group in a spec matches the test-writing pattern,
   THEN THE system SHALL not inject any auditor node for that spec.

2. [46-REQ-3.E2] IF a group title contains a test-writing pattern as a
   substring (e.g., "Write failing spec tests for module X"), THEN THE
   system SHALL detect it as a test-writing group.

### Requirement 4: Auto-Mid Injection

**User Story:** As a system operator, I want the auditor to be automatically
inserted into the task graph between test-writing and implementation groups.

#### Acceptance Criteria

1. [46-REQ-4.1] WHEN the auditor archetype is enabled and a test-writing
   group is detected, THE system SHALL inject an auditor node into the
   task graph with edges: `test_group -> auditor -> next_group`.

2. [46-REQ-4.2] THE injected auditor node SHALL have its `instances` field
   set from `archetypes_config.instances.auditor`.

3. [46-REQ-4.3] THE injected auditor node SHALL have its `archetype` field
   set to `"auditor"`.

4. [46-REQ-4.4] WHEN the spec has fewer than `auditor_config.min_ts_entries`
   test spec entries, THE system SHALL skip auditor injection and log an
   INFO message.

#### Edge Cases

1. [46-REQ-4.E1] IF the auditor archetype is disabled in config, THEN THE
   system SHALL not inject any auditor nodes regardless of group detection.

2. [46-REQ-4.E2] IF the test-writing group is the last group in the spec,
   THEN THE system SHALL inject the auditor node after it with no successor
   edge.

3. [46-REQ-4.E3] IF both auto_pre (skeptic) and auto_mid (auditor) are
   enabled, THEN THE system SHALL inject both without conflict: skeptic
   at group 0, auditor between the test-writing group and the next group.

### Requirement 5: Auditor Prompt Template

**User Story:** As a system operator, I want the auditor to use a dedicated
prompt template that instructs it to audit test quality.

#### Acceptance Criteria

1. [46-REQ-5.1] THE system SHALL include an `auditor.md` prompt template
   in `agent_fox/_templates/prompts/`.

2. [46-REQ-5.2] THE `auditor.md` template SHALL instruct the agent to
   evaluate each TS entry across five dimensions: coverage, assertion
   strength, precondition fidelity, edge case rigor, and independence.

3. [46-REQ-5.3] THE `auditor.md` template SHALL specify the structured
   JSON output format with per-TS-entry verdicts (PASS, WEAK, MISSING,
   MISALIGNED) and an overall verdict (PASS, FAIL).

4. [46-REQ-5.4] THE `auditor.md` template SHALL define FAIL criteria:
   any MISSING entry, any MISALIGNED entry, or 2+ WEAK entries.

5. [46-REQ-5.5] THE `auditor.md` template SHALL include `{spec_name}`
   and `{task_group}` template variables.

#### Edge Cases

1. [46-REQ-5.E1] IF the `auditor.md` template file is missing, THEN THE
   system SHALL raise an error during prompt construction (existing
   behavior from spec 26).

### Requirement 6: Convergence

**User Story:** As a system operator, I want multi-instance auditor results
to be merged conservatively so that weak tests are not missed.

#### Acceptance Criteria

1. [46-REQ-6.1] WHEN multiple auditor instances produce results, THE system
   SHALL merge them using union semantics: a TS entry is flagged if ANY
   instance flags it.

2. [46-REQ-6.2] THE convergence function SHALL accept a list of per-instance
   audit results and return a single merged audit result.

3. [46-REQ-6.3] THE merged overall verdict SHALL be FAIL if any instance's
   overall verdict is FAIL.

4. [46-REQ-6.4] THE convergence function SHALL not use LLM calls.

#### Edge Cases

1. [46-REQ-6.E1] IF only one auditor instance runs, THEN THE system SHALL
   return its result directly without convergence processing.

2. [46-REQ-6.E2] IF all auditor instances fail (no results), THEN THE
   system SHALL treat the audit as PASS with a warning log and proceed.

### Requirement 7: Retry Loop and Circuit Breaker

**User Story:** As a system operator, I want the auditor to retry the
test-writing coder when tests are inadequate, with a circuit breaker to
prevent infinite loops.

#### Acceptance Criteria

1. [46-REQ-7.1] WHEN the auditor overall verdict is FAIL, THE system SHALL
   reset the predecessor test-writing coder node to `pending` with the
   auditor findings as error context.

2. [46-REQ-7.2] AFTER the coder retries, THE system SHALL re-run the
   auditor on the revised tests.

3. [46-REQ-7.3] THE system SHALL track the number of auditor-coder retry
   iterations per auditor node.

4. [46-REQ-7.4] WHEN the retry count reaches `auditor_config.max_retries`,
   THE system SHALL stop retrying, mark the auditor node as `blocked`,
   and log a WARNING indicating the circuit breaker has tripped.

5. [46-REQ-7.5] WHEN the circuit breaker trips, THE system SHALL prevent
   all downstream nodes (implementation groups) of the blocked auditor
   node from executing.

6. [46-REQ-7.6] WHEN the circuit breaker trips, THE system SHALL file a
   GitHub issue with title `[Auditor] {spec_name}: circuit breaker tripped`
   using the search-before-create pattern, including the retry count and
   last audit findings in the issue body.

#### Edge Cases

1. [46-REQ-7.E1] IF `auditor_config.max_retries` is `0`, THEN THE system
   SHALL run the auditor once; IF the verdict is FAIL, THEN THE system
   SHALL mark the auditor node as `blocked` and file a GitHub issue.

2. [46-REQ-7.E2] IF the auditor verdict is PASS on the first run, THEN
   THE system SHALL not trigger any retry.

### Requirement 8: Output Persistence and GitHub Issues

**User Story:** As a system operator, I want the auditor to persist its
findings and file GitHub issues so that audit results are visible.

#### Acceptance Criteria

1. [46-REQ-8.1] WHEN the auditor completes, THE system SHALL write its
   findings to `.specs/{spec_name}/audit.md`.

2. [46-REQ-8.2] WHEN the auditor verdict is FAIL, THE system SHALL file
   a GitHub issue with title `[Auditor] {spec_name}: FAIL` using the
   search-before-create pattern.

3. [46-REQ-8.3] WHEN the auditor verdict is PASS and an existing auditor
   issue is found, THE system SHALL close the issue.

4. [46-REQ-8.4] WHEN the auditor triggers a coder retry, THE system SHALL
   emit an audit event of type `auditor.retry` with the spec name, group
   number, and attempt number.

#### Edge Cases

1. [46-REQ-8.E1] IF `gh` CLI is unavailable, THEN THE system SHALL log
   the failure and not block execution.

2. [46-REQ-8.E2] IF writing `audit.md` fails due to filesystem error,
   THEN THE system SHALL log the error and not block execution.
