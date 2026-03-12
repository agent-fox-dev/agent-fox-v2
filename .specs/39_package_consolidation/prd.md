# PRD: Package Consolidation -- Merge memory/ into knowledge/

## Problem

The agent-fox codebase has two overlapping packages for knowledge management:

- `agent_fox/memory/` (7 files): JSONL fact store, extraction, compaction,
  filtering, rendering, types
- `agent_fox/knowledge/` (14 files): DuckDB store, migrations, review findings,
  causal graphs, embeddings, search, sinks, ingest

The boundary between them is blurry. The memory package dual-writes to DuckDB
(a knowledge concern), and the knowledge package reads from JSONL (a memory
concern). Import paths cross between the two packages in both directions.
Several modules import from both `agent_fox.memory` and `agent_fox.knowledge`
in the same file.

This split creates confusion about where new functionality belongs, increases
the number of cross-package imports, and makes the architecture harder to
reason about.

## Source

GitHub issue #142: "refactor: merge knowledge/ into memory -- unified state
machine". The consolidation target was changed from `memory/` to `knowledge/`
as an architectural decision: DuckDB is now the primary store, and the package
name `knowledge` better describes the unified system's purpose.

## Goals

1. Consolidate all modules from `agent_fox/memory/` into `agent_fox/knowledge/`.
2. Make DuckDB the primary read path for facts (replacing JSONL reads).
3. Demote JSONL to export-only (written at session end, never read as primary).
4. Introduce `KnowledgeStateMachine` for in-memory fact/finding buffering
   during orchestrator runs.
5. Delete the `agent_fox/memory/` package entirely.

## Scope

**In:**

- Move 6 modules from `memory/` to `knowledge/` with renames:
  - `memory/memory.py` -> `knowledge/store.py`
  - `memory/types.py` -> `knowledge/facts.py`
  - `memory/filter.py` -> `knowledge/filtering.py`
  - `memory/render.py` -> `knowledge/rendering.py`
  - `memory/extraction.py` -> `knowledge/extraction.py` (name preserved)
  - `memory/compaction.py` -> `knowledge/compaction.py` (name preserved)
- Update all imports across the codebase (production and test code)
- Re-export public APIs from `agent_fox.knowledge.__init__`
- Delete `agent_fox/memory/` package
- Make `load_all_facts()` and `load_facts_by_spec()` read from DuckDB
- JSONL write at session end and compaction only (export format)
- `KnowledgeStateMachine` for in-memory buffering with flush points

**Out:**

- Audit log (spec 40)
- New DuckDB tables or schema migrations (except adjusting existing DDL if
  needed for moved code)
- Duration ordering, predictive features (separate specs)
- Reporting migration to DuckDB (spec 40)
- New features -- this is a structural refactor

## Dependencies

- **Spec 37** (confidence normalization): modifies `memory/types.py` which
  this spec moves. Must be complete first.
- **Spec 38** (DuckDB hardening): modifies `memory/memory.py` which this
  spec moves. Must be complete first.

## Module Mapping

| Source (memory/) | Target (knowledge/) | Rationale |
|------------------|---------------------|-----------|
| `types.py` | `facts.py` | Contains `Fact`, `Category`, confidence utils -- "facts" is more specific |
| `memory.py` | `store.py` | Contains `MemoryStore`, JSONL I/O -- "store" describes the role |
| `filter.py` | `filtering.py` | Avoids shadowing Python's built-in `filter` |
| `render.py` | `rendering.py` | Consistent with `filtering.py` naming |
| `extraction.py` | `extraction.py` | Name is already clear |
| `compaction.py` | `compaction.py` | Name is already clear |

## Clarifications

1. The `MemoryStore` class keeps its name (renaming it would be a separate
   refactor with no functional benefit).
2. JSONL files on disk (`.agent-fox/memory.jsonl`) keep their current paths --
   this spec changes code structure, not file formats or on-disk locations.
3. The `KnowledgeStateMachine` is an in-memory buffer, not a persistent state
   machine. It accumulates facts and findings during a run and flushes them
   to DuckDB at defined sync points.
4. Test files under `tests/unit/memory/` and `tests/property/memory/` will be
   moved to `tests/unit/knowledge/` and `tests/property/knowledge/` respectively.
