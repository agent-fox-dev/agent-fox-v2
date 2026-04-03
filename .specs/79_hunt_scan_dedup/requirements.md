# Requirements Document

## Introduction

This specification adds cross-iteration deduplication to night-shift's hunt
scan pipeline. It prevents the system from creating duplicate platform issues
when the same maintenance problem persists across consecutive scan iterations.

## Glossary

- **Fingerprint**: A truncated SHA-256 hex digest computed from a FindingGroup's
  `category` and sorted `affected_files`. Used to identify equivalent findings
  across scan iterations.
- **Fingerprint marker**: An HTML comment embedded in the issue body containing
  the fingerprint, in the format `<!-- af:fingerprint:{hex} -->`. Invisible when
  rendered but extractable via regex.
- **af:hunt label**: A platform label assigned to every issue created by the
  hunt scan pipeline. Used to efficiently query only night-shift-created issues
  during the dedup check.
- **Dedup gate**: The pre-creation check that compares new FindingGroup
  fingerprints against fingerprints extracted from existing open `af:hunt`
  issues. FindingGroups with matching fingerprints are skipped.
- **Known fingerprints**: The set of fingerprints extracted from existing open
  `af:hunt` issues, loaded once per issue-creation phase.

## Requirements

### Requirement 1: FindingGroup Fingerprint Computation

**User Story:** As a night-shift operator, I want each FindingGroup to have a
deterministic fingerprint so that the same problem produces the same identifier
across scan iterations.

#### Acceptance Criteria

[79-REQ-1.1] WHEN a FindingGroup is produced by the consolidation stage, THE
system SHALL compute a fingerprint by hashing the concatenation of the group's
`category` and its sorted `affected_files` list using SHA-256, AND return the
first 16 hex characters of the digest.

[79-REQ-1.2] THE fingerprint function SHALL produce identical output for two
FindingGroups that have the same `category` and the same set of
`affected_files`, regardless of finding order, title, description, or other
fields.

[79-REQ-1.3] THE fingerprint function SHALL produce different output for two
FindingGroups that differ in `category` or in `affected_files`.

#### Edge Cases

[79-REQ-1.E1] IF a FindingGroup has an empty `affected_files` list, THEN THE
system SHALL compute the fingerprint using only the `category` field.

[79-REQ-1.E2] IF two FindingGroups have the same `affected_files` but different
`category` values, THEN THE system SHALL produce different fingerprints.

### Requirement 2: Fingerprint Embedding in Issue Body

**User Story:** As a night-shift operator, I want the fingerprint stored in the
issue body so that it survives platform round-trips and can be extracted later.

#### Acceptance Criteria

[79-REQ-2.1] WHEN creating a platform issue from a FindingGroup, THE system
SHALL append a fingerprint marker to the issue body in the format
`<!-- af:fingerprint:{hex} -->` where `{hex}` is the 16-character fingerprint.

[79-REQ-2.2] WHEN extracting a fingerprint from an issue body, THE system SHALL
parse the body for the pattern `<!-- af:fingerprint:([0-9a-f]{16}) -->` AND
return the captured hex string, or `None` if no match is found.

#### Edge Cases

[79-REQ-2.E1] IF an issue body contains multiple fingerprint markers, THEN THE
system SHALL extract the first one.

[79-REQ-2.E2] IF an issue body contains no fingerprint marker, THEN THE system
SHALL return `None` and the issue SHALL be ignored during dedup matching.

### Requirement 3: Hunt Issue Identification

**User Story:** As a night-shift operator, I want hunt-created issues tagged so
that the dedup gate can efficiently query only night-shift issues.

#### Acceptance Criteria

[79-REQ-3.1] WHEN creating a platform issue from a hunt scan FindingGroup, THE
system SHALL include the `af:hunt` label on the created issue.

[79-REQ-3.2] WHEN the `--auto` flag is active, THE system SHALL assign both the
`af:hunt` and `af:fix` labels to the created issue.

#### Edge Cases

[79-REQ-3.E1] IF label assignment fails after issue creation, THEN THE system
SHALL log a warning and continue without blocking issue creation or the dedup
gate.

### Requirement 4: Pre-Creation Duplicate Gate

**User Story:** As a night-shift operator, I want the system to check for
existing equivalent issues before creating new ones, so that I do not receive
duplicate issues for the same unfixed problem.

#### Acceptance Criteria

[79-REQ-4.1] WHEN the issue-creation phase begins after finding consolidation,
THE system SHALL fetch all open issues with the `af:hunt` label from the
platform in a single API call AND return their bodies for fingerprint
extraction.

[79-REQ-4.2] WHEN creating issues from FindingGroups, THE system SHALL compute
the fingerprint for each FindingGroup AND skip creation for any group whose
fingerprint matches a fingerprint extracted from the fetched open issues.

[79-REQ-4.3] WHEN a FindingGroup is skipped due to a duplicate match, THE
system SHALL log at INFO level a message containing the group title and the
issue number of the matching existing issue.

[79-REQ-4.4] WHEN the dedup gate completes filtering, THE system SHALL return
only the non-duplicate FindingGroups to the issue-creation function AND return
the list of created issue references to the caller for use in subsequent
operations (e.g. label assignment).

#### Edge Cases

[79-REQ-4.E1] IF the platform API call to fetch existing issues fails, THEN THE
system SHALL log a warning and proceed to create all issues without dedup
filtering (fail-open).

[79-REQ-4.E2] IF no open `af:hunt` issues exist on the platform, THEN THE
system SHALL proceed to create all issues (empty known-fingerprint set).

[79-REQ-4.E3] IF all FindingGroups are duplicates, THEN THE system SHALL create
no issues and return an empty list.

### Requirement 5: Fingerprint Consistency

**User Story:** As a night-shift operator, I want fingerprints to be stable
across scan iterations so that the same problem is reliably detected as a
duplicate.

#### Acceptance Criteria

[79-REQ-5.1] THE fingerprint function SHALL use a deterministic separator
between fields (null byte `\0`) so that `category="ab"` +
`file="c"` and `category="a"` + `file="bc"` produce different fingerprints.

[79-REQ-5.2] THE fingerprint function SHALL sort `affected_files`
lexicographically before hashing so that file order does not affect the result.

#### Edge Cases

[79-REQ-5.E1] IF `affected_files` contains duplicate entries, THEN THE system
SHALL deduplicate them before sorting and hashing.
