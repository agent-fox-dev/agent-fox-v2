# Test Specification: Fact Lifecycle Management

## Overview

Test cases cover three fact lifecycle mechanisms (deduplication, contradiction
detection, decay) and their integration into the harvest pipeline and
end-of-run cleanup. Tests use in-memory DuckDB instances with pre-seeded
facts and mock LLM responses. Property tests verify mathematical invariants
of the decay formula and threshold behavior.

## Test Cases

### TS-90-1: Dedup detects near-duplicate by embedding similarity

**Requirement:** 90-REQ-1.1
**Type:** unit
**Description:** Verify that `dedup_new_facts()` identifies existing facts
with cosine similarity above the threshold.

**Preconditions:**
- In-memory DuckDB with `memory_facts` and `memory_embeddings` tables.
- One existing active fact with embedding `[0.1, 0.2, ..., 0.384]`.
- Dedup threshold set to 0.92.

**Input:**
- A new fact whose embedding has cosine similarity 0.95 to the existing fact.

**Expected:**
- `DedupResult.superseded_ids` contains the existing fact's UUID.
- `DedupResult.surviving_facts` contains the new fact.

**Assertion pseudocode:**
```
result = dedup_new_facts(conn, [new_fact], threshold=0.92)
ASSERT len(result.superseded_ids) == 1
ASSERT result.superseded_ids[0] == existing_fact.id
ASSERT len(result.surviving_facts) == 1
```

### TS-90-2: Dedup supersedes older fact

**Requirement:** 90-REQ-1.2
**Type:** unit
**Description:** Verify that the older fact's `superseded_by` is set to the
new fact's UUID after dedup.

**Preconditions:**
- In-memory DuckDB with one existing active fact (older).
- New fact is a near-duplicate (similarity > 0.92).

**Input:**
- One new fact with high similarity to the existing fact.

**Expected:**
- The existing fact's `superseded_by` column equals the new fact's UUID.
- The new fact remains active (`superseded_by IS NULL`).

**Assertion pseudocode:**
```
dedup_new_facts(conn, [new_fact], threshold=0.92)
row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [old_fact.id]).fetchone()
ASSERT str(row[0]) == new_fact.id
new_row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [new_fact.id]).fetchone()
ASSERT new_row[0] IS NULL
```

### TS-90-3: Dedup supersedes multiple existing facts

**Requirement:** 90-REQ-1.3
**Type:** unit
**Description:** When multiple existing facts exceed the threshold, all are
superseded.

**Preconditions:**
- In-memory DuckDB with three existing active facts, all with similar
  embeddings.

**Input:**
- One new fact similar to all three.

**Expected:**
- All three existing facts have `superseded_by` set to the new fact's UUID.

**Assertion pseudocode:**
```
result = dedup_new_facts(conn, [new_fact], threshold=0.92)
ASSERT len(result.superseded_ids) == 3
for old_id in result.superseded_ids:
    row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [old_id]).fetchone()
    ASSERT str(row[0]) == new_fact.id
```

### TS-90-4: Dedup threshold is configurable

**Requirement:** 90-REQ-1.4
**Type:** unit
**Description:** Verify that the threshold is read from config and controls
dedup behavior.

**Preconditions:**
- Two facts with cosine similarity of 0.90.

**Input:**
- `threshold=0.85` (should trigger dedup) and `threshold=0.95` (should not).

**Expected:**
- At 0.85: dedup supersedes the older fact.
- At 0.95: no supersession.

**Assertion pseudocode:**
```
result_low = dedup_new_facts(conn, [new_fact], threshold=0.85)
ASSERT len(result_low.superseded_ids) == 1

result_high = dedup_new_facts(conn, [new_fact], threshold=0.95)
ASSERT len(result_high.superseded_ids) == 0
```

### TS-90-5: Contradiction detection identifies candidates by similarity

**Requirement:** 90-REQ-2.1
**Type:** unit
**Description:** Verify that candidate pairs are generated from facts with
similarity above the contradiction threshold.

**Preconditions:**
- In-memory DuckDB with existing facts and embeddings.
- Mock LLM returns `contradicts: false` for all pairs.

