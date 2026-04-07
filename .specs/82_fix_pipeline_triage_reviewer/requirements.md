# Requirements Document

## Introduction

This specification defines two new archetypes — **triage** and
**fix_reviewer** — that replace the skeptic and verifier in the night-shift
fix pipeline. The triage archetype analyzes GitHub issues and produces
structured acceptance criteria; the fix reviewer verifies the coder's
implementation against those criteria and drives retry/escalation on failure.

## Glossary

- **Acceptance criterion (AC)**: A structured test case produced by the triage
  archetype, following the `test_spec.md` format (ID, description,
  preconditions, expected result, assertion).
- **Fix pipeline**: The `FixPipeline.process_issue()` workflow that processes
  `af:fix`-labeled GitHub issues through a sequence of archetype sessions.
- **Triage report**: The triage archetype's output: a JSON object containing a
  summary, affected files, and an array of acceptance criteria.
- **Review report**: The fix reviewer's output: a JSON object containing
  per-criterion PASS/FAIL verdicts and an overall verdict.
- **EscalationLadder**: The existing mechanism (`routing/escalation.py`) that
  tracks consecutive failures and escalates model tier when
  `retries_before_escalation` is exceeded.
- **Archetype registry**: The `ARCHETYPE_REGISTRY` dict in `archetypes.py`
  that maps archetype names to their configuration (template, model tier,
  allowlist, max turns).

## Requirements

### Requirement 1: Triage Archetype Registration

**User Story:** As the fix pipeline, I want a registered triage archetype so
that it can be invoked with proper model tier, allowlist, and prompt template.

#### Acceptance Criteria

1. [82-REQ-1.1] WHEN the archetype registry is loaded, THE system SHALL
   contain an entry named `"triage"` with a dedicated prompt template
   `triage.md`, default model tier `ADVANCED`, and a read-only command
   allowlist matching the skeptic's allowlist.
2. [82-REQ-1.2] WHEN `build_system_prompt()` is called with
   `archetype="triage"`, THE system SHALL load the `triage.md` template and
   interpolate `{spec_name}` with the fix-issue identifier.

### Requirement 2: Triage Output

**User Story:** As the coder and reviewer, I want the triage agent to produce
structured acceptance criteria so that I have concrete targets to implement
and verify against.

#### Acceptance Criteria

1. [82-REQ-2.1] WHEN the triage archetype completes a session, THE system
   SHALL parse its output as a JSON object with wrapper key
   `"acceptance_criteria"` containing an array of criterion objects, and
   return a `TriageResult` to the caller.
2. [82-REQ-2.2] THE system SHALL require each criterion object to contain
   the fields `id` (string, e.g. `"AC-1"`), `description` (string),
   `preconditions` (string), `expected` (string), and `assertion` (string).
3. [82-REQ-2.3] THE system SHALL parse the top-level `summary` field
   (string, root-cause analysis) and `affected_files` field (array of file
   path strings) from the triage JSON output.
4. [82-REQ-2.4] WHEN the triage prompt template instructs the agent, THE
   template SHALL direct the agent to explore the codebase areas relevant to
   the issue and produce acceptance criteria in the `test_spec.md` format.

#### Edge Cases

1. [82-REQ-2.E1] IF the triage output contains no parseable JSON or the
   `acceptance_criteria` array is empty, THEN THE system SHALL return an
   empty `TriageResult` and log a warning.

### Requirement 3: Triage Issue Comment

**User Story:** As a developer monitoring fixes, I want the triage report
posted to the GitHub issue so that I can see what criteria the fix must
satisfy.

#### Acceptance Criteria

1. [82-REQ-3.1] WHEN the triage archetype produces a non-empty result, THE
   fix pipeline SHALL post a markdown-formatted comment to the originating
   GitHub issue containing the summary, affected files, and all acceptance
   criteria rendered in `test_spec.md` format.

#### Edge Cases

1. [82-REQ-3.E1] IF posting the triage comment fails, THEN THE fix pipeline
   SHALL log a warning and continue the pipeline with the triage result
   in memory.

### Requirement 4: Fix Reviewer Archetype Registration

**User Story:** As the fix pipeline, I want a registered fix_reviewer
archetype so that it can verify coder output with proper model tier,
allowlist, and prompt template.

#### Acceptance Criteria

1. [82-REQ-4.1] WHEN the archetype registry is loaded, THE system SHALL
   contain an entry named `"fix_reviewer"` with a dedicated prompt template
   `fix_reviewer.md`, default model tier `ADVANCED`, and a command allowlist
   that includes test-running commands (`uv run pytest`, `uv run ruff check`,
   `make`).
