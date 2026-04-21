# Test Specification: Knowledge System Effectiveness

## Test Environment

- **Framework:** pytest with pytest-asyncio
- **Database:** In-memory DuckDB (fresh per test via fixture)
- **LLM mocking:** `unittest.mock.AsyncMock` for LLM extraction calls
- **File I/O:** `tmp_path` fixture for JSONL trace files and audit reports
- **Existing fixtures:** Reuse `knowledge_db`, `duckdb_conn` fixtures from
  `tests/conftest.py`

## Test Suites

### Suite 1: Full Transcript Reconstruction

**File:** `tests/knowledge/test_transcript_reconstruction.py`

#### TS-1.1: Reconstruct Transcript from Agent Trace JSONL

**Covers:** 113-REQ-1.1, CP-1

**Setup:** Create a JSONL file at `{tmp_path}/agent_test-run.jsonl` with:
- 3 `assistant.message` events for `node_id="spec:1"` with content
  `"Message A"`, `"Message B"`, `"Message C"`
- 2 `assistant.message` events for `node_id="other:1"` (noise)
- 1 `tool.use` event for `node_id="spec:1"` (noise)

**Action:** Call `reconstruct_transcript(tmp_path, "test-run", "spec:1")`.

**Assertions:**
1. Return value contains `"Message A"`, `"Message B"`, `"Message C"`.
2. Return value does NOT contain content from `node_id="other:1"`.
3. Messages appear in JSONL file order (A before B before C).

#### TS-1.2: Fallback When JSONL Missing

**Covers:** 113-REQ-1.E1, CP-2

**Setup:** `tmp_path` contains no JSONL file.

**Action:** Call `reconstruct_transcript(tmp_path, "missing-run", "spec:1")`.

**Assertions:**
1. Returns empty string.
2. No exception raised.

#### TS-1.3: Skip When Zero Assistant Messages for Node

**Covers:** 113-REQ-1.E2, CP-2

**Setup:** Create JSONL with only `tool.use` events for `node_id="spec:1"`.

**Action:** Call `reconstruct_transcript(tmp_path, "test-run", "spec:1")`.

**Assertions:**
1. Returns empty string.

#### TS-1.4: Integration — Lifecycle Uses Reconstructed Transcript

**Covers:** 113-REQ-1.1, 113-REQ-1.2, 113-REQ-1.3

**Setup:**
- Create a JSONL trace file with 5 assistant messages totaling > 2000 chars
  for `node_id="spec:1"`.
- Mock `extract_and_store_knowledge` to capture its `transcript` argument.
- Create a `session-summary.json` with a short summary.

**Action:** Call `_extract_knowledge_and_findings("spec:1", 1, workspace)`.

**Assertions:**
1. `extract_and_store_knowledge` was called with `transcript` containing the
   full reconstructed transcript (not the short summary).
2. The session log message uses the summary from `session-summary.json`.

#### TS-1.5: Fallback to _build_fallback_input When Trace Empty

**Covers:** 113-REQ-1.E1, 113-REQ-1.3

**Setup:**
- No JSONL trace file exists.
- `_build_fallback_input` returns a string > 2000 chars.
- Mock `extract_and_store_knowledge`.

**Action:** Call `_extract_knowledge_and_findings("spec:1", 1, workspace)`.

**Assertions:**
1. `extract_and_store_knowledge` called with fallback input as transcript.
2. Warning logged about missing trace file.

---

### Suite 2: LLM-Powered Git Commit Extraction

**File:** `tests/knowledge/test_git_extraction.py`

#### TS-2.1: Extract Structured Facts from Commit Batch

**Covers:** 113-REQ-2.1, 113-REQ-2.3, CP-3

**Setup:**
- 5 commit messages, each > 20 chars, with substantive content.
- Mock LLM to return JSON array with 3 facts: one high, one medium, one low
  confidence.

**Action:** Call `_extract_git_facts_llm(batch)`.

**Assertions:**
1. Returns exactly 3 `Fact` objects.
2. Confidence values are 0.9, 0.6, 0.3 respectively.
3. Each fact has `category` in `{"decision", "pattern", "gotcha", "convention"}`.
4. Each fact has non-empty `keywords` list.

#### TS-2.2: Zero Facts from LLM Yields No Storage

**Covers:** 113-REQ-2.2, CP-3

**Setup:**
- 3 boilerplate commit messages ("chore: bump version", etc.).
- Mock LLM to return `[]`.

**Action:** Call `ingest_git_commits()`.

**Assertions:**
1. No rows inserted into `memory_facts` with `category='git'`.
2. `IngestResult.facts_added == 0`.

#### TS-2.3: LLM Failure Skips Batch

**Covers:** 113-REQ-2.E1