**Input:**
- New facts with varying similarity to existing facts.
- Contradiction threshold of 0.8.

**Expected:**
- Only pairs with similarity >= 0.8 are sent to the LLM.
- Pairs below 0.8 are not evaluated.

**Assertion pseudocode:**
```
with mock_llm(return_value=no_contradiction):
    result = detect_contradictions(conn, new_facts, threshold=0.8)
    ASSERT mock_llm.call_count == expected_batch_count
    # Verify only high-similarity pairs were sent
```

### TS-90-6: Contradiction confirmed by LLM triggers supersession

**Requirement:** 90-REQ-2.2, 90-REQ-2.3
**Type:** unit
**Description:** When the LLM confirms a contradiction, the older fact is
superseded.

**Preconditions:**
- One existing fact: "Use kuksa.VAL service for data access."
- One new fact: "Use kuksa.val.v2.VAL service; kuksa.VAL is deprecated."
- Mock LLM returns `{"contradicts": true, "reason": "API version changed"}`.

**Input:**
- The new fact with high similarity to the existing fact.

**Expected:**
- The existing fact's `superseded_by` equals the new fact's UUID.
- `ContradictionResult.verdicts[0].contradicts` is true.

**Assertion pseudocode:**
```
result = detect_contradictions(conn, [new_fact], threshold=0.8, model="SIMPLE")
ASSERT len(result.superseded_ids) == 1
ASSERT result.superseded_ids[0] == old_fact.id
ASSERT result.verdicts[0].contradicts is True
ASSERT result.verdicts[0].reason == "API version changed"
```

### TS-90-7: Non-contradiction leaves facts unchanged

**Requirement:** 90-REQ-2.4
**Type:** unit
**Description:** When the LLM says no contradiction, no supersession occurs.

**Preconditions:**
- Existing fact and new fact with high similarity but no contradiction.
- Mock LLM returns `{"contradicts": false, "reason": "Related but compatible"}`.

**Input:**
- The new fact.

**Expected:**
- No facts superseded.
- Both facts remain active.

**Assertion pseudocode:**
```
result = detect_contradictions(conn, [new_fact], threshold=0.8)
ASSERT len(result.superseded_ids) == 0
old_row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [old_fact.id]).fetchone()
ASSERT old_row[0] IS NULL
```

### TS-90-8: Contradiction batching respects max size

**Requirement:** 90-REQ-2.5
**Type:** unit
**Description:** Candidate pairs are batched in groups of at most 10 for
LLM calls.

**Preconditions:**
- 25 candidate pairs identified by similarity.
- Mock LLM returns non-contradiction for all.

**Input:**
- 25 candidate pairs.

**Expected:**
- 3 LLM calls made (10 + 10 + 5).

**Assertion pseudocode:**
```
with mock_llm() as llm:
    detect_contradictions(conn, new_facts, threshold=0.8)
    ASSERT llm.call_count == 3
```

### TS-90-9: Decay formula computes correct effective confidence

**Requirement:** 90-REQ-3.1
**Type:** unit
**Description:** Verify the decay formula produces correct results at
known ages.

**Preconditions:**
- A fact with stored confidence 0.9, half-life 90 days.

**Input:**
- Age 0 days, 90 days, 180 days, 270 days.

**Expected:**
- Age 0: effective = 0.9
- Age 90: effective = 0.45
- Age 180: effective = 0.225
- Age 270: effective = 0.1125

**Assertion pseudocode:**
```
ASSERT effective_confidence(0.9, age=0, half_life=90) == approx(0.9)
ASSERT effective_confidence(0.9, age=90, half_life=90) == approx(0.45)
ASSERT effective_confidence(0.9, age=180, half_life=90) == approx(0.225)
ASSERT effective_confidence(0.9, age=270, half_life=90) == approx(0.1125)
```

### TS-90-10: Decay auto-supersedes facts below floor

**Requirement:** 90-REQ-3.2
**Type:** unit
**Description:** Facts whose effective confidence falls below the decay floor
are self-superseded.

