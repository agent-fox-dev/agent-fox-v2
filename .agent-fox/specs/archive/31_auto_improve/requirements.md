# Requirements Document: Auto-Improve

## Introduction

This document specifies the auto-improve extension to `agent-fox fix`. When
invoked with `--auto`, the fix command adds a second phase after the existing
repair loop: an iterative improvement cycle that analyzes the entire codebase,
implements improvements, and verifies them using a three-agent pipeline
(analyzer, coder, verifier). It builds on error auto-fix (spec 08) for the
repair phase, session runner (spec 03) for session execution, agent archetypes
(spec 26) for the verifier, fox ball (spec 12) for oracle knowledge enrichment,
and structured review records (spec 27) for prior review context.

## Glossary

| Term | Definition |
|------|-----------|
| Repair phase | Phase 1 of `fix --auto`: the existing fix loop that runs quality checks, clusters failures, and fixes them iteratively until all pass |
| Improve phase | Phase 2 of `fix --auto`: an iterative loop that analyzes, implements, and verifies codebase improvements after all quality checks pass |
| Improvement pass | One complete cycle of Phase 2: analyze, code, verify |
| Analyzer | A STANDARD-tier agent session that audits the codebase and produces a structured improvement plan |
| Improvement plan | The analyzer's structured JSON output: a prioritized list of improvements with tier, impact, confidence, and a diminishing-returns flag |
| Improvement tier | Priority classification for an improvement: quick_win (highest), structural, or design_level (lowest) |
| Diminishing returns | The analyzer's judgment that remaining improvement opportunities are too minor or risky to justify a coding session |
| Rollback | Reverting an improvement pass by removing its git commit via `git reset --hard HEAD~1` |
| Oracle context | Project knowledge retrieved from the knowledge store's vector search and injected into the analyzer's system prompt |
| Improvement validation | The verifier's assessment that changes are genuine improvements: no regressions, code measurably simpler, public APIs preserved |

## Requirements

### Requirement 1: CLI Extension

**User Story:** As a developer, I want a `--auto` flag on `agent-fox fix` that
triggers iterative improvement after all quality checks pass.

#### Acceptance Criteria

1. [31-REQ-1.1] THE `fix` command SHALL accept a `--auto` flag (boolean,
   default false) that enables Phase 2 (improve) after Phase 1 (repair)
   completes with all checks passing.

2. [31-REQ-1.2] THE `fix` command SHALL accept a `--improve-passes` option
   (integer, default 3) that controls the maximum number of improvement passes
   in Phase 2.

3. [31-REQ-1.3] THE `--improve-passes` option SHALL require `--auto` to be
   set. IF `--improve-passes` is provided without `--auto`, THE system SHALL
   report an error and exit with non-zero code.

4. [31-REQ-1.4] WHEN `--auto` is set and Phase 1 terminates with a reason
   other than `ALL_FIXED`, THE system SHALL skip Phase 2 and exit with the
   existing Phase 1 exit code and report.

#### Edge Cases

1. [31-REQ-1.E1] IF `--improve-passes` is set to 0 or a negative number,
   THEN THE system SHALL clamp it to 1 and log a warning.

2. [31-REQ-1.E2] IF `--dry-run` is combined with `--auto`, THEN Phase 2
   SHALL NOT run. THE system SHALL log an info message explaining that
   dry-run mode is incompatible with Phase 2.

---

### Requirement 2: Phase 2 Entry and Gating

**User Story:** As a developer, I want Phase 2 to start only when all quality
checks pass, so improvements are applied to a known-good baseline.

#### Acceptance Criteria

1. [31-REQ-2.1] Phase 2 SHALL begin only when Phase 1 terminates with
   `TerminationReason.ALL_FIXED`.

2. [31-REQ-2.2] BEFORE the first improvement pass, THE system SHALL record
   the current git HEAD as the Phase 2 baseline commit.

3. [31-REQ-2.3] Phase 2 SHALL share the cost budget with Phase 1. The cost
   consumed during Phase 1 SHALL reduce the budget available for Phase 2.
   The shared budget is `config.orchestrator.max_cost`.

---

### Requirement 3: Analyzer Agent

**User Story:** As a developer, I want an automated analysis of my entire
codebase that identifies improvement opportunities prioritized by tier and
confidence.

#### Acceptance Criteria

1. [31-REQ-3.1] THE analyzer SHALL run as a STANDARD-tier agent session that
   audits the entire repository (not scoped to specific files).

