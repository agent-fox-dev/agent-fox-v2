# Test Specification: Knowledge Harvest & Causal Graph

## Overview

Tests validate that the knowledge harvest pipeline extracts facts from every
successful coder session (with fallback when summaries are absent), stores them
with full provenance, generates embeddings, extracts causal links with a
bounded context window, and emits appropriate audit events. Tests map to
requirements in `requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-52-1: Fact extraction from session summary

**Requirement:** 52-REQ-1.1
**Type:** unit
**Description:** Verify that a completed session with a valid
`.session-summary.json` triggers fact extraction with the summary text.

**Preconditions:**
- Session completed with status `"completed"`.
- `.session-summary.json` exists with `{"summary": "test transcript text"}`.
- Mock LLM returns one valid fact.

**Input:**
- Session status: `"completed"`
- Summary JSON: `{"summary": "The API retry logic needs exponential backoff."}`

**Expected:**
- `extract_and_store_knowledge()` called with `transcript="The API retry logic needs exponential backoff."`
- One fact inserted into `memory_facts`.

**Assertion pseudocode:**
```
mock_extract = mock(extract_and_store_knowledge)
lifecycle.post_session_integrate(status="completed")
ASSERT mock_extract.called_once
ASSERT mock_extract.call_args.transcript == "The API retry logic needs exponential backoff."
```

### TS-52-2: Fallback input when summary is absent

**Requirement:** 52-REQ-1.2
**Type:** unit
**Description:** Verify that a completed session without
`.session-summary.json` constructs and uses a fallback input.

**Preconditions:**
- Session completed with status `"completed"`.
- `.session-summary.json` does not exist.
- Session has spec_name, task_group, node_id, and commits.

**Input:**
- Session status: `"completed"`
- No summary file.
- spec_name: `"03_api_routes"`, task_group: `2`, node_id: `"coder_03_2"`
- Commit diff: `"diff --git a/routes.py..."`

**Expected:**
- `extract_and_store_knowledge()` called with fallback input containing
  spec name, task group, node ID, and commit diff.

**Assertion pseudocode:**
```
lifecycle.summary_file = None
mock_extract = mock(extract_and_store_knowledge)
lifecycle.post_session_integrate(status="completed")
ASSERT mock_extract.called_once
transcript = mock_extract.call_args.transcript
ASSERT "03_api_routes" IN transcript
ASSERT "coder_03_2" IN transcript
ASSERT "diff --git" IN transcript
```

### TS-52-3: Extraction error does not fail session

**Requirement:** 52-REQ-1.3
**Type:** unit
**Description:** Verify that an exception from `extract_and_store_knowledge()`
is caught and logged, not propagated.

**Preconditions:**
- Session completed with status `"completed"`.
- `extract_and_store_knowledge()` raises `RuntimeError`.

**Input:**
- Session status: `"completed"`
- Mock extract raises `RuntimeError("LLM timeout")`

**Expected:**
- No exception propagated to caller.
- Warning logged.
- Session record returned normally.

**Assertion pseudocode:**
```
mock_extract = mock(extract_and_store_knowledge, side_effect=RuntimeError)
record = lifecycle.post_session_integrate(status="completed")
ASSERT record.status == "completed"
ASSERT warning_logged("Knowledge extraction failed")
```

### TS-52-4: Fact provenance fields populated

**Requirement:** 52-REQ-2.1
**Type:** integration
**Description:** Verify that inserted facts have all provenance fields
populated (non-NULL).

**Preconditions:**
- In-memory DuckDB with `memory_facts` table.
- LLM returns a fact with category, confidence, content.

**Input:**
- Fact with content `"DuckDB needs explicit UUID casting"`,
  category `"gotcha"`, confidence `0.9`.
- spec_name: `"11_duckdb"`, session_id: `"coder_11_1"`,
  commit_sha: `"abc123"`.

**Expected:**
- Row in `memory_facts` with all fields non-NULL except `supersedes`.

**Assertion pseudocode:**
```
sync_facts_to_duckdb(db, [fact])
row = db.execute("SELECT * FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
ASSERT row.category IS NOT NULL
ASSERT row.confidence IS NOT NULL
ASSERT row.spec_name == "11_duckdb"
ASSERT row.session_id == "coder_11_1"
ASSERT row.commit_sha == "abc123"
```

### TS-52-5: Duplicate fact insertion is idempotent

**Requirement:** 52-REQ-2.2
**Type:** unit
**Description:** Verify that inserting the same fact twice results in one row.

**Preconditions:**
- In-memory DuckDB with `memory_facts` table.

**Input:**
- Same fact inserted twice (same UUID).

**Expected:**
- Exactly one row in `memory_facts` for that UUID.

**Assertion pseudocode:**
```
sync_facts_to_duckdb(db, [fact])
sync_facts_to_duckdb(db, [fact])
count = db.execute("SELECT COUNT(*) FROM memory_facts WHERE id = ?", [fact.id]).fetchone()[0]
ASSERT count == 1
```

### TS-52-6: Embedding generated for new fact

**Requirement:** 52-REQ-3.1
**Type:** integration
**Description:** Verify that embeddings are generated and stored for new facts.

**Preconditions:**
- In-memory DuckDB with `memory_facts` and `memory_embeddings` tables.
- Embedding model available (or mocked).

**Input:**
- One fact inserted into `memory_facts`.

**Expected:**
- Corresponding row in `memory_embeddings` with non-null embedding vector.

**Assertion pseudocode:**
```
extract_and_store_knowledge(transcript, ...)
row = db.execute("SELECT embedding FROM memory_embeddings WHERE id = ?", [fact.id]).fetchone()
ASSERT row IS NOT NULL
ASSERT len(row.embedding) > 0
```

### TS-52-7: Embedding failure does not block fact storage

**Requirement:** 52-REQ-3.2
**Type:** unit
**Description:** Verify that a fact is stored even when embedding generation
fails.

**Preconditions:**
- Embedding generator raises an exception.

**Input:**
- One fact, embedding model raises `RuntimeError`.

**Expected:**
- Fact exists in `memory_facts`.
- No row in `memory_embeddings` for that fact.
- Warning logged.

**Assertion pseudocode:**
```
mock_embedder = mock(EmbeddingGenerator, side_effect=RuntimeError)
extract_and_store_knowledge(transcript, ..., embedder=mock_embedder)
fact_row = db.execute("SELECT * FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
ASSERT fact_row IS NOT NULL
embed_row = db.execute("SELECT * FROM memory_embeddings WHERE id = ?", [fact.id]).fetchone()
ASSERT embed_row IS NULL
ASSERT warning_logged("embedding")
```

### TS-52-8: Harvest.complete audit event emitted

**Requirement:** 52-REQ-4.1
**Type:** unit
**Description:** Verify that a `harvest.complete` audit event is emitted on
successful extraction with >= 1 fact.

**Preconditions:**
- Sink dispatcher available with run_id set.
- LLM returns 3 facts.

**Input:**
- Transcript producing 3 facts in categories `["gotcha", "pattern"]`.

**Expected:**
- `harvest.complete` audit event emitted with `fact_count=3`,
  `categories=["gotcha", "pattern"]`, and `causal_link_count` >= 0.

**Assertion pseudocode:**
```
events = capture_audit_events(extract_and_store_knowledge(...))
harvest_events = [e for e in events if e.event_type == "harvest.complete"]
ASSERT len(harvest_events) == 1
ASSERT harvest_events[0].payload["fact_count"] == 3
ASSERT set(harvest_events[0].payload["categories"]) == {"gotcha", "pattern"}
```

### TS-52-9: Harvest.empty audit event on zero facts

**Requirement:** 52-REQ-4.2
**Type:** unit
**Description:** Verify that a warning-severity `harvest.empty` event is
emitted when extraction produces zero facts from non-empty input.

**Preconditions:**
- Sink dispatcher available.
- LLM returns empty fact list.

**Input:**
- Non-empty transcript `"Some session content"` producing zero facts.

**Expected:**
- `harvest.empty` audit event with warning severity.

**Assertion pseudocode:**
```
mock_llm returns []
events = capture_audit_events(extract_and_store_knowledge("Some session content", ...))
empty_events = [e for e in events if e.event_type == "harvest.empty"]
ASSERT len(empty_events) == 1
ASSERT empty_events[0].severity == "warning"
```

### TS-52-10: Causal extraction triggered when fact count >= 5

**Requirement:** 52-REQ-5.1
**Type:** unit
**Description:** Verify that causal link extraction is invoked when fact
count meets the threshold.

**Preconditions:**
- 5 existing non-superseded facts in `memory_facts`.
- New extraction produces 1 fact.

**Input:**
- Transcript producing 1 new fact. Total fact count after insertion: 6.

**Expected:**
- `_extract_causal_links()` called.

**Assertion pseudocode:**
```
db = setup_db_with_n_facts(5)
mock_causal = mock(_extract_causal_links)
extract_and_store_knowledge(transcript, ...)
ASSERT mock_causal.called_once
```

### TS-52-11: Causal extraction skipped when fact count < 5

**Requirement:** 52-REQ-5.2
**Type:** unit
**Description:** Verify that causal link extraction is skipped when fewer
than 5 non-superseded facts exist.

**Preconditions:**
- 2 existing non-superseded facts in `memory_facts`.
- New extraction produces 1 fact.

**Input:**
- Transcript producing 1 new fact. Total fact count: 3.

**Expected:**
- `_extract_causal_links()` NOT called.
- Debug log emitted: `"Skipping causal extraction: insufficient facts (3 < 5)"`.

**Assertion pseudocode:**
```
db = setup_db_with_n_facts(2)
mock_causal = mock(_extract_causal_links)
extract_and_store_knowledge(transcript, ...)
ASSERT NOT mock_causal.called
ASSERT debug_logged("Skipping causal extraction")
```

### TS-52-12: Causal context window bounded

**Requirement:** 52-REQ-6.1
**Type:** unit
**Description:** Verify that when fact count exceeds `causal_context_limit`,
only the top N by similarity are included in the prompt.

**Preconditions:**
- 250 existing facts with embeddings.
- `causal_context_limit` = 200.
- New extraction produces 1 fact.

**Input:**
- 251 total facts, limit 200.

**Expected:**
- Causal extraction prompt contains at most 201 facts (200 prior + 1 new).

**Assertion pseudocode:**
```
db = setup_db_with_n_facts(250)
prompt = capture_causal_prompt(extract_and_store_knowledge(transcript, ...))
fact_count_in_prompt = count_facts_in_prompt(prompt)
ASSERT fact_count_in_prompt <= 201
```

### TS-52-13: Causal link idempotent insertion

**Requirement:** 52-REQ-7.1
**Type:** integration
**Description:** Verify that inserting the same causal link twice results in
one row.

**Preconditions:**
- Two facts exist in `memory_facts`.

**Input:**
- Insert link (fact_a, fact_b) twice.

**Expected:**
- Exactly one row in `fact_causes` for (fact_a, fact_b).

**Assertion pseudocode:**
```
store_causal_links(conn, [(fact_a.id, fact_b.id)])
store_causal_links(conn, [(fact_a.id, fact_b.id)])
count = conn.execute("SELECT COUNT(*) FROM fact_causes WHERE cause_id = ? AND effect_id = ?", [fact_a.id, fact_b.id]).fetchone()[0]
ASSERT count == 1
```

### TS-52-14: Causal link audit event

**Requirement:** 52-REQ-7.2
**Type:** unit
**Description:** Verify that a `fact.causal_links` audit event is emitted
after link extraction.

**Preconditions:**
- Sink dispatcher available.
- Causal extraction produces 2 new links.

**Input:**
- LLM returns 2 causal links.

**Expected:**
- `fact.causal_links` audit event with `new_link_count=2` and
  `total_link_count` >= 2.

**Assertion pseudocode:**
```
events = capture_audit_events(_extract_causal_links(...))
link_events = [e for e in events if e.event_type == "fact.causal_links"]
ASSERT len(link_events) == 1
ASSERT link_events[0].payload["new_link_count"] == 2
```

## Edge Case Tests

### TS-52-E1: Fallback with no commits

**Requirement:** 52-REQ-1.E1
**Type:** unit
**Description:** Verify fallback input is constructed without diff when
session has no commits.

**Preconditions:**
- No `.session-summary.json`.
- Session made no commits (empty diff).

**Input:**
- spec_name: `"05_store"`, node_id: `"coder_05_1"`.

**Expected:**
- Fallback input contains spec name and node ID.
- Fallback input does NOT contain a `## Changes` section.

**Assertion pseudocode:**
```
fallback = lifecycle._build_fallback_input(workspace, "coder_05_1")
ASSERT "05_store" IN fallback
ASSERT "coder_05_1" IN fallback
ASSERT "## Changes" NOT IN fallback
```

### TS-52-E2: Non-completed session skips extraction

**Requirement:** 52-REQ-1.E2
**Type:** unit
**Description:** Verify that failed sessions do not trigger fact extraction.

**Preconditions:**
- Session completed with status `"failed"`.

**Input:**
- Session status: `"failed"`.

**Expected:**
- `extract_and_store_knowledge()` NOT called.

**Assertion pseudocode:**
```
mock_extract = mock(extract_and_store_knowledge)
lifecycle.post_session_integrate(status="failed")
ASSERT NOT mock_extract.called
```

### TS-52-E3: Invalid category fact skipped

**Requirement:** 52-REQ-2.E1
**Type:** unit
**Description:** Verify that facts with invalid categories are skipped.

**Preconditions:**
- LLM returns a fact with category `"invalid_cat"`.

**Input:**
- Fact JSON: `{"content": "test", "category": "invalid_cat", "confidence": "high"}`

**Expected:**
- Fact is not inserted into `memory_facts`.
- Warning logged.

**Assertion pseudocode:**
```
facts = parse_extracted_facts([{"category": "invalid_cat", ...}])
ASSERT len(facts) == 0
ASSERT warning_logged("invalid category")
```

### TS-52-E4: Missing fact in causal link

**Requirement:** 52-REQ-7.E1
**Type:** integration
**Description:** Verify that causal links referencing non-existent facts are
skipped.

**Preconditions:**
- One fact exists in `memory_facts`. The other does not.

**Input:**
- Link: `(existing_fact_id, nonexistent_id)`.

**Expected:**
- Link NOT inserted into `fact_causes`.
- Warning logged with the missing fact ID.

**Assertion pseudocode:**
```
stored = store_causal_links(conn, [(existing_id, nonexistent_id)])
ASSERT stored == 0
count = conn.execute("SELECT COUNT(*) FROM fact_causes").fetchone()[0]
ASSERT count == 0
ASSERT warning_logged(nonexistent_id)
```

### TS-52-E5: Sink dispatcher is None

**Requirement:** 52-REQ-4.E1
**Type:** unit
**Description:** Verify that audit events are silently skipped when sink
dispatcher is None.

**Preconditions:**
- `sink_dispatcher=None`.

**Input:**
- Successful extraction producing 1 fact.

**Expected:**
- No exception raised.
- No audit events emitted.

**Assertion pseudocode:**
```
extract_and_store_knowledge(transcript, ..., sink_dispatcher=None)
# No exception means pass
```

### TS-52-E6: Facts without embeddings in causal context

**Requirement:** 52-REQ-6.E1
**Type:** unit
**Description:** Verify that facts lacking embeddings are appended after
similarity-ranked facts.

**Preconditions:**
- 250 facts total: 200 with embeddings, 50 without.
- `causal_context_limit` = 200.

**Input:**
- 1 new fact.

**Expected:**
- Top similarity-ranked facts included first.
- Non-embedded facts appended after, up to limit.
- Total facts in prompt <= 201.

**Assertion pseudocode:**
```
db = setup_db_with_mixed_embeddings(200_with, 50_without)
prompt = capture_causal_prompt(extract_and_store_knowledge(transcript, ...))
ASSERT count_facts_in_prompt(prompt) <= 201
```

## Property Test Cases

### TS-52-P1: Harvest always attempts extraction

**Property:** Property 1 from design.md
**Validates:** 52-REQ-1.1, 52-REQ-1.2
**Type:** property
**Description:** For any completed session, extraction is invoked with
non-empty input regardless of summary file presence.

**For any:** session with status "completed", with or without
`.session-summary.json`, with or without commits.
**Invariant:** `extract_and_store_knowledge()` is called with a non-empty
transcript string.

**Assertion pseudocode:**
```
FOR ANY session IN completed_sessions(has_summary=booleans(), has_commits=booleans()):
    mock_extract = mock(extract_and_store_knowledge)
    lifecycle.post_session_integrate(status="completed")
    ASSERT mock_extract.called_once
    ASSERT len(mock_extract.call_args.transcript) > 0
```

### TS-52-P2: Fact provenance completeness

**Property:** Property 2 from design.md
**Validates:** 52-REQ-2.1
**Type:** property
**Description:** For any extracted fact, all provenance fields are non-NULL.

**For any:** fact with valid category, confidence in [0.0, 1.0], non-empty
content, spec_name, session_id, and commit_sha.
**Invariant:** After insertion, the row in `memory_facts` has no NULL fields
except `supersedes`.

**Assertion pseudocode:**
```
FOR ANY fact IN valid_facts():
    sync_facts_to_duckdb(db, [fact])
    row = db.execute("SELECT * FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
    ASSERT row.category IS NOT NULL
    ASSERT row.confidence IS NOT NULL
    ASSERT row.spec_name IS NOT NULL
    ASSERT row.session_id IS NOT NULL
    ASSERT row.commit_sha IS NOT NULL
```

### TS-52-P3: Embedding failure isolation

**Property:** Property 3 from design.md
**Validates:** 52-REQ-3.1, 52-REQ-3.2
**Type:** property
**Description:** Embedding failure never prevents fact storage.

**For any:** fact where embedding generation may succeed or fail.
**Invariant:** The fact exists in `memory_facts` regardless of embedding
outcome.

**Assertion pseudocode:**
```
FOR ANY fact IN valid_facts(), embed_fails IN booleans():
    embedder = mock(EmbeddingGenerator, fails=embed_fails)
    store_fact_with_embedding(db, fact, embedder)
    row = db.execute("SELECT id FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
    ASSERT row IS NOT NULL
```

### TS-52-P4: Causal extraction minimum threshold

**Property:** Property 4 from design.md
**Validates:** 52-REQ-5.1, 52-REQ-5.2
**Type:** property
**Description:** Causal extraction only runs when fact count >= 5.

**For any:** fact count in [0, 100].
**Invariant:** `_extract_causal_links()` is called if and only if total
non-superseded fact count >= 5.

**Assertion pseudocode:**
```
FOR ANY n IN integers(0, 100):
    db = setup_db_with_n_facts(n)
    mock_causal = mock(_extract_causal_links)
    # trigger extraction that adds 1 fact
    extract_and_store_knowledge(transcript, ...)
    IF n + 1 >= 5:
        ASSERT mock_causal.called
    ELSE:
        ASSERT NOT mock_causal.called
```

### TS-52-P5: Causal context window bound

**Property:** Property 5 from design.md
**Validates:** 52-REQ-6.1, 52-REQ-6.2
**Type:** property
**Description:** Causal prompt never exceeds the context limit.

**For any:** fact count in [5, 500], causal_context_limit in [10, 500].
**Invariant:** The number of prior facts in the causal extraction prompt is
<= causal_context_limit.

**Assertion pseudocode:**
```
FOR ANY n IN integers(5, 500), limit IN integers(10, 500):
    db = setup_db_with_n_facts(n)
    prompt = capture_causal_prompt(extract_with_limit(db, limit))
    ASSERT count_prior_facts_in_prompt(prompt) <= limit
```

### TS-52-P6: Causal link idempotency

**Property:** Property 6 from design.md
**Validates:** 52-REQ-7.1
**Type:** property
**Description:** Inserting the same causal link N times results in one row.

**For any:** valid fact pair (cause, effect), N insertions in [1, 10].
**Invariant:** Exactly one row exists in `fact_causes`.

**Assertion pseudocode:**
```
FOR ANY cause_id, effect_id IN valid_fact_pairs(), n IN integers(1, 10):
    FOR i IN range(n):
        store_causal_links(conn, [(cause_id, effect_id)])
    count = conn.execute("SELECT COUNT(*) FROM fact_causes WHERE cause_id = ? AND effect_id = ?", [cause_id, effect_id]).fetchone()[0]
    ASSERT count == 1
```

### TS-52-P7: Causal link referential integrity

**Property:** Property 7 from design.md
**Validates:** 52-REQ-7.E1
**Type:** property
**Description:** Links with non-existent fact IDs are never stored.

**For any:** link where at least one fact ID does not exist in `memory_facts`.
**Invariant:** The link is not inserted; `store_causal_links()` returns 0
for that link.

**Assertion pseudocode:**
```
FOR ANY existing_ids IN sets_of_uuids(), missing_id IN uuids():
    ASSUME missing_id NOT IN existing_ids
    stored = store_causal_links(conn, [(existing_ids[0], missing_id)])
    ASSERT stored == 0
```

### TS-52-P8: Audit event on success

**Property:** Property 8 from design.md
**Validates:** 52-REQ-4.1
**Type:** property
**Description:** Successful harvest always emits a `harvest.complete` event.

**For any:** extraction producing N facts where N >= 1.
**Invariant:** Exactly one `harvest.complete` event is emitted with
`fact_count == N`.

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 20):
    mock_llm returns n facts
    events = capture_audit_events(extract_and_store_knowledge(...))
    harvest_events = [e for e in events if e.event_type == "harvest.complete"]
    ASSERT len(harvest_events) == 1
    ASSERT harvest_events[0].payload["fact_count"] == n
```

### TS-52-P9: Audit event on empty harvest

**Property:** Property 9 from design.md
**Validates:** 52-REQ-4.2
**Type:** property
**Description:** Empty harvest from non-empty input always emits
`harvest.empty`.

**For any:** non-empty transcript producing zero facts.
**Invariant:** Exactly one `harvest.empty` event with warning severity.

**Assertion pseudocode:**
```
FOR ANY transcript IN non_empty_strings():
    mock_llm returns []
    events = capture_audit_events(extract_and_store_knowledge(transcript, ...))
    empty_events = [e for e in events if e.event_type == "harvest.empty"]
    ASSERT len(empty_events) == 1
    ASSERT empty_events[0].severity == "warning"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 52-REQ-1.1 | TS-52-1 | unit |
| 52-REQ-1.2 | TS-52-2 | unit |
| 52-REQ-1.3 | TS-52-3 | unit |
| 52-REQ-1.E1 | TS-52-E1 | unit |
| 52-REQ-1.E2 | TS-52-E2 | unit |
| 52-REQ-2.1 | TS-52-4 | integration |
| 52-REQ-2.2 | TS-52-5 | unit |
| 52-REQ-2.E1 | TS-52-E3 | unit |
| 52-REQ-3.1 | TS-52-6 | integration |
| 52-REQ-3.2 | TS-52-7 | unit |
| 52-REQ-3.E1 | TS-52-E6 | unit |
| 52-REQ-4.1 | TS-52-8 | unit |
| 52-REQ-4.2 | TS-52-9 | unit |
| 52-REQ-4.E1 | TS-52-E5 | unit |
| 52-REQ-5.1 | TS-52-10 | unit |
| 52-REQ-5.2 | TS-52-11 | unit |
| 52-REQ-5.E1 | TS-52-E6 | unit |
| 52-REQ-6.1 | TS-52-12 | unit |
| 52-REQ-6.2 | TS-52-12 | unit |
| 52-REQ-6.E1 | TS-52-E6 | unit |
| 52-REQ-7.1 | TS-52-13 | integration |
| 52-REQ-7.2 | TS-52-14 | unit |
| 52-REQ-7.E1 | TS-52-E4 | integration |
| Property 1 | TS-52-P1 | property |
| Property 2 | TS-52-P2 | property |
| Property 3 | TS-52-P3 | property |
| Property 4 | TS-52-P4 | property |
| Property 5 | TS-52-P5 | property |
| Property 6 | TS-52-P6 | property |
| Property 7 | TS-52-P7 | property |
| Property 8 | TS-52-P8 | property |
| Property 9 | TS-52-P9 | property |
