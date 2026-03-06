# PRD: Developer Utility Scripts

## Problem

Developers and coding agents working on agent-fox need a way to inspect the
contents of the DuckDB knowledge store (`knowledge.duckdb`). Currently there is
no quick way to see what facts, session outcomes, causal links, or tool usage
data the system has accumulated — you have to write ad-hoc DuckDB queries.

## Solution

Create a `scripts/` directory at the repo root for developer utility scripts.
The first script dumps the entire knowledge store (minus embedding vectors)
into a well-structured, human-readable Markdown file at
`.agent-fox/knowledge_dump.md`.

Scripts must reuse code from the `agent_fox` module (e.g., `KnowledgeDB`,
`KnowledgeConfig`, spec parser) rather than reimplementing logic.

## Requirements

1. A `scripts/` directory at the repo root for developer utility scripts.
2. A Python script `scripts/dump_knowledge.py` that:
   - Auto-detects the knowledge store at the default path
     (`.agent-fox/knowledge.duckdb` via `KnowledgeConfig`).
   - Opens the DB using `KnowledgeDB` from `agent_fox.knowledge.db`.
   - Dumps all tables **except** `memory_embeddings` to Markdown.
   - Writes output to `.agent-fox/knowledge_dump.md`.
   - Structures the output with clear headings, row counts, and readable tables.
   - Exits gracefully if the DB file does not exist.

## Non-Goals

- No CLI framework (argparse/click) — keep it simple, just run with `python`.
- No tests required — this is a developer utility, not production code.
- No additional scripts in this spec (future scripts will be added ad-hoc).

## Clarifications

- Embedding vectors (384-float arrays) are excluded because they are not
  human-readable and would bloat the output.
- The script writes to `.agent-fox/knowledge_dump.md` which is already
  gitignored via the `.agent-fox/` directory.
- The script reuses `KnowledgeConfig` defaults for auto-detection of the DB path.
