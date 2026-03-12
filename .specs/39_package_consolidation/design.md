# Design Document: Package Consolidation

## Overview

This design describes the structural refactor that merges `agent_fox/memory/`
into `agent_fox/knowledge/`, makes DuckDB the primary read path for facts,
demotes JSONL to an export format, and introduces `KnowledgeStateMachine` for
buffered writes.

## Architecture

### Package Layout (After)

```
agent_fox/knowledge/
    __init__.py          # Re-exports public API
    compaction.py        # (moved from memory/) dedup + supersession
    db.py                # (existing) KnowledgeDB lifecycle
    duckdb_sink.py       # (existing) SessionSink for DuckDB
    extraction.py        # (moved from memory/) LLM fact extraction
    facts.py             # (moved from memory/types.py) Fact, Category, confidence
    filtering.py         # (moved from memory/filter.py) select_relevant_facts
    rendering.py         # (moved from memory/render.py) markdown summary
    store.py             # (moved from memory/memory.py) MemoryStore, JSONL I/O
    state_machine.py     # (new) KnowledgeStateMachine
    # ... existing knowledge modules unchanged ...
    blocking_history.py
    causal.py
    embeddings.py
    ingest.py
    jsonl_sink.py
    migrations.py
    project_model.py
    query.py
    review_store.py
    search.py
    sink.py
```

### Module Dependency Graph (Simplified)

```
facts.py          <-- no internal deps (leaf module)
    ^
    |
store.py          <-- depends on facts.py, duckdb
    ^
    |
filtering.py      <-- depends on facts.py
extraction.py     <-- depends on facts.py, core.client, core.models
compaction.py     <-- depends on store.py, facts.py
rendering.py      <-- depends on store.py, facts.py
state_machine.py  <-- depends on store.py, facts.py
```

## Interfaces

### `agent_fox.knowledge.facts` (moved from `memory/types.py`)

No API changes. All existing symbols are preserved:

```python
class Category(StrEnum): ...
class ConfidenceLevel(StrEnum): ...  # deprecated
CONFIDENCE_MAP: dict[str, float]
DEFAULT_CONFIDENCE: float
def parse_confidence(value: str | float | int | None) -> float: ...

@dataclass
class Fact:
    id: str
    content: str
    category: str
    spec_name: str
    keywords: list[str]
    confidence: float
    created_at: str
    supersedes: str | None = None
    session_id: str | None = None
    commit_sha: str | None = None
```

### `agent_fox.knowledge.store` (moved from `memory/memory.py`)

#### Changed Functions

```python
def load_all_facts(conn: duckdb.DuckDBPyConnection) -> list[Fact]:
    """Load all non-superseded facts from DuckDB memory_facts table.

    Previously read from JSONL. Now queries DuckDB directly.
    """

def load_facts_by_spec(
    spec_name: str,
    conn: duckdb.DuckDBPyConnection,
) -> list[Fact]:
    """Load non-superseded facts for a spec from DuckDB.

    Previously filtered JSONL in Python. Now uses SQL WHERE clause.
    """
```

#### Retained Functions (JSONL export helpers)

```python
def append_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Append facts to JSONL. Used for export only."""

def write_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Overwrite JSONL file. Used by compaction and session-end export."""

def export_facts_to_jsonl(
    conn: duckdb.DuckDBPyConnection,
    path: Path = DEFAULT_MEMORY_PATH,
) -> int:
    """Export all non-superseded facts from DuckDB to JSONL. Returns count."""
```

#### MemoryStore Changes

```python
class MemoryStore:
    def write_fact(self, fact: Fact) -> None:
        """Write fact to DuckDB only. JSONL write removed.

        1. Insert into memory_facts (must succeed).
        2. Generate embedding (best-effort).
        """
```

### `agent_fox.knowledge.state_machine` (new module)

```python
class KnowledgeStateMachine:
    """In-memory buffer for facts during an orchestrator run.

    Facts are accumulated via add_fact() and written to DuckDB in
    batch via flush(). The state machine does not own the DuckDB
    connection -- it delegates to MemoryStore.
    """

    def __init__(self, store: MemoryStore) -> None:
        """Initialize with a MemoryStore for DuckDB access."""

    @property
    def pending(self) -> list[Fact]:
        """Return a copy of buffered facts not yet flushed."""

    def add_fact(self, fact: Fact) -> None:
        """Buffer a fact for later flushing. No DuckDB write."""

    def flush(self) -> int:
        """Write all buffered facts to DuckDB via MemoryStore.

        Returns the number of facts flushed. Clears the buffer on
        success. On partial failure, removes successfully-written
        facts from the buffer and re-raises the error.
        """
```

