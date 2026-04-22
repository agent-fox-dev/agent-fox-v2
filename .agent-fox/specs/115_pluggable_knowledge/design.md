# Design Document: Pluggable Knowledge Provider

## Overview

This spec implements the `KnowledgeProvider` protocol (defined in spec 114) with
a `FoxKnowledgeProvider` that stores and retrieves three categories of scoped
knowledge: gotchas, review carry-forward, and errata pointers. The design
inverts the old system's priorities: hard to write to, easy to read from.

## Architecture

```
Engine
  │
  └── KnowledgeProvider protocol
           │
           └── FoxKnowledgeProvider
                  │
                  ├── GotchaStore      (gotchas table)
                  ├── ReviewReader     (review_findings table, read-only)
                  └── ErrataIndex      (errata_index table)
```

The provider is a composition of three internal stores, each handling one
knowledge category. The stores are implementation details — external code
interacts only through `ingest()` and `retrieve()`.

### FoxKnowledgeProvider

```python
# agent_fox/knowledge/fox_provider.py

from agent_fox.knowledge.provider import KnowledgeProvider
from agent_fox.knowledge.db import KnowledgeDB

class FoxKnowledgeProvider:
    """Concrete KnowledgeProvider: gotchas, review carry-forward, errata."""

    def __init__(self, db: KnowledgeDB, config: KnowledgeProviderConfig) -> None:
        self._gotcha_store = GotchaStore(db, config)
        self._review_reader = ReviewReader(db)
        self._errata_index = ErrataIndex(db)
        self._max_items = config.max_items

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict,
    ) -> None:
        if context.get("session_status") != "completed":
            return
        self._gotcha_store.extract_and_store(session_id, spec_name, context)

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        errata = self._errata_index.get(spec_name)
        reviews = self._review_reader.get_unresolved(spec_name)
        gotchas = self._gotcha_store.get_recent(spec_name)

        # Priority: errata > reviews > gotchas
        result = errata + reviews
        remaining = max(0, self._max_items - len(result))
        result += gotchas[:remaining]
        return result
```

### GotchaStore

```python
# agent_fox/knowledge/gotcha_store.py

class GotchaStore:
    """LLM-gated gotcha extraction and storage."""

    def __init__(self, db: KnowledgeDB, config: KnowledgeProviderConfig) -> None:
        self._db = db
        self._model_tier = config.model_tier
        self._ttl_days = config.gotcha_ttl_days

    def extract_and_store(
        self,
        session_id: str,
        spec_name: str,
        context: dict,
    ) -> None:
        """Prompt LLM for gotchas, deduplicate by content hash, store."""
        candidates = self._extract_gotchas(context)  # 0-3 items
        for candidate in candidates[:3]:
            content_hash = self._hash(candidate)
            if not self._exists(spec_name, content_hash):
                self._store(spec_name, candidate, content_hash, session_id)

    def get_recent(self, spec_name: str) -> list[str]:
        """Return up to 5 non-expired gotchas, most recent first."""
        cutoff = datetime.utcnow() - timedelta(days=self._ttl_days)
        rows = self._db.execute(
            """SELECT text FROM gotchas
               WHERE spec_name = ? AND created_at > ?
               ORDER BY created_at DESC LIMIT 5""",
            [spec_name, cutoff],
        )
        return [f"[GOTCHA] {row[0]}" for row in rows]

    def _extract_gotchas(self, context: dict) -> list[str]:
        """Call LLM with SIMPLE tier to extract gotcha candidates."""
        # Prompt: "Based on this session, what was surprising or non-obvious?
        # What would you want to know if starting a new session on this spec?
        # Return 0-3 short findings. If nothing was surprising, return empty."
        ...

    def _hash(self, text: str) -> str:
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _exists(self, spec_name: str, content_hash: str) -> bool:
        rows = self._db.execute(
            "SELECT 1 FROM gotchas WHERE spec_name = ? AND content_hash = ?",
            [spec_name, content_hash],
        )
        return len(rows) > 0

    def _store(self, spec_name, text, content_hash, session_id):
        self._db.execute(
            """INSERT INTO gotchas (id, spec_name, category, text,
               content_hash, session_id, created_at)
               VALUES (?, ?, 'gotcha', ?, ?, ?, ?)""",
            [generate_id(), spec_name, text, content_hash,
             session_id, datetime.utcnow()],
        )
```

### ReviewReader

```python
# agent_fox/knowledge/review_reader.py

class ReviewReader:
    """Read-only access to unresolved review findings."""

    def __init__(self, db: KnowledgeDB) -> None:
        self._db = db

    def get_unresolved(self, spec_name: str) -> list[str]:
        """Return critical/major findings with open/in_progress status."""
        rows = self._db.execute(
            """SELECT severity, category, description
               FROM review_findings
               WHERE spec_name = ?
                 AND severity IN ('critical', 'major')
                 AND status IN ('open', 'in_progress')
               ORDER BY severity, created_at DESC""",
            [spec_name],
        )
        return [
            f"[REVIEW] [{row[0].upper()}] {row[1]}: {row[2]}"
            for row in rows
        ]
```