2. [31-REQ-3.2] THE analyzer's system prompt SHALL include:
   - The project's coding conventions (from CLAUDE.md, AGENTS.md, or README.md)
   - The project file tree (module boundaries)
   - Oracle context (project knowledge from the knowledge store), if available
   - Skeptic and verifier findings from DuckDB, if any exist
   - The diff of changes made during Phase 1, if any
   - Results from the previous improvement pass (if not the first pass)

3. [31-REQ-3.3] THE analyzer SHALL produce a structured JSON response
   containing:
   - `improvements`: a list of improvement objects, each with `id` (string),
     `tier` (one of `quick_win`, `structural`, `design_level`), `title`
     (string), `description` (string), `files` (list of file paths), `impact`
     (one of `low`, `medium`, `high`), and `confidence` (one of `high`,
     `medium`, `low`)
   - `summary`: a human-readable summary string
   - `diminishing_returns`: a boolean flag

4. [31-REQ-3.4] THE system SHALL filter the analyzer's output to exclude
   improvements with `confidence: "low"` before passing the plan to the coder.

5. [31-REQ-3.5] THE analyzer SHALL order improvements by tier priority:
   `quick_win` first, then `structural`, then `design_level`.

#### Edge Cases

1. [31-REQ-3.E1] IF the analyzer's response is not valid JSON or is missing
   required fields, THEN THE system SHALL treat it as zero improvements found
   and terminate Phase 2.

2. [31-REQ-3.E2] IF the analyzer session fails (timeout, backend error), THEN
   THE system SHALL terminate Phase 2 and report the failure. No rollback is
   needed because no code changes were made in this pass.

---

### Requirement 4: Oracle Context Enrichment

**User Story:** As a developer, I want the analyzer to respect my project's
established patterns and conventions, informed by the knowledge store.

#### Acceptance Criteria

1. [31-REQ-4.1] BEFORE the analyzer runs, THE system SHALL query the oracle
   with the seed question: "What are the established patterns, conventions,
   and architectural decisions in this project?"

2. [31-REQ-4.2] THE system SHALL retrieve the top-k facts (k=10) from the
   knowledge store's vector search and include them in the analyzer's system
   prompt under a `## Project Knowledge` section, with provenance metadata
   (spec name, ADR reference, or commit SHA).

3. [31-REQ-4.3] IF the knowledge store is unavailable (no DuckDB database,
   no embedded facts, embedding API failure), THE analyzer SHALL run without
   the `## Project Knowledge` section. THE system SHALL log an info message
   noting the omission.

#### Edge Cases

1. [31-REQ-4.E1] IF the oracle query returns zero results, THE analyzer
   SHALL run without the `## Project Knowledge` section. This is not an error.

---

### Requirement 5: Coder Agent

**User Story:** As a developer, I want the system to implement the analyzer's
improvement suggestions with minimal, correct changes.

#### Acceptance Criteria

1. [31-REQ-5.1] THE coder SHALL run as an ADVANCED-tier agent session (same
   model tier as repair sessions) that implements improvements from the
   analyzer's filtered plan.

2. [31-REQ-5.2] THE coder's system prompt SHALL include the simplifier
   guardrails:
   - Never refactor test code for DRYness
   - Preserve public APIs
   - Preserve "why" comments
   - Maintain error handling and logging
   - Favor deletion over addition

3. [31-REQ-5.3] THE coder SHALL implement improvements in tier-priority order
   (quick_win first, structural second, design_level third).

4. [31-REQ-5.4] AFTER the coder session completes, THE system SHALL create a
   single git commit on the current branch with the message:
   `refactor: auto-improve pass {N} - {summary}` where N is the pass number
   and summary is derived from the analyzer's summary field.

#### Edge Cases

1. [31-REQ-5.E1] IF the coder session fails (timeout, backend error), THEN
   THE system SHALL terminate Phase 2. IF the coder made partial file changes
   before failing, THE system SHALL discard them via `git checkout -- .`.

---

### Requirement 6: Verifier Agent

**User Story:** As a developer, I want every improvement pass verified for
correctness before it is accepted.

#### Acceptance Criteria

1. [31-REQ-6.1] THE verifier SHALL run as a STANDARD-tier agent session that
   performs two checks:
   - Quality gate check: run all detected quality checks (same detection logic
     as Phase 1). ALL checks must pass.
   - Improvement validation: confirm that changes are genuine improvements (no
     functionality removed, no public API changes, no test coverage reduction,
     code measurably simpler or clearer).

