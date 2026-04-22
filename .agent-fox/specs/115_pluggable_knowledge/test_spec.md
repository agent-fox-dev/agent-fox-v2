# Test Specification: Pluggable Knowledge Provider

## Test Environment

- Python 3.11+
- pytest with tmp_path fixtures for DuckDB isolation
- Mock LLM calls for gotcha extraction (no real LLM in unit tests)

## Test Contracts

### TC-1: FoxKnowledgeProvider Protocol Conformance

**Verifies:** [115-REQ-1.1], [115-REQ-1.2], [115-REQ-1.3]

**File:** `tests/unit/knowledge/test_fox_provider.py`

#### TC-1.1: Satisfies KnowledgeProvider protocol

```
GIVEN a FoxKnowledgeProvider constructed with a valid KnowledgeDB and config
WHEN isinstance(provider, KnowledgeProvider) is called
THEN it returns True
```

#### TC-1.2: Constructor accepts required arguments

```
GIVEN a KnowledgeDB connection and KnowledgeProviderConfig
WHEN FoxKnowledgeProvider(db, config) is constructed
THEN no exception is raised
AND the provider has ingest and retrieve methods
```

### TC-2: Gotcha Ingestion

**Verifies:** [115-REQ-2.1], [115-REQ-2.2], [115-REQ-2.3], [115-REQ-2.4],
[115-REQ-2.5], [115-REQ-2.E1], [115-REQ-2.E2], [115-REQ-2.E3]

**File:** `tests/unit/knowledge/test_gotcha_store.py`

#### TC-2.1: Gotchas extracted and stored on completed session

```
GIVEN a GotchaStore with a mock LLM that returns 2 gotcha candidates
WHEN extract_and_store() is called with session_status="completed"
THEN 2 rows are inserted into the gotchas table
AND each row has the correct spec_name, category, content_hash, session_id
```

#### TC-2.2: No extraction on non-completed session

```
GIVEN a FoxKnowledgeProvider
WHEN ingest() is called with context {"session_status": "failed"}
THEN no LLM call is made
AND no rows are inserted into the gotchas table
```

#### TC-2.3: Zero gotchas from LLM stores nothing

```
GIVEN a GotchaStore with a mock LLM that returns an empty list
WHEN extract_and_store() is called
THEN no rows are inserted into the gotchas table
```

#### TC-2.4: Duplicate gotcha is skipped

```
GIVEN a gotchas table with an existing gotcha for spec "foo" with content_hash H
WHEN extract_and_store() returns a candidate with the same normalized text (hash H)
THEN no new row is inserted
AND no error is raised
```

#### TC-2.5: LLM failure is logged and swallowed

```
GIVEN a GotchaStore with a mock LLM that raises RuntimeError
WHEN extract_and_store() is called
THEN a WARNING log message is emitted
AND no rows are inserted
AND no exception propagates
```

#### TC-2.6: More than 3 candidates truncated to 3

```
GIVEN a GotchaStore with a mock LLM that returns 5 candidates
WHEN extract_and_store() is called
THEN exactly 3 rows are inserted into the gotchas table
```

#### TC-2.7: Content hash normalization

```
GIVEN two texts "Foo  BAR  baz" and "foo bar baz"
WHEN _hash() is called on each
THEN both return the same SHA-256 hash
```

### TC-3: Gotcha Retrieval

**Verifies:** [115-REQ-3.1], [115-REQ-3.2], [115-REQ-3.3], [115-REQ-3.4],
[115-REQ-3.E1]

**File:** `tests/unit/knowledge/test_gotcha_store.py`

#### TC-3.1: Returns recent gotchas for spec

```
GIVEN 3 gotchas in the table for spec "foo" created within TTL
WHEN get_recent("foo") is called
THEN 3 strings are returned
AND each starts with "[GOTCHA] "
AND they are ordered most recent first
```

#### TC-3.2: Expired gotchas excluded

```
GIVEN a gotcha created 100 days ago with gotcha_ttl_days=90
WHEN get_recent() is called
THEN the expired gotcha is not in the result
```

#### TC-3.3: At most 5 gotchas returned

```
GIVEN 8 non-expired gotchas for spec "foo"
WHEN get_recent("foo") is called
THEN exactly 5 strings are returned
```

#### TC-3.4: No gotchas returns empty list

```
GIVEN an empty gotchas table
WHEN get_recent("foo") is called
THEN an empty list is returned
```

#### TC-3.5: Gotchas scoped to spec

```
GIVEN 2 gotchas for spec "foo" and 3 gotchas for spec "bar"
WHEN get_recent("foo") is called
THEN only the 2 "foo" gotchas are returned
```

### TC-4: Review Carry-Forward