**Setup:**
- 2 batches of 20 commits each.
- Mock LLM to raise `TimeoutError` on first batch, return 2 facts on second.

**Action:** Call `ingest_git_commits()`.

**Assertions:**
1. Warning logged for first batch failure.
2. Second batch produces 2 facts.
3. `IngestResult.facts_added == 2`.

#### TS-2.4: Short Commit Messages Excluded

**Covers:** 113-REQ-2.E2

**Setup:**
- 3 commits: "fix typo" (9 chars), "ok" (2 chars), "refactor: extract
  helper function for date parsing to reduce duplication" (60 chars).
- Mock LLM to return 1 fact for the valid message.

**Action:** Call `ingest_git_commits()`.

**Assertions:**
1. LLM called with batch containing only the 60-char message.
2. The two short messages are not included in the LLM prompt.

#### TS-2.5: Batch Size Limit of 20

**Covers:** 113-REQ-2.1

**Setup:** 25 valid commit messages. Mock LLM for both batches.

**Action:** Call `ingest_git_commits()`.

**Assertions:**
1. LLM called exactly twice (batch of 20, batch of 5).

---

### Suite 3: Entity Signal Activation

**File:** `tests/knowledge/test_entity_signal_activation.py`

#### TS-3.1: Prior Touched Files Queried and Passed

**Covers:** 113-REQ-3.1, CP-4

**Setup:**
- Seed `session_outcomes` with 3 completed sessions for `spec_name="05_foo"`:
  - Session 1: `touched_path="src/a.py,src/b.py"`
  - Session 2: `touched_path="src/b.py,src/c.py"`
  - Session 3: `touched_path=NULL`

**Action:** Call `_query_prior_touched_files("05_foo")`.

**Assertions:**
1. Returns `["src/a.py", "src/b.py", "src/c.py"]` (deduplicated).
2. NULL touched_path rows are excluded.

#### TS-3.2: Limit to 50 Most Recent Paths

**Covers:** 113-REQ-3.2, CP-4

**Setup:**
- Seed `session_outcomes` with 60 sessions, each touching a unique file path,
  with sequential `created_at` timestamps.

**Action:** Call `_query_prior_touched_files("05_foo")`.

**Assertions:**
1. Returns exactly 50 paths.
2. The 50 paths correspond to the 50 most recently created sessions.

#### TS-3.3: No Prior Sessions Returns Empty List

**Covers:** 113-REQ-3.E1

**Setup:** Empty `session_outcomes` table.

**Action:** Call `_query_prior_touched_files("05_foo")`.

**Assertions:**
1. Returns `[]`.

#### TS-3.4: Integration — Retriever Receives Touched Files

**Covers:** 113-REQ-3.1

**Setup:**
- Seed `session_outcomes` with prior sessions.
- Mock `AdaptiveRetriever.retrieve` to capture `touched_files` argument.

**Action:** Call `_build_prompts(repo_root, 1, None)`.

**Assertions:**
1. `AdaptiveRetriever.retrieve` called with non-empty `touched_files`.

---

### Suite 4: Audit Report Consumption

**File:** `tests/knowledge/test_audit_consumption.py`

#### TS-4.1: Audit Findings Persisted to Database

**Covers:** 113-REQ-4.1, CP-5

**Setup:**
- Create an `AuditResult` with `overall_verdict="FAIL"` and 3 entries.
- DuckDB connection with `review_findings` table.

**Action:** Persist auditor results through the audit-review pathway.

**Assertions:**
1. `review_findings` table contains 3 rows with `category='audit'`.
2. Each row has correct `spec_name`, `severity`, `description`.

#### TS-4.2: Audit Findings Injected into Coder Prompts

**Covers:** 113-REQ-4.2, CP-5

**Setup:**
- Seed `review_findings` with 2 audit findings (category='audit',
  severity='critical') for `spec_name="05_foo"`.
- Configure a `NodeSessionRunner` for spec `05_foo`, archetype `coder`.

**Action:** Call `_build_prompts(repo_root, 1, None)`.

**Assertions:**
1. Task prompt contains audit finding descriptions.
2. Audit findings appear with the same formatting as pre-review findings.

#### TS-4.3: Audit Reports Retained Until End-of-Run

**Covers:** 113-REQ-4.3

**Setup:**
- Write an audit report to `.agent-fox/audit/audit_05_foo.md`.
- Simulate mid-run state (spec not fully completed).

**Action:** Verify that audit report file exists after audit persistence.

**Assertions:**
1. Audit report file still exists on disk.
2. File is only deleted by `cleanup_completed_spec_audits` at end-of-run.

#### TS-4.4: Unparseable Audit Report

**Covers:** 113-REQ-4.E1

