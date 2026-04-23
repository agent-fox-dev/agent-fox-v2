# Knowledge System Architecture

## Conceptual Overview

---

## 1. What the Knowledge System Is

The agent-fox knowledge system is the institutional memory of an autonomous
coding orchestrator. It captures what happens during sessions — surprising
behaviors, unresolved quality concerns, spec corrections — and makes that
information available to future sessions for the same spec. This happens through
a clean protocol boundary: the engine calls `retrieve()` before a session and
`ingest()` after, never importing knowledge internals directly.

The system operates on a fundamental architectural principle: **every coding
session starts with a fresh context window, but not a blank mind.** The
orchestrator deliberately resets the LLM's context between sessions to prevent
accumulated confusion, while the knowledge system provides curated, relevant
prior knowledge to each new session. This separation of concerns — stateless
execution with persistent knowledge — is what allows agent-fox to run
autonomously across dozens or hundreds of sessions without context window
degradation.

---

## 2. The KnowledgeProvider Protocol

The engine interacts with the knowledge system through a two-method protocol:

```
KnowledgeProvider
  retrieve(spec_name, task_description) → list[str]
  ingest(session_id, spec_name, context)
```

`retrieve()` is called before a session to load relevant knowledge items.
`ingest()` is called after a successful coder session to extract and store new
knowledge from that session's work.

The concrete implementation is always `FoxKnowledgeProvider`, constructed at
startup in `run.py` and threaded through the session runner factory. A
`NoOpKnowledgeProvider` (which discards all ingestion and returns empty
retrieval results) serves as the fallback — useful for testing.

This boundary means the engine never imports knowledge internals directly. The
full knowledge pipeline can be replaced by providing a different implementation
of the protocol.

---

## 3. Knowledge Flow

```
     Coding Session (completed)
          │
          │ context dict
          │  • spec_name
          │  • touched_files
          │  • commit_sha
          │  • session_status
          ▼
  ┌───────────────────────────┐
  │  FoxKnowledgeProvider     │
  │       ingest()            │
  │                           │
  │  extract_gotchas()  ←LLM  │
  │  store_gotchas()          │
  └───────────┬───────────────┘
              │ 0-3 gotchas
              ▼
  ┌──────────────────────────────────────────────────────┐
  │                KNOWLEDGE STORE (DuckDB)               │
  │                                                      │
  │   gotchas ──────── errata_index                      │
  │                                                      │
  │   review_findings ──── verification_results           │
  │   session_outcomes ──── runs                          │
  └──────────────────────┬───────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  RETRIEVAL          │
              │  by spec_name only  │
              │  • errata           │
              │  • review findings  │
              │  • gotchas (TTL)    │
              └──────────┬──────────┘
                         │ labelled text blocks
              ┌──────────▼──────────┐
              │  CONTEXT INJECTION  │
              │  Into session prompt│
              └─────────────────────┘
```

---

## 4. Ingestion: Gotcha Extraction

`FoxKnowledgeProvider.ingest()` runs after every successful coder session
(sessions with `session_status == "completed"`). Review and verification sessions
are excluded — their outputs are already stored as structured findings.

The ingestion process:

1. **Build context.** Collects spec name, touched files, commit SHA, and session
   status into a context dict.

2. **Extract gotchas via LLM.** Calls `extract_gotchas()` with the configured
   SIMPLE-tier model. The extraction prompt asks: *"Based on this coding session,
   what was surprising or non-obvious? What would you want to know if you were
   starting a new session on this spec?"* The LLM returns 0–3 bullet points;
   each becomes a `GotchaCandidate` with a content hash (SHA-256 of normalized
   text).

3. **Store with deduplication.** `store_gotchas()` checks whether a gotcha with
   the same content hash already exists for that spec. Duplicates are silently
   skipped; new gotchas are inserted. Capped at 3 per session even if extraction
   returns more.

4. **Graceful failure.** Any exception during extraction or storage is logged as
   a WARNING. The session outcome is not affected — ingestion never blocks the
   coding lifecycle.

---

## 5. The Knowledge Store

Three tables hold the operational knowledge memory in DuckDB:

### 5.1 `gotchas`

Surprising or non-obvious findings extracted from session transcripts.

| Column | Description |
|---|---|
| `id` | UUID primary key |
| `spec_name` | Spec this gotcha belongs to |
| `text` | The gotcha description (1-3 sentences) |
| `content_hash` | SHA-256 of normalized text — used for deduplication |
| `session_id` | Node ID of the session that produced the gotcha |
| `created_at` | UTC timestamp — used for TTL expiry at retrieval time |

### 5.2 `errata_index`

Pointers from spec names to errata document file paths.

| Column | Description |
|---|---|
| `spec_name` | The specification name |
| `file_path` | Path to the errata document (e.g. `docs/errata/28_fix.md`) |
| `created_at` | UTC timestamp |

Errata entries are not produced automatically. They are registered explicitly
via `register_errata(conn, spec_name, file_path)` as part of a maintenance
workflow when a spec-to-code divergence is discovered and documented.

### 5.3 `review_findings` (shared with QA state)