2. [82-REQ-4.2] WHEN `build_system_prompt()` is called with
   `archetype="fix_reviewer"`, THE system SHALL load the `fix_reviewer.md`
   template and interpolate `{spec_name}` with the fix-issue identifier.

### Requirement 5: Fix Reviewer Behavior

**User Story:** As the pipeline, I want the reviewer to verify the coder's
work against the triage criteria and produce a structured PASS/FAIL verdict
so that I can decide whether to retry.

#### Acceptance Criteria

1. [82-REQ-5.1] WHEN the fix reviewer archetype completes a session, THE
   system SHALL parse its output as a JSON object with wrapper key
   `"verdicts"` containing an array of verdict objects, each with
   `criterion_id` (string matching a triage AC id), `verdict` (one of
   `"PASS"`, `"FAIL"`), and `evidence` (string), plus a top-level
   `overall_verdict` (one of `"PASS"`, `"FAIL"`) and `summary` (string),
   and return a `FixReviewResult` to the caller.
2. [82-REQ-5.2] WHEN the fix reviewer runs, THE fix reviewer SHALL run the
   project test suite (`make check`) and include the pass/fail result in its
   evidence.
3. [82-REQ-5.3] THE fix reviewer's system prompt SHALL include the triage
   acceptance criteria so that it can verify each criterion individually.

#### Edge Cases

1. [82-REQ-5.E1] IF no triage criteria are available (empty triage result),
   THEN THE fix reviewer's prompt SHALL instruct it to verify based on the
   issue description alone and produce a single verdict for the overall fix.

### Requirement 6: Fix Reviewer Issue Comment

**User Story:** As a developer monitoring fixes, I want the review report
posted to the GitHub issue so that I can see the verification outcome.

#### Acceptance Criteria

1. [82-REQ-6.1] WHEN the fix reviewer produces a result, THE fix pipeline
   SHALL post a markdown-formatted comment to the originating GitHub issue
   containing the overall verdict, per-criterion verdicts with evidence, and
   the summary.

#### Edge Cases

1. [82-REQ-6.E1] IF posting the review comment fails, THEN THE fix pipeline
   SHALL log a warning and continue.

### Requirement 7: Pipeline Wiring

**User Story:** As the fix pipeline, I want to run triage → coder →
fix_reviewer in sequence with proper data flow between archetypes.

#### Acceptance Criteria

1. [82-REQ-7.1] WHEN `FixPipeline.process_issue()` executes, THE fix
   pipeline SHALL run archetypes in the order `("triage", "coder",
   "fix_reviewer")` instead of the former `("skeptic", "coder", "verifier")`.
2. [82-REQ-7.2] WHEN the coder session is prepared, THE fix pipeline SHALL
   inject the triage acceptance criteria into the coder's system prompt as
   structured context so the coder knows what to implement.
3. [82-REQ-7.3] WHEN the fix reviewer session is prepared, THE fix pipeline
   SHALL inject the triage acceptance criteria into the reviewer's system
   prompt so the reviewer knows what to verify.

#### Edge Cases

1. [82-REQ-7.E1] IF the triage session fails (exception or timeout), THEN
   THE fix pipeline SHALL proceed with the coder using the issue body only
   (no acceptance criteria) and log a warning.

### Requirement 8: Coder Retry and Model Escalation

**User Story:** As the pipeline, I want the coder to be retried with
reviewer feedback on FAIL, escalating the model tier if needed, so that
difficult fixes get the same escalation treatment as spec-based sessions.

#### Acceptance Criteria

1. [82-REQ-8.1] WHEN the fix reviewer's overall verdict is `"FAIL"`, THE
   fix pipeline SHALL retry the coder with the reviewer's per-criterion
   evidence injected into the coder's task prompt as error context.
2. [82-REQ-8.2] THE fix pipeline SHALL instantiate an `EscalationLadder`
   using the orchestrator config values `retries_before_escalation` and
   `max_retries`, and call `record_failure()` on each reviewer FAIL.
3. [82-REQ-8.3] WHEN `EscalationLadder.current_tier` changes after a
   `record_failure()` call, THE fix pipeline SHALL use the new tier's model
   for the next coder session.
4. [82-REQ-8.4] WHEN `EscalationLadder.is_exhausted` is true, THE fix
   pipeline SHALL stop retrying, post a failure comment to the issue, and
   return.

#### Edge Cases

1. [82-REQ-8.E1] THE fix pipeline SHALL NOT retry the triage or fix_reviewer
   sessions — only the coder is subject to retry and escalation.
