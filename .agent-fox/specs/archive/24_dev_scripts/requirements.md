# Requirements Document

## Introduction

Developer utility scripts for inspecting agent-fox internals. The first script
dumps the DuckDB knowledge store to a human-readable Markdown file.

## Glossary

- **Knowledge store**: The DuckDB database at `.agent-fox/knowledge.duckdb`
  that persists facts, session outcomes, causal links, and tool usage data.
- **Dump**: A full export of all table contents (excluding embedding vectors)
  into a structured Markdown document.

## Requirements

### Requirement 1: Scripts Directory

**User Story:** As a developer, I want a conventional location for utility
scripts, so that I can find and add debug tools easily.

#### Acceptance Criteria

1. 24-REQ-1.1: THE project SHALL contain a `scripts/` directory at the
   repository root.

### Requirement 2: Knowledge Store Dump

**User Story:** As a developer, I want to dump the knowledge store contents
to a readable file, so that I can inspect what data the system has accumulated.

#### Acceptance Criteria

1. 24-REQ-2.1: WHEN the script `scripts/dump_knowledge.py` is executed,
   THE script SHALL open the knowledge store using `KnowledgeDB` from
   `agent_fox.knowledge.db` with default `KnowledgeConfig` settings.

2. 24-REQ-2.2: WHEN the knowledge store is open, THE script SHALL query
   every table except `memory_embeddings` and write the results to
   `.agent-fox/knowledge_dump.md`.

3. 24-REQ-2.3: THE script SHALL format each table as a Markdown section with:
   a heading containing the table name, the row count, and a Markdown table
   of all rows.

4. 24-REQ-2.4: THE script SHALL close the database connection after writing
   the dump file.

#### Edge Cases

1. 24-REQ-2.E1: IF the knowledge store file does not exist, THEN THE script
   SHALL print an informative message to stderr and exit with code 1.

2. 24-REQ-2.E2: IF a table is empty, THEN THE script SHALL render the table
   section with a "No rows." note instead of an empty table.

### Requirement 3: Module Reuse

**User Story:** As a developer, I want scripts to reuse existing module code,
so that logic is not duplicated and scripts stay in sync with the codebase.

#### Acceptance Criteria

1. 24-REQ-3.1: THE script SHALL import and use `KnowledgeDB` and
   `KnowledgeConfig` from the `agent_fox` package for database access.

2. 24-REQ-3.2: THE script SHALL NOT reimplement database connection logic,
   schema knowledge, or configuration loading that already exists in
   `agent_fox`.