**Preconditions:**
- In-memory DuckDB with facts at various ages.
- Half-life 90 days, floor 0.1.
- Fact A: confidence 0.9, age 300 days → effective ≈ 0.088 (below floor).
- Fact B: confidence 0.9, age 30 days → effective ≈ 0.72 (above floor).

**Input:**
- Run `run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)`.

**Expected:**
- Fact A: `superseded_by = A.id` (self-superseded).
- Fact B: `superseded_by IS NULL` (still active).

**Assertion pseudocode:**
```
count = run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)
ASSERT count == 1
row_a = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [fact_a.id]).fetchone()
ASSERT str(row_a[0]) == fact_a.id
row_b = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [fact_b.id]).fetchone()
ASSERT row_b[0] IS NULL
```

### TS-90-11: Stored confidence column unchanged after decay

**Requirement:** 90-REQ-3.6
**Type:** unit
**Description:** Decay cleanup does not modify the stored confidence value.

**Preconditions:**
- Fact with confidence 0.9, old enough to be auto-superseded.

**Input:**
- Run `run_decay_cleanup()`.

**Expected:**
- The `confidence` column still reads 0.9 after cleanup.

**Assertion pseudocode:**
```
run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)
row = conn.execute("SELECT confidence FROM memory_facts WHERE id = ?", [fact.id]).fetchone()
ASSERT row[0] == 0.9
```

### TS-90-12: End-of-run cleanup runs when fact count exceeds threshold

**Requirement:** 90-REQ-4.1, 90-REQ-4.2
**Type:** integration
**Description:** Cleanup executes during end-of-run when active facts exceed
the threshold.

**Preconditions:**
- In-memory DuckDB with 600 active facts (above default 500 threshold).
- Some facts old enough to decay.

**Input:**
- Call `run_cleanup(conn, config)`.

**Expected:**
- Decay runs and supersedes expired facts.
- `CleanupResult.facts_expired > 0`.

**Assertion pseudocode:**
```
result = run_cleanup(conn, config)
ASSERT result.facts_expired > 0
ASSERT result.active_facts_remaining < 600
```

### TS-90-13: End-of-run cleanup skipped below threshold

**Requirement:** 90-REQ-4.2, 90-REQ-4.3
**Type:** unit
**Description:** Decay does not run when active facts are at or below the
threshold.

**Preconditions:**
- In-memory DuckDB with 100 active facts (below default 500 threshold).

**Input:**
- Call `run_cleanup(conn, config)`.

**Expected:**
- `CleanupResult.facts_expired == 0`.

**Assertion pseudocode:**
```
result = run_cleanup(conn, config)
ASSERT result.facts_expired == 0
```

### TS-90-14: Cleanup emits audit event

**Requirement:** 90-REQ-4.5
**Type:** unit
**Description:** `fact.cleanup` audit event is emitted with correct payload.

**Preconditions:**
- Mock `SinkDispatcher`.
- Facts seeded to trigger decay.

**Input:**
- Call `run_cleanup(conn, config, sink_dispatcher=mock_sink, run_id="r1")`.

**Expected:**
- `mock_sink.emit_audit_event` called once.
- Event type is `FACT_CLEANUP`.
- Payload contains `facts_expired`, `facts_deduped`, `facts_contradicted`,
  `active_facts_remaining`.

**Assertion pseudocode:**
```
run_cleanup(conn, config, sink_dispatcher=mock_sink, run_id="r1")
ASSERT mock_sink.emit_audit_event.call_count == 1
event = mock_sink.emit_audit_event.call_args[0][0]
ASSERT event.event_type == AuditEventType.FACT_CLEANUP
ASSERT "facts_expired" in event.payload
ASSERT "active_facts_remaining" in event.payload
```

### TS-90-15: Cleanup returns summary dataclass

**Requirement:** 90-REQ-4.6
**Type:** unit
**Description:** `run_cleanup()` returns a `CleanupResult` with accurate counts.

**Preconditions:**
- DuckDB with known facts set up to produce specific counts.

**Input:**
- Call `run_cleanup()`.

**Expected:**
- Returned `CleanupResult` has correct counts matching DB state.

**Assertion pseudocode:**
```
result = run_cleanup(conn, config)
ASSERT isinstance(result, CleanupResult)
remaining = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
ASSERT result.active_facts_remaining == remaining
```

