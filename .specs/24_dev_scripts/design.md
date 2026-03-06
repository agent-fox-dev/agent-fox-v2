# Design Document: Developer Utility Scripts

## Overview

A `scripts/` directory at the repo root containing standalone Python scripts
for developer debugging. The first script, `dump_knowledge.py`, exports the
DuckDB knowledge store to a Markdown file using the existing `agent_fox`
module APIs.

## Architecture

```
scripts/
  dump_knowledge.py      # Knowledge store -> Markdown dump
```

No new modules are added to `agent_fox/`. The script is a thin consumer of
existing APIs.

### Module Responsibilities

1. `scripts/dump_knowledge.py` — Opens the knowledge store via `KnowledgeDB`,
   queries all tables (except `memory_embeddings`), formats results as
   Markdown, writes to `.agent-fox/knowledge_dump.md`.

## Components and Interfaces

### dump_knowledge.py

```python
TABLES_TO_DUMP: list[str]
# All tables from the schema except memory_embeddings:
# schema_version, memory_facts, session_outcomes, fact_causes,
# tool_calls, tool_errors

def dump_table(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    """Query all rows from table, return formatted Markdown section."""

def main() -> None:
    """Entry point: open DB, dump tables, write file, close DB."""
```

### Reused from agent_fox

- `agent_fox.knowledge.db.KnowledgeDB` — DB lifecycle (open/close, schema init)
- `agent_fox.core.config.KnowledgeConfig` — Default store path

## Data Models

### Output Format

```markdown
# Knowledge Store Dump

Generated: 2026-03-06T10:30:00

## schema_version (1 row)

| version | applied_at | description |
|---------|------------|-------------|
| 1 | 2026-03-01 12:00:00 | initial schema |

## memory_facts (42 rows)

| id | content | category | spec_name | session_id | commit_sha | confidence | created_at | superseded_by |
|----|---------|----------|-----------|------------|------------|------------|------------|---------------|
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

## session_outcomes (15 rows)

...

## fact_causes (8 rows)

...

## tool_calls (0 rows)

No rows.

## tool_errors (0 rows)

No rows.
```

## Correctness Properties

### Property 1: All Non-Embedding Tables Dumped

*For any* knowledge store with N tables, the script SHALL produce a Markdown
section for every table except `memory_embeddings`.

**Validates: Requirements 2.2**

### Property 2: Row Count Accuracy

*For any* table with R rows, the section heading SHALL display the count R
and the Markdown table SHALL contain exactly R data rows.

**Validates: Requirements 2.3**

### Property 3: Graceful Missing DB

*For any* execution where the DB file does not exist, the script SHALL exit
with code 1 and print a message to stderr without raising an unhandled
exception.

**Validates: Requirements 2.E1**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| DB file missing | Print message to stderr, exit(1) | 24-REQ-2.E1 |
| Empty table | Render "No rows." instead of table | 24-REQ-2.E2 |

## Technology Stack

- Python 3.12+
- `duckdb` (via `agent_fox.knowledge.db`)
- No additional dependencies

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. The script runs successfully against a real knowledge store
3. Output Markdown is well-formed and readable
4. No linter warnings introduced
5. Code is committed on a feature branch and pushed to remote

## Testing Strategy

This is a developer utility script — no automated tests are required.
Manual verification: run the script against a real `.agent-fox/knowledge.duckdb`
and inspect the output.
