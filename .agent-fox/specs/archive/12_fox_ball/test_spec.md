# Test Specification: Fox Ball -- Semantic Knowledge Oracle

## Overview

Tests for the Fox Ball: embedding generation, vector similarity search,
dual-write fact persistence, the oracle RAG pipeline, additional source
ingestion, the `agent-fox ask` CLI command, contradiction detection,
supersession tracking, and confidence indicators. Tests map to requirements
in `requirements.md` and correctness properties in `design.md`.

All Anthropic API calls are mocked. All DuckDB operations use in-memory
databases. No network calls in tests.

## Test Cases

### TS-12-1: Embed single text returns 1024-dim vector

**Requirement:** 12-REQ-2.1
**Type:** unit
**Description:** Verify that `embed_text` returns a 1024-dimensional float
vector when the API call succeeds.

**Preconditions:**
- Anthropic client is mocked to return a valid embedding response.

**Input:**
- `embed_text("DuckDB was chosen for its columnar analytics capabilities")`

**Expected:**
- Returns a list of 1024 floats.
- All values are finite numbers.

**Assertion pseudocode:**
```
mock_anthropic_embeddings(return_value=mock_1024_vector)
generator = EmbeddingGenerator(config)
result = generator.embed_text("DuckDB was chosen...")
ASSERT result IS NOT None
ASSERT len(result) == 1024
ASSERT all(isinstance(v, float) for v in result)
```

---

### TS-12-2: Embed batch returns parallel list of vectors

**Requirement:** 12-REQ-2.2
**Type:** unit
**Description:** Verify that `embed_batch` returns one embedding per input
text, in the same order.

**Preconditions:**
- Anthropic client is mocked to return N embedding vectors.

**Input:**
- `embed_batch(["fact one", "fact two", "fact three"])`

**Expected:**
- Returns a list of 3 items.
- Each item is a list of 1024 floats.

**Assertion pseudocode:**
```
mock_anthropic_embeddings(return_value=[vec1, vec2, vec3])
generator = EmbeddingGenerator(config)
results = generator.embed_batch(["fact one", "fact two", "fact three"])
ASSERT len(results) == 3
FOR EACH result IN results:
    ASSERT result IS NOT None
    ASSERT len(result) == 1024
```

---

### TS-12-3: Embed failure returns None

**Requirement:** 12-REQ-2.E1
**Type:** unit
**Description:** Verify that `embed_text` returns None and logs a warning
when the API call fails.

**Preconditions:**
- Anthropic client is mocked to raise an API error.

**Input:**
- `embed_text("some text")`

**Expected:**
- Returns None.
- A warning is logged mentioning the embedding failure.

**Assertion pseudocode:**
```
mock_anthropic_embeddings(side_effect=APIError("rate limited"))
generator = EmbeddingGenerator(config)
result = generator.embed_text("some text")
ASSERT result IS None
ASSERT "embedding" IN caplog.text.lower()
```

---

### TS-12-4: Vector search returns results sorted by similarity

**Requirement:** 12-REQ-3.1, 12-REQ-3.2
**Type:** unit
**Description:** Verify that vector search returns results ordered by
descending cosine similarity.

**Preconditions:**
- In-memory DuckDB with 5 facts and embeddings inserted.
- Query embedding is constructed to have known similarity to each fact.

**Input:**
- `search(query_embedding=query_vec, top_k=3)`

**Expected:**
- Returns exactly 3 results.
- Results are sorted: `results[0].similarity >= results[1].similarity >= results[2].similarity`.
- Each result has fact_id, content, spec_name, and similarity fields populated.

**Assertion pseudocode:**
```
db = setup_inmemory_db_with_5_facts_and_embeddings()
searcher = VectorSearch(db.connection, config)
results = searcher.search(query_vec, top_k=3)
ASSERT len(results) == 3
ASSERT results[0].similarity >= results[1].similarity
ASSERT results[1].similarity >= results[2].similarity
ASSERT all(r.fact_id != "" for r in results)
```

---

### TS-12-5: Vector search excludes facts without embeddings

**Requirement:** 12-REQ-3.3
**Type:** unit
**Description:** Verify that facts in `memory_facts` without a corresponding
row in `memory_embeddings` are excluded from search results.

**Preconditions:**
- In-memory DuckDB with 3 facts: 2 with embeddings, 1 without.