### TS-90-16: Harvest pipeline runs dedup then contradiction

**Requirement:** 90-REQ-5.1, 90-REQ-5.2, 90-REQ-5.3
**Type:** integration
**Description:** After extraction, dedup runs first, then contradiction
detection on surviving facts.

**Preconditions:**
- Mock `extract_facts()` returning 3 facts: one duplicate, one
  contradiction, one novel.
- Mock LLM for contradiction returns `contradicts: true` for one pair.

**Input:**
- Call `extract_and_store_knowledge()` with a transcript.

**Expected:**
- The duplicate is superseded before contradiction detection.
- The contradicted existing fact is superseded.
- The novel fact and the contradiction-triggering fact remain active.

**Assertion pseudocode:**
```
await extract_and_store_knowledge(transcript, spec, node_id, model, db)
active = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
ASSERT active == expected_active_count
```

### TS-90-17: Harvest event includes dedup and contradiction counts

**Requirement:** 90-REQ-5.4
**Type:** unit
**Description:** The `harvest.complete` audit event includes lifecycle counts.

**Preconditions:**
- Mock sink dispatcher.
- Harvest produces dedup and contradiction supersessions.

**Input:**
- Run harvest pipeline.

**Expected:**
- `harvest.complete` event payload contains `dedup_count` and
  `contradiction_count` keys.

**Assertion pseudocode:**
```
await extract_and_store_knowledge(...)
event = mock_sink.last_harvest_complete_event
ASSERT "dedup_count" in event.payload
ASSERT "contradiction_count" in event.payload
```

## Edge Case Tests

### TS-90-E1: Dedup skipped when new fact has no embedding

**Requirement:** 90-REQ-1.E1
**Type:** unit
**Description:** Facts without embeddings bypass dedup entirely.

**Preconditions:**
- New fact exists in DuckDB but has no entry in `memory_embeddings`.

**Input:**
- Call `dedup_new_facts()` with that fact.

**Expected:**
- No supersession. Fact inserted normally.
- `DedupResult.superseded_ids` is empty.

**Assertion pseudocode:**
```
result = dedup_new_facts(conn, [fact_without_embedding], threshold=0.92)
ASSERT len(result.superseded_ids) == 0
ASSERT len(result.surviving_facts) == 1
```

### TS-90-E2: Dedup skipped when no existing embeddings

**Requirement:** 90-REQ-1.E2
**Type:** unit
**Description:** When `memory_embeddings` is empty, dedup is skipped.

**Preconditions:**
- Empty `memory_embeddings` table. Facts exist in `memory_facts`.

**Input:**
- Call `dedup_new_facts()`.

**Expected:**
- No supersession. All new facts survive.

**Assertion pseudocode:**
```
result = dedup_new_facts(conn, new_facts, threshold=0.92)
ASSERT len(result.superseded_ids) == 0
ASSERT len(result.surviving_facts) == len(new_facts)
```

### TS-90-E3: LLM failure during contradiction is non-fatal

**Requirement:** 90-REQ-2.E1
**Type:** unit
**Description:** API errors during contradiction check are caught and logged.

**Preconditions:**
- Mock LLM raises `anthropic.APIError`.

**Input:**
- Call `detect_contradictions()`.

**Expected:**
- No supersession. All facts remain active.
- Warning logged.
- No exception propagated.

**Assertion pseudocode:**
```
with mock_llm(side_effect=APIError):
    result = detect_contradictions(conn, new_facts, threshold=0.8)
    ASSERT len(result.superseded_ids) == 0
```

### TS-90-E4: Malformed LLM JSON treated as non-contradiction

**Requirement:** 90-REQ-2.E3
**Type:** unit
**Description:** Invalid JSON from LLM does not trigger supersession.

**Preconditions:**
- Mock LLM returns `"not valid json {"`.

**Input:**
- Call `detect_contradictions()`.

**Expected:**
- No supersession. Warning logged.

**Assertion pseudocode:**
```
with mock_llm(return_value="not valid json {"):
    result = detect_contradictions(conn, new_facts, threshold=0.8)
    ASSERT len(result.superseded_ids) == 0
```

