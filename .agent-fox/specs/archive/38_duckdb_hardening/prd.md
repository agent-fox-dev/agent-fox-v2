# PRD: DuckDB Hardening

## Problem

DuckDB connectivity is treated as optional throughout the agent-fox codebase.
When DuckDB is unavailable, the system silently degrades: causal context is
lost, session outcomes are not persisted, adaptive routing falls back to
heuristics, and review findings are not queryable. This silent degradation
makes debugging difficult and leads to underreporting of costs and reduced
context quality — problems that are hard to diagnose because no error is
raised.

The system has 15+ locations where `KnowledgeDB | None` parameters, `if conn
is None: return` guards, and `except Exception: logger.warning(...)` patterns
silently skip DuckDB-dependent functionality.

## Source

Extracted from research spike `docs/brainstorm/predictive-planning-and-knowledge.md`
(issue #146). User clarification: "DuckDB is a hard requirement. Look for other
parts in the code where DuckDB is a soft requirement and make it a hard one. If
DuckDB is not reachable, abort with an error."

## Goals

1. Make DuckDB a hard requirement — if it cannot be opened, abort with a clear
   error message.
2. Remove all `KnowledgeDB | None` and `conn | None` optional patterns.
3. Remove silent degradation (try/except that swallows DuckDB errors).
4. Ensure all tests that need DuckDB use a proper test fixture.

## Scope

**In:**
- `open_knowledge_store()` — raise on failure instead of returning None
- All `KnowledgeDB | None` parameters → `KnowledgeDB` (required)
- All `duckdb.DuckDBPyConnection | None` parameters → required
- All `if knowledge_db is None: return` guards → remove
- All try/except blocks that swallow DuckDB errors → let errors propagate
- Test infrastructure: shared DuckDB fixture for tests that need it

**Out:**
- DuckDB performance optimization
- Schema changes (handled by other specs)
- New DuckDB features or queries

## Affected Locations

| File | Pattern | Change |
|------|---------|--------|
| `knowledge/db.py` | `open_knowledge_store()` returns None | Raise on failure |
| `cli/code.py` | 4 locations with None checks | Remove guards |
| `engine/session_lifecycle.py` | Optional `knowledge_db` param | Make required |
| `engine/knowledge_harvest.py` | 3 locations with None guards | Remove guards |
| `memory/memory.py` | Optional `db_conn` param | Make required |
| `session/prompt.py` | Optional `conn` param | Make required |
| `routing/assessor.py` | Optional `db` param | Make required |
| `knowledge/duckdb_sink.py` | Try/except in all record methods | Let errors propagate |
| `fix/analyzer.py` | 2 try/except blocks | Let errors propagate |

## Clarifications

1. No `--no-knowledge` escape hatch. DuckDB is mandatory for all operations.
2. JSONL remains the primary store for facts (append-only log). DuckDB is
   mandatory as the index/query layer. Both must succeed on write.
3. Tests that previously skipped DuckDB will use an in-memory DuckDB fixture.
4. Clear error message on startup failure:
   `"Knowledge store initialization failed: {error}. DuckDB is required."`