**Input:**
- `search(query_embedding=query_vec, top_k=10)`

**Expected:**
- Returns at most 2 results.
- The fact without an embedding is not in the results.

**Assertion pseudocode:**
```
db = setup_db_with_2_embedded_1_unembedded()
searcher = VectorSearch(db.connection, config)
results = searcher.search(query_vec, top_k=10)
ASSERT len(results) == 2
fact_ids = {r.fact_id for r in results}
ASSERT unembedded_fact_id NOT IN fact_ids
```

---

### TS-12-6: Vector search excludes superseded facts

**Requirement:** 12-REQ-7.2
**Type:** unit
**Description:** Verify that facts with `superseded_by IS NOT NULL` are
excluded from default search results.

**Preconditions:**
- In-memory DuckDB with 3 facts and embeddings. One fact has `superseded_by`
  set to another fact's ID.

**Input:**
- `search(query_embedding=query_vec, top_k=10, exclude_superseded=True)`

**Expected:**
- The superseded fact is not in the results.
- The superseding fact is in the results.

**Assertion pseudocode:**
```
db = setup_db_with_superseded_fact()
searcher = VectorSearch(db.connection, config)
results = searcher.search(query_vec, top_k=10, exclude_superseded=True)
fact_ids = {r.fact_id for r in results}
ASSERT superseded_fact_id NOT IN fact_ids
ASSERT superseding_fact_id IN fact_ids
```

---

### TS-12-7: Vector search returns empty for no embedded facts

**Requirement:** 12-REQ-3.E1
**Type:** unit
**Description:** Verify that search returns an empty list when there are no
embedded facts, without raising an error.

**Preconditions:**
- In-memory DuckDB with schema created but no facts or embeddings.

**Input:**
- `search(query_embedding=query_vec, top_k=20)`

**Expected:**
- Returns an empty list.
- No exception raised.

**Assertion pseudocode:**
```
db = setup_empty_db()
searcher = VectorSearch(db.connection, config)
results = searcher.search(query_vec, top_k=20)
ASSERT results == []
```

---

### TS-12-8: Dual-write writes to both JSONL and DuckDB

**Requirement:** 12-REQ-1.1, 12-REQ-1.3
**Type:** unit
**Description:** Verify that `write_fact` writes to both JSONL and DuckDB
with all provenance fields.

**Preconditions:**
- `tmp_path` JSONL file and in-memory DuckDB with schema.
- Embedding generator mocked to return a valid vector.

**Input:**
- `write_fact(fact)` with all provenance fields populated.

**Expected:**
- Fact appears in the JSONL file.
- Fact appears in `memory_facts` with all provenance fields.
- Embedding appears in `memory_embeddings`.

**Assertion pseudocode:**
```
store = MemoryStore(jsonl_path, db_conn, embedder)
store.write_fact(fact_with_provenance)
# Check JSONL
ASSERT fact_in_jsonl(jsonl_path, fact.id)
# Check DuckDB
row = db_conn.execute("SELECT * FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
ASSERT row IS NOT None
ASSERT row.content == fact.content
ASSERT row.spec_name == fact.spec_name
# Check embedding
emb = db_conn.execute("SELECT * FROM memory_embeddings WHERE id = ?", [fact.id]).fetchone()
ASSERT emb IS NOT None
```

---

### TS-12-9: Dual-write continues on DuckDB failure

**Requirement:** 12-REQ-1.E1
**Type:** unit
**Description:** Verify that JSONL write succeeds even when DuckDB is
unavailable, and a warning is logged.

**Preconditions:**
- `tmp_path` JSONL file.
- DuckDB connection is None (simulating unavailability).

**Input:**
- `write_fact(fact)`

**Expected:**
- Fact appears in the JSONL file.
- A warning is logged about DuckDB unavailability.
- No exception raised.

**Assertion pseudocode:**
```
store = MemoryStore(jsonl_path, db_conn=None, embedder=None)
store.write_fact(fact)
ASSERT fact_in_jsonl(jsonl_path, fact.id)
ASSERT "warning" IN caplog.text.lower() OR "duckdb" IN caplog.text.lower()
```

---

### TS-12-10: Dual-write stores fact without embedding on API failure

**Requirement:** 12-REQ-2.E1
**Type:** unit
**Description:** Verify that when embedding generation fails, the fact is
still written to both JSONL and DuckDB (without embedding).

