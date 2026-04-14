# Errata: Memory JSONL Removal (Spec 104)

## Affected Specs

- Spec 104 (`104_adaptive_retrieval`) — triggers the removal
- Spec 39 (`39_knowledge_extraction`) — introduced JSONL as primary fact store
- Spec 96 (`96_knowledge_consolidation`) — uses JSONL export after compaction

## Divergence: memory.jsonl Removed Entirely

With the introduction of the `AdaptiveRetriever` (spec 104), DuckDB's
`memory_facts` table is the sole authoritative fact store. All retrieval
queries go through DuckDB directly. The JSONL file (`.agent-fox/memory.jsonl`)
served three purposes — all now obsolete:

1. **Fallback when DuckDB is locked** — `read_all_facts()` had a three-tier
   fallback chain: provided connection -> read-only DuckDB -> JSONL file. With
   DuckDB as the sole source, the JSONL fallback is removed. If DuckDB is
   unavailable, the retriever returns empty results rather than falling back
   to a stale snapshot.

2. **Backup/portability** — Facts were exported to JSONL after compaction,
   barrier syncs, and cleanup. This was a pre-DuckDB artifact from when
   JSONL was the primary store. DuckDB file-based storage provides the
   same portability.

3. **Git-tracked state** — `memory.jsonl` was committed alongside
   `state.jsonl`. The JSONL file is no longer tracked.

### Affected Modules

| Module | Change |
|--------|--------|
| `core/paths.py` | Remove `MEMORY_PATH` constant |
| `knowledge/store.py` | Remove `export_facts_to_jsonl`, `load_facts_from_jsonl`, `append_facts`, `_write_jsonl`; simplify `read_all_facts` fallback |
| `knowledge/compaction.py` | Remove JSONL export step |
| `engine/run.py` | Remove JSONL export from `_barrier_sync` and `_cleanup_infrastructure` |
| `engine/barrier.py` | Remove JSONL export from barrier sync |
| `engine/reset.py` | Remove `memory_path` parameter threading |
| `cli/reset.py` | Remove `memory_path` construction and passing |
| `workspace/init_project.py` | Stop creating empty `memory.jsonl` seed file |
| `.gitignore` | Remove `!.agent-fox/memory.jsonl` exception |
| `AGENTS.md`, `_templates/agents_md.md` | Remove `memory.jsonl` from git-tracked state files |

### docs/memory.md Unchanged

`docs/memory.md` continues to be generated at end-of-run from DuckDB for
external tool consumption (Cursor, Codex, etc.). Agent-fox's own sessions
do not read this file — the adaptive retriever queries DuckDB directly.

## Impact

- Tests referencing `memory.jsonl` need updating or removal (34+ test files)
- The `read_all_facts` function signature changes (no `jsonl_path` parameter)
- Hard reset no longer needs `memory_path` parameter
- Git commits no longer include `.agent-fox/memory.jsonl`
- The `DEFAULT_MEMORY_PATH` constant in `store.py` is removed
