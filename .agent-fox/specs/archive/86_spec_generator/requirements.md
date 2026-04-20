# Requirements Document

## Introduction

The spec generator is a daemon work stream that autonomously creates
specification packages from GitHub issues labeled `af:spec`. It polls for
eligible issues, analyzes their content via AI, drives a clarification loop
through issue comments, generates a 5-file spec package following the
`/af-spec` skill's structure, and lands the result on `develop` via the
standard feature-branch workflow.

This spec also extends the platform layer with three new operations needed
by the generator: label removal, comment listing, and single-issue fetching.

## Glossary

| Term | Definition |
|------|-----------|
| **Spec package** | The standard 5-file set: `prd.md`, `requirements.md`, `design.md`, `test_spec.md`, `tasks.md` |
| **Fox comment** | A GitHub issue comment whose body starts with `## Agent Fox` |
| **Human comment** | Any issue comment that is not a fox comment |
| **Clarification round** | One cycle of: fox posts questions -> human replies |
| **Label transition** | Removing the current `af:spec-*` label and assigning a new one |
| **Spec prefix** | The two-digit numeric prefix (NN) of a spec folder name |
| **Analysis** | An AI call that assesses whether an issue body (plus comments) contains enough information to generate a spec |
| **Scope overlap** | When an existing spec in `.specs/` covers substantially the same feature or concern as a new issue |
| **Landing** | The git workflow of creating a feature branch, committing spec files, and merging to `develop` |
| **Stale issue** | An `af:spec` issue whose last activity (comment or label change) is older than 30 days |
| **SharedBudget** | The daemon-level cost tracker from spec 85 that aggregates cost across all work streams |
| **SpecGeneratorStream** | The WorkStream implementation that runs the spec generator on a timer |

## Requirements

### Requirement 1: Platform Extensions

**User Story:** As the spec generator, I want to remove labels, list
comments, and fetch individual issues so that I can implement the label
state machine and gather issue context.

#### Acceptance Criteria

1. [86-REQ-1.1] WHEN `remove_label(issue_number, label)` is called, THE
   platform SHALL send a DELETE request to the GitHub API to remove the
   specified label from the issue AND return successfully.

2. [86-REQ-1.2] WHEN `remove_label()` is called with a label that is not
   present on the issue, THE platform SHALL succeed without error
   (idempotent).

3. [86-REQ-1.3] WHEN `list_issue_comments(issue_number)` is called, THE
   platform SHALL return a list of `IssueComment` objects ordered
   chronologically, each containing `id`, `body`, `user`, and
   `created_at` fields.

4. [86-REQ-1.4] WHEN `get_issue(issue_number)` is called, THE platform
   SHALL return an `IssueResult` with the issue's `number`, `title`,
   `html_url`, and `body`.

5. [86-REQ-1.5] THE platform protocol SHALL include `remove_label()`,
   `list_issue_comments()`, and `get_issue()` method signatures so that
   all platform implementations can support the spec generator.

#### Edge Cases

1. [86-REQ-1.E1] IF `remove_label()` receives a non-404 error response
   from the API, THEN THE platform SHALL raise `IntegrationError`.

2. [86-REQ-1.E2] IF `list_issue_comments()` is called on an issue with
   no comments, THEN THE platform SHALL return an empty list.

3. [86-REQ-1.E3] IF `get_issue()` is called with a non-existent issue
   number, THEN THE platform SHALL raise `IntegrationError`.

---

### Requirement 2: Issue Discovery

**User Story:** As the daemon, I want to discover `af:spec` issues and
process them sequentially so that specs are generated reliably without
conflicts.

#### Acceptance Criteria

1. [86-REQ-2.1] WHEN `SpecGeneratorStream.run_once()` is called, THE
   system SHALL poll the platform for issues labeled `af:spec` and
   `af:spec-pending`, AND return both lists to the caller for processing.

2. [86-REQ-2.2] WHEN multiple `af:spec` issues exist, THE system SHALL
   process only the oldest issue (by creation date) per cycle AND leave
   remaining issues for subsequent cycles.

3. [86-REQ-2.3] WHEN an `af:spec-pending` issue has a new human comment
   posted after the last fox comment, THE system SHALL transition it to
   `af:spec-analyzing` for re-analysis.

4. [86-REQ-2.4] WHILE an `af:spec-pending` issue has no new human
   comment after the last fox comment, THE system SHALL skip it.

#### Edge Cases

1. [86-REQ-2.E1] IF no issues are labeled `af:spec` or `af:spec-pending`,
   THEN THE system SHALL return without action (no-op).

2. [86-REQ-2.E2] IF an `af:spec` issue's last activity (comment or label
   change) is older than 30 days, THEN THE system SHALL skip it AND log
   a warning.

---

### Requirement 3: State Machine