### `agent_fox.knowledge.filtering` (moved from `memory/filter.py`)

No API changes. Internal imports updated from `agent_fox.memory.types` to
`agent_fox.knowledge.facts`.

### `agent_fox.knowledge.rendering` (moved from `memory/render.py`)

Signature change to support DuckDB read path:

```python
def render_summary(
    conn: duckdb.DuckDBPyConnection,
    output_path: Path = DEFAULT_SUMMARY_PATH,
) -> None:
    """Render markdown summary. Reads facts from DuckDB instead of JSONL."""
```

### `agent_fox.knowledge.compaction` (moved from `memory/compaction.py`)

Signature change to operate on DuckDB:

```python
def compact(conn: duckdb.DuckDBPyConnection, jsonl_path: Path = DEFAULT_MEMORY_PATH) -> tuple[int, int]:
    """Compact facts in DuckDB, then export to JSONL.

    1. Load all facts from DuckDB.
    2. Deduplicate by content hash.
    3. Resolve supersession chains.
    4. Update DuckDB (delete removed facts).
    5. Export surviving facts to JSONL.
    """
```

### `agent_fox.knowledge.__init__` Re-exports

```python
from agent_fox.knowledge.facts import (
    Category,
    ConfidenceLevel,
    CONFIDENCE_MAP,
    DEFAULT_CONFIDENCE,
    Fact,
    parse_confidence,
)
from agent_fox.knowledge.store import (
    DEFAULT_MEMORY_PATH,
    MemoryStore,
    append_facts,
    export_facts_to_jsonl,
    load_all_facts,
    load_facts_by_spec,
    write_facts,
)
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.rendering import render_summary
from agent_fox.knowledge.extraction import extract_facts
from agent_fox.knowledge.compaction import compact
from agent_fox.knowledge.state_machine import KnowledgeStateMachine
```

## Correctness Properties

1. **Lossless migration:** Every public symbol accessible via
   `agent_fox.memory.*` before this change is accessible via
   `agent_fox.knowledge.*` after it. No symbol is dropped.

2. **Import completeness:** After consolidation, zero files in the repository
   import from `agent_fox.memory`. Verified by `grep -r "from agent_fox.memory"`.

3. **Read consistency:** `load_all_facts(conn)` returns the same logical set
   of facts that was previously returned by `load_all_facts(path)`, assuming
   the DuckDB and JSONL stores were in sync at the point of migration.

4. **Flush atomicity:** After `KnowledgeStateMachine.flush()` succeeds,
   `pending` is empty and all facts are in DuckDB. After `flush()` fails,
   `pending` contains exactly the facts that were not written.

5. **Export idempotency:** Calling `export_facts_to_jsonl()` twice with no
   intervening writes produces identical JSONL files.

6. **No silent fallback:** If DuckDB is unavailable, errors propagate. There
   is no fallback to JSONL reads (consistent with spec 38).

## Error Handling

| Scenario | Behavior |
|----------|----------|
| DuckDB read failure in `load_all_facts()` | Exception propagates |
| DuckDB write failure in `MemoryStore.write_fact()` | Exception propagates |
| DuckDB write failure in `KnowledgeStateMachine.flush()` | Partially-flushed facts removed from buffer, exception propagates |
| JSONL export failure in `export_facts_to_jsonl()` | Warning logged, DuckDB state preserved |
| Import from `agent_fox.memory` | `ImportError` (package deleted) |

## Migration Strategy

The consolidation is a single atomic change:

1. Copy modules from `memory/` to `knowledge/` with renames.
2. Update all internal imports within the moved modules.
3. Update all imports across the codebase (production + test).
4. Move test files from `tests/*/memory/` to `tests/*/knowledge/`.
5. Update `knowledge/__init__.py` with re-exports.
6. Delete `agent_fox/memory/` directory.
7. Run `make check` to verify.

All steps happen in a single feature branch. There is no gradual migration
or compatibility shim -- the old package is deleted outright.