### TS-90-E5: Decay skipped for fact with NULL created_at

**Requirement:** 90-REQ-3.E1
**Type:** unit
**Description:** Facts without parseable timestamps are skipped by decay.

**Preconditions:**
- Fact in DuckDB with `created_at = NULL`.

**Input:**
- Call `run_decay_cleanup()`.

**Expected:**
- That fact remains active. Warning logged.

**Assertion pseudocode:**
```
count = run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)
row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [null_ts_fact.id]).fetchone()
ASSERT row[0] IS NULL
```

### TS-90-E6: Future-dated fact gets zero decay

**Requirement:** 90-REQ-3.E2
**Type:** unit
**Description:** Facts with future timestamps are treated as having zero age.

**Preconditions:**
- Fact with `created_at` set to tomorrow.

**Input:**
- Call `run_decay_cleanup()`.

**Expected:**
- Effective confidence equals stored confidence (no decay). Fact remains active.

**Assertion pseudocode:**
```
count = run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)
row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [future_fact.id]).fetchone()
ASSERT row[0] IS NULL
```

### TS-90-E7: Cleanup disabled via config

**Requirement:** 90-REQ-4.E1
**Type:** unit
**Description:** When `cleanup_enabled = false`, cleanup is fully skipped.

**Preconditions:**
- Config with `cleanup_enabled = False`.
- Facts that would normally be decayed.

**Input:**
- Call `run_cleanup()`.

**Expected:**
- `CleanupResult` with all counts at zero.
- No facts modified.

**Assertion pseudocode:**
```
config.knowledge.cleanup_enabled = False
result = run_cleanup(conn, config)
ASSERT result.facts_expired == 0
ASSERT result.facts_deduped == 0
ASSERT result.facts_contradicted == 0
```

### TS-90-E8: All new facts deduped skips contradiction

**Requirement:** 90-REQ-5.E1
**Type:** unit
**Description:** When dedup removes all new facts, contradiction detection
is skipped.

**Preconditions:**
- All new facts are near-duplicates of existing facts.
- Mock LLM for contradiction (should not be called).

**Input:**
- Run harvest pipeline.

**Expected:**
- LLM for contradiction is never called.
- `harvest.complete` event has `contradiction_count: 0`.

**Assertion pseudocode:**
```
with mock_contradiction_llm() as llm:
    await extract_and_store_knowledge(...)
    ASSERT llm.call_count == 0
```

## Property Test Cases

### TS-90-P1: Dedup idempotency

**Property:** Property 1 from design.md
**Validates:** 90-REQ-1.1, 90-REQ-1.2
**Type:** property
**Description:** Running dedup twice produces the same DB state.

**For any:** Set of 1-10 new facts with randomly generated embeddings and
1-20 existing facts with randomly generated embeddings.
**Invariant:** After calling `dedup_new_facts()` twice, the set of active
fact IDs is identical.

**Assertion pseudocode:**
```
FOR ANY new_facts IN gen_facts(1, 10), existing IN gen_facts(1, 20):
    setup_db(existing)
    dedup_new_facts(conn, new_facts, threshold=0.92)
    active_after_first = get_active_ids(conn)
    dedup_new_facts(conn, new_facts, threshold=0.92)
    active_after_second = get_active_ids(conn)
    ASSERT active_after_first == active_after_second
```

### TS-90-P2: Dedup threshold monotonicity

**Property:** Property 2 from design.md
**Validates:** 90-REQ-1.1, 90-REQ-1.2, 90-REQ-1.4
**Type:** property
**Description:** Lowering the threshold can only increase (or maintain) the
number of superseded facts.

**For any:** Threshold values t1, t2 where 0.5 <= t1 < t2 <= 1.0, and a
set of facts.
**Invariant:** `count_superseded(t1) >= count_superseded(t2)`.

**Assertion pseudocode:**
```
FOR ANY t1, t2 IN floats(0.5, 1.0) WHERE t1 < t2:
    setup_db(facts)
    r1 = dedup_new_facts(conn, new_facts, threshold=t1)
    reset_db(facts)
    r2 = dedup_new_facts(conn, new_facts, threshold=t2)
    ASSERT len(r1.superseded_ids) >= len(r2.superseded_ids)
```

