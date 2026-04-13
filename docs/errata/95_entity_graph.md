# Errata: 95_entity_graph — DuckDB FK Constraint Bug

**Spec:** 95_entity_graph
**Date:** 2026-04-13
**Status:** Active

## Divergence

The `entity_edges` and `fact_entities` tables were designed to use SQL foreign
key constraints referencing `entity_graph(id)` and `memory_facts(id)`
respectively. The migration v8 DDL in the spec (design.md) includes:

```sql
entity_edges.source_id UUID NOT NULL REFERENCES entity_graph(id)
entity_edges.target_id UUID NOT NULL REFERENCES entity_graph(id)
fact_entities.fact_id  UUID NOT NULL REFERENCES memory_facts(id)
fact_entities.entity_id UUID NOT NULL REFERENCES entity_graph(id)
```

The actual implementation **omits these FK constraints** from the DDL.

## Root Cause

DuckDB 1.5.x has a bug where UPDATE statements on a table that is referenced
by FK constraints are incorrectly blocked with a `ConstraintException`, even
when the UPDATE does not modify the referenced primary key column. For example:

```sql
-- entity_edges.source_id references entity_graph.id
-- This UPDATE only changes deleted_at, NOT id — but DuckDB 1.5.x rejects it:
UPDATE entity_graph SET deleted_at = CURRENT_TIMESTAMP WHERE id = '...';
-- Error: Violates foreign key constraint because key "source_id: ..." is still
-- referenced by a foreign key in a different table.
```

This bug was reproduced and confirmed with `duckdb==1.5.1`. The bug makes
soft-delete (`soft_delete_missing`) and restore (`upsert_entities` restoring a
soft-deleted entity) impossible when FK constraints are present on dependent
tables.

## Mitigation

1. FK constraints are **omitted** from the `entity_edges` and `fact_entities`
   table DDL in migration v8.

2. Referential integrity is enforced **at the application layer** in
   `agent_fox/knowledge/entity_store.py`:

   - `upsert_edges`: validates `source_id` and `target_id` exist in
     `entity_graph` before inserting; raises `ValueError` on violation.
   - `create_fact_entity_links`: validates `fact_id` in `memory_facts` and
     `entity_id` in `entity_graph` before inserting; raises `ValueError` on
     violation.

3. Self-referencing edge rejection (`source_id == target_id`) is enforced
   by raising `ValueError` before insertion.

## When to Revisit

If DuckDB is upgraded to a version that fixes this FK UPDATE bug, the
constraints can be re-added to the DDL via a new migration and the manual
validation code in entity_store.py can be removed or simplified.

Track against: https://github.com/duckdb/duckdb/issues (search "foreign key UPDATE bug")