**Verifies:** [115-REQ-4.1], [115-REQ-4.2], [115-REQ-4.3], [115-REQ-4.E1],
[115-REQ-4.E2]

**File:** `tests/unit/knowledge/test_review_reader.py`

#### TC-4.1: Returns unresolved critical/major findings

```
GIVEN review_findings with 1 critical open, 1 major open, 1 minor open for spec "foo"
WHEN get_unresolved("foo") is called
THEN 2 strings are returned (critical and major only)
AND each starts with "[REVIEW] "
```

#### TC-4.2: Excludes resolved findings

```
GIVEN review_findings with 1 critical resolved finding for spec "foo"
WHEN get_unresolved("foo") is called
THEN an empty list is returned
```

#### TC-4.3: Missing review_findings table

```
GIVEN a database without the review_findings table
WHEN get_unresolved("foo") is called
THEN an empty list is returned
AND no exception is raised
```

#### TC-4.4: Read-only — no writes to review_findings

```
GIVEN a ReviewReader
WHEN get_unresolved() is called
THEN no INSERT, UPDATE, or DELETE is executed on review_findings
```

### TC-5: Errata Index

**Verifies:** [115-REQ-5.1], [115-REQ-5.2], [115-REQ-5.3], [115-REQ-5.4],
[115-REQ-5.E1], [115-REQ-5.E2]

**File:** `tests/unit/knowledge/test_errata_index.py`

#### TC-5.1: Register and retrieve errata

```
GIVEN an empty errata_index table
WHEN register("spec_foo", "docs/errata/42_divergence.md") is called
AND get("spec_foo") is called
THEN 1 string is returned starting with "[ERRATA] "
AND the string contains the file path
AND register returns {"spec_name": "spec_foo", "file_path": "docs/errata/42_divergence.md"}
```

#### TC-5.2: Duplicate registration is idempotent

```
GIVEN an errata entry already registered for ("spec_foo", "docs/errata/42.md")
WHEN register("spec_foo", "docs/errata/42.md") is called again
THEN no error is raised
AND get("spec_foo") still returns exactly 1 entry
```

#### TC-5.3: Unregister removes entry

```
GIVEN a registered errata entry for ("spec_foo", "docs/errata/42.md")
WHEN unregister("spec_foo", "docs/errata/42.md") is called
AND get("spec_foo") is called
THEN an empty list is returned
```

#### TC-5.4: No errata returns empty list

```
GIVEN an empty errata_index table
WHEN get("nonexistent_spec") is called
THEN an empty list is returned
```

### TC-6: Retrieval Composition

**Verifies:** [115-REQ-6.1], [115-REQ-6.2], [115-REQ-6.3], [115-REQ-6.E1],
[115-REQ-6.E2]

**File:** `tests/unit/knowledge/test_fox_provider.py`

#### TC-6.1: Total items capped at max_items

```
GIVEN max_items=10, 2 errata, 3 review findings, 8 gotchas
WHEN retrieve() is called
THEN 10 items are returned: 2 errata + 3 reviews + 5 gotchas
```

#### TC-6.2: Gotchas trimmed first

```
GIVEN max_items=5, 0 errata, 3 review findings, 5 gotchas
WHEN retrieve() is called
THEN 5 items are returned: 3 reviews + 2 gotchas
```

#### TC-6.3: Reviews and errata exceed cap — all included

```
GIVEN max_items=5, 3 errata, 4 review findings, 2 gotchas
WHEN retrieve() is called
THEN 7 items are returned: 3 errata + 4 reviews + 0 gotchas
```

#### TC-6.4: Category order preserved

```
GIVEN 1 errata, 1 review finding, 1 gotcha
WHEN retrieve() is called
THEN the result order is: [ERRATA], [REVIEW], [GOTCHA]
```

#### TC-6.5: All categories empty

```
GIVEN no gotchas, no unresolved findings, no errata for spec "empty"
WHEN retrieve("empty", "any task") is called
THEN an empty list is returned
```

### TC-7: Gotcha Expiry

**Verifies:** [115-REQ-7.1], [115-REQ-7.2], [115-REQ-7.E1]

**File:** `tests/unit/knowledge/test_gotcha_store.py`

#### TC-7.1: Expired gotchas not in retrieval but still in DB

```
GIVEN a gotcha created 100 days ago with gotcha_ttl_days=90
WHEN get_recent() is called
THEN the gotcha is not returned
AND the row still exists in the gotchas table
```

#### TC-7.2: TTL of 0 excludes all gotchas

```
GIVEN gotcha_ttl_days=0 and 3 gotchas created today
WHEN get_recent() is called
THEN an empty list is returned
```

### TC-8: Configuration

**Verifies:** [115-REQ-8.1], [115-REQ-8.2], [115-REQ-8.3]