### TS-90-P3: Contradiction requires LLM confirmation

**Property:** Property 3 from design.md
**Validates:** 90-REQ-2.2, 90-REQ-2.3, 90-REQ-2.4
**Type:** property
**Description:** No fact is superseded by contradiction without the LLM
returning `contradicts: true`.

**For any:** Set of candidate pairs where the mock LLM returns
`contradicts: false` for all.
**Invariant:** `ContradictionResult.superseded_ids` is empty.

**Assertion pseudocode:**
```
FOR ANY pairs IN gen_candidate_pairs(1, 20):
    with mock_llm(always_false):
        result = detect_contradictions(conn, new_facts, threshold=0.8)
        ASSERT len(result.superseded_ids) == 0
```

### TS-90-P4: Contradiction graceful degradation

**Property:** Property 4 from design.md
**Validates:** 90-REQ-2.E1, 90-REQ-2.E3
**Type:** property
**Description:** Any LLM failure leaves all facts unchanged and does not
propagate exceptions.

**For any:** Set of candidate pairs where the mock LLM raises an exception
or returns malformed JSON (randomly chosen per invocation).
**Invariant:** No facts are superseded by contradiction detection, and no
exception escapes `detect_contradictions()`.

**Assertion pseudocode:**
```
FOR ANY pairs IN gen_candidate_pairs(1, 15), failure IN [APIError, malformed_json, timeout]:
    active_before = get_active_ids(conn)
    result = detect_contradictions(conn, new_facts, threshold=0.8)  # no exception
    active_after = get_active_ids(conn)
    ASSERT active_before == active_after
    ASSERT len(result.superseded_ids) == 0
```

### TS-90-P5: Decay monotonicity

**Property:** Property 5 from design.md
**Validates:** 90-REQ-3.1
**Type:** property
**Description:** Effective confidence is non-increasing with age.

**For any:** Stored confidence c in (0, 1], half-life h > 0, ages a1 < a2.
**Invariant:** `effective(c, a1, h) >= effective(c, a2, h)`.

**Assertion pseudocode:**
```
FOR ANY c IN floats(0.01, 1.0), h IN floats(1, 365), a1, a2 IN floats(0, 1000) WHERE a1 < a2:
    ASSERT effective_confidence(c, a1, h) >= effective_confidence(c, a2, h)
```

### TS-90-P6: Decay floor auto-supersession boundary

**Property:** Property 6 from design.md
**Validates:** 90-REQ-3.2, 90-REQ-3.4
**Type:** property
**Description:** Facts exactly at the floor remain active; facts below are
superseded.

**For any:** Confidence c, half-life h, floor f, age a such that
`effective(c, a, h)` is deterministically above or below f.
**Invariant:** If `effective < f` then superseded; if `effective >= f`
then active.

**Assertion pseudocode:**
```
FOR ANY c, h, f, a IN valid_ranges:
    eff = effective_confidence(c, a, h)
    setup_fact_with_age(conn, confidence=c, age_days=a)
    run_decay_cleanup(conn, half_life_days=h, decay_floor=f)
    is_superseded = fact_is_superseded(conn, fact.id)
    IF eff < f:
        ASSERT is_superseded
    ELSE:
        ASSERT NOT is_superseded
```

### TS-90-P7: Stored confidence immutability

**Property:** Property 7 from design.md
**Validates:** 90-REQ-3.6
**Type:** property
**Description:** No lifecycle operation modifies the `confidence` column.

**For any:** Set of facts with random confidences, run through dedup, decay,
and cleanup.
**Invariant:** The `confidence` column for every fact is unchanged after all
operations.

**Assertion pseudocode:**
```
FOR ANY facts IN gen_facts(1, 50):
    setup_db(facts)
    confidences_before = {f.id: f.confidence for f in facts}
    run_decay_cleanup(conn, ...)
    dedup_new_facts(conn, new_facts, ...)
    FOR EACH fact_id, expected_conf IN confidences_before:
        row = conn.execute("SELECT confidence FROM memory_facts WHERE id = ?", [fact_id]).fetchone()
        ASSERT row[0] == expected_conf
```

