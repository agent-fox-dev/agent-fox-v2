# Test Specification: Pluggable Knowledge Provider

## Overview

Tests verify that the `FoxKnowledgeProvider` correctly implements the
`KnowledgeProvider` protocol, stores and retrieves gotchas/review
findings/errata with proper scoping, respects retrieval caps and TTL,
and handles all error conditions gracefully. Most tests use in-memory
DuckDB connections for speed.

## Test Cases

### TS-115-1: FoxKnowledgeProvider Implements Protocol

**Requirement:** 115-REQ-1.1
**Type:** unit
**Description:** Verify `FoxKnowledgeProvider` has both `ingest` and `retrieve`
methods with correct signatures.

**Preconditions:**
- `agent_fox.knowledge.fox_provider` module is importable.

**Input:**
- Import and inspect `FoxKnowledgeProvider`.

**Expected:**
- Class has `ingest(self, session_id, spec_name, context)` and
  `retrieve(self, spec_name, task_description)` methods.

**Assertion pseudocode:**
```
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider
ASSERT hasattr(FoxKnowledgeProvider, "ingest")
ASSERT hasattr(FoxKnowledgeProvider, "retrieve")
```

### TS-115-2: FoxKnowledgeProvider isinstance Check

**Requirement:** 115-REQ-1.2
**Type:** unit
**Description:** Verify `isinstance(FoxKnowledgeProvider(...), KnowledgeProvider)` returns True.

**Preconditions:**
- In-memory DuckDB with schema initialized.
- Default `KnowledgeProviderConfig`.

**Input:**
- Construct `FoxKnowledgeProvider(knowledge_db, config)`.

**Expected:**
- `isinstance(provider, KnowledgeProvider)` is True.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import KnowledgeProvider
from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

provider = FoxKnowledgeProvider(test_db, default_config)
ASSERT isinstance(provider, KnowledgeProvider)
```

### TS-115-3: Constructor Accepts KnowledgeDB and Config

**Requirement:** 115-REQ-1.3
**Type:** unit
**Description:** Verify constructor signature accepts required parameters.

**Preconditions:**
- In-memory DuckDB.
- `KnowledgeProviderConfig` instance.

**Input:**
- `FoxKnowledgeProvider(knowledge_db, config)`.

**Expected:**
- Construction succeeds without error.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, KnowledgeProviderConfig())
ASSERT provider is not None
```

### TS-115-4: Gotcha Extraction on Ingest

**Requirement:** 115-REQ-2.1
**Type:** unit
**Description:** Verify `ingest()` calls LLM for gotcha extraction and stores
results.

**Preconditions:**
- In-memory DuckDB with schema.
- Mock LLM returning 2 gotcha candidates.

**Input:**
- `ingest("session-1", "spec_01", {"session_status": "completed", "touched_files": ["f.py"], "commit_sha": "abc"})`.

**Expected:**
- LLM called with gotcha extraction prompt.
- 2 gotchas stored in `gotchas` table with `spec_name="spec_01"`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, config, llm=mock_llm)
provider.ingest("session-1", "spec_01", {"session_status": "completed", "touched_files": ["f.py"], "commit_sha": "abc"})
rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
ASSERT len(rows) == 2
ASSERT mock_llm.called
```

### TS-115-5: SIMPLE Model Tier for Extraction

**Requirement:** 115-REQ-2.2
**Type:** unit
**Description:** Verify gotcha extraction uses the SIMPLE model tier.

**Preconditions:**
- Mock LLM that records the model tier used.

**Input:**
- `ingest()` with completed session context.

**Expected:**
- LLM called with model tier `SIMPLE`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, KnowledgeProviderConfig(model_tier="SIMPLE"), llm=mock_llm)
provider.ingest("s1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})
ASSERT mock_llm.last_model_tier == "SIMPLE"
```

### TS-115-6: Zero Gotchas From LLM

**Requirement:** 115-REQ-2.3
**Type:** unit
**Description:** Verify no storage when LLM returns zero candidates.

**Preconditions:**
- Mock LLM returning empty list.

**Input:**
- `ingest()` with completed session.

**Expected:**
- No rows in `gotchas` table.
- No error raised.

**Assertion pseudocode:**
```
mock_llm.returns = []
provider.ingest("s1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})
rows = conn.execute("SELECT * FROM gotchas").fetchall()
ASSERT len(rows) == 0
```

### TS-115-7: Gotcha Record Fields

**Requirement:** 115-REQ-2.4
**Type:** unit
**Description:** Verify stored gotcha has all required fields.

**Preconditions:**
- Mock LLM returning 1 gotcha.

**Input:**
- `ingest()` with session context.

**Expected:**
- Stored record has: `spec_name`, `category='gotcha'`, `text`, `content_hash`
  (SHA-256), `session_id`, `created_at` (UTC timestamp).

**Assertion pseudocode:**
```
provider.ingest("session-1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})
row = conn.execute("SELECT * FROM gotchas").fetchone()
ASSERT row.spec_name == "spec_01"
ASSERT row.category == "gotcha"
ASSERT row.text is not None and len(row.text) > 0
ASSERT row.content_hash is not None and len(row.content_hash) == 64  # SHA-256 hex
ASSERT row.session_id == "session-1"
ASSERT row.created_at is not None
```

### TS-115-8: Skip Ingest for Non-Completed Sessions