**File:** `tests/unit/core/test_config_knowledge.py`

#### TC-8.1: Default KnowledgeProviderConfig values

```
GIVEN no arguments
WHEN KnowledgeProviderConfig() is constructed
THEN max_items=10, gotcha_ttl_days=90, model_tier="SIMPLE"
```

#### TC-8.2: KnowledgeConfig includes provider config

```
GIVEN a KnowledgeConfig()
WHEN accessing config.provider
THEN it returns a KnowledgeProviderConfig with defaults
```

#### TC-8.3: Extra fields ignored

```
GIVEN a dict with unknown fields
WHEN KnowledgeProviderConfig(**dict) is constructed
THEN no ValidationError is raised
```

### TC-9: Schema Migration

**Verifies:** [115-REQ-9.1], [115-REQ-9.2], [115-REQ-9.3], [115-REQ-9.4]

**File:** `tests/unit/knowledge/test_migrations.py`

#### TC-9.1: gotchas table created

```
GIVEN a fresh DuckDB database
WHEN migrations are run
THEN the gotchas table exists with expected columns
```

#### TC-9.2: errata_index table created

```
GIVEN a fresh DuckDB database
WHEN migrations are run
THEN the errata_index table exists with expected columns
```

#### TC-9.3: Migration is idempotent

```
GIVEN a database where migrations have already run
WHEN migrations are run again
THEN no error is raised
AND table schemas are unchanged
```

### TC-10: Provider Registration

**Verifies:** [115-REQ-10.1], [115-REQ-10.2], [115-REQ-10.3]

**File:** `tests/unit/engine/test_provider_registration.py`

#### TC-10.1: Engine uses FoxKnowledgeProvider by default

```
GIVEN a standard engine configuration
WHEN the engine is constructed
THEN the provider is an instance of FoxKnowledgeProvider
AND isinstance(provider, KnowledgeProvider) is True
```

#### TC-10.2: Engine module boundary respected

```
GIVEN the engine source files after changes
WHEN scanning imports
THEN no engine file imports a knowledge module outside the allowed set
```

## Traceability Matrix

| Requirement | Test Contract |
|-------------|---------------|
| [115-REQ-1.1] | TC-1.1 |
| [115-REQ-1.2] | TC-1.1 |
| [115-REQ-1.3] | TC-1.2 |
| [115-REQ-1.E1] | TC-1.2 |
| [115-REQ-2.1] | TC-2.1 |
| [115-REQ-2.2] | TC-2.1 |
| [115-REQ-2.3] | TC-2.3 |
| [115-REQ-2.4] | TC-2.1 |
| [115-REQ-2.5] | TC-2.2 |
| [115-REQ-2.E1] | TC-2.4 |
| [115-REQ-2.E2] | TC-2.5 |
| [115-REQ-2.E3] | TC-2.6 |
| [115-REQ-3.1] | TC-3.1 |
| [115-REQ-3.2] | TC-3.2 |
| [115-REQ-3.3] | TC-3.3 |
| [115-REQ-3.4] | TC-3.1 |
| [115-REQ-3.E1] | TC-3.4 |
| [115-REQ-4.1] | TC-4.1 |
| [115-REQ-4.2] | TC-4.1 |
| [115-REQ-4.3] | TC-4.1 |
| [115-REQ-4.E1] | TC-4.2 |
| [115-REQ-4.E2] | TC-4.3 |
| [115-REQ-5.1] | TC-5.1 |
| [115-REQ-5.2] | TC-5.1 |
| [115-REQ-5.3] | TC-5.1 |
| [115-REQ-5.4] | TC-5.1, TC-5.3 |
| [115-REQ-5.E1] | TC-5.4 |
| [115-REQ-5.E2] | TC-5.1 |
| [115-REQ-6.1] | TC-6.1 |
| [115-REQ-6.2] | TC-6.2 |
| [115-REQ-6.3] | TC-6.4 |
| [115-REQ-6.E1] | TC-6.5 |
| [115-REQ-6.E2] | TC-6.3 |
| [115-REQ-7.1] | TC-7.1 |
| [115-REQ-7.2] | TC-7.1 |
| [115-REQ-7.E1] | TC-7.2 |
| [115-REQ-8.1] | TC-8.1 |
| [115-REQ-8.2] | TC-8.2 |
| [115-REQ-8.3] | TC-8.3 |
| [115-REQ-9.1] | TC-9.1 |
| [115-REQ-9.2] | TC-9.2 |
| [115-REQ-9.3] | TC-9.3 |
| [115-REQ-9.4] | TC-9.3 |
| [115-REQ-10.1] | TC-10.1 |
| [115-REQ-10.2] | TC-10.1 |
| [115-REQ-10.3] | TC-10.2 |
