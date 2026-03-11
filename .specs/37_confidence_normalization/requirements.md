# Requirements Document

## Introduction

The agent-fox codebase uses two incompatible confidence representations: string
enums (`"high"`, `"medium"`, `"low"`) in the memory/knowledge system and floats
(`[0.0, 1.0]`) in the routing/assessment system. This spec normalizes all
confidence values to `float [0.0, 1.0]`, enabling threshold-based filtering,
machine learning integration, and consistent cross-system comparisons.

## Glossary

| Term | Definition |
|------|------------|
| **Confidence** | A floating-point score in `[0.0, 1.0]` expressing how certain the system is about a fact, assessment, pattern, or improvement. `0.0` = no confidence, `1.0` = complete certainty. |
| **Fact** | A structured knowledge item extracted from session transcripts, stored in JSONL and DuckDB. |
| **Memory Facts** | The `memory_facts` DuckDB table that indexes facts for search and causal traversal. |
| **ConfidenceLevel** | The current `StrEnum` in `memory/types.py` with values `"high"`, `"medium"`, `"low"`. To be replaced by float representation. |
| **Canonical Mapping** | The default string-to-float conversion: `"high"` → `0.9`, `"medium"` → `0.6`, `"low"` → `0.3`. |
| **OracleAnswer** | A structured response from the knowledge query system, containing a confidence score. |
| **Pattern** | A recurring observation detected from memory facts, with a confidence score derived from occurrence count. |
| **Improvement** | A code improvement suggestion from the auto-improve analyzer, with a confidence score. |

## Requirements

### Requirement 1: Fact Confidence as Float

**User Story:** As a system component, I want all fact confidence values stored
as floats, so that I can apply threshold-based filtering and statistical
comparisons.

#### Acceptance Criteria

1. [37-REQ-1.1] WHEN a new fact is extracted from a session transcript, THE system SHALL store its `confidence` field as a `float` in the range `[0.0, 1.0]`.
2. [37-REQ-1.2] WHEN the LLM extraction returns a string confidence value (`"high"`, `"medium"`, `"low"`), THE system SHALL convert it to a float using the canonical mapping: `"high"` → `0.9`, `"medium"` → `0.6`, `"low"` → `0.3`.
3. [37-REQ-1.3] WHEN the LLM extraction returns a numeric confidence value, THE system SHALL clamp it to `[0.0, 1.0]`.
4. [37-REQ-1.4] THE system SHALL update the `Fact` dataclass to use `confidence: float` with a default of `0.6`.

#### Edge Cases

1. [37-REQ-1.E1] IF the LLM returns an unrecognized confidence string, THEN THE system SHALL default to `0.6` and log a warning.
2. [37-REQ-1.E2] IF the LLM returns a confidence value outside `[0.0, 1.0]`, THEN THE system SHALL clamp it to the nearest bound (`0.0` or `1.0`).

### Requirement 2: DuckDB Schema Migration

**User Story:** As a system operator, I want the DuckDB schema to store
confidence as a float, so that SQL queries can use numeric comparisons and
thresholds.

#### Acceptance Criteria

1. [37-REQ-2.1] WHEN the knowledge store opens, THE system SHALL apply a migration that converts `memory_facts.confidence` from `TEXT` to `FLOAT`.
2. [37-REQ-2.2] WHEN migrating existing rows, THE system SHALL convert string values using the canonical mapping and default unrecognized values to `0.6`.
3. [37-REQ-2.3] THE system SHALL preserve all existing fact data during migration (no data loss).

#### Edge Cases

1. [37-REQ-2.E1] IF a row has a `NULL` confidence value, THEN THE system SHALL set it to `0.6` during migration.

### Requirement 3: JSONL Backward Compatibility

**User Story:** As a system operator, I want existing JSONL memory files with
string confidence values to continue loading correctly after the upgrade.

#### Acceptance Criteria

1. [37-REQ-3.1] WHEN loading facts from JSONL, THE system SHALL accept both float and string confidence values.
2. [37-REQ-3.2] WHEN a string confidence value is encountered during JSONL loading, THE system SHALL convert it using the canonical mapping.
3. [37-REQ-3.3] WHEN writing facts to JSONL, THE system SHALL write confidence as a float.

### Requirement 4: Knowledge Query Confidence

**User Story:** As a knowledge consumer, I want oracle answers and pattern
detections to use float confidence, so that downstream systems can apply
consistent thresholds.

#### Acceptance Criteria

1. [37-REQ-4.1] THE system SHALL update `OracleAnswer.confidence` to `float` type.
2. [37-REQ-4.2] WHEN determining oracle answer confidence, THE system SHALL compute a float based on result count and similarity scores.
3. [37-REQ-4.3] THE system SHALL update `Pattern.confidence` to `float` type.
4. [37-REQ-4.4] WHEN assigning pattern confidence, THE system SHALL use occurrence-based mapping: `5+` → `0.9`, `3-4` → `0.7`, `2` → `0.4`.

### Requirement 5: Auto-Improve Analyzer Confidence

**User Story:** As the auto-improve system, I want improvement suggestions to
use float confidence, so that filtering thresholds can be tuned precisely.

#### Acceptance Criteria

1. [37-REQ-5.1] THE system SHALL update `Improvement.confidence` to `float` type.
2. [37-REQ-5.2] WHEN the LLM returns a string confidence for an improvement, THE system SHALL convert it using the canonical mapping.
3. [37-REQ-5.3] WHEN filtering low-confidence improvements, THE system SHALL exclude items with `confidence < 0.5` (replacing the current `!= "low"` check).

### Requirement 6: Rendering

**User Story:** As a developer reading rendered output, I want confidence
displayed in a human-readable format alongside facts.

#### Acceptance Criteria

1. [37-REQ-6.1] WHEN rendering a fact for display, THE system SHALL format confidence as a two-decimal float (e.g., `confidence: 0.90`).