**User Story:** As the spec generator, I want to track issue progress
through labels so that state is visible on GitHub and survives daemon
restarts.

#### Acceptance Criteria

1. [86-REQ-3.1] WHEN transitioning an issue's state, THE system SHALL
   assign the new label first, then remove the old label, ensuring the
   issue always has exactly one `af:spec-*` label.

2. [86-REQ-3.2] WHEN the system picks up an `af:spec` issue for
   processing, THE system SHALL transition it to `af:spec-analyzing`.

3. [86-REQ-3.3] WHEN analysis determines the issue is clear, THE system
   SHALL transition to `af:spec-generating`.

4. [86-REQ-3.4] WHEN generation completes successfully, THE system SHALL
   transition to `af:spec-done` AND close the issue.

#### Edge Cases

1. [86-REQ-3.E1] IF the daemon finds an issue labeled
   `af:spec-analyzing` that it did not transition in this cycle (stale
   from a crash), THEN THE system SHALL reset it to `af:spec` for
   re-processing.

2. [86-REQ-3.E2] IF the daemon finds an issue labeled
   `af:spec-generating` that it did not transition in this cycle (stale
   from a crash), THEN THE system SHALL reset it to `af:spec` for
   re-processing.

---

### Requirement 4: Issue Analysis

**User Story:** As the spec generator, I want to assess whether an issue
contains enough information to generate a spec so that I can ask targeted
clarification questions when needed.

#### Acceptance Criteria

1. [86-REQ-4.1] WHEN analyzing an issue, THE system SHALL send the issue
   body, all comments, referenced issue context, existing spec summaries,
   and steering directives to the AI model AND return an `AnalysisResult`
   indicating whether the issue is clear or ambiguous, with a list of
   questions if ambiguous.

2. [86-REQ-4.2] WHEN the analysis determines the issue is ambiguous, THE
   system SHALL post a clarification comment in the standard format (with
   numbered questions and round counter) AND transition to
   `af:spec-pending`.

3. [86-REQ-4.3] WHEN parsing issue body and comments for `#N` references,
   THE system SHALL fetch the body and comments of each referenced issue
   AND include them as context for analysis, AND return the gathered
   context to the caller.

#### Edge Cases

1. [86-REQ-4.E1] IF a referenced issue (`#N`) is inaccessible (404 or
   permission error), THEN THE system SHALL log a warning AND skip that
   reference without failing the analysis.

2. [86-REQ-4.E2] IF the issue body is empty, THEN THE system SHALL treat
   the issue as ambiguous AND post clarification questions.

---

### Requirement 5: Clarification Loop

**User Story:** As the spec generator, I want to drive a multi-turn
clarification conversation so that ambiguous issues can be refined into
complete specs.

#### Acceptance Criteria

1. [86-REQ-5.1] WHEN counting clarification rounds, THE system SHALL
   count the number of fox clarification comments in the issue's comment
   history AND return the count.

2. [86-REQ-5.2] WHEN the clarification round count reaches
   `max_clarification_rounds`, THE system SHALL post an escalation
   comment listing remaining open questions AND transition to
   `af:spec-blocked`.

3. [86-REQ-5.3] WHEN detecting whether a comment is a fox comment, THE
   system SHALL check if the comment body starts with `## Agent Fox`
   AND return a boolean result.

#### Edge Cases

1. [86-REQ-5.E1] IF `max_clarification_rounds` is reached on the first
   analysis (round 0 with no prior clarification), THEN THE system SHALL
   still post the escalation comment with the unresolved questions.

---

### Requirement 6: Spec Generation

**User Story:** As the spec generator, I want to produce a complete
5-file spec package so that the spec executor can implement it
automatically.

#### Acceptance Criteria

1. [86-REQ-6.1] WHEN generating a spec package, THE system SHALL produce
   all five files (`prd.md`, `requirements.md`, `design.md`,
   `test_spec.md`, `tasks.md`) following the structure and rules of the
   `/af-spec` skill AND return the generated file contents as a
   `SpecPackage`.

2. [86-REQ-6.2] WHEN generating the `prd.md`, THE system SHALL use the
   issue body (plus clarification answers from comments) as the PRD
   content AND append a `## Source` section linking back to the GitHub
   issue URL.

3. [86-REQ-6.3] WHEN choosing a spec folder name, THE system SHALL find
   the highest existing numeric prefix in `.specs/` AND use the next
   sequential number, zero-padded to two digits, combined with a
   snake_case name derived from the issue title.

4. [86-REQ-6.4] WHEN generating spec documents, THE system SHALL use the
   model tier configured in `spec_gen_model_tier` (resolved via
   `resolve_model()`) for all AI API calls AND track the cost of each
   call.

#### Edge Cases