**Preconditions:**
- `tmp_path` JSONL file and in-memory DuckDB.
- Embedding generator mocked to return None (failure).

**Input:**
- `write_fact(fact)`

**Expected:**
- Fact in JSONL.
- Fact in `memory_facts`.
- No row in `memory_embeddings` for this fact.
- Warning logged about embedding failure.

**Assertion pseudocode:**
```
mock_embedder = MockEmbedder(return_value=None)
store = MemoryStore(jsonl_path, db_conn, mock_embedder)
store.write_fact(fact)
ASSERT fact_in_jsonl(jsonl_path, fact.id)
row = db_conn.execute("SELECT * FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
ASSERT row IS NOT None
emb = db_conn.execute("SELECT * FROM memory_embeddings WHERE id = ?", [fact.id]).fetchone()
ASSERT emb IS None
```

---

### TS-12-11: Oracle returns grounded answer with sources

**Requirement:** 12-REQ-5.1, 12-REQ-5.2
**Type:** unit
**Description:** Verify that the oracle pipeline returns an answer with
source citations matching retrieved facts.

**Preconditions:**
- Embedding generator mocked to return a query vector.
- VectorSearch mocked to return 3 search results.
- Anthropic synthesis API mocked to return an answer with citations.

**Input:**
- `oracle.ask("why did we choose DuckDB?")`

**Expected:**
- Returns an OracleAnswer.
- `answer` is a non-empty string.
- `sources` contains the 3 search results.
- Each source has provenance (spec_name, etc.).

**Assertion pseudocode:**
```
mock_embedder.embed_text.return_value = query_vec
mock_search.search.return_value = [result1, result2, result3]
mock_anthropic_messages(return_value="DuckDB was chosen because...")
oracle = Oracle(mock_embedder, mock_search, config)
answer = oracle.ask("why did we choose DuckDB?")
ASSERT answer.answer != ""
ASSERT len(answer.sources) == 3
ASSERT answer.confidence IN ["high", "medium", "low"]
```

---

### TS-12-12: Oracle uses single API call (not streaming)

**Requirement:** 12-REQ-5.3
**Type:** unit
**Description:** Verify that the oracle uses `client.messages.create()` (not
`client.messages.stream()`).

**Preconditions:**
- All dependencies mocked.

**Input:**
- `oracle.ask("any question")`

**Expected:**
- `client.messages.create` is called exactly once.
- `client.messages.stream` is never called.

**Assertion pseudocode:**
```
oracle = Oracle(mock_embedder, mock_search, config)
oracle.ask("any question")
ASSERT mock_client.messages.create.call_count == 1
ASSERT mock_client.messages.stream.call_count == 0
```

---

### TS-12-13: Oracle flags contradictions

**Requirement:** 12-REQ-6.1
**Type:** unit
**Description:** Verify that the oracle identifies contradictions when the
synthesis model flags them.

**Preconditions:**
- Synthesis model mocked to return a response containing contradiction flags.

**Input:**
- `oracle.ask("what database do we use?")`
- Retrieved facts include one saying "SQLite" and another saying "DuckDB".

**Expected:**
- `answer.contradictions` is not None and not empty.
- Contradiction text references the conflicting facts.

**Assertion pseudocode:**
```
mock_synthesis_response = "...CONTRADICTION: fact A says SQLite, fact B says DuckDB..."
oracle = Oracle(mock_embedder, mock_search, config)
answer = oracle.ask("what database do we use?")
ASSERT answer.contradictions IS NOT None
ASSERT len(answer.contradictions) > 0
```

---

### TS-12-14: Ask command renders answer

**Requirement:** 12-REQ-5.1
**Type:** integration
**Description:** Verify that `agent-fox ask "question"` prints a formatted
answer to the terminal.

**Preconditions:**
- Oracle mocked to return a complete OracleAnswer.

**Input:**
- CLI invocation: `["ask", "why did we choose DuckDB?"]`

**Expected:**
- Exit code 0.
- Output contains the answer text.
- Output contains source citations.

**Assertion pseudocode:**
```
mock_oracle.ask.return_value = OracleAnswer(
    answer="DuckDB was chosen...",
    sources=[result1],
    contradictions=None,
    confidence="high",
)
result = cli_runner.invoke(main, ["ask", "why did we choose DuckDB?"])
ASSERT result.exit_code == 0
ASSERT "DuckDB was chosen" IN result.output
ASSERT "high" IN result.output.lower() OR "confidence" IN result.output.lower()
```