**Requirement:** 115-REQ-2.5
**Type:** unit
**Description:** Verify `ingest()` skips extraction when session_status is not
"completed".

**Preconditions:**
- Mock LLM (should not be called).

**Input:**
- `ingest("s1", "spec_01", {"session_status": "failed", "touched_files": [], "commit_sha": ""})`.

**Expected:**
- LLM not called.
- No gotchas stored.

**Assertion pseudocode:**
```
provider.ingest("s1", "spec_01", {"session_status": "failed", "touched_files": [], "commit_sha": ""})
ASSERT mock_llm.called == False
rows = conn.execute("SELECT * FROM gotchas").fetchall()
ASSERT len(rows) == 0
```

### TS-115-9: Gotcha Retrieval by Spec

**Requirement:** 115-REQ-3.1
**Type:** unit
**Description:** Verify `retrieve()` returns gotchas filtered by spec_name,
ordered by recency.

**Preconditions:**
- 3 gotchas stored for "spec_01", 2 for "spec_02".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Returns gotchas for "spec_01" only.
- Most recent first.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 3
# Verify ordering: first gotcha has newest timestamp
```

### TS-115-10: Gotcha TTL Exclusion

**Requirement:** 115-REQ-3.2
**Type:** unit
**Description:** Verify gotchas older than TTL are excluded from retrieval.

**Preconditions:**
- 1 gotcha from 100 days ago, 1 from 10 days ago, TTL = 90 days.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Only the 10-day-old gotcha is returned.

**Assertion pseudocode:**
```
# Insert gotcha with created_at = now - 100 days
# Insert gotcha with created_at = now - 10 days
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 1
ASSERT "10-day-old content" IN gotchas[0]
```

### TS-115-11: Max 5 Gotchas Per Retrieval

**Requirement:** 115-REQ-3.3
**Type:** unit
**Description:** Verify at most 5 gotchas are returned.

**Preconditions:**
- 8 gotchas stored for "spec_01", all within TTL.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- At most 5 gotcha items (the 5 most recent).

**Assertion pseudocode:**
```
# Insert 8 gotchas
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) <= 5
```

### TS-115-12: Gotcha Prefix

**Requirement:** 115-REQ-3.4
**Type:** unit
**Description:** Verify each gotcha string is prefixed with `[GOTCHA] `.

**Preconditions:**
- 1 gotcha stored.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Gotcha string starts with `"[GOTCHA] "`.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
for g in gotchas:
    ASSERT g.startswith("[GOTCHA] ")
```

### TS-115-13: Review Carry-Forward

**Requirement:** 115-REQ-4.1
**Type:** unit
**Description:** Verify `retrieve()` includes unresolved critical/major review
findings.

**Preconditions:**
- 2 review findings in `review_findings` table for "spec_01": one critical
  (active), one minor (active).

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Result includes the critical finding.
- Result does NOT include the minor finding.

**Assertion pseudocode:**
```
# Insert critical finding for spec_01
# Insert minor finding for spec_01
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
ASSERT len(reviews) == 1
ASSERT "critical" IN reviews[0].lower()
```

### TS-115-14: Review Findings Not Subject to Gotcha Limit

**Requirement:** 115-REQ-4.2
**Type:** unit
**Description:** Verify review findings are included regardless of gotcha limit.

**Preconditions:**
- 5 gotchas + 3 critical review findings for "spec_01".
- max_items = 10.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- All 3 review findings included.
- Gotchas trimmed to fit within max_items.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
ASSERT len(reviews) == 3
ASSERT len(result) <= 10
```

### TS-115-15: Review Finding Prefix

**Requirement:** 115-REQ-4.3
**Type:** unit
**Description:** Verify each review finding string has `[REVIEW] ` prefix and
includes severity, category, and description.

**Preconditions:**
- 1 critical review finding with category "security" and description "SQL injection".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- String starts with `"[REVIEW] "` and contains severity, category, description.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
ASSERT len(reviews) == 1
ASSERT "[REVIEW] " in reviews[0]
ASSERT "critical" IN reviews[0].lower()
ASSERT "SQL injection" IN reviews[0]
```

### TS-115-16: Errata Storage

**Requirement:** 115-REQ-5.1
**Type:** unit
**Description:** Verify errata entries are stored as `(spec_name, file_path)`
pairs.

**Preconditions:**
- In-memory DuckDB with schema.

**Input:**
- `register_errata(conn, "spec_28", "docs/errata/28_github_issue_rest_api.md")`.

**Expected:**
- Row exists in `errata_index` with correct spec_name and file_path.

**Assertion pseudocode:**
```
from agent_fox.knowledge.errata_store import register_errata

entry = register_errata(conn, "spec_28", "docs/errata/28_github_issue_rest_api.md")
row = conn.execute("SELECT * FROM errata_index WHERE spec_name='spec_28'").fetchone()
ASSERT row.spec_name == "spec_28"
ASSERT row.file_path == "docs/errata/28_github_issue_rest_api.md"
ASSERT entry.spec_name == "spec_28"
```

### TS-115-17: Errata Retrieval

**Requirement:** 115-REQ-5.2
**Type:** unit
**Description:** Verify `retrieve()` includes errata for the given spec.

**Preconditions:**
- 1 errata entry for "spec_28".

**Input:**
- `retrieve("spec_28", "task desc")`.

