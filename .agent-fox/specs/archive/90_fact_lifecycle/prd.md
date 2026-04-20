# PRD: Fact Lifecycle Management

## Problem

The DuckDB `memory_facts` table accumulates facts indefinitely with no
automated hygiene. Across 409 active facts, zero have ever been superseded
(`superseded_by IS NULL` for all). The `review_findings` and
`verification_results` tables also show zero fact-level supersession activity.

This means outdated facts persist indefinitely. For example, a coder session
discovered and fixed a critical proto API mismatch ("tests used a non-existent
kuksa.VAL service while the actual Kuksa Databroker 0.5.0 exposes
kuksa.val.v2.VAL with different RPC methods"). Any prior fact stating "use
kuksa.VAL service" is now wrong but still active in the knowledge store and
could be served to future sessions.

Similarly, exact duplicate facts exist in the store (e.g., "chore: checkpoint
task group 4..." appears twice).

### Impact

- Stale facts pollute context assembly, potentially misleading future sessions.
- Duplicate facts waste context window budget.
- The supersession mechanism exists in code (`MemoryStore.mark_superseded()`,
  `Fact.supersedes` field) but is never triggered in practice.
- As the knowledge base grows, the signal-to-noise ratio decreases.

## Solution

Implement three automated fact lifecycle mechanisms:

### 1. Deduplication on Ingestion

Before inserting a new fact, compute its embedding and check cosine similarity
against existing active facts. If similarity exceeds a configurable threshold
(default: 0.92), supersede the older fact with the newer one instead of
inserting a duplicate.

This supplements the existing content-hash deduplication in `compaction.py`
(which catches exact string matches) by catching semantically equivalent facts
that differ only in phrasing.

### 2. LLM-Powered Contradiction Detection

After extracting new facts from a session transcript, use embedding similarity
to identify candidate pairs (new fact vs. existing fact with high similarity).
For each candidate pair, call an LLM to classify whether the new fact
contradicts the existing one. If the LLM confirms a contradiction, supersede
the older fact.

This is the core mechanism for resolving the "kuksa.VAL vs. kuksa.val.v2.VAL"
class of problems: two facts about the same topic where the newer one
invalidates the older.

The LLM call receives both facts and returns a structured verdict:
`{contradicts: bool, reason: str}`. Only confirmed contradictions trigger
supersession.

### 3. Age-Based Confidence Decay with Auto-Supersession

Facts lose relevance over time. Implement a decay function that reduces a
fact's effective confidence based on its age. When a fact's effective
confidence drops below a configured floor, it is automatically marked as
superseded (self-superseded, using its own ID as the `superseded_by` value,
matching the existing compaction pattern).

Decay is applied during periodic cleanup, not on every read. The decay
function uses a configurable half-life (default: 90 days) so that a fact's
effective confidence halves every 90 days.

### 4. End-of-Run Cleanup

Integrate the above mechanisms into the orchestrator's end-of-run flow:

- **After every run**: Run deduplication and contradiction detection on the
  facts extracted during that run (already in the harvest pipeline).
- **When fact count exceeds a threshold**: Run age-based decay and
  auto-supersession across the entire knowledge base. The threshold
  (default: 500 active facts) prevents unnecessary cleanup on small stores.

Both triggers are configurable and can be disabled independently.

## Non-Goals

- File/function reference staleness detection (too fragile for free-text fact
  content).
- Replacing the existing `compact()` function — the new mechanisms supplement
  it.
- Modifying the `review_findings`, `verification_results`, or
  `drift_findings` tables — those already have per-(spec, task_group)
  supersession via `insert_findings()` / `insert_verdicts()` /
  `insert_drift_findings()`.

## Dependencies

This spec has no cross-spec dependencies. It modifies existing modules in
`agent_fox/knowledge/` and `agent_fox/engine/knowledge_harvest.py` without
depending on artifacts from other specs.