---

### TS-12-15: Ingest ADRs creates facts with correct category

**Requirement:** 12-REQ-4.1, 12-REQ-4.3
**Type:** unit
**Description:** Verify that ingesting ADRs creates facts with
`category="adr"` and embeds them.

**Preconditions:**
- `tmp_path` with two ADR markdown files.
- In-memory DuckDB with schema.
- Embedding generator mocked to return valid vectors.

**Input:**
- `ingestor.ingest_adrs(adr_dir=tmp_adr_dir)`

**Expected:**
- 2 facts added to `memory_facts` with `category="adr"`.
- 2 embeddings in `memory_embeddings`.
- `IngestResult.facts_added == 2`.

**Assertion pseudocode:**
```
create_adr_files(tmp_path / "docs/adr", ["001-use-duckdb.md", "002-use-click.md"])
ingestor = KnowledgeIngestor(db_conn, mock_embedder, tmp_path)
result = ingestor.ingest_adrs()
ASSERT result.facts_added == 2
ASSERT result.source_type == "adr"
rows = db_conn.execute("SELECT * FROM memory_facts WHERE category = 'adr'").fetchall()
ASSERT len(rows) == 2
```

---

### TS-12-16: Ingest git commits creates facts with commit SHA

**Requirement:** 12-REQ-4.2, 12-REQ-4.3
**Type:** unit
**Description:** Verify that ingesting git commits creates facts with
`category="git"` and the commit SHA recorded.

**Preconditions:**
- `subprocess.run` mocked to return 3 git log entries.
- In-memory DuckDB with schema.
- Embedding generator mocked.

**Input:**
- `ingestor.ingest_git_commits(limit=10)`

**Expected:**
- 3 facts added with `category="git"`.
- Each fact has `commit_sha` populated.

**Assertion pseudocode:**
```
mock_git_log(return_value=[commit1, commit2, commit3])
ingestor = KnowledgeIngestor(db_conn, mock_embedder, tmp_path)
result = ingestor.ingest_git_commits(limit=10)
ASSERT result.facts_added == 3
rows = db_conn.execute("SELECT * FROM memory_facts WHERE category = 'git'").fetchall()
ASSERT len(rows) == 3
ASSERT all(row.commit_sha IS NOT None for row in rows)
```

---

### TS-12-17: Supersession marks old fact correctly

**Requirement:** 12-REQ-7.1
**Type:** unit
**Description:** Verify that `mark_superseded` updates the `superseded_by`
column in `memory_facts`.

**Preconditions:**
- In-memory DuckDB with two facts (old and new).

**Input:**
- `store.mark_superseded(old_fact_id, new_fact_id)`

**Expected:**
- `memory_facts` row for old fact has `superseded_by = new_fact_id`.

**Assertion pseudocode:**
```
store.mark_superseded(old_id, new_id)
row = db_conn.execute(
    "SELECT superseded_by FROM memory_facts WHERE id = ?", [old_id]
).fetchone()
ASSERT str(row[0]) == new_id
```

---

### TS-12-18: has_embeddings returns correct state

**Requirement:** 12-REQ-5.E1
**Type:** unit
**Description:** Verify that `has_embeddings` returns False for an empty store
and True after inserting embeddings.

**Preconditions:**
- In-memory DuckDB with schema.

**Input:**
- `searcher.has_embeddings()` before and after inserting a fact with embedding.

**Expected:**
- Returns False initially.
- Returns True after inserting a fact with embedding.

**Assertion pseudocode:**
```
searcher = VectorSearch(db_conn, config)
ASSERT searcher.has_embeddings() == False
insert_fact_with_embedding(db_conn, fact, embedding)
ASSERT searcher.has_embeddings() == True
```

## Property Test Cases

### TS-12-P1: Dual-write consistency

**Property:** Property 1 from design.md
**Validates:** 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.E1
**Type:** property
**Description:** For any fact, after `write_fact()`, the fact is always
present in JSONL. If DuckDB is available, it is also in `memory_facts`.

**For any:** valid MemoryFact with random content and category
**Invariant:** Fact exists in JSONL after write. If DuckDB connection is
non-None, fact exists in `memory_facts`.

