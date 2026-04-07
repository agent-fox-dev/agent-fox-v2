# Requirements Document

## Introduction

This spec adds 6 new validation rules to the `lint-specs` command, closing
coverage gaps between the af-spec skill's completeness checklist and the
static validation rules enforced by the linter. Each rule targets a specific
structural or traceability requirement that specs must satisfy.

## Glossary

- **EARS**: Easy Approach to Requirements Syntax — a structured requirement
  pattern using keywords like SHALL, WHEN, WHILE, IF/THEN, WHERE.
- **lint-specs**: The CLI command (`agent-fox lint-specs`) that validates
  specification files for structural and quality problems.
- **Section schema**: The mapping of expected H2 headings per spec file,
  defined in `_SECTION_SCHEMAS` in the validators helper module.
- **Task group**: A top-level numbered checkbox item in `tasks.md`
  (e.g., `- [ ] 1. Write failing spec tests`).
- **Edge case requirement**: A requirement ID matching the pattern
  `NN-REQ-X.EN` where E indicates an edge case.
- **TS entry**: A test specification entry identified by a heading like
  `### TS-NN-N`, `### TS-NN-PN`, or `### TS-NN-EN`.
- **Completed spec**: A spec whose `tasks.md` has all task group checkboxes
  marked as complete (`[x]`).

## Requirements

### Requirement 1: Execution Paths Section Check

**User Story:** As a spec author, I want `lint-specs` to warn me when
`design.md` is missing an `## Execution Paths` section, so that I don't
forget this required section.

#### Acceptance Criteria

1. [83-REQ-1.1] WHEN `lint-specs` validates a spec whose `design.md` lacks
   a `## Execution Paths` section, THE validator SHALL produce a finding
   with rule `missing-section`, severity `warning`, and a message indicating
   the missing section.

2. [83-REQ-1.2] WHEN `design.md` contains a `## Execution Paths` section,
   THE validator SHALL NOT produce a `missing-section` finding for that
   section.

#### Edge Cases

1. [83-REQ-1.E1] IF `design.md` does not exist in the spec folder, THEN THE
   validator SHALL skip the Execution Paths check without error.

### Requirement 2: Integration Smoke Tests Section Check

**User Story:** As a spec author, I want `lint-specs` to warn me when
`test_spec.md` is missing an `## Integration Smoke Tests` section, so that
I remember to include smoke tests for execution paths.

#### Acceptance Criteria

1. [83-REQ-2.1] WHEN `lint-specs` validates a spec whose `test_spec.md`
   lacks an `## Integration Smoke Tests` section, THE validator SHALL
   produce a finding with rule `missing-section`, severity `warning`, and
   a message indicating the missing section.

2. [83-REQ-2.2] WHEN `test_spec.md` contains an `## Integration Smoke Tests`
   section, THE validator SHALL NOT produce a `missing-section` finding for
   that section.

#### Edge Cases

1. [83-REQ-2.E1] IF `test_spec.md` does not exist in the spec folder, THEN
   THE validator SHALL skip the Integration Smoke Tests check without error.

### Requirement 3: Requirement Count Limit

**User Story:** As a spec author, I want `lint-specs` to warn me when a
spec contains more than 10 requirements, so that I know to split it into
multiple specs.

#### Acceptance Criteria

1. [83-REQ-3.1] WHEN `lint-specs` validates a spec whose `requirements.md`
   contains more than 10 `### Requirement N:` headings, THE validator SHALL
   produce a finding with rule `too-many-requirements`, severity `warning`,
   and a message stating the count and the 10-requirement limit.

2. [83-REQ-3.2] WHEN `requirements.md` contains 10 or fewer
   `### Requirement N:` headings, THE validator SHALL NOT produce a
   `too-many-requirements` finding.

#### Edge Cases

1. [83-REQ-3.E1] IF `requirements.md` does not exist in the spec folder,
   THEN THE validator SHALL skip the requirement count check without error.

2. [83-REQ-3.E2] IF `requirements.md` contains zero `### Requirement N:`
   headings, THEN THE validator SHALL NOT produce a `too-many-requirements`
   finding.

### Requirement 4: First Task Group Title

**User Story:** As a spec author, I want `lint-specs` to warn me when the
first task group in `tasks.md` is not about writing failing tests, so that
the spec follows the mandatory test-first workflow.

#### Acceptance Criteria

1. [83-REQ-4.1] WHEN `lint-specs` validates a spec whose first parsed task
   group title does not contain both keywords "fail" and "test"
   (case-insensitive), THE validator SHALL produce a finding with rule
   `wrong-first-group`, severity `warning`, and a message indicating the
   expected content.

2. [83-REQ-4.2] WHEN the first task group title contains both "fail" and
   "test" (case-insensitive), THE validator SHALL NOT produce a
   `wrong-first-group` finding.

#### Edge Cases

1. [83-REQ-4.E1] IF `tasks.md` does not exist or cannot be parsed, THEN THE
   validator SHALL skip the first-group check without error.

2. [83-REQ-4.E2] IF `tasks.md` contains zero task groups, THEN THE validator
   SHALL skip the first-group check without error.

### Requirement 5: Last Task Group Title

**User Story:** As a spec author, I want `lint-specs` to warn me when the
last task group in `tasks.md` is not a wiring verification group, so that
integration gaps are caught before the spec is declared done.

#### Acceptance Criteria

1. [83-REQ-5.1] WHEN `lint-specs` validates a spec whose last parsed task
   group title does not contain both keywords "wiring" and "verification"
   (case-insensitive), THE validator SHALL produce a finding with rule
   `wrong-last-group`, severity `warning`, and a message indicating the
   expected content.

2. [83-REQ-5.2] WHEN the last task group title contains both "wiring" and
   "verification" (case-insensitive), THE validator SHALL NOT produce a
   `wrong-last-group` finding.

#### Edge Cases

1. [83-REQ-5.E1] IF `tasks.md` does not exist or cannot be parsed, THEN THE
   validator SHALL skip the last-group check without error.

2. [83-REQ-5.E2] IF `tasks.md` contains zero task groups, THEN THE validator
   SHALL skip the last-group check without error.

### Requirement 6: Edge Case Traceability

**User Story:** As a spec author, I want `lint-specs` to warn me when an
edge case requirement is not covered by a dedicated edge case test entry,
so that edge case testing is not overlooked.

#### Acceptance Criteria

1. [83-REQ-6.1] WHEN `lint-specs` validates a spec and finds an edge case
   requirement ID (matching `NN-REQ-X.EN`) in `requirements.md` that does
   not appear in the `## Edge Case Tests` section of `test_spec.md`, THE
   validator SHALL produce a finding with rule `untraced-edge-case`,
   severity `warning`, and a message naming the untraced requirement ID.

2. [83-REQ-6.2] WHEN every edge case requirement ID in `requirements.md`
   appears in the `## Edge Case Tests` section of `test_spec.md`, THE
   validator SHALL NOT produce any `untraced-edge-case` findings.

#### Edge Cases

1. [83-REQ-6.E1] IF `requirements.md` or `test_spec.md` does not exist,
   THEN THE validator SHALL skip the edge case traceability check without
   error.

2. [83-REQ-6.E2] IF `requirements.md` contains no edge case requirement IDs,
   THEN THE validator SHALL NOT produce any `untraced-edge-case` findings.

3. [83-REQ-6.E3] IF `test_spec.md` has no `## Edge Case Tests` section,
   THEN THE validator SHALL treat the section as empty and report all edge
   case requirements as untraced.