2. [31-REQ-6.2] THE verifier SHALL produce a structured JSON verdict:
   - `quality_gates`: `"PASS"` or `"FAIL"`
   - `improvement_valid`: boolean
   - `verdict`: `"PASS"` or `"FAIL"` (PASS requires both quality_gates PASS
     and improvement_valid true)
   - `evidence`: a human-readable summary string

3. [31-REQ-6.3] THE verifier SHALL use the verifier archetype template
   (spec 26) with an extended prompt that adds improvement validation criteria
   on top of the standard quality gate check.

#### Edge Cases

1. [31-REQ-6.E1] IF the verifier session fails (timeout, backend error), THEN
   THE system SHALL treat it as a FAIL verdict and roll back the pass.

2. [31-REQ-6.E2] IF the verifier's response is not valid JSON or is missing
   required fields, THEN THE system SHALL treat it as a FAIL verdict and roll
   back the pass.

---

### Requirement 7: Rollback

**User Story:** As a developer, I want failed improvement passes rolled back
automatically so my codebase is never left in a worse state.

#### Acceptance Criteria

1. [31-REQ-7.1] WHEN the verifier verdict is FAIL, THE system SHALL roll back
   the improvement pass by running `git reset --hard HEAD~1` to remove the
   coder's commit.

2. [31-REQ-7.2] AFTER a rollback, Phase 2 SHALL terminate. THE system SHALL
   NOT retry a failed improvement pass.

3. [31-REQ-7.3] THE system SHALL log the rollback action, including the commit
   hash that was reverted and the verifier's evidence string.

#### Edge Cases

1. [31-REQ-7.E1] IF the git reset command fails (e.g., not a git repository,
   commit does not exist), THEN THE system SHALL log an error with the git
   output and terminate Phase 2 with exit code 1.

---

### Requirement 8: Termination and Convergence

**User Story:** As a developer, I want the improvement loop to stop
automatically when it has done enough.

#### Acceptance Criteria

1. [31-REQ-8.1] Phase 2 SHALL terminate when ANY of the following conditions
   is met:
   - The analyzer sets `diminishing_returns: true`
   - The analyzer returns zero high-or-medium-confidence improvements
   - The `--improve-passes` limit is reached
   - The shared cost limit (`config.orchestrator.max_cost`) is exhausted
   - The verifier returns FAIL (after rollback)
   - The user interrupts with Ctrl+C

2. [31-REQ-8.2] THE system SHALL track a termination reason for Phase 2 as
   one of: `converged` (diminishing returns or no improvements), `pass_limit`
   (improve-passes exhausted), `cost_limit`, `verifier_fail`, or
   `interrupted`.

3. [31-REQ-8.3] BEFORE each improvement pass, THE system SHALL check whether
   the remaining cost budget is sufficient for at least one full pass (analyzer
   + coder + verifier). IF insufficient, THE system SHALL terminate Phase 2
   with reason `cost_limit`.

---

### Requirement 9: Report

**User Story:** As a developer, I want a combined report showing both repair
and improvement results.

#### Acceptance Criteria

1. [31-REQ-9.1] WHEN `--auto` is used, THE completion report SHALL include
   both Phase 1 and Phase 2 summaries. Phase 1 reports: passes completed,
   clusters resolved, sessions consumed, termination reason. Phase 2 reports:
   passes completed (of max), improvements applied, improvements by tier,
   verifier verdicts (PASS/FAIL counts), sessions consumed (broken down by
   analyzer/coder/verifier), termination reason.

2. [31-REQ-9.2] THE report SHALL include a total cost line combining both
   phases.

3. [31-REQ-9.3] IN JSON mode (`--json`), THE report SHALL be emitted as JSONL
   with an `"event": "complete"` line containing both phase summaries as
   nested objects.

#### Edge Cases

1. [31-REQ-9.E1] IF Phase 2 did not run (Phase 1 did not achieve all-green,
   or `--auto` not set), THE report SHALL omit the Phase 2 section entirely.

---

### Requirement 10: Exit Codes

**User Story:** As a CI system, I want meaningful exit codes that distinguish
between different outcomes.

#### Acceptance Criteria

1. [31-REQ-10.1] Exit code 0 SHALL mean: Phase 1 achieved all-green AND
   Phase 2 completed successfully (all improvement passes verified, or
   converged naturally). When `--auto` is not set, exit code 0 means Phase 1
   all-green (existing behavior, unchanged).

2. [31-REQ-10.2] Exit code 1 SHALL mean: Phase 1 did not achieve all-green,
   OR Phase 2 verifier failed (after rollback).

3. [31-REQ-10.3] Exit code 130 SHALL mean: interrupted by SIGINT.