**Assertion pseudocode:**
```
FOR ANY fact IN random_memory_facts():
    store = MemoryStore(jsonl_path, db_conn, mock_embedder)
    store.write_fact(fact)
    ASSERT fact_in_jsonl(jsonl_path, fact.id)
    IF db_conn IS NOT None:
        row = db_conn.execute("SELECT id FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
        ASSERT row IS NOT None
```

---

### TS-12-P2: Embedding non-fatality

**Property:** Property 2 from design.md
**Validates:** 12-REQ-2.E1
**Type:** property
**Description:** For any fact where embedding fails, the fact is still
written to JSONL and DuckDB. No exception propagates.

**For any:** valid MemoryFact, with embedding generator that randomly
succeeds or fails
**Invariant:** Fact is always in JSONL and `memory_facts`. No exception.

**Assertion pseudocode:**
```
FOR ANY fact IN random_memory_facts(),
        embed_succeeds IN booleans():
    embedder = MockEmbedder(succeeds=embed_succeeds)
    store = MemoryStore(jsonl_path, db_conn, embedder)
    # Should never raise
    store.write_fact(fact)
    ASSERT fact_in_jsonl(jsonl_path, fact.id)
    ASSERT fact_in_duckdb(db_conn, fact.id)
```

---

### TS-12-P3: Search result ordering

**Property:** Property 3 from design.md
**Validates:** 12-REQ-3.1
**Type:** property
**Description:** For any vector search, results are sorted by descending
similarity.

**For any:** in-memory DuckDB with N embedded facts (N in [1, 50]),
random query vector
**Invariant:** For all i < j: `results[i].similarity >= results[j].similarity`

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 50):
    db = setup_db_with_n_random_facts(n)
    searcher = VectorSearch(db.connection, config)
    results = searcher.search(random_query_vec(), top_k=n)
    FOR i IN range(len(results) - 1):
        ASSERT results[i].similarity >= results[i + 1].similarity
```

---

### TS-12-P4: Ingestion idempotency

**Property:** Property 7 from design.md
**Validates:** 12-REQ-4.1, 12-REQ-4.2
**Type:** property
**Description:** Ingesting the same source twice does not create duplicates.

**For any:** set of ADR files or git commits
**Invariant:** After two ingestions, the fact count equals the source count.

**Assertion pseudocode:**
```
FOR ANY adr_count IN integers(1, 10):
    create_n_adr_files(tmp_path, adr_count)
    ingestor = KnowledgeIngestor(db_conn, mock_embedder, tmp_path)
    result1 = ingestor.ingest_adrs()
    result2 = ingestor.ingest_adrs()
    ASSERT result1.facts_added == adr_count
    ASSERT result2.facts_added == 0
    ASSERT result2.facts_skipped == adr_count
    total = db_conn.execute("SELECT COUNT(*) FROM memory_facts WHERE category = 'adr'").fetchone()[0]
    ASSERT total == adr_count
```

## Edge Case Tests

### TS-12-E1: Ask with empty knowledge store

**Requirement:** 12-REQ-5.E1
**Type:** integration
**Description:** Verify that `agent-fox ask` on an empty store prints a
helpful message.

**Preconditions:**
- In-memory DuckDB with schema but no facts.

**Input:**
- CLI invocation: `["ask", "any question"]`

**Expected:**
- Exit code 0 (informational, not an error).
- Output mentions that no knowledge has been accumulated.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["ask", "any question"])
ASSERT result.exit_code == 0
ASSERT "no knowledge" IN result.output.lower() OR "accumulated" IN result.output.lower()
```

---

### TS-12-E2: Ask with unavailable knowledge store

**Requirement:** 12-REQ-5.E2
**Type:** integration
**Description:** Verify that `agent-fox ask` reports an error when the
knowledge store is unavailable.

**Preconditions:**
- `open_knowledge_store` mocked to return None.

**Input:**
- CLI invocation: `["ask", "any question"]`

**Expected:**
- Exit code 1.
- Output mentions that the knowledge store is unavailable.

**Assertion pseudocode:**
```
mock_open_knowledge_store(return_value=None)
result = cli_runner.invoke(main, ["ask", "any question"])
ASSERT result.exit_code == 1
ASSERT "unavailable" IN result.output.lower() OR "knowledge store" IN result.output.lower()
```

---

### TS-12-E3: Embedding API failure on ask query

