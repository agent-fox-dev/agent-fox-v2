# Requirements Document

## Introduction

This specification defines embedding-based duplicate detection and the
`af:ignore` label for the night-shift hunt scan pipeline. Together, these
features prevent the scanner from filing duplicate or near-duplicate issues
and allow users to permanently suppress false-positive findings.

## Glossary

- **Hunt scan:** The periodic code-quality scan performed by the `night-shift`
  command. Runs all enabled hunt categories in parallel and produces
  `Finding` objects.
- **FindingGroup:** A group of related findings consolidated by the AI critic,
  representing a single issue to be filed on the platform.
- **Fingerprint:** A 16-character hex SHA-256 digest of a FindingGroup's
  category and sorted affected files. Used for exact-match deduplication.
- **Embedding:** A fixed-length vector representation of text, computed by a
  sentence-transformers model. Used for semantic similarity comparison.
- **Cosine similarity:** A measure of similarity between two vectors, ranging
  from -1 (opposite) to 1 (identical). For normalized embeddings, values
  above 0.85 typically indicate near-duplicates.
- **Similarity threshold:** A configurable float (0.0 to 1.0) above which
  two items are considered semantically similar enough to be duplicates.
- **`af:ignore` label:** A platform label that users apply to hunt issues to
  indicate the finding is not a real problem and should not be re-discovered.
- **`af:hunt` label:** The existing platform label applied to all issues
  created by the hunt scan pipeline.
- **Anti-pattern fact:** A knowledge store entry (category `anti_pattern`)
  recording a known false-positive pattern so that future scans can avoid
  reporting it.
- **Knowledge ingestion marker:** An HTML comment
  (`<!-- af:knowledge-ingested -->`) embedded in an issue body to indicate
  that its content has been ingested into the knowledge store.

## Requirements

### Requirement 1: `af:ignore` label setup

**User Story:** As a night-shift user, I want an `af:ignore` label available
on my repository, so that I can mark hunt-filed issues as false positives.

#### Acceptance Criteria

[110-REQ-1.1] THE system SHALL define a label constant `LABEL_IGNORE` with
value `"af:ignore"` in the `platform/labels.py` module.

[110-REQ-1.2] THE system SHALL define a color constant `LABEL_IGNORE_COLOR`
with a gray hex value in the `platform/labels.py` module.

[110-REQ-1.3] THE system SHALL include `af:ignore` in the `REQUIRED_LABELS`
list with the gray color and description
`"Hunt findings marked as not-an-issue by the user"`.

[110-REQ-1.4] WHEN `agent-fox init` runs, THE system SHALL create the
`af:ignore` label on the repository (idempotent, succeeds if already exists).

#### Edge Cases

[110-REQ-1.E1] IF the `af:ignore` label already exists on the repository,
THEN THE system SHALL skip creation silently (existing `create_label`
idempotency).

### Requirement 2: Embedding-based similarity computation

**User Story:** As a night-shift operator, I want the system to detect
semantically similar findings, so that near-duplicate issues are not filed
even when their exact file lists differ.

#### Acceptance Criteria

[110-REQ-2.1] WHEN comparing a FindingGroup against an existing issue, THE
system SHALL compute a text representation for each, generate embeddings using
`EmbeddingGenerator.embed_batch()`, and compute cosine similarity between the
resulting vectors AND return the similarity score as a float.

[110-REQ-2.2] THE system SHALL construct the text representation for a
FindingGroup as: `"{category}: {title}\nFiles: {comma-separated affected_files}"`.

[110-REQ-2.3] THE system SHALL construct the text representation for an
existing issue as: `"{title}\n{body[:500]}"` (title followed by the first
500 characters of the body).

[110-REQ-2.4] THE system SHALL provide a `cosine_similarity(a, b)` function
that accepts two float vectors and returns a float in [-1.0, 1.0] AND the
function SHALL return 0.0 if either vector is zero-length or None.

#### Edge Cases

[110-REQ-2.E1] IF `EmbeddingGenerator.embed_text()` returns `None` for any
input, THEN THE system SHALL treat the similarity as 0.0 (no match) and log
a warning.

[110-REQ-2.E2] IF the `EmbeddingGenerator` cannot be instantiated (e.g.,
`sentence-transformers` not installed), THEN THE system SHALL fall back to
fingerprint-only matching and log a warning.

### Requirement 3: Enhanced dedup — closed issues and similarity matching

**User Story:** As a night-shift operator, I want the dedup check to cover
both open and closed issues, and to catch near-duplicates via embedding
similarity, so that previously reported findings are not re-filed.

#### Acceptance Criteria

[110-REQ-3.1] WHEN `filter_known_duplicates()` is called, THE system SHALL
fetch `af:hunt` issues with `state="all"` (both open and closed) in a single
API call AND return the novel FindingGroups after filtering.

[110-REQ-3.2] WHEN a FindingGroup's fingerprint matches any existing `af:hunt`
issue, THE system SHALL skip that group (existing behaviour, now extended to
closed issues).

[110-REQ-3.3] WHEN a FindingGroup's embedding similarity to any existing
`af:hunt` issue exceeds the configured similarity threshold, THE system SHALL
skip that group AND log an INFO message with the group title, matching issue
number, and similarity score.

[110-REQ-3.4] THE system SHALL accept a `similarity_threshold` parameter
(float, default 0.85) in `filter_known_duplicates()`.

[110-REQ-3.5] THE system SHALL check fingerprint matches first, then embedding
similarity only for groups that pass the fingerprint check (short-circuit
optimisation).

#### Edge Cases

[110-REQ-3.E1] IF embedding computation fails for any reason, THEN THE system
SHALL fall back to fingerprint-only matching (fail-open) and log a warning.