### TS-90-P8: Cleanup threshold gate

**Property:** Property 8 from design.md
**Validates:** 90-REQ-4.2, 90-REQ-4.3
**Type:** property
**Description:** Decay only runs when active fact count exceeds the threshold.

**For any:** Active fact count N and threshold T where N and T are positive
integers.
**Invariant:** If `N <= T` then `CleanupResult.facts_expired == 0`
(decay did not run). If `N > T` then decay ran (may or may not expire facts
depending on age).

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 1000), t IN integers(1, 1000):
    setup_db_with_n_facts(conn, n, all_young=True)  # young facts won't decay
    config.knowledge.cleanup_fact_threshold = t
    result = run_cleanup(conn, config)
    IF n <= t:
        ASSERT result.facts_expired == 0  # decay did not run
```

### TS-90-P9: Pipeline order invariant

**Property:** Property 9 from design.md
**Validates:** 90-REQ-5.3, 90-REQ-5.E1
**Type:** property
**Description:** Facts superseded by dedup are never passed to contradiction
detection.

**For any:** Set of new facts where some are duplicates and some are
contradiction candidates.
**Invariant:** The contradiction detection function receives only facts that
survived dedup.

**Assertion pseudocode:**
```
FOR ANY new_facts IN gen_mixed_facts(1, 10):
    setup_db(existing)
    # Intercept contradiction detection input
    with mock_detect_contradictions() as mock_cd:
        run_harvest_pipeline(new_facts)
        actual_input = mock_cd.call_args.new_facts
        dedup_result = dedup_new_facts(conn, new_facts, ...)
        ASSERT set(f.id for f in actual_input) == set(f.id for f in dedup_result.surviving_facts)
```

## Integration Smoke Tests

### TS-90-SMOKE-1: Harvest dedup path end-to-end

**Execution Path:** Path 1 from design.md
**Description:** A duplicate fact extracted from a session is superseded
during harvest, and the original fact is marked superseded in DuckDB.

**Setup:** In-memory DuckDB with one existing fact and embedding. Mock
`extract_facts()` to return a near-duplicate. Real `dedup_new_facts()`,
real `MemoryStore.mark_superseded()`.

**Trigger:** `await extract_and_store_knowledge(transcript, ...)`.

**Expected side effects:**
- Existing fact's `superseded_by` is set to the new fact's UUID.
- New fact is active in `memory_facts`.

**Must NOT satisfy with:** Mocked `dedup_new_facts()` or mocked
`mark_superseded()`.

**Assertion pseudocode:**
```
existing = seed_fact_with_embedding(conn, content="Use kuksa.VAL service")
mock_extract = AsyncMock(return_value=[near_duplicate_fact])
with patch("...extract_facts", mock_extract):
    await extract_and_store_knowledge(transcript, spec, node, model, db)
row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [existing.id]).fetchone()
ASSERT row[0] IS NOT NULL
```

### TS-90-SMOKE-2: Contradiction detection path end-to-end

**Execution Path:** Path 2 from design.md
**Description:** A contradictory fact triggers LLM classification, and the
older fact is superseded.

**Setup:** In-memory DuckDB with existing fact and embedding. Mock
`extract_facts()` to return a contradictory fact. Mock LLM to return
`contradicts: true`. Real `detect_contradictions()`, real
`mark_superseded()`.

**Trigger:** `await extract_and_store_knowledge(transcript, ...)`.

**Expected side effects:**
- LLM called with the pair.
- Existing fact's `superseded_by` is set.

**Must NOT satisfy with:** Mocked `detect_contradictions()` or mocked
`mark_superseded()`.

**Assertion pseudocode:**
```
existing = seed_fact_with_embedding(conn, content="Use kuksa.VAL service")
new = make_fact(content="Use kuksa.val.v2.VAL; kuksa.VAL is deprecated")
mock_extract = AsyncMock(return_value=[new])
with patch("...extract_facts", mock_extract), \
     patch("...cached_messages_create_sync", return_value=contradiction_response):
    await extract_and_store_knowledge(transcript, spec, node, model, db)
