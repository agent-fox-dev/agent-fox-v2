# Requirements Document

## Introduction

This specification defines a cross-category finding consolidation critic for
night-shift's hunt scanner. The critic replaces the existing mechanical
`consolidate_findings()` function with an AI-powered stage that deduplicates
findings across categories, validates evidence, calibrates severity, and
synthesises coherent issue descriptions.

## Glossary

- **Finding**: A frozen dataclass produced by a hunt category, containing
  category, title, description, severity, affected_files, suggested_fix,
  evidence, and group_key.
- **FindingGroup**: A frozen dataclass representing a consolidated group of
  related findings, ready for issue creation. Contains findings, title, body,
  and category.
- **Critic stage**: The AI-powered consolidation pass that receives all
  findings from a hunt scan and produces validated, deduplicated FindingGroups.
- **Mechanical grouping**: The fallback consolidation path where each finding
  becomes its own FindingGroup without AI analysis.
- **Evidence**: The `evidence` field of a Finding — static tool output, code
  snippets, or line references that substantiate the finding.
- **Minimum threshold**: The minimum number of findings (3) required to trigger
  the critic stage.
- **Critic decision**: A logged record of a merge, drop, or severity change
  made by the critic.

## Requirements

### Requirement 1: Cross-Category Deduplication

**User Story:** As a maintainer reviewing night-shift issues, I want findings
about the same root cause from different categories merged into a single issue,
so that I don't waste time triaging duplicates.

#### Acceptance Criteria

[73-REQ-1.1] WHEN the critic stage receives findings from multiple categories
that share the same root cause or affect overlapping files, THE system SHALL
merge them into a single FindingGroup.

[73-REQ-1.2] WHEN findings are merged, THE system SHALL produce a FindingGroup
whose `affected_files` is the union of all merged findings' affected files.

[73-REQ-1.3] WHEN findings are merged, THE system SHALL produce a FindingGroup
whose title and body synthesise the combined context rather than using only the
first finding's text.

#### Edge Cases

[73-REQ-1.E1] IF all findings in a batch share the same root cause, THEN THE
system SHALL merge them into a single FindingGroup.

[73-REQ-1.E2] IF no findings in a batch share a root cause, THEN THE system
SHALL produce one FindingGroup per finding.

### Requirement 2: Evidence Validation

**User Story:** As a maintainer, I want low-confidence findings filtered out
before issues are created, so that the issue stream stays trustworthy.

#### Acceptance Criteria

[73-REQ-2.1] WHEN the critic stage evaluates a finding, THE system SHALL check
whether the `evidence` field contains concrete proof (tool output, code
snippets, or line references).

[73-REQ-2.2] WHEN a finding's evidence is empty or purely speculative, THE
system SHALL drop the finding from the output.

[73-REQ-2.3] WHEN a finding is dropped, THE system SHALL log the finding title
and the reason for dropping at INFO level.

#### Edge Cases

[73-REQ-2.E1] IF all findings in a batch are dropped by the critic, THEN THE
system SHALL return an empty list of FindingGroups and log a summary.

[73-REQ-2.E2] IF a finding has non-empty evidence but the evidence is
speculative (e.g., "might be", "could potentially"), THEN THE system SHALL
treat it as insufficient and drop the finding.

### Requirement 3: Severity Calibration

**User Story:** As a maintainer, I want finding severity to reflect the full
picture across categories, so that I can prioritise effectively.

#### Acceptance Criteria

[73-REQ-3.1] WHEN findings are merged into a FindingGroup, THE system SHALL
assign a final severity based on the combined context of all merged findings.

[73-REQ-3.2] WHEN the critic changes a finding's severity, THE system SHALL
log the original severity, the new severity, and the justification at INFO
level.

#### Edge Cases

[73-REQ-3.E1] IF a finding is not merged with others, THEN THE system SHALL
preserve its original severity unchanged.

### Requirement 4: Minimum-Threshold Skip

**User Story:** As a cost-conscious user, I want trivial batches handled
mechanically without an extra AI call.

#### Acceptance Criteria

[73-REQ-4.1] WHEN a hunt scan produces fewer than 3 findings, THE system SHALL
skip the critic stage entirely.

[73-REQ-4.2] WHEN the critic stage is skipped, THE system SHALL use mechanical
grouping where each finding becomes its own FindingGroup.

#### Edge Cases

[73-REQ-4.E1] IF a hunt scan produces exactly 0 findings, THEN THE system
SHALL return an empty list of FindingGroups without invoking the critic or
mechanical grouping.

### Requirement 5: Critic Output Format

**User Story:** As a developer maintaining the pipeline, I want the critic to
produce the same FindingGroup format so downstream code is unchanged.

#### Acceptance Criteria

[73-REQ-5.1] THE critic stage SHALL return a `list[FindingGroup]` compatible
with the existing `create_issues_from_groups()` function.

[73-REQ-5.2] WHEN the critic produces output, THE system SHALL parse the AI
response as JSON and construct FindingGroup instances from it.

[73-REQ-5.3] THE critic stage SHALL include the original Finding objects in
each FindingGroup's `findings` list, preserving full traceability.

#### Edge Cases

[73-REQ-5.E1] IF the AI response is malformed or unparseable JSON, THEN THE
system SHALL fall back to mechanical grouping and log a warning.

[73-REQ-5.E2] IF the AI response references finding indices that are out of
bounds, THEN THE system SHALL ignore the invalid references and log a warning.

### Requirement 6: Transparency and Logging

**User Story:** As an operator, I want full visibility into critic decisions so
I can tune categories and trust the output.

#### Acceptance Criteria

[73-REQ-6.1] WHEN findings are merged, THE system SHALL log the merged finding
titles, their source categories, and the merge reason at INFO level.

[73-REQ-6.2] WHEN findings are dropped, THE system SHALL log the dropped
finding title and the drop reason at INFO level.

[73-REQ-6.3] WHEN the critic completes, THE system SHALL log a summary
containing: total findings received, findings dropped, findings merged, and
FindingGroups produced, at INFO level.

[73-REQ-6.4] THE system SHALL log full critic reasoning at DEBUG level.

#### Edge Cases

[73-REQ-6.E1] IF logging fails, THEN THE system SHALL not interrupt the
consolidation pipeline.

### Requirement 7: Pipeline Integration

**User Story:** As a developer, I want the critic to slot into the existing
pipeline without changing the engine's calling code beyond the consolidation
call site.

#### Acceptance Criteria

[73-REQ-7.1] THE system SHALL replace the existing `consolidate_findings()`
function with the new critic-based consolidation.

[73-REQ-7.2] THE new consolidation function SHALL accept `list[Finding]` and
return `list[FindingGroup]`, matching the existing signature.

[73-REQ-7.3] THE new consolidation function SHALL be async to support AI
calls.

#### Edge Cases

[73-REQ-7.E1] IF the AI backend is unavailable, THEN THE system SHALL fall
back to mechanical grouping and log a warning.
