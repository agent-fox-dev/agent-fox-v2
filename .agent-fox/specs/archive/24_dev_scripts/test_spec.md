# Test Specification: Developer Utility Scripts

## Overview

No automated tests for this spec. This is a developer utility script validated
by manual execution against a real knowledge store.

## Manual Verification

1. Run `python scripts/dump_knowledge.py` from the repo root.
2. Confirm `.agent-fox/knowledge_dump.md` is created.
3. Confirm all tables (except `memory_embeddings`) have sections.
4. Confirm row counts match actual table contents.
5. Confirm empty tables show "No rows." instead of an empty table.
6. Delete `.agent-fox/knowledge.duckdb` temporarily and confirm the script
   prints an error and exits with code 1.

## Coverage Matrix

| Requirement | Verification | Type |
|-------------|-------------|------|
| 24-REQ-1.1 | Directory exists | manual |
| 24-REQ-2.1 | Script opens DB via KnowledgeDB | manual |
| 24-REQ-2.2 | All tables except embeddings dumped | manual |
| 24-REQ-2.3 | Sections have heading, count, table | manual |
| 24-REQ-2.4 | DB connection closed | manual |
| 24-REQ-2.E1 | Missing DB prints error, exit 1 | manual |
| 24-REQ-2.E2 | Empty tables show "No rows." | manual |
| 24-REQ-3.1 | Imports KnowledgeDB, KnowledgeConfig | manual (code review) |
| 24-REQ-3.2 | No reimplemented logic | manual (code review) |