### ErrataIndex

```python
# agent_fox/knowledge/errata_index.py

class ErrataIndex:
    """Spec-to-errata-document pointer store."""

    def __init__(self, db: KnowledgeDB) -> None:
        self._db = db

    def get(self, spec_name: str) -> list[str]:
        rows = self._db.execute(
            """SELECT file_path FROM errata_index
               WHERE spec_name = ?
               ORDER BY created_at""",
            [spec_name],
        )
        return [f"[ERRATA] See {row[0]}" for row in rows]

    def register(self, spec_name: str, file_path: str) -> dict:
        self._db.execute(
            """INSERT INTO errata_index (spec_name, file_path, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT (spec_name, file_path) DO NOTHING""",
            [spec_name, file_path, datetime.utcnow()],
        )
        return {"spec_name": spec_name, "file_path": file_path}

    def unregister(self, spec_name: str, file_path: str) -> None:
        self._db.execute(
            "DELETE FROM errata_index WHERE spec_name = ? AND file_path = ?",
            [spec_name, file_path],
        )
```

### Configuration

```python
# Addition to agent_fox/core/config.py

class KnowledgeProviderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    max_items: int = 10
    gotcha_ttl_days: int = 90
    model_tier: str = "SIMPLE"

class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    store_path: str = ".agent-fox/knowledge.duckdb"
    provider: KnowledgeProviderConfig = KnowledgeProviderConfig()
```

### Schema Migration

```sql
-- Migration: add_gotchas_table
CREATE TABLE IF NOT EXISTS gotchas (
    id VARCHAR PRIMARY KEY,
    spec_name VARCHAR NOT NULL,
    category VARCHAR NOT NULL DEFAULT 'gotcha',
    text VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gotchas_spec
    ON gotchas (spec_name, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gotchas_dedup
    ON gotchas (spec_name, content_hash);

-- Migration: add_errata_index_table
CREATE TABLE IF NOT EXISTS errata_index (
    spec_name VARCHAR NOT NULL,
    file_path VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (spec_name, file_path)
);
```

### Gotcha Extraction Prompt

```
You just completed a coding session for spec "{spec_name}".

Session context:
- Files touched: {touched_files}
- Commit: {commit_sha}
- Status: {session_status}

Based on this session, what was surprising or non-obvious? What would a future
developer want to know before working on this spec?

Rules:
- Return 0-3 short findings (1-2 sentences each).
- Only include things that were genuinely surprising — not generic patterns.
- If nothing was surprising, return an empty list.
- Format: JSON array of strings. Example: ["Finding 1", "Finding 2"]
```

### Provider Registration

In `engine/run.py` (after spec 114's changes):

```python
from agent_fox.knowledge.provider import KnowledgeProvider
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

def _build_provider(db: KnowledgeDB, config: KnowledgeConfig) -> KnowledgeProvider:
    return FoxKnowledgeProvider(db, config.provider)
```

## Correctness Properties

### CP-1: Protocol Conformance

**Property:** `isinstance(FoxKnowledgeProvider(...), KnowledgeProvider)` returns
`True`.

**Validation:** [115-REQ-1.1], [115-REQ-1.2]

### CP-2: Gotcha Deduplication

**Property:** Two gotchas with identical normalized text for the same spec_name
never both exist in the `gotchas` table.

**Validation:** [115-REQ-2.E1]

### CP-3: Retrieval Cap

**Property:** `len(retrieve(...))` never exceeds `max_items` unless review
findings + errata alone exceed it.

**Validation:** [115-REQ-6.1], [115-REQ-6.E2]

### CP-4: Category Priority

**Property:** When items must be trimmed, gotchas are removed before review
findings, and review findings before errata.

**Validation:** [115-REQ-6.2]

### CP-5: Gotcha Expiry

**Property:** No gotcha with `created_at` older than `gotcha_ttl_days` ago
appears in retrieval results.

**Validation:** [115-REQ-7.1]

### CP-6: Ingestion Gating

**Property:** `ingest()` performs no LLM call and stores no data when
`session_status != "completed"`.

**Validation:** [115-REQ-2.5]

### CP-7: Review Store Read-Only

**Property:** The provider never writes to or modifies the `review_findings`
table. It reads only.

**Validation:** [115-REQ-4.1]

### CP-8: Errata Registration Idempotence

**Property:** Registering the same `(spec_name, file_path)` pair twice does not
raise an error or create a duplicate row.

**Validation:** [115-REQ-5.4]