Findings from pre-review, drift-review, and audit-review sessions. Unresolved
critical/major findings are also surfaced at retrieval time so coders see active
quality concerns in their context.

---

## 6. Retrieval: Finding the Right Knowledge

Before each session, `FoxKnowledgeProvider.retrieve(spec_name, task_description)`
is called. It queries three categories, all scoped by `spec_name`, using direct
DuckDB column-filter queries — no embeddings, no vector search:

| Category | Source table | Filter |
|---|---|---|
| **Errata** | `errata_index` | `spec_name = ?` |
| **Review carry-forward** | `review_findings` | `spec_name = ?`, severity in (`critical`, `major`), not superseded |
| **Gotchas** | `gotchas` | `spec_name = ?`, `created_at > now() - ttl_days` |

Results are assembled in priority order: errata first, reviews second, gotchas
last. Only gotchas are trimmed when the total count exceeds the configured
`max_items` cap (default: 10); errata and critical reviews are never dropped.

Each item is returned as a labelled text block (`[ERRATA]`, `[REVIEW]`,
`[GOTCHA]`) ready for prompt injection. If `retrieve()` raises any exception,
the session proceeds without knowledge context.

---

## 7. Context Injection: How Knowledge Enters a Session

When the orchestrator prepares a coding session, context assembly follows this
sequence:

1. **Extract subtask descriptions** from the task group in `tasks.md` to
   form the `task_description` passed to `retrieve()`.

2. **Call `KnowledgeProvider.retrieve()`** → returns labelled text blocks.

3. **Assemble context** — spec files (`requirements.md`, `design.md`,
   `test_spec.md`, `tasks.md`), DB-backed review/drift/verification findings,
   steering directives, the retrieved knowledge items, and prior group findings.

4. **Build system prompt** from the three-layer assembly: agent base profile +
   archetype profile + task context.

5. **Build task prompt** with archetype-specific instructions; for retry
   attempts, the previous error and active critical/major findings are prepended.

6. **Launch session.** The coding agent receives both prompts in a fresh context
   window inside an isolated git worktree.

After the session completes:

7. **Parse review findings** (for review archetypes) and persist to DuckDB.

8. **Call `KnowledgeProvider.ingest()`** (for coder sessions only) → extract
   0–3 gotchas via LLM and store with content-hash deduplication.

9. **Record session outcome** in `session_outcomes`.

10. **Emit audit events** to the per-run JSONL file.

This cycle repeats for every session, continuously growing the gotcha store for
each spec while TTL-based expiry prevents stale knowledge from accumulating.

---

## 8. Quality Assurance Layer

Beyond gotcha memory, agent-fox maintains a parallel quality knowledge layer
through its archetype system. Multiple agent archetypes produce structured
findings stored in DuckDB:

### Review Findings

The reviewer archetype (`pre-review` and `drift-review` modes) produces findings
classified by severity: critical, major, minor, and observation. Findings support
supersession — a finding can be marked as resolved when a subsequent session
addresses the issue.

### Drift Findings

The reviewer archetype (`drift-review` mode) compares spec assumptions against
the actual codebase and detects drift: places where existing code diverges from
what the spec assumes.

### Verification Results

The verifier archetype checks individual requirements against the implementation,
producing per-requirement pass/fail verdicts with evidence text.

### Blocking Decision History

When quality gates block a spec from proceeding (critical findings above
threshold), the blocking decision is recorded in `blocking_history` with outcome
tracking for future threshold calibration.

---

## 9. Audit and Observability

Every significant operation emits a structured audit event (run.start,
session.start, session.complete, session.fail, git.merge, git.conflict,
preflight_skip, config.reloaded). Events are severity-classified (info,
warning, error) and written to per-run JSONL files under `.agent-fox/audit/`.

Completed spec audit files are cleaned up at end-of-run to avoid unbounded
growth. The audit trail provides full traceability from session dispatch through
harvest to knowledge storage.

---

## 10. Design Principles

**A clean protocol boundary.** The engine calls `retrieve()` and `ingest()` on
a `KnowledgeProvider` — it never imports knowledge internals. The implementation
can be replaced (or no-oped) without touching the engine.

**Spec-scoped, high-signal.** Retrieval is intentionally narrow: errata and
gotchas are keyed by `spec_name` only, reviews are filtered to critical/major
only. This trades recall breadth for precision — the agent gets a small number
of directly relevant items rather than a large ranked list of loosely related
ones.

**No embeddings.** All retrieval uses direct column-filter SQL. This eliminates
the computational overhead and operational complexity of embedding generation and
vector indexing, at the cost of cross-spec knowledge transfer. The tradeoff
favors operational simplicity.

**TTL-based staleness.** Gotchas expire after a configurable number of days
rather than through decay formulas or contradiction detection. Old gotchas simply
stop appearing in retrieval. This is simple, predictable, and correct for the
common case where a gotcha is no longer relevant because the spec has been fully
implemented.

**Graceful degradation everywhere.** If knowledge retrieval fails, the session
proceeds without context. If gotcha extraction fails, the session outcome is
unaffected. The knowledge system never blocks the coding lifecycle.