[110-REQ-3.E2] IF the platform API call to fetch issues fails, THEN THE
system SHALL return all groups unfiltered (existing fail-open behaviour).

### Requirement 4: `af:ignore` dedup gate

**User Story:** As a user who has labelled a hunt issue as `af:ignore`, I want
the scanner to stop re-discovering similar findings, so that false positives
are permanently suppressed.

#### Acceptance Criteria

[110-REQ-4.1] WHEN the hunt scan dedup pipeline runs, THE system SHALL call
`filter_ignored()` after `filter_known_duplicates()` AND return the
FindingGroups that pass both filters.

[110-REQ-4.2] THE `filter_ignored()` function SHALL fetch all `af:ignore`
issues with `state="all"` (both open and closed) in a single API call.

[110-REQ-4.3] WHEN a FindingGroup's embedding similarity to any `af:ignore`
issue exceeds the configured similarity threshold, THE system SHALL skip
that group AND log an INFO message stating the group title, matching issue
number, and that the finding matches an ignored issue.

[110-REQ-4.4] THE `filter_ignored()` function SHALL accept a
`similarity_threshold` parameter (float, default 0.85) AND return the list
of novel FindingGroups to the caller for use in issue creation.

#### Edge Cases

[110-REQ-4.E1] IF no `af:ignore` issues exist on the platform, THEN THE
system SHALL return all groups unfiltered.

[110-REQ-4.E2] IF the platform API call to fetch `af:ignore` issues fails,
THEN THE system SHALL return all groups unfiltered (fail-open) and log a
warning.

[110-REQ-4.E3] IF embedding computation fails for `af:ignore` comparison,
THEN THE system SHALL return all groups unfiltered (fail-open) and log a
warning.

### Requirement 5: Knowledge ingestion of `af:ignore` signals

**User Story:** As a night-shift operator, I want `af:ignore` signals stored
in the knowledge system, so that future scans benefit from accumulated
false-positive knowledge.

#### Acceptance Criteria

[110-REQ-5.1] WHEN the hunt scan pre-phase runs, THE system SHALL fetch all
`af:ignore` issues (state `"all"`) and identify those not yet ingested
(lacking the `<!-- af:knowledge-ingested -->` marker in their body).

[110-REQ-5.2] WHEN a new `af:ignore` issue is identified, THE system SHALL
create an `anti_pattern` fact in the knowledge store with: content describing
the false-positive pattern (issue title and category extracted from the body),
keywords extracted from the issue title, confidence 0.9 (high), and
spec_name `"nightshift:ignore"`.

[110-REQ-5.3] WHEN a fact is successfully created for an `af:ignore` issue,
THE system SHALL append the marker `<!-- af:knowledge-ingested -->` to the
issue body via the platform API AND return the count of newly ingested facts
to the caller.

[110-REQ-5.4] THE system SHALL extract the hunt category from the issue body
by parsing the `**Category:**` field (present in all hunt-generated issue
bodies).

#### Edge Cases

[110-REQ-5.E1] IF the `<!-- af:knowledge-ingested -->` marker is already
present in the issue body, THEN THE system SHALL skip ingestion for that issue.

[110-REQ-5.E2] IF updating the issue body with the ingestion marker fails,
THEN THE system SHALL log a warning and continue (the fact is still stored;
re-ingestion on next scan is acceptable).

[110-REQ-5.E3] IF the knowledge store is unavailable (no DuckDB connection),
THEN THE system SHALL skip ingestion entirely and log a warning.

### Requirement 6: AI critic false-positive awareness

**User Story:** As a night-shift operator, I want the AI critic to know about
previously ignored findings, so that it can proactively drop similar findings
before they reach the dedup gate.

#### Acceptance Criteria

[110-REQ-6.1] WHEN `consolidate_findings()` is called, THE system SHALL
accept an optional `false_positives` parameter (list of strings) describing
known false-positive patterns.

[110-REQ-6.2] WHEN `false_positives` is non-empty, THE system SHALL append a
`Known False Positives` section to the critic system prompt listing each
false-positive pattern, instructing the critic to drop findings that match
these patterns.

[110-REQ-6.3] WHEN the engine calls `consolidate_findings()`, THE system
SHALL query the knowledge store for `anti_pattern` facts with
spec_name `"nightshift:ignore"` and pass their content strings as the
`false_positives` parameter AND the list of false-positive strings SHALL be
available to the critic for use in its consolidation decisions.

#### Edge Cases

[110-REQ-6.E1] IF the knowledge store query fails, THEN THE system SHALL
call `consolidate_findings()` with an empty `false_positives` list
(fail-open).

[110-REQ-6.E2] IF `false_positives` is empty or None, THEN THE system SHALL
not modify the critic system prompt (no empty section appended).

### Requirement 7: Configuration

**User Story:** As a night-shift operator, I want to tune the similarity
threshold, so that I can control the sensitivity of near-duplicate detection.

#### Acceptance Criteria

[110-REQ-7.1] THE system SHALL add a `similarity_threshold` field to
`NightShiftConfig` with type `float`, default `0.85`, clamped to `[0.0, 1.0]`.

[110-REQ-7.2] WHEN `filter_known_duplicates()` or `filter_ignored()` is
called from the engine, THE system SHALL pass the configured
`similarity_threshold` value from `NightShiftConfig`.

#### Edge Cases

[110-REQ-7.E1] IF `similarity_threshold` is set to `0.0` in configuration,
THEN THE system SHALL treat all non-zero similarities as matches (aggressive
dedup — effectively suppresses all findings that have any embedding).

[110-REQ-7.E2] IF `similarity_threshold` is set to `1.0` in configuration,
THEN THE system SHALL only match identical embeddings (effectively disabling
similarity matching, leaving fingerprint-only dedup).