1. [86-REQ-6.E1] IF an AI API call fails during generation, THEN THE
   system SHALL abort the generation, post a comment explaining the
   failure, AND transition to `af:spec-blocked`.

2. [86-REQ-6.E2] IF the `.specs/` directory contains no existing spec
   folders, THEN THE system SHALL use `01` as the spec prefix.

---

### Requirement 7: Duplicate Detection

**User Story:** As the spec generator, I want to detect when an issue
overlaps with an existing spec so that duplicate work is avoided.

#### Acceptance Criteria

1. [86-REQ-7.1] WHEN processing an issue, THE system SHALL use an AI
   call to compare the issue title and body against existing spec names
   and PRD summaries AND return a `DuplicateCheckResult` indicating
   whether a likely duplicate exists and which spec it overlaps with.

2. [86-REQ-7.2] WHEN a likely duplicate is detected, THE system SHALL
   post a comment asking whether to supersede the existing spec or skip
   AND transition to `af:spec-pending`.

3. [86-REQ-7.3] WHEN the human responds to a duplicate check with
   "supersede", THE system SHALL generate the new spec with a
   `## Supersedes` section referencing the old spec.

#### Edge Cases

1. [86-REQ-7.E1] IF no specs exist in `.specs/`, THEN THE system SHALL
   skip the duplicate detection step entirely.

---

### Requirement 8: Landing Workflow

**User Story:** As the spec generator, I want to commit the spec package
to develop via a feature branch so that the landing follows the project's
standard git workflow.

#### Acceptance Criteria

1. [86-REQ-8.1] WHEN landing a spec, THE system SHALL create a feature
   branch named `spec/<spec_name>` from `develop`, write all spec files,
   and commit with message `feat(spec): generate <spec_name> from
   #<issue_number>`.

2. [86-REQ-8.2] WHEN `merge_strategy` is `"direct"`, THE system SHALL
   merge the feature branch into `develop` AND delete the feature branch.

3. [86-REQ-8.3] WHEN `merge_strategy` is `"pr"`, THE system SHALL create
   a draft pull request from the feature branch to `develop` via
   `platform.create_pull_request()` AND return the PR URL.

4. [86-REQ-8.4] WHEN landing completes successfully, THE system SHALL
   post a completion comment on the issue (with spec folder, file list,
   and commit hash), transition to `af:spec-done`, AND close the issue.

#### Edge Cases

1. [86-REQ-8.E1] IF the feature branch already exists, THEN THE system
   SHALL append a short suffix to the branch name to avoid collision.

2. [86-REQ-8.E2] IF the merge or PR creation fails, THEN THE system
   SHALL post a comment with the branch name for manual recovery AND
   transition to `af:spec-blocked`.

---

### Requirement 9: Configuration

**User Story:** As an operator, I want to configure the spec generator's
behavior so that I can tune clarification limits, cost caps, and model
selection.

#### Acceptance Criteria

1. [86-REQ-9.1] THE `NightShiftConfig` SHALL include a
   `max_clarification_rounds` field (integer, default 3) that controls
   the maximum number of clarification rounds before escalation.

2. [86-REQ-9.2] THE `NightShiftConfig` SHALL include a `max_budget_usd`
   field (float, default 2.0) that sets the per-spec generation cost cap.

3. [86-REQ-9.3] THE `NightShiftConfig` SHALL include a
   `spec_gen_model_tier` field (string, default `"ADVANCED"`) that
   specifies which model tier to use for spec generation API calls.

#### Edge Cases

1. [86-REQ-9.E1] IF `max_clarification_rounds` is less than 1, THEN THE
   config validator SHALL clamp it to 1.

2. [86-REQ-9.E2] IF `spec_gen_model_tier` is not a valid tier name or
   model ID, THEN THE system SHALL fall back to `"ADVANCED"` AND log a
   warning.

---

### Requirement 10: Cost Management

**User Story:** As the daemon, I want to enforce per-spec cost limits and
report costs to the shared budget so that runaway analysis is prevented.

#### Acceptance Criteria

1. [86-REQ-10.1] WHILE generating a spec, THE system SHALL track the
   cumulative cost of all AI API calls for that spec AND compare it
   against `max_budget_usd` after each call.

2. [86-REQ-10.2] IF the cumulative cost exceeds `max_budget_usd` during
   generation, THEN THE system SHALL abort the generation, post a
   budget-exceeded comment on the issue, AND transition to
   `af:spec-blocked`.

3. [86-REQ-10.3] WHEN a `run_once()` cycle completes, THE
   `SpecGeneratorStream` SHALL report the total cost consumed during
   the cycle to the daemon's `SharedBudget` via `add_cost()`.

#### Edge Cases

1. [86-REQ-10.E1] IF `max_budget_usd` is `None` or `0`, THEN THE system
   SHALL treat the per-spec budget as unlimited (no cap enforcement).