**Setup:** Provide malformed audit result that fails parsing.

**Action:** Attempt to persist audit findings.

**Assertions:**
1. Warning logged.
2. Raw audit report file retained.
3. No rows inserted into `review_findings`.

---

### Suite 5: Compaction and Noise Reduction

**File:** `tests/knowledge/test_compaction_improvements.py`

#### TS-5.1: Substring Supersession

**Covers:** 113-REQ-5.1, CP-7

**Setup:** Insert 3 facts into `memory_facts`:
- Fact A: content="Use retry logic" (confidence=0.8)
- Fact B: content="Use retry logic with exponential backoff for API calls"
  (confidence=0.8)
- Fact C: content="Database connections use connection pooling" (confidence=0.7)

**Action:** Call `_substring_supersede(facts)`.

**Assertions:**
1. Fact A is superseded (its content is a substring of Fact B).
2. Fact B survives.
3. Fact C is unaffected.
4. Returns `superseded_count == 1`.

#### TS-5.2: Minimum Content Length Filter (Unit)

**Covers:** 113-REQ-5.2, CP-8

**Setup:** 3 facts with content lengths 30, 49, 50.

**Action:** Call `_filter_minimum_length(facts, min_length=50)`.

**Assertions:**
1. Only the 50-char fact survives.
2. Returns `filtered_count == 2`.

#### TS-5.2b: Short Facts Rejected at Transcript Ingestion (Integration)

**Covers:** 113-REQ-5.2, CP-8

**Setup:**
- Mock LLM extraction to return 3 facts: content lengths 30, 49, 60.
- DuckDB connection with `memory_facts` table.
- Valid transcript string exceeding minimum character threshold.

**Action:** Call `extract_and_store_knowledge(transcript, ...)`.

**Assertions:**
1. Only the 60-char fact is stored in `memory_facts`.
2. The two short facts are not present in `memory_facts`.

#### TS-5.2c: Short Facts Rejected at Git Ingestion (Integration)

**Covers:** 113-REQ-5.2, CP-8

**Setup:**
- Mock LLM to return 2 facts: content lengths 40, 80.
- DuckDB connection with `memory_facts` table.

**Action:** Call `ingest_git_commits()`.

**Assertions:**
1. Only the 80-char fact is stored in `memory_facts`.
2. The 40-char fact is not present in `memory_facts`.

#### TS-5.3: Confidence-Aware Deduplication

**Covers:** 113-REQ-5.3, CP-7

**Setup:** Two facts with cosine similarity > 0.92:
- Fact A: confidence=0.6, created earlier
- Fact B: confidence=0.8, created later

**Action:** Run deduplication with threshold=0.92.

**Assertions:**
1. Fact A is superseded (lower confidence).
2. Fact B survives.

#### TS-5.4: Confidence Tie-Breaking by Recency

**Covers:** 113-REQ-5.3

**Setup:** Two near-duplicate facts with identical confidence=0.7:
- Fact A: created at T1
- Fact B: created at T2 (later)

**Action:** Run deduplication.

**Assertions:**
1. Fact A is superseded.
2. Fact B (more recent) survives.

#### TS-5.5: Large Compaction Logged

**Covers:** 113-REQ-5.E1

**Setup:** 10 facts, 6 of which are duplicates or substrings.

**Action:** Call `compact(conn)`.

**Assertions:**
1. Info log emitted with before (10) and after (4) counts.
2. Log only emitted because reduction > 50%.

---

### Suite 6: Cold-Start Detection

**File:** `tests/knowledge/test_cold_start.py`

#### TS-6.1: Cold-Start Returns Empty Result

**Covers:** 113-REQ-6.1, 113-REQ-6.2, CP-6

**Setup:** Empty `memory_facts` table.

**Action:** Call `AdaptiveRetriever.retrieve(spec_name="new_spec", ...)`.

**Assertions:**
1. Returns `RetrievalResult` with `cold_start=True`.
2. `context` is empty or minimal header.
3. `signal_counts` is empty.
4. Debug log contains "Skipping retrieval: no facts available (cold start)".

#### TS-6.2: Non-Cold-Start Proceeds Normally

**Covers:** 113-REQ-6.1, 113-REQ-6.2

**Setup:** Insert 5 facts for `spec_name="existing_spec"` into `memory_facts`.

**Action:** Call `AdaptiveRetriever.retrieve(spec_name="existing_spec", ...)`.

**Assertions:**
1. `cold_start=False`.
2. `signal_counts` contains at least one non-zero signal.

#### TS-6.3: Count Query Failure Falls Through

**Covers:** 113-REQ-6.E1

**Setup:** Mock the count query to raise `duckdb.Error`.