row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?", [existing.id]).fetchone()
ASSERT str(row[0]) == new.id
```

### TS-90-SMOKE-3: Decay cleanup path end-to-end

**Execution Path:** Path 3 from design.md
**Description:** End-of-run cleanup decays old facts and marks them
self-superseded.

**Setup:** In-memory DuckDB with 600 facts, some >300 days old (will decay
below floor). Config with `cleanup_fact_threshold=500`.

**Trigger:** `run_cleanup(conn, config)`.

**Expected side effects:**
- Old facts with effective confidence below floor have
  `superseded_by = id`.
- Young facts remain active.
- `CleanupResult.facts_expired > 0`.

**Must NOT satisfy with:** Mocked `run_decay_cleanup()`.

**Assertion pseudocode:**
```
seed_facts(conn, count=600, some_old=True)
result = run_cleanup(conn, config)
ASSERT result.facts_expired > 0
old_rows = conn.execute(
    "SELECT id, superseded_by FROM memory_facts WHERE created_at < ?", [cutoff]
).fetchall()
for row in old_rows:
    ASSERT str(row[1]) == str(row[0])  # self-superseded
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 90-REQ-1.1 | TS-90-1 | unit |
| 90-REQ-1.2 | TS-90-2 | unit |
| 90-REQ-1.3 | TS-90-3 | unit |
| 90-REQ-1.4 | TS-90-4 | unit |
| 90-REQ-1.5 | TS-90-5 (logging) | unit |
| 90-REQ-1.E1 | TS-90-E1 | unit |
| 90-REQ-1.E2 | TS-90-E2 | unit |
| 90-REQ-2.1 | TS-90-5 | unit |
| 90-REQ-2.2 | TS-90-6 | unit |
| 90-REQ-2.3 | TS-90-6 | unit |
| 90-REQ-2.4 | TS-90-7 | unit |
| 90-REQ-2.5 | TS-90-8 | unit |
| 90-REQ-2.6 | TS-90-6 (logging) | unit |
| 90-REQ-2.7 | TS-90-5 | unit |
| 90-REQ-2.8 | TS-90-6 | unit |
| 90-REQ-2.E1 | TS-90-E3 | unit |
| 90-REQ-2.E2 | TS-90-E1 | unit |
| 90-REQ-2.E3 | TS-90-E4 | unit |
| 90-REQ-3.1 | TS-90-9 | unit |
| 90-REQ-3.2 | TS-90-10 | unit |
| 90-REQ-3.3 | TS-90-9 | unit |
| 90-REQ-3.4 | TS-90-10 | unit |
| 90-REQ-3.5 | TS-90-10 (logging) | unit |
| 90-REQ-3.6 | TS-90-11 | unit |
| 90-REQ-3.E1 | TS-90-E5 | unit |
| 90-REQ-3.E2 | TS-90-E6 | unit |
| 90-REQ-4.1 | TS-90-12 | integration |
| 90-REQ-4.2 | TS-90-12, TS-90-13 | integration, unit |
| 90-REQ-4.3 | TS-90-13 | unit |
| 90-REQ-4.4 | TS-90-E7 | unit |
| 90-REQ-4.5 | TS-90-14 | unit |
| 90-REQ-4.6 | TS-90-15 | unit |
| 90-REQ-4.E1 | TS-90-E7 | unit |
| 90-REQ-4.E2 | (covered by E7 pattern) | unit |
| 90-REQ-5.1 | TS-90-16 | integration |
| 90-REQ-5.2 | TS-90-16 | integration |
| 90-REQ-5.3 | TS-90-16 | integration |
| 90-REQ-5.4 | TS-90-17 | unit |
| 90-REQ-5.E1 | TS-90-E8 | unit |
| Property 1 | TS-90-P1 | property |
| Property 2 | TS-90-P2 | property |
| Property 3 | TS-90-P3 | property |
| Property 4 | TS-90-P4 | property |
| Property 5 | TS-90-P5 | property |
| Property 6 | TS-90-P6 | property |
| Property 7 | TS-90-P7 | property |
| Property 8 | TS-90-P8 | property |
| Property 9 | TS-90-P9 | property |