**Expected:**
- Result includes the errata entry.

**Assertion pseudocode:**
```
register_errata(conn, "spec_28", "docs/errata/28_fix.md")
result = provider.retrieve("spec_28", "task desc")
errata = [r for r in result if r.startswith("[ERRATA]")]
ASSERT len(errata) == 1
```

### TS-115-18: Errata Prefix

**Requirement:** 115-REQ-5.3
**Type:** unit
**Description:** Verify each errata string has `[ERRATA] ` prefix and includes
file path.

**Preconditions:**
- 1 errata entry registered.

**Input:**
- `retrieve("spec_28", "task desc")`.

**Expected:**
- String starts with `"[ERRATA] "` and contains the file path.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_28", "task desc")
errata = [r for r in result if r.startswith("[ERRATA]")]
ASSERT errata[0].startswith("[ERRATA] ")
ASSERT "docs/errata/28_fix.md" IN errata[0]
```

### TS-115-19: Register and Unregister Errata

**Requirement:** 115-REQ-5.4
**Type:** unit
**Description:** Verify errata can be registered and unregistered, and
`register_errata` returns the registered entry.

**Preconditions:**
- In-memory DuckDB with schema.

**Input:**
- Register, verify exists, unregister, verify gone.

**Expected:**
- After register: entry exists, returned entry matches.
- After unregister: entry removed.

**Assertion pseudocode:**
```
entry = register_errata(conn, "spec_28", "docs/errata/28_fix.md")
ASSERT entry.spec_name == "spec_28"
ASSERT entry.file_path == "docs/errata/28_fix.md"

rows = conn.execute("SELECT * FROM errata_index WHERE spec_name='spec_28'").fetchall()
ASSERT len(rows) == 1

removed = unregister_errata(conn, "spec_28", "docs/errata/28_fix.md")
ASSERT removed == True

rows = conn.execute("SELECT * FROM errata_index WHERE spec_name='spec_28'").fetchall()
ASSERT len(rows) == 0
```

### TS-115-20: Total Retrieval Cap

**Requirement:** 115-REQ-6.1
**Type:** unit
**Description:** Verify total items do not exceed `max_items`.

**Preconditions:**
- 5 gotchas, 3 review findings, 2 errata for "spec_01". max_items=10.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Total items <= 10.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
ASSERT len(result) <= 10
```

### TS-115-21: Gotchas Trimmed First

**Requirement:** 115-REQ-6.2
**Type:** unit
**Description:** Verify gotchas are trimmed when total exceeds cap.

**Preconditions:**
- 5 gotchas, 4 review findings, 3 errata. max_items=10.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- All 4 reviews + 3 errata included.
- Gotchas trimmed to 3 (10 - 4 - 3 = 3).

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
errata = [r for r in result if r.startswith("[ERRATA]")]
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(reviews) == 4
ASSERT len(errata) == 3
ASSERT len(gotchas) == 3
ASSERT len(result) == 10
```

### TS-115-22: Category Order

**Requirement:** 115-REQ-6.3
**Type:** unit
**Description:** Verify retrieval order: errata first, reviews second, gotchas
last.

**Preconditions:**
- 1 gotcha, 1 review, 1 errata for "spec_01".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- First item starts with `[ERRATA]`.
- Second with `[REVIEW]`.
- Third with `[GOTCHA]`.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
ASSERT result[0].startswith("[ERRATA]")
ASSERT result[1].startswith("[REVIEW]")
ASSERT result[2].startswith("[GOTCHA]")
```

### TS-115-23: Gotcha TTL Retrieval Exclusion

**Requirement:** 115-REQ-7.1
**Type:** unit
**Description:** Verify gotchas older than TTL excluded (same as TS-115-10
but directly testing the TTL config).

**Preconditions:**
- Gotcha from 91 days ago. TTL = 90.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No gotchas returned.

**Assertion pseudocode:**
```
# Insert gotcha with created_at = now - 91 days
config = KnowledgeProviderConfig(gotcha_ttl_days=90)
provider = FoxKnowledgeProvider(test_db, config)
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 0
```

### TS-115-24: Expired Gotchas Not Deleted

**Requirement:** 115-REQ-7.2
**Type:** unit
**Description:** Verify expired gotchas remain in the database.

**Preconditions:**
- Gotcha from 100 days ago. TTL = 90.

**Input:**
- `retrieve("spec_01", "task desc")` — doesn't return it.
- Direct query to `gotchas` table.

**Expected:**
- Gotcha excluded from retrieval but still exists in DB.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 0

# But still in DB
rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
ASSERT len(rows) == 1
```

### TS-115-25: KnowledgeProviderConfig Fields

**Requirement:** 115-REQ-8.1
**Type:** unit
**Description:** Verify `KnowledgeProviderConfig` has correct fields and defaults.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Construct `KnowledgeProviderConfig()`.

**Expected:**
- `max_items=10`, `gotcha_ttl_days=90`, `model_tier="SIMPLE"`.

**Assertion pseudocode:**
```
from agent_fox.core.config import KnowledgeProviderConfig

