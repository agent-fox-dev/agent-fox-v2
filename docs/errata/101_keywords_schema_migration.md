# Errata: 101_knowledge_onboarding — Keywords Column Requires Schema Migration

**Spec:** 101_knowledge_onboarding
**Date:** 2026-04-14
**Status:** Active

## Summary

The design document (design.md §Operational Readiness) states:

> "No schema migrations needed — all tables already exist from Spec 95 and
> the base knowledge schema."

This claim is incorrect. The fingerprint-based deduplication strategy
(101-REQ-4.E3, 101-REQ-5.6, 101-REQ-6.6, 101-REQ-8.2) requires that
each fact's `keywords` list be persisted in DuckDB so that
`_is_mining_fact_exists()` can query for fingerprint keywords like
`onboard:fragile:src/hot.py`. The `memory_facts` table had no `keywords`
column in the existing schema.

## Resolution

A migration (v9) was added to `agent_fox/knowledge/migrations.py` that adds:

```sql
ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS keywords TEXT[] DEFAULT []
```

The `KnowledgeDB._initialize_schema()` in `db.py` was also updated to
include `keywords TEXT[] DEFAULT []` in the CREATE TABLE DDL so new
databases are created with the column from the start.

`MemoryStore._write_to_duckdb()` now stores the `keywords` field, and
`load_all_facts()` / `load_facts_by_spec()` now SELECT and populate it.

`_is_mining_fact_exists()` uses DuckDB's `list_contains(keywords, ?)` to
check for fingerprint presence.

## Impact

- Existing databases will receive the `keywords` column via migration v9
  when they next open via `KnowledgeDB.open()`.
- Facts written before this change will have `keywords = []` (the column
  default), which is correct — they have no fingerprints and will not
  interfere with deduplication logic.
- No data loss or backward-incompatible change is introduced.
