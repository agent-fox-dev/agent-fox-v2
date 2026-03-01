# Requirements Document: Structured Memory

## Introduction

This document specifies the structured memory system for agent-fox v2: fact
extraction from session transcripts, fact categorization, JSONL-based storage,
context selection for upcoming sessions, knowledge base compaction, and
human-readable summary generation. It depends on the core foundation (spec 01)
for configuration, errors, and model resolution, and on the session runner
(spec 03) for the `SessionOutcome` that triggers extraction.

## Glossary

| Term | Definition |
|------|-----------|
| Fact | A structured unit of knowledge extracted from a coding session, containing content, category, keywords, and metadata |
| Category | One of six classification labels for facts: gotcha, pattern, decision, convention, anti_pattern, fragile_area |
| Confidence | A fact's reliability level: high, medium, or low |
| Supersession | When a newer fact replaces an older fact on the same topic, creating a chain via UUID reference |
| Content hash | SHA-256 hash of a fact's content string, used for deduplication |
| Context selection | The process of choosing relevant facts to include in a coding session's working context |
| Context budget | The maximum number of facts (50) that may be included in a session's context |
| Compaction | The process of removing duplicate and superseded facts from the knowledge base |
| Knowledge base | The JSONL file at `.agent-fox/memory.jsonl` containing all stored facts |
| Memory summary | The human-readable markdown file at `docs/memory.md` summarizing all facts by category |
| SIMPLE model | The lowest-cost AI model tier (Haiku-class), used for fact extraction |
| Extraction prompt | The structured prompt sent to the SIMPLE model requesting JSON-formatted fact output |

## Requirements

### Requirement 1: Fact Extraction

**User Story:** As a developer, I want agent-fox to automatically extract
structured learnings from completed coding sessions so that knowledge is
preserved for future sessions.

#### Acceptance Criteria

1. [05-REQ-1.1] AFTER a successful coding session, THE system SHALL send the
   session transcript to the configured memory extraction model (default:
   SIMPLE tier) with a prompt requesting structured JSON output.

2. [05-REQ-1.2] THE extraction prompt SHALL request the following fields for
   each extracted fact: content (description of the learning), category (one
   of the six defined categories), confidence (high, medium, or low), and
   keywords (list of relevant terms).

3. [05-REQ-1.3] THE system SHALL assign each extracted fact a unique UUID, the
   source spec name, and an ISO 8601 timestamp.

#### Edge Cases

1. [05-REQ-1.E1] IF the extraction model returns invalid JSON or an
   unparseable response, THEN THE system SHALL log a warning and skip fact
   extraction for that session without raising an error.

2. [05-REQ-1.E2] IF the extraction model returns zero facts, THEN THE system
   SHALL log a debug message and continue without error.

---

### Requirement 2: Fact Categories

**User Story:** As a developer, I want extracted facts classified into
meaningful categories so that I can understand what type of knowledge agent-fox
has accumulated.

#### Acceptance Criteria

1. [05-REQ-2.1] THE system SHALL recognize exactly six fact categories:
   `gotcha` (things that tripped up the agent), `pattern` (successful
   approaches), `decision` (architectural choices made), `convention` (project
   style rules), `anti_pattern` (approaches to avoid), and `fragile_area`
   (code regions sensitive to change).

2. [05-REQ-2.2] WHEN an extracted fact specifies a category not in the
   defined set, THE system SHALL log a warning and default to `gotcha`.

---

### Requirement 3: JSONL Storage

**User Story:** As a developer, I want facts stored in a simple, append-only
format that is git-trackable and human-inspectable so that the knowledge base
is transparent and portable.

#### Acceptance Criteria

1. [05-REQ-3.1] THE system SHALL store facts in `.agent-fox/memory.jsonl`,
   one JSON object per line.

2. [05-REQ-3.2] Each stored fact SHALL contain all fields defined by the Fact
   data model: id (UUID), content, category, spec_name, keywords, confidence,
   created_at (ISO 8601), and supersedes (optional UUID).

3. [05-REQ-3.3] THE system SHALL append new facts to the end of the file
   without modifying existing lines.

#### Edge Cases

1. [05-REQ-3.E1] IF the memory file does not exist when facts are appended,
   THEN THE system SHALL create it.

2. [05-REQ-3.E2] IF the memory file cannot be written (permission denied, disk
   full), THEN THE system SHALL log an error and continue without raising an
   exception to the session runner.

---

### Requirement 4: Context Selection

**User Story:** As a developer, I want agent-fox to include relevant prior
learnings in each coding session's context so that the agent benefits from
accumulated knowledge.

#### Acceptance Criteria

1. [05-REQ-4.1] BEFORE each coding session, THE system SHALL select stored
   facts relevant to the current task by matching on spec_name (exact match)
   and keyword overlap with the task description.

2. [05-REQ-4.2] THE system SHALL rank matched facts by a relevance score
   computed as: keyword match count plus a recency bonus (more recently created
   facts score higher).

3. [05-REQ-4.3] THE system SHALL return at most 50 facts (the context budget),
   selecting the top-scoring facts when more than 50 match.

#### Edge Cases

1. [05-REQ-4.E1] IF no facts match the current task, THEN THE system SHALL
   return an empty list without error.

2. [05-REQ-4.E2] IF the memory file does not exist or is empty, THEN THE
   system SHALL return an empty list without error.

---

### Requirement 5: Knowledge Base Compaction

**User Story:** As a developer, I want to compact the knowledge base on demand
to remove duplicates and outdated entries so that context selection remains
efficient and relevant.

#### Acceptance Criteria

1. [05-REQ-5.1] WHEN the user runs `agent-fox compact`, THE system SHALL
   remove duplicate facts identified by content hash (SHA-256 of the content
   string), keeping the earliest instance.

2. [05-REQ-5.2] WHEN the user runs `agent-fox compact`, THE system SHALL
   resolve supersession chains: if fact B supersedes fact A, and fact C
   supersedes fact B, only fact C is retained.

3. [05-REQ-5.3] THE system SHALL rewrite the JSONL file in place after
   compaction, preserving only the surviving facts.

#### Edge Cases

1. [05-REQ-5.E1] IF the memory file does not exist or is empty, THEN THE
   system SHALL report that no compaction was needed and exit successfully.

2. [05-REQ-5.E2] WHEN compaction is run multiple times consecutively, THE
   system SHALL produce the same result (idempotency).

---

### Requirement 6: Human-Readable Summary

**User Story:** As a developer, I want a human-readable summary of all
accumulated knowledge organized by category so that I can review what agent-fox
has learned at any time.

#### Acceptance Criteria

1. [05-REQ-6.1] THE system SHALL generate a markdown file at `docs/memory.md`
   containing all facts organized by category, with section headings for each
   category.

2. [05-REQ-6.2] Each fact entry in the summary SHALL include the fact content,
   the source spec name, and the confidence level.

3. [05-REQ-6.3] THE system SHALL regenerate the summary at sync barriers
   (REQ-050) and when invoked on demand.

#### Edge Cases

1. [05-REQ-6.E1] IF the `docs/` directory does not exist, THEN THE system
   SHALL create it before writing the summary.

2. [05-REQ-6.E2] IF there are no facts in the knowledge base, THEN THE system
   SHALL generate a summary file with a message indicating no facts have been
   recorded yet.
