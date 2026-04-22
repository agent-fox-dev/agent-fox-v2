# Implementation Tasks: Pluggable Knowledge Provider

## Task Group 1: Schema, Config, and Provider Shell

### Tasks

- [ ] Add `KnowledgeProviderConfig` to `core/config.py`
  - Fields: `max_items` (int, default 10), `gotcha_ttl_days` (int, default 90),
    `model_tier` (str, default "SIMPLE")
  - `ConfigDict(extra="ignore")`
  - Add as `provider: KnowledgeProviderConfig` field on `KnowledgeConfig`
  - Ref: [115-REQ-8.1], [115-REQ-8.2], [115-REQ-8.3]

- [ ] Add schema migration for `gotchas` and `errata_index` tables in
  `knowledge/migrations.py`
  - `gotchas`: id, spec_name, category, text, content_hash, session_id,
    created_at + indexes
  - `errata_index`: spec_name, file_path, created_at + composite PK
  - Must be idempotent (CREATE TABLE IF NOT EXISTS)
  - Ref: [115-REQ-9.1], [115-REQ-9.2], [115-REQ-9.3], [115-REQ-9.4]

- [ ] Create `knowledge/fox_provider.py` with `FoxKnowledgeProvider` class shell
  - Implement `KnowledgeProvider` protocol
  - Constructor accepts `KnowledgeDB` and `KnowledgeProviderConfig`
  - `ingest()` and `retrieve()` delegate to internal stores (stubbed for now)
  - Ref: [115-REQ-1.1], [115-REQ-1.2], [115-REQ-1.3]

- [ ] Write tests for config and migration
  - TC-8.1, TC-8.2, TC-8.3 in `tests/unit/core/test_config_knowledge.py`
  - TC-9.1, TC-9.2, TC-9.3 in `tests/unit/knowledge/test_migrations.py`
  - TC-1.1, TC-1.2 in `tests/unit/knowledge/test_fox_provider.py`

### Verification

```bash
uv run pytest tests/unit/core/test_config_knowledge.py tests/unit/knowledge/test_migrations.py tests/unit/knowledge/test_fox_provider.py -v
```

Confirm: config defaults correct, tables created, provider satisfies protocol.

---

## Task Group 2: GotchaStore — Ingestion and Retrieval

### Tasks

- [ ] Create `knowledge/gotcha_store.py` with `GotchaStore` class
  - `extract_and_store(session_id, spec_name, context)`: LLM extraction,
    content-hash dedup, store 0-3 gotchas
  - `get_recent(spec_name) -> list[str]`: query by spec_name, exclude expired,
    order by recency, limit 5, prefix with `[GOTCHA] `
  - `_hash(text)`: normalize whitespace + lowercase, SHA-256
  - `_exists(spec_name, content_hash)`: check dedup index
  - Ref: [115-REQ-2.1] through [115-REQ-2.5], [115-REQ-3.1] through
    [115-REQ-3.4]

- [ ] Write gotcha extraction prompt (SIMPLE model tier)
  - Input: session context (touched_files, commit_sha, session_status)
  - Output: JSON array of 0-3 strings
  - Ref: [115-REQ-2.1], [115-REQ-2.2]

- [ ] Write tests in `tests/unit/knowledge/test_gotcha_store.py`
  - TC-2.1 through TC-2.7 (ingestion)
  - TC-3.1 through TC-3.5 (retrieval)
  - TC-7.1, TC-7.2 (expiry)

### Verification

```bash
uv run pytest tests/unit/knowledge/test_gotcha_store.py -v
```

Confirm: extraction works with mock LLM, dedup prevents duplicates, expiry
excludes old gotchas, scoping filters by spec.

---

## Task Group 3: ReviewReader and ErrataIndex

### Tasks

- [ ] Create `knowledge/review_reader.py` with `ReviewReader` class
  - `get_unresolved(spec_name) -> list[str]`: query review_findings for
    critical/major + open/in_progress, prefix with `[REVIEW] `
  - Handle missing review_findings table gracefully
  - Read-only — no writes to review_findings
  - Ref: [115-REQ-4.1] through [115-REQ-4.3], [115-REQ-4.E1], [115-REQ-4.E2]

- [ ] Create `knowledge/errata_index.py` with `ErrataIndex` class
  - `get(spec_name) -> list[str]`: query errata_index, prefix with `[ERRATA] `
  - `register(spec_name, file_path) -> dict`: insert with ON CONFLICT DO
    NOTHING, return registered entry
  - `unregister(spec_name, file_path)`: delete
  - Ref: [115-REQ-5.1] through [115-REQ-5.4]

- [ ] Write tests
  - TC-4.1 through TC-4.4 in `tests/unit/knowledge/test_review_reader.py`
  - TC-5.1 through TC-5.4 in `tests/unit/knowledge/test_errata_index.py`

### Verification

```bash
uv run pytest tests/unit/knowledge/test_review_reader.py tests/unit/knowledge/test_errata_index.py -v
```

Confirm: review reader returns correct findings, handles missing table, errata
registration is idempotent.

---

## Task Group 4: Provider Composition and Registration

### Tasks

- [ ] Complete `knowledge/fox_provider.py`
  - Wire `GotchaStore`, `ReviewReader`, `ErrataIndex` into provider
  - `ingest()`: skip if session_status != "completed", delegate to
    GotchaStore.extract_and_store()
  - `retrieve()`: compose results from all three stores, apply max_items cap
    with priority trimming (errata > reviews > gotchas)
  - Ref: [115-REQ-6.1], [115-REQ-6.2], [115-REQ-6.3]

- [ ] Update `engine/run.py` to construct `FoxKnowledgeProvider` instead of
  `NoOpKnowledgeProvider`
  - Ref: [115-REQ-10.1], [115-REQ-10.2]

- [ ] Write tests
  - TC-6.1 through TC-6.5 in `tests/unit/knowledge/test_fox_provider.py`
  - TC-10.1, TC-10.2 in `tests/unit/engine/test_provider_registration.py`

### Verification

```bash
uv run pytest tests/unit/knowledge/test_fox_provider.py tests/unit/engine/test_provider_registration.py -v
```

Confirm: retrieval composition caps correctly, priority trimming works,
engine uses FoxKnowledgeProvider by default, import boundary respected.

---

## Task Group 5: Integration Testing and Final Verification

### Tasks

- [ ] Write integration test: full ingest/retrieve cycle
  - Create a FoxKnowledgeProvider with a real DuckDB (tmp_path)
  - Ingest a session with mock LLM returning 2 gotchas
  - Register an errata entry
  - Insert a review finding directly in review_findings table
  - Call retrieve() and verify all three categories appear in correct order

- [ ] Run `make check` — full lint + test suite
  - Ref: all requirements

### Verification

```bash
make check
```

Confirm: all tests pass, no lint errors, no import errors.
All correctness properties (CP-1 through CP-8) validated.