**Requirement:** 12-REQ-2.E2
**Type:** unit
**Description:** Verify that the oracle raises `KnowledgeStoreError` when the
query embedding fails.

**Preconditions:**
- Embedding generator mocked to return None for the query.

**Input:**
- `oracle.ask("any question")`

**Expected:**
- `KnowledgeStoreError` raised.
- Error message suggests retrying.

**Assertion pseudocode:**
```
mock_embedder.embed_text.return_value = None
oracle = Oracle(mock_embedder, mock_search, config)
ASSERT_RAISES KnowledgeStoreError FROM oracle.ask("any question")
ASSERT "retry" IN str(error).lower() OR "embedding" IN str(error).lower()
```

---

### TS-12-E4: Ingest ADRs with missing directory

**Requirement:** 12-REQ-4.1
**Type:** unit
**Description:** Verify that ingesting ADRs when `docs/adr/` does not exist
returns zero facts without error.

**Preconditions:**
- `docs/adr/` directory does not exist in the project root.

**Input:**
- `ingestor.ingest_adrs()`

**Expected:**
- Returns `IngestResult(source_type="adr", facts_added=0, facts_skipped=0, embedding_failures=0)`.
- No exception raised.

**Assertion pseudocode:**
```
ingestor = KnowledgeIngestor(db_conn, mock_embedder, tmp_path_without_adr_dir)
result = ingestor.ingest_adrs()
ASSERT result.facts_added == 0
ASSERT result.facts_skipped == 0
```

---

### TS-12-E5: Confidence levels based on result quality

**Requirement:** 12-REQ-8.1
**Type:** unit
**Description:** Verify that the oracle assigns correct confidence levels
based on the number and similarity of retrieved facts.

**Preconditions:**
- Oracle with mocked search returning varying numbers of results.

**Input:**
- Case 1: 5 results with similarity > 0.7 --> "high"
- Case 2: 1 result with similarity 0.6 --> "medium"
- Case 3: 0 results --> "low"

**Expected:**
- Confidence matches the expected level for each case.

**Assertion pseudocode:**
```
# High confidence
results_high = [SearchResult(..., similarity=0.8)] * 5
ASSERT oracle._determine_confidence(results_high) == "high"

# Medium confidence
results_med = [SearchResult(..., similarity=0.6)]
ASSERT oracle._determine_confidence(results_med) == "medium"

# Low confidence
ASSERT oracle._determine_confidence([]) == "low"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 12-REQ-1.1 | TS-12-8, TS-12-P1 | unit, property |
| 12-REQ-1.2 | TS-12-P1 | property |
| 12-REQ-1.3 | TS-12-8 | unit |
| 12-REQ-1.E1 | TS-12-9, TS-12-P1 | unit, property |
| 12-REQ-2.1 | TS-12-1 | unit |
| 12-REQ-2.2 | TS-12-2 | unit |
| 12-REQ-2.E1 | TS-12-3, TS-12-10, TS-12-P2 | unit, property |
| 12-REQ-2.E2 | TS-12-E3 | unit |
| 12-REQ-3.1 | TS-12-4, TS-12-P3 | unit, property |
| 12-REQ-3.2 | TS-12-4 | unit |
| 12-REQ-3.3 | TS-12-5 | unit |
| 12-REQ-3.E1 | TS-12-7 | unit |
| 12-REQ-4.1 | TS-12-15, TS-12-P4, TS-12-E4 | unit, property |
| 12-REQ-4.2 | TS-12-16, TS-12-P4 | unit, property |
| 12-REQ-4.3 | TS-12-15, TS-12-16 | unit |
| 12-REQ-5.1 | TS-12-11, TS-12-14 | unit, integration |
| 12-REQ-5.2 | TS-12-11 | unit |
| 12-REQ-5.3 | TS-12-12 | unit |
| 12-REQ-5.E1 | TS-12-18, TS-12-E1 | unit, integration |
| 12-REQ-5.E2 | TS-12-E2 | integration |
| 12-REQ-6.1 | TS-12-13 | unit |
| 12-REQ-7.1 | TS-12-17 | unit |
| 12-REQ-7.2 | TS-12-6 | unit |
| 12-REQ-8.1 | TS-12-E5 | unit |
| Property 1 | TS-12-P1 | property |
| Property 2 | TS-12-P2 | property |
| Property 3 | TS-12-P3 | property |
| Property 7 | TS-12-P4 | property |
