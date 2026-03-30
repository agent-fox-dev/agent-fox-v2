# Requirements Document

## Introduction

Specification for the `agent-fox dump` CLI command, which exports knowledge
store data in Markdown or JSON format. The command provides two mutually
exclusive export modes: memory summary (`--memory`) and full database dump
(`--db`).

## Glossary

- **Knowledge store**: The DuckDB database at `.agent-fox/knowledge.duckdb`
  that holds facts, session outcomes, embeddings, and other structured data.
- **Memory summary**: A Markdown document (`docs/memory.md`) listing all
  active facts grouped by category (gotchas, patterns, decisions, etc.).
- **Database dump**: A Markdown document (`.agent-fox/knowledge_dump.md`)
  containing every table in the knowledge store rendered as Markdown tables.
- **Fact**: A structured learning extracted from coding sessions, stored in
  the `memory_facts` table with content, category, spec name, and confidence.
- **Global `--json` flag**: The existing `--json` flag on the `agent-fox` CLI
  group that switches output to structured JSON.

## Requirements

### Requirement 1: Command Registration

**User Story:** As a developer, I want a `dump` subcommand available in the
`agent-fox` CLI, so that I can export knowledge store data on demand.

#### Acceptance Criteria

1. [49-REQ-1.1] THE CLI SHALL register a `dump` subcommand under the main
   `agent-fox` command group.
2. [49-REQ-1.2] WHEN `agent-fox dump` is invoked without `--memory` or
   `--db`, THE CLI SHALL print an error message indicating that one flag is
   required and exit with code 1.

#### Edge Cases

1. [49-REQ-1.E1] WHEN both `--memory` and `--db` are provided, THE CLI SHALL
   print an error message indicating the flags are mutually exclusive and exit
   with code 1.

### Requirement 2: Memory Export (`--memory`)

**User Story:** As a developer, I want to regenerate `docs/memory.md` from
the database on demand, so that I can refresh the memory file without running
a full orchestrator session.

#### Acceptance Criteria

1. [49-REQ-2.1] WHEN `--memory` is provided, THE command SHALL read all
   active facts from the knowledge store and write them to `docs/memory.md`
   grouped by category, using the same format as `render_summary()`.
2. [49-REQ-2.2] WHEN `--memory` is provided AND the global `--json` flag is
   active, THE command SHALL write all active facts to `docs/memory.json` as
   a JSON object with a `facts` array and a `generated` ISO-8601 timestamp.
3. [49-REQ-2.3] WHEN `--memory` is provided, THE command SHALL print a
   confirmation message to stderr indicating the output file path and fact
   count.

#### Edge Cases

1. [49-REQ-2.E1] IF the knowledge store contains no facts, THEN THE command
   SHALL write an empty-state file (empty Markdown summary or JSON with an
   empty `facts` array) and print a warning to stderr.

### Requirement 3: Database Dump (`--db`)

**User Story:** As a developer, I want to dump the full knowledge database to
a file, so that I can inspect all stored data without running SQL queries
manually.

#### Acceptance Criteria

1. [49-REQ-3.1] WHEN `--db` is provided, THE command SHALL discover all
   tables in the knowledge store and write each table's contents to
   `.agent-fox/knowledge_dump.md` as Markdown tables with headers, column
   names, and data rows.
2. [49-REQ-3.2] WHEN `--db` is provided AND the global `--json` flag is
   active, THE command SHALL write all tables to
   `.agent-fox/knowledge_dump.json` as a JSON object with a `tables` dict
   (keyed by table name, values are arrays of row objects) and a `generated`
   ISO-8601 timestamp.
3. [49-REQ-3.3] WHEN `--db` is provided, THE command SHALL print a
   confirmation message to stderr indicating the output file path and table
   count.
4. [49-REQ-3.4] WHEN `--db` is provided, THE command SHALL truncate cell
   values longer than 120 characters in the Markdown output and escape pipe
   characters.

#### Edge Cases

1. [49-REQ-3.E1] IF the knowledge store contains no tables, THEN THE command
   SHALL print a warning to stderr and exit with code 1.

### Requirement 4: Database Availability

**User Story:** As a developer, I want a clear error when the database is
missing, so that I know to run `agent-fox code` first.

#### Acceptance Criteria

1. [49-REQ-4.1] IF the knowledge store file does not exist at the expected
   path, THEN THE command SHALL print an error message to stderr and exit
   with code 1.

### Requirement 5: Read-Only Access

**User Story:** As a developer, I want the dump command to be safe to run at
any time, including while an orchestrator session is active.

#### Acceptance Criteria

1. [49-REQ-5.1] THE command SHALL open the knowledge store in read-only mode.