**Action:** Call `AdaptiveRetriever.retrieve(...)`.

**Assertions:**
1. Normal retrieval proceeds (signals run).
2. Warning logged about count query failure.
3. `cold_start=False`.

#### TS-6.4: Global High-Confidence Facts Prevent Cold-Start

**Covers:** 113-REQ-6.1

**Setup:**
- No facts for `spec_name="new_spec"`.
- 3 facts with `spec_name="other_spec"` and `confidence=0.9` (above threshold).

**Action:** Call `AdaptiveRetriever.retrieve(spec_name="new_spec", confidence_threshold=0.5)`.

**Assertions:**
1. `cold_start=False` (high-confidence global facts exist).
2. Normal retrieval proceeds.

---

### Suite 7: Retrieval Quality Validation

**File:** `tests/knowledge/test_retrieval_quality.py`

#### TS-7.1: Retrieval Audit Event Emitted

**Covers:** 113-REQ-7.1, CP-9

**Setup:**
- Insert facts for `spec_name="05_foo"`.
- Provide a `SinkDispatcher` mock to capture audit events.
- Set `node_id="05_foo:1"` on the retriever context.

**Action:** Call `AdaptiveRetriever.retrieve(...)`.

**Assertions:**
1. Exactly one `knowledge.retrieval` audit event emitted.
2. Event payload contains:
   - `spec_name == "05_foo"`
   - `node_id == "05_foo:1"`
   - `facts_returned` (int, matches anchor count)
   - `signals_active` (list of signal names with non-empty results)
   - `cold_start == False`
   - `token_budget_used` (int >= 0)

#### TS-7.2: Retrieval Summary Stored in Session Outcomes

**Covers:** 113-REQ-7.2

**Setup:**
- Insert facts and run a full session lifecycle mock.
- Capture the `session_outcomes` row written by `DuckDBSink`.

**Action:** Complete a session through `NodeSessionRunner.execute()`.

**Assertions:**
1. `retrieval_summary` column in `session_outcomes` is non-null.
2. JSON-parsed value contains `facts_injected` (int) and `signals_active`
   (list of strings).

#### TS-7.3: Audit Event Failure Does Not Block Session

**Covers:** 113-REQ-7.E1

**Setup:** Mock `emit_audit_event` to raise an exception.

**Action:** Call `AdaptiveRetriever.retrieve(...)`.

**Assertions:**
1. Retrieval returns a valid `RetrievalResult` (no exception propagated).
2. Warning logged about audit event failure.

---

## Traceability Matrix

| Requirement | Test(s) | Correctness Property |
|-------------|---------|---------------------|
| 113-REQ-1.1 | TS-1.1, TS-1.4 | CP-1 |
| 113-REQ-1.2 | TS-1.4 | CP-1 |
| 113-REQ-1.3 | TS-1.4, TS-1.5 | CP-2 |
| 113-REQ-1.E1 | TS-1.2, TS-1.5 | CP-2 |
| 113-REQ-1.E2 | TS-1.3 | CP-2 |
| 113-REQ-2.1 | TS-2.1, TS-2.5 | CP-3 |
| 113-REQ-2.2 | TS-2.2 | CP-3 |
| 113-REQ-2.3 | TS-2.1 | CP-3 |
| 113-REQ-2.E1 | TS-2.3 | CP-3 |
| 113-REQ-2.E2 | TS-2.4 | CP-3 |
| 113-REQ-3.1 | TS-3.1, TS-3.4 | CP-4 |
| 113-REQ-3.2 | TS-3.2 | CP-4 |
| 113-REQ-3.E1 | TS-3.3 | CP-4 |
| 113-REQ-4.1 | TS-4.1 | CP-5 |
| 113-REQ-4.2 | TS-4.2 | CP-5 |
| 113-REQ-4.3 | TS-4.3 | CP-5 |
| 113-REQ-4.E1 | TS-4.4 | CP-5 |
| 113-REQ-5.1 | TS-5.1 | CP-7 |
| 113-REQ-5.2 | TS-5.2, TS-5.2b, TS-5.2c | CP-8 |
| 113-REQ-5.3 | TS-5.3, TS-5.4 | CP-7 |
| 113-REQ-5.E1 | TS-5.5 | CP-7 |
| 113-REQ-6.1 | TS-6.1, TS-6.4 | CP-6 |
| 113-REQ-6.2 | TS-6.1, TS-6.2 | CP-6 |
| 113-REQ-6.E1 | TS-6.3 | CP-6 |
| 113-REQ-7.1 | TS-7.1 | CP-9 |
| 113-REQ-7.2 | TS-7.2 | CP-9 |
| 113-REQ-7.E1 | TS-7.3 | CP-9 |
