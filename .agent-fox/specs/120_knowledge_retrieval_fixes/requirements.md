# Requirements Document

## Introduction

This specification fixes four bugs in the knowledge system's retrieval
pipeline. The write side (storing findings, summaries, verdicts) works
correctly. The read side (serving stored knowledge to downstream sessions)
is broken: session summaries are never retrieved due to a missing `run_id`
wire, pre-review findings bypass the injection tracking system, only coder
sessions produce summaries, and findings orphaned by stalled runs are never
surfaced again.

## Glossary

- **run_id**: A unique identifier generated per engine run (format:
  `YYYYMMDD_HHMMSS_random`). Used to scope summary queries to the current
  run.
- **FoxKnowledgeProvider**: The concrete knowledge provider that retrieves
  review findings, errata, ADRs, verdicts, and session summaries for
  injection into session prompts.
- **Pre-review**: The group 0 skeptic review session that analyzes the spec
  before any code is written. Produces review findings tagged
  `task_group="0"`.
- **Finding injection**: The process of recording which finding/verdict IDs
  were served to a session, enabling supersession on session completion.
- **Cross-run carry-forward**: Surfacing unresolved findings from a prior
  run at the start of a new run.
- **Archetype**: The role of a session: `coder`, `reviewer`, or `verifier`.
- **Supersession**: Marking a finding as replaced by setting its
  `superseded_by` column to the session ID that resolved it.
- **Same-spec summary**: A session summary from a prior task group within
  the same spec, served as `[CONTEXT]` to downstream sessions.
- **Cross-spec summary**: A session summary from a different spec in the
  same run, served as `[CROSS-SPEC]` to downstream sessions.

## Requirements

### Requirement 1: Wire run_id to FoxKnowledgeProvider

**User Story:** As a system operator, I want session summaries to be
retrieved and injected into downstream sessions so that later task groups
have context about what earlier groups built.

#### Acceptance Criteria

[120-REQ-1.1] THE `FoxKnowledgeProvider` class SHALL expose a
`set_run_id(run_id: str)` method that stores the run ID for use in
summary queries.

[120-REQ-1.2] WHEN `set_run_id()` is called with a non-empty string, THE
`FoxKnowledgeProvider` SHALL use that run ID in subsequent calls to
`_query_same_spec_summaries()` and `_query_cross_spec_summaries()`.

[120-REQ-1.3] WHEN the engine generates a run ID via `generate_run_id()`,
THE engine SHALL call `set_run_id()` on the knowledge provider instance
before dispatching any sessions.

[120-REQ-1.4] WHEN `_query_same_spec_summaries()` is called with a valid
`run_id`, THE method SHALL return summaries from prior task groups in the
same spec and run, formatted as `[CONTEXT]` items.

[120-REQ-1.5] WHEN `_query_cross_spec_summaries()` is called with a valid
`run_id`, THE method SHALL return summaries from other specs in the same
run, formatted as `[CROSS-SPEC]` items.

#### Edge Cases

[120-REQ-1.E1] IF `set_run_id()` is never called (e.g., provider used
outside the engine), THEN THE `FoxKnowledgeProvider` SHALL return empty
lists from summary queries without raising an exception.

[120-REQ-1.E2] IF `set_run_id()` is called with an empty string, THEN THE
`FoxKnowledgeProvider` SHALL treat it as unset and return empty lists from
summary queries.

### Requirement 2: Elevate Pre-Review Findings

**User Story:** As a coding agent, I want to see the skeptic pre-review
findings as tracked, actionable items so that I address spec issues before
writing code, and so those findings are properly superseded when I do.

#### Acceptance Criteria

[120-REQ-2.1] WHEN `retrieve()` is called for a session with a non-zero
`task_group`, THE `FoxKnowledgeProvider` SHALL include active group 0
(pre-review) findings in the primary review results alongside same-group
findings.

[120-REQ-2.2] WHEN group 0 findings are included in the primary review
results, THE system SHALL track them in `finding_injections` so they can
be superseded on session completion.

[120-REQ-2.3] WHEN group 0 findings are included in the primary review
results, THE system SHALL exclude them from the cross-group results to
avoid duplication.

[120-REQ-2.4] THE system SHALL sort group 0 findings alongside same-group
findings using the existing severity-then-relevance ordering.

#### Edge Cases

[120-REQ-2.E1] IF there are no active group 0 findings for the spec, THEN
THE system SHALL return only same-group findings (no change in behavior).

[120-REQ-2.E2] IF the session's `task_group` is `"0"` (the pre-review
itself), THEN THE system SHALL NOT include group 0 findings in cross-group
results (prevents self-injection).

### Requirement 3: All-Archetype Summary Storage

**User Story:** As a coding agent, I want to see what reviewers flagged
and what verifiers confirmed so I have full context about the spec's
progress, not just what other coders built.

#### Acceptance Criteria

[120-REQ-3.1] WHEN a reviewer session completes successfully, THE engine
SHALL generate a summary string containing the finding count by severity
and the descriptions of up to 3 top-severity findings, AND pass it in
the session context dict for storage.

[120-REQ-3.2] WHEN a verifier session completes successfully, THE engine
SHALL generate a summary string containing the pass/fail verdict counts
and the requirement IDs of all FAIL verdicts, AND pass it in the session
context dict for storage.

[120-REQ-3.3] WHEN `query_same_spec_summaries()` is called, THE function
SHALL return summaries from all archetypes (coder, reviewer, verifier),
not only coder summaries.

[120-REQ-3.4] THE formatted summary items SHALL include the archetype in
the `[CONTEXT]` prefix so downstream sessions can distinguish coder
summaries from reviewer/verifier summaries.

#### Edge Cases

[120-REQ-3.E1] IF a reviewer session completes with zero findings, THEN
THE engine SHALL generate a summary stating "no findings" rather than
omitting the summary.

[120-REQ-3.E2] IF a verifier session completes with zero verdicts, THEN
THE engine SHALL generate a summary stating "no verdicts" rather than
omitting the summary.

### Requirement 4: Cross-Run Finding Carry-Forward

**User Story:** As a system operator, I want unresolved findings from
stalled or completed prior runs to be surfaced at the start of a new run
so that known issues are not silently forgotten.

#### Acceptance Criteria

[120-REQ-4.1] WHEN a new run starts AND the database contains active
(non-superseded) critical/major review findings from a prior run, THE
engine SHALL query those findings and make them available to sessions
via the knowledge provider.

[120-REQ-4.2] WHEN prior-run findings are served to a session, THE
`FoxKnowledgeProvider` SHALL format them with a `[PRIOR-RUN]` prefix
that includes the source run ID and spec name.

[120-REQ-4.3] THE system SHALL cap prior-run findings at a configurable
limit per spec (default: 5) AND return the highest-severity findings
first.

[120-REQ-4.4] WHEN prior-run findings are served, THE system SHALL NOT
track them in `finding_injections` (they are informational context, not
directives that create supersession obligations).

[120-REQ-4.5] WHEN prior-run FAIL verdicts exist for the same spec, THE
system SHALL include them in the prior-run context alongside findings,
formatted with a `[PRIOR-RUN]` prefix.

#### Edge Cases

[120-REQ-4.E1] IF there are no prior runs in the database, THEN THE
system SHALL return empty prior-run context without error.

[120-REQ-4.E2] IF the prior run's findings have all been superseded
(i.e., a previous run resolved everything), THEN THE system SHALL
return empty prior-run context.

[120-REQ-4.E3] IF the `review_findings` or `verification_results` table
does not exist (fresh database), THEN THE system SHALL handle the missing
table gracefully and return empty prior-run context.