cfg = KnowledgeProviderConfig()
ASSERT cfg.max_items == 10
ASSERT cfg.gotcha_ttl_days == 90
ASSERT cfg.model_tier == "SIMPLE"
```

### TS-115-26: Config Nested in KnowledgeConfig

**Requirement:** 115-REQ-8.2
**Type:** unit
**Description:** Verify `KnowledgeProviderConfig` is a field in
`KnowledgeConfig`.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Inspect `KnowledgeConfig.model_fields`.

**Expected:**
- `provider` field exists and defaults to `KnowledgeProviderConfig()`.

**Assertion pseudocode:**
```
from agent_fox.core.config import KnowledgeConfig

ASSERT "provider" IN KnowledgeConfig.model_fields
kc = KnowledgeConfig()
ASSERT kc.provider.max_items == 10
```

### TS-115-27: Config Extra Ignore

**Requirement:** 115-REQ-8.3
**Type:** unit
**Description:** Verify `KnowledgeProviderConfig` ignores unknown fields.

**Preconditions:**
- None.

**Input:**
- `KnowledgeProviderConfig(max_items=5, unknown_field="foo")`.

**Expected:**
- No validation error. `unknown_field` silently ignored.

**Assertion pseudocode:**
```
cfg = KnowledgeProviderConfig(max_items=5, unknown_field="foo")
ASSERT cfg.max_items == 5
ASSERT NOT hasattr(cfg, "unknown_field")
```

### TS-115-28: Gotchas Table Schema

**Requirement:** 115-REQ-9.1
**Type:** unit
**Description:** Verify `gotchas` table created with correct columns.

**Preconditions:**
- In-memory DuckDB after migration v17.

**Input:**
- Query table metadata.

**Expected:**
- Table exists with columns: id, spec_name, category, text, content_hash,
  session_id, created_at.

**Assertion pseudocode:**
```
columns = conn.execute("DESCRIBE gotchas").fetchall()
col_names = {c[0] for c in columns}
ASSERT col_names == {"id", "spec_name", "category", "text", "content_hash", "session_id", "created_at"}
```

### TS-115-29: Errata Index Table Schema

**Requirement:** 115-REQ-9.2
**Type:** unit
**Description:** Verify `errata_index` table created with correct columns and
composite primary key.

**Preconditions:**
- In-memory DuckDB after migration v17.

**Input:**
- Query table metadata.

**Expected:**
- Table exists with columns: spec_name, file_path, created_at.
- Primary key on (spec_name, file_path).

**Assertion pseudocode:**
```
columns = conn.execute("DESCRIBE errata_index").fetchall()
col_names = {c[0] for c in columns}
ASSERT col_names == {"spec_name", "file_path", "created_at"}
```

### TS-115-30: Migration Via Framework

**Requirement:** 115-REQ-9.3
**Type:** unit
**Description:** Verify tables are created through the migration framework.

**Preconditions:**
- Fresh in-memory DuckDB.

**Input:**
- Run `apply_pending_migrations(conn)`.

**Expected:**
- Both `gotchas` and `errata_index` tables exist after migration.

**Assertion pseudocode:**
```
from agent_fox.knowledge.migrations import apply_pending_migrations

apply_pending_migrations(conn)
tables = conn.execute("SHOW TABLES").fetchall()
table_names = {t[0] for t in tables}
ASSERT "gotchas" IN table_names
ASSERT "errata_index" IN table_names
```

### TS-115-31: Idempotent Migration

**Requirement:** 115-REQ-9.4
**Type:** unit
**Description:** Verify migration can run twice without error.

**Preconditions:**
- In-memory DuckDB.

**Input:**
- Run `apply_pending_migrations(conn)` twice.

**Expected:**
- No error on second run.

**Assertion pseudocode:**
```
apply_pending_migrations(conn)
apply_pending_migrations(conn)  # should not raise
```

### TS-115-32: Provider Construction at Startup

**Requirement:** 115-REQ-10.1
**Type:** integration
**Description:** Verify `_setup_infrastructure` constructs `FoxKnowledgeProvider`.

**Preconditions:**
- Default config with `KnowledgeProviderConfig`.

**Input:**
- Call `_setup_infrastructure(config)`.

**Expected:**
- Returned infrastructure dict contains a `FoxKnowledgeProvider` instance.

**Assertion pseudocode:**
```
infra = _setup_infrastructure(config)
ASSERT isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)
```

### TS-115-33: Replaces NoOpKnowledgeProvider

**Requirement:** 115-REQ-10.2
**Type:** integration
**Description:** Verify `FoxKnowledgeProvider` replaces `NoOpKnowledgeProvider`
as default.

**Preconditions:**
- Default config.

**Input:**
- Call `_setup_infrastructure(config)`.

**Expected:**
- Provider is NOT `NoOpKnowledgeProvider`.
- Provider IS `FoxKnowledgeProvider`.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import NoOpKnowledgeProvider

infra = _setup_infrastructure(config)
ASSERT NOT isinstance(infra["knowledge_provider"], NoOpKnowledgeProvider)
ASSERT isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)
```

### TS-115-34: Engine Import Boundary

**Requirement:** 115-REQ-10.3
**Type:** integration
**Description:** Verify engine modules only import from the allowed set of
knowledge modules.

**Preconditions:**
- All engine source files accessible.

**Input:**
- Scan `agent_fox/engine/*.py` for `agent_fox.knowledge` imports.

**Expected:**
- Only imports from: `provider`, `db`, `review_store`, `audit`, `sink`,
  `duckdb_sink`, `blocking_history`, `agent_trace`, `migrations`.

**Assertion pseudocode:**
```
ALLOWED = {"provider", "db", "review_store", "audit", "sink", "duckdb_sink",
           "blocking_history", "agent_trace", "migrations", "fox_provider"}
for file in glob("agent_fox/engine/*.py"):
    source = read(file)
    for match in re.findall(r"agent_fox\.knowledge\.(\w+)", source):
        ASSERT match IN ALLOWED
```

## Edge Case Tests

### TS-115-E1: Closed DB Connection

**Requirement:** 115-REQ-1.E1
**Type:** unit
**Description:** Verify descriptive error when DB connection is closed.

**Preconditions:**
- `FoxKnowledgeProvider` constructed, then DB connection closed.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Raises error with descriptive message (not generic DuckDB error).

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, config)
test_db.close()
ASSERT_RAISES(KnowledgeStoreError, provider.retrieve, "spec_01", "task")
```

### TS-115-E2: Duplicate Gotcha Hash

**Requirement:** 115-REQ-2.E1
**Type:** unit
**Description:** Verify duplicate gotchas are skipped silently.

**Preconditions:**
- 1 gotcha already stored for spec_01 with content hash H.

**Input:**
- Store another gotcha with same content hash H.

**Expected:**
- Second store is a no-op. Total gotchas for spec = 1.

**Assertion pseudocode:**
```
store_gotchas(conn, "spec_01", "s1", [candidate_with_hash_H])
store_gotchas(conn, "spec_01", "s2", [candidate_with_same_hash_H])
rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
ASSERT len(rows) == 1
```

### TS-115-E3: LLM Extraction Failure

**Requirement:** 115-REQ-2.E2
**Type:** unit
**Description:** Verify LLM failure is logged and no gotchas stored.

**Preconditions:**
- Mock LLM that raises RuntimeError.

**Input:**
- `ingest("s1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})`.

**Expected:**
- No exception propagated. WARNING logged. No gotchas stored.

**Assertion pseudocode:**
```
mock_llm.raises = RuntimeError("LLM failed")
provider.ingest("s1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})
rows = conn.execute("SELECT * FROM gotchas").fetchall()
ASSERT len(rows) == 0
ASSERT caplog contains WARNING
```

### TS-115-E4: LLM Returns More Than 3

**Requirement:** 115-REQ-2.E3
**Type:** unit
**Description:** Verify only first 3 gotchas stored when LLM returns more.

**Preconditions:**
- Mock LLM returning 5 candidates.

**Input:**
- `ingest()` with completed session.

**Expected:**
- Exactly 3 gotchas stored.

**Assertion pseudocode:**
```
mock_llm.returns = [candidate_1, candidate_2, candidate_3, candidate_4, candidate_5]
provider.ingest("s1", "spec_01", {"session_status": "completed", "touched_files": [], "commit_sha": ""})
rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
ASSERT len(rows) == 3
```

### TS-115-E5: No Gotchas for Spec

**Requirement:** 115-REQ-3.E1
**Type:** unit
**Description:** Verify empty gotcha contribution when none exist.

**Preconditions:**
- No gotchas stored for "spec_01".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No `[GOTCHA]` items in result.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 0
```

### TS-115-E6: No Findings for Spec

**Requirement:** 115-REQ-4.E1
**Type:** unit
**Description:** Verify empty review contribution when none exist.

**Preconditions:**
- No review findings for "spec_01".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No `[REVIEW]` items in result.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
ASSERT len(reviews) == 0
```

### TS-115-E7: Missing review_findings Table

**Requirement:** 115-REQ-4.E2
**Type:** unit
**Description:** Verify graceful handling when review_findings table is absent.

**Preconditions:**
- Fresh DuckDB without review_findings table.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No error. Empty review contribution.

**Assertion pseudocode:**
```
# Use fresh DB without running full migrations (only v17)
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
ASSERT len(reviews) == 0
```

### TS-115-E8: No Errata for Spec

**Requirement:** 115-REQ-5.E1
**Type:** unit
**Description:** Verify empty errata contribution when none registered.

**Preconditions:**
- No errata for "spec_01".

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No `[ERRATA]` items in result.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
errata = [r for r in result if r.startswith("[ERRATA]")]
ASSERT len(errata) == 0
```

### TS-115-E9: Errata File Missing on Disk

**Requirement:** 115-REQ-5.E2
**Type:** unit
**Description:** Verify errata entry returned even when file doesn't exist.

**Preconditions:**
- Errata entry registered for nonexistent file.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Errata entry still included in result.

**Assertion pseudocode:**
```
register_errata(conn, "spec_01", "docs/errata/nonexistent.md")
result = provider.retrieve("spec_01", "task desc")
errata = [r for r in result if r.startswith("[ERRATA]")]
ASSERT len(errata) == 1
ASSERT "nonexistent.md" IN errata[0]
```

### TS-115-E10: All Categories Empty

**Requirement:** 115-REQ-6.E1
**Type:** unit
**Description:** Verify empty list when all categories are empty.

**Preconditions:**
- No gotchas, no findings, no errata.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- Empty list returned.

**Assertion pseudocode:**
```
result = provider.retrieve("spec_01", "task desc")
ASSERT result == []
```

### TS-115-E11: Reviews+Errata Exceed Cap

**Requirement:** 115-REQ-6.E2
**Type:** unit
**Description:** Verify all reviews+errata returned even if exceeding max_items.

**Preconditions:**
- 8 review findings + 5 errata for "spec_01". max_items=10.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- All 8 reviews + 5 errata returned (total 13 > max_items).
- No gotchas included.

**Assertion pseudocode:**
```
config = KnowledgeProviderConfig(max_items=10)
provider = FoxKnowledgeProvider(test_db, config)
result = provider.retrieve("spec_01", "task desc")
reviews = [r for r in result if r.startswith("[REVIEW]")]
errata = [r for r in result if r.startswith("[ERRATA]")]
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(reviews) == 8
ASSERT len(errata) == 5
ASSERT len(gotchas) == 0
```

### TS-115-E12: TTL Zero Excludes All

**Requirement:** 115-REQ-7.E1
**Type:** unit
**Description:** Verify TTL=0 excludes all gotchas.

**Preconditions:**
- 3 gotchas stored just now. TTL=0.

**Input:**
- `retrieve("spec_01", "task desc")`.

**Expected:**
- No gotchas returned.

**Assertion pseudocode:**
```
config = KnowledgeProviderConfig(gotcha_ttl_days=0)
provider = FoxKnowledgeProvider(test_db, config)
result = provider.retrieve("spec_01", "task desc")
gotchas = [r for r in result if r.startswith("[GOTCHA]")]
ASSERT len(gotchas) == 0
```

## Property Test Cases

### TS-115-P1: Protocol Conformance

**Property:** Property 1 from design.md
**Validates:** 115-REQ-1.1, 115-REQ-1.2
**Type:** property
**Description:** FoxKnowledgeProvider always satisfies isinstance check.

**For any:** valid KnowledgeDB and KnowledgeProviderConfig.
**Invariant:** `isinstance(FoxKnowledgeProvider(db, config), KnowledgeProvider)` is True.

**Assertion pseudocode:**
```
@given(st.just(True))
def test_protocol_conformance(_):
    provider = FoxKnowledgeProvider(test_db, default_config)
    ASSERT isinstance(provider, KnowledgeProvider)
```

### TS-115-P2: Gotcha Deduplication

**Property:** Property 2 from design.md
**Validates:** 115-REQ-2.4, 115-REQ-2.E1
**Type:** property
**Description:** Duplicate content hashes for same spec are stored only once.

**For any:** sequence of gotcha texts drawn from `st.lists(st.text(min_size=1))`.
**Invariant:** After storing all, count of rows for spec equals count of unique
content hashes.

**Assertion pseudocode:**
```
@given(texts=st.lists(st.text(min_size=1), min_size=1, max_size=10))
def test_dedup(texts):
    candidates = [GotchaCandidate(t, compute_content_hash(t)) for t in texts]
    store_gotchas(conn, "spec_01", "s1", candidates)
    rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
    expected = len({compute_content_hash(t) for t in texts})
    ASSERT len(rows) == expected
```

### TS-115-P3: Gotcha TTL Exclusion

**Property:** Property 3 from design.md
**Validates:** 115-REQ-3.2, 115-REQ-7.1
**Type:** property
**Description:** Gotchas older than TTL never appear in retrieval.

**For any:** `ttl_days` drawn from `st.integers(0, 365)`, gotcha ages drawn
from `st.integers(0, 400)`.
**Invariant:** A gotcha with age > ttl_days is not in the result.

**Assertion pseudocode:**
```
@given(ttl=st.integers(0, 365), age=st.integers(0, 400))
def test_ttl_exclusion(ttl, age):
    # Insert gotcha with created_at = now - age days
    result = query_gotchas(conn, "spec_01", ttl, limit=5)
    if age > ttl:
        ASSERT len(result) == 0
```

### TS-115-P4: Retrieval Cap

**Property:** Property 4 from design.md
**Validates:** 115-REQ-6.1, 115-REQ-6.2, 115-REQ-6.E2
**Type:** property
**Description:** Total items respect max_items unless reviews+errata exceed it.

**For any:** `n_gotchas` in 0-10, `n_reviews` in 0-10, `n_errata` in 0-5,
`max_items` in 1-20.
**Invariant:** `len(result) <= max(max_items, n_reviews + n_errata)`.

**Assertion pseudocode:**
```
@given(
    n_gotchas=st.integers(0, 10),
    n_reviews=st.integers(0, 10),
    n_errata=st.integers(0, 5),
    max_items=st.integers(1, 20),
)
def test_retrieval_cap(n_gotchas, n_reviews, n_errata, max_items):
    # Seed DB with n_gotchas, n_reviews, n_errata
    result = provider.retrieve("spec_01", "task")
    ASSERT len(result) <= max(max_items, n_reviews + n_errata)
```

### TS-115-P5: Category Priority Order

**Property:** Property 5 from design.md
**Validates:** 115-REQ-6.3
**Type:** property
**Description:** Items always appear in errata-review-gotcha order.

**For any:** non-empty retrieval result.
**Invariant:** All `[ERRATA]` items precede all `[REVIEW]` items, which precede
all `[GOTCHA]` items.

**Assertion pseudocode:**
```
@given(st.just(True))
def test_category_order(_):
    result = provider.retrieve("spec_01", "task")
    categories = [r.split("]")[0] + "]" for r in result]
    # Check order: [ERRATA] then [REVIEW] then [GOTCHA]
    seen_review = False
    seen_gotcha = False
    for cat in categories:
        if cat == "[ERRATA]":
            ASSERT NOT seen_review AND NOT seen_gotcha
        elif cat == "[REVIEW]":
            seen_review = True
            ASSERT NOT seen_gotcha
        elif cat == "[GOTCHA]":
            seen_gotcha = True
```

### TS-115-P6: Gotcha Extraction Cap

**Property:** Property 6 from design.md
**Validates:** 115-REQ-2.E3
**Type:** property
**Description:** Extract always returns at most 3 candidates.

**For any:** LLM response with N candidates where N > 0.
**Invariant:** `len(extract_gotchas(...)) <= 3`.

**Assertion pseudocode:**
```
@given(n=st.integers(0, 20))
def test_extraction_cap(n):
    mock_llm.returns = [f"gotcha_{i}" for i in range(n)]
    result = extract_gotchas(context, "SIMPLE")
    ASSERT len(result) <= 3
```

### TS-115-P7: Failed Session Skip

**Property:** Property 7 from design.md
**Validates:** 115-REQ-2.5
**Type:** property
**Description:** Non-completed sessions never trigger extraction.

**For any:** `status` drawn from `st.sampled_from(["failed", "timeout", "", "in_progress"])`.
**Invariant:** `ingest()` with non-completed status does not call LLM.

**Assertion pseudocode:**
```
@given(status=st.sampled_from(["failed", "timeout", "", "in_progress"]))
def test_skip_non_completed(status):
    provider.ingest("s1", "spec_01", {"session_status": status, "touched_files": [], "commit_sha": ""})
    ASSERT mock_llm.called == False
```

### TS-115-P8: Content Hash Determinism

**Property:** Property 8 from design.md
**Validates:** 115-REQ-2.4
**Type:** property
**Description:** Same text always produces the same hash; whitespace/case
variations produce the same hash.

**For any:** text drawn from `st.text(min_size=1)`.
**Invariant:** `compute_content_hash(t) == compute_content_hash(t)` and
`compute_content_hash(t.upper()) == compute_content_hash(t.lower())`.

**Assertion pseudocode:**
```
@given(text=st.text(min_size=1))
def test_hash_determinism(text):
    h1 = compute_content_hash(text)
    h2 = compute_content_hash(text)
    ASSERT h1 == h2
    ASSERT compute_content_hash(text.upper()) == compute_content_hash(text.lower())
```

### TS-115-P9: Review Category Prefix

**Property:** Property 9 from design.md
**Validates:** 115-REQ-4.3
**Type:** property
**Description:** Every review finding string has the correct prefix format.

**For any:** review finding with severity in `{"critical", "major"}`.
**Invariant:** Formatted string starts with `"[REVIEW] "` and contains the
severity.

**Assertion pseudocode:**
```
@given(severity=st.sampled_from(["critical", "major"]))
def test_review_prefix(severity):
    # Insert finding with given severity
    result = provider.retrieve("spec_01", "task")
    reviews = [r for r in result if r.startswith("[REVIEW]")]
    for r in reviews:
        ASSERT r.startswith("[REVIEW] ")
        ASSERT severity IN r.lower()
```

## Integration Smoke Tests

### TS-115-SMOKE-1: Pre-Session Retrieval Path

**Execution Path:** Path 1 from design.md
**Description:** Verify full retrieval path returns composed results from all
three categories.

**Setup:** In-memory DuckDB with schema. Seed gotchas, review findings, and
errata. Real `FoxKnowledgeProvider`.

**Trigger:** `provider.retrieve("spec_01", "implement feature X")`.

**Expected side effects:**
- Returns list with items from all 3 categories.
- Items in order: errata, reviews, gotchas.
- Total <= max_items.

**Must NOT satisfy with:** Mocking `FoxKnowledgeProvider`, `gotcha_store`,
`errata_store`, or `review_store`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, config)  # real provider
# Seed: 1 errata, 1 critical finding, 2 gotchas
result = provider.retrieve("spec_01", "implement feature X")
ASSERT len(result) == 4
ASSERT result[0].startswith("[ERRATA]")
ASSERT result[1].startswith("[REVIEW]")
ASSERT result[2].startswith("[GOTCHA]")
ASSERT result[3].startswith("[GOTCHA]")
```

### TS-115-SMOKE-2: Post-Session Ingestion Path

**Execution Path:** Path 2 from design.md
**Description:** Verify full ingestion path extracts gotchas via LLM and stores
them.

**Setup:** In-memory DuckDB with schema. Mock LLM returning 2 candidates.
Real `FoxKnowledgeProvider` and `gotcha_store`.

**Trigger:** `provider.ingest("session-1", "spec_01", context)`.

**Expected side effects:**
- LLM called with extraction prompt.
- 2 rows in `gotchas` table.

**Must NOT satisfy with:** Mocking `FoxKnowledgeProvider` or `gotcha_store`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(test_db, config, llm=mock_llm)  # real provider, mock LLM only
mock_llm.returns = [candidate_1, candidate_2]
provider.ingest("session-1", "spec_01", {"session_status": "completed", "touched_files": ["f.py"], "commit_sha": "abc"})
rows = conn.execute("SELECT * FROM gotchas WHERE spec_name='spec_01'").fetchall()
ASSERT len(rows) == 2
```

### TS-115-SMOKE-3: Errata Registration Path

**Execution Path:** Path 3 from design.md
**Description:** Verify errata registration stores entry and retrieval returns
it.

**Setup:** In-memory DuckDB with schema. Real errata_store functions.

**Trigger:** `register_errata(conn, "spec_28", "docs/errata/28_fix.md")`.

**Expected side effects:**
- Row in `errata_index` table.
- `retrieve("spec_28", ...)` includes the errata.
- Returned entry matches input.

**Must NOT satisfy with:** Mocking `errata_store`.

**Assertion pseudocode:**
```
entry = register_errata(conn, "spec_28", "docs/errata/28_fix.md")
ASSERT entry.spec_name == "spec_28"
provider = FoxKnowledgeProvider(test_db, config)
result = provider.retrieve("spec_28", "task")
errata = [r for r in result if r.startswith("[ERRATA]")]
ASSERT len(errata) == 1
ASSERT "28_fix.md" IN errata[0]
```

### TS-115-SMOKE-4: Provider Construction at Startup

**Execution Path:** Path 4 from design.md
**Description:** Verify `_setup_infrastructure` constructs
`FoxKnowledgeProvider` and wires it into the session runner factory.

**Setup:** Mock `open_knowledge_store`. Default config with
`KnowledgeProviderConfig`.

**Trigger:** `_setup_infrastructure(config)`.

**Expected side effects:**
- Infrastructure dict contains `knowledge_provider` of type
  `FoxKnowledgeProvider`.

**Must NOT satisfy with:** Mocking `_setup_infrastructure`.

**Assertion pseudocode:**
```
with patch("agent_fox.engine.run.open_knowledge_store", return_value=mock_db):
    infra = _setup_infrastructure(config)
ASSERT isinstance(infra["knowledge_provider"], FoxKnowledgeProvider)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 115-REQ-1.1 | TS-115-1 | unit |
| 115-REQ-1.2 | TS-115-2 | unit |
| 115-REQ-1.3 | TS-115-3 | unit |
| 115-REQ-1.E1 | TS-115-E1 | unit |
| 115-REQ-2.1 | TS-115-4 | unit |
| 115-REQ-2.2 | TS-115-5 | unit |
| 115-REQ-2.3 | TS-115-6 | unit |
| 115-REQ-2.4 | TS-115-7 | unit |
| 115-REQ-2.5 | TS-115-8 | unit |
| 115-REQ-2.E1 | TS-115-E2 | unit |
| 115-REQ-2.E2 | TS-115-E3 | unit |
| 115-REQ-2.E3 | TS-115-E4 | unit |
| 115-REQ-3.1 | TS-115-9 | unit |
| 115-REQ-3.2 | TS-115-10 | unit |
| 115-REQ-3.3 | TS-115-11 | unit |
| 115-REQ-3.4 | TS-115-12 | unit |
| 115-REQ-3.E1 | TS-115-E5 | unit |
| 115-REQ-4.1 | TS-115-13 | unit |
| 115-REQ-4.2 | TS-115-14 | unit |
| 115-REQ-4.3 | TS-115-15 | unit |
| 115-REQ-4.E1 | TS-115-E6 | unit |
| 115-REQ-4.E2 | TS-115-E7 | unit |
| 115-REQ-5.1 | TS-115-16 | unit |
| 115-REQ-5.2 | TS-115-17 | unit |
| 115-REQ-5.3 | TS-115-18 | unit |
| 115-REQ-5.4 | TS-115-19 | unit |
| 115-REQ-5.E1 | TS-115-E8 | unit |
| 115-REQ-5.E2 | TS-115-E9 | unit |
| 115-REQ-6.1 | TS-115-20 | unit |
| 115-REQ-6.2 | TS-115-21 | unit |
| 115-REQ-6.3 | TS-115-22 | unit |
| 115-REQ-6.E1 | TS-115-E10 | unit |
| 115-REQ-6.E2 | TS-115-E11 | unit |
| 115-REQ-7.1 | TS-115-23 | unit |
| 115-REQ-7.2 | TS-115-24 | unit |
| 115-REQ-7.E1 | TS-115-E12 | unit |
| 115-REQ-8.1 | TS-115-25 | unit |
| 115-REQ-8.2 | TS-115-26 | unit |
| 115-REQ-8.3 | TS-115-27 | unit |
| 115-REQ-9.1 | TS-115-28 | unit |
| 115-REQ-9.2 | TS-115-29 | unit |
| 115-REQ-9.3 | TS-115-30 | unit |
| 115-REQ-9.4 | TS-115-31 | unit |
| 115-REQ-10.1 | TS-115-32 | integration |
| 115-REQ-10.2 | TS-115-33 | integration |
| 115-REQ-10.3 | TS-115-34 | integration |
| Property 1 | TS-115-P1 | property |
| Property 2 | TS-115-P2 | property |
| Property 3 | TS-115-P3 | property |
| Property 4 | TS-115-P4 | property |
| Property 5 | TS-115-P5 | property |
| Property 6 | TS-115-P6 | property |
| Property 7 | TS-115-P7 | property |
| Property 8 | TS-115-P8 | property |
| Property 9 | TS-115-P9 | property |
| Path 1 | TS-115-SMOKE-1 | integration |
| Path 2 | TS-115-SMOKE-2 | integration |
| Path 3 | TS-115-SMOKE-3 | integration |
| Path 4 | TS-115-SMOKE-4 | integration |
