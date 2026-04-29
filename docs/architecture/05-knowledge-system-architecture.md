# Knowledge System Architecture

## Conceptual Overview

---

## 1. What the Knowledge System Is

The agent-fox knowledge system is the institutional memory of an autonomous
coding orchestrator. It captures what happens during sessions — quality
concerns, architectural decisions, spec corrections, session summaries — and
makes that information available to future sessions for the same or related
specs. This happens through a clean protocol boundary: the engine calls
`retrieve()` before a session and `ingest()` after, never importing knowledge
internals directly.

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
  retrieve(spec_name, task_description, task_group?, session_id?) → list[str]
  ingest(session_id, spec_name, context)
```

`retrieve()` is called before a session to load relevant knowledge items.
`ingest()` is called after a session to process its outputs and update the
knowledge store.

The concrete implementation is `FoxKnowledgeProvider`, constructed at startup
in `run.py` and threaded through the session runner factory. A
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
          │  • summary
          │  • archetype, task_group, attempt
          ▼
  ┌───────────────────────────────┐
  │  FoxKnowledgeProvider         │
  │       ingest()                │
  │                               │
  │  supersede injected findings  │
  │  store session summary        │
  │  detect & index ADR files     │
  └───────────┬───────────────────┘
              │
              ▼
  ┌──────────────────────────────────────────────────────┐
  │                KNOWLEDGE STORE (DuckDB)               │
  │                                                      │
  │   review_findings ──── drift_findings                │
  │   verification_results ── finding_injections          │
  │   session_summaries ──── adr_entries                  │
  │   errata ──────────────── audit_events                │
  └──────────────────────┬───────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  RETRIEVAL          │
              │  8 query categories │
              │  by spec + group    │
              │  keyword scoring    │
              └──────────┬──────────┘
                         │ prefixed text blocks
              ┌──────────▼──────────┐
              │  CONTEXT INJECTION  │
              │  Into session prompt│
              └─────────────────────┘
```

---

## 4. Ingestion: Post-Session Processing

`FoxKnowledgeProvider.ingest()` runs after every session. It performs three
actions:

### 4.1 Finding Supersession

If the session completed successfully, all review findings and verification
verdicts that were injected into that session (as tracked in the
`finding_injections` table) are automatically superseded. The logic: if the
coder saw the finding and completed the work, the finding is considered
addressed. Superseded findings remain in the database with a `superseded_by`
reference for audit history but are excluded from active queries.

This closes the retrieve-inject-address-supersede feedback loop — the core
mechanism by which the knowledge store stays current. Without it, resolved
findings would accumulate indefinitely and consume prompt space.

### 4.2 Session Summary Storage

Completed sessions that produced a non-empty summary are stored in the
`session_summaries` table. The summary is extracted from one of two sources:

- The agent's `session-summary.json` artifact (written by coder sessions).
- An auto-generated summary from persisted findings and verdicts (for
  reviewer and verifier sessions that don't produce artifact files).

Each summary record carries the spec name, task group, archetype, attempt
number, run ID, and creation timestamp. These summaries are later retrieved by
future sessions to provide cross-session context.

### 4.3 ADR Detection and Indexing

The session's `touched_files` are scanned for ADR files matching the
`docs/adr/*.md` pattern. For each detected file:

1. The markdown is parsed according to the MADR 4.0.0 format.
2. Mandatory sections (context, options, decision outcome) are extracted.
3. Keywords are derived via stop-word filtering.
4. Spec references are detected from requirement identifiers in the text.
5. The entry is stored in the `adr_entries` table with a content hash for
   deduplication (updates replace entries with matching file paths).

This ensures that architectural decisions made during coding sessions are
automatically indexed and available to future sessions working on related
functionality.

### 4.4 Graceful Failure

Any exception during ingestion is logged as a WARNING. The session outcome is
not affected — ingestion never blocks the coding lifecycle.

---

## 5. The Knowledge Store

The knowledge store lives in a single DuckDB database
(`.agent-fox/knowledge.duckdb`). The following tables form the knowledge layer
(separate from plan state and execution state):

### 5.1 `review_findings`

Findings from pre-review, drift-review, and audit-review sessions, classified
by severity (critical, major, minor, observation). Each finding has provenance
(spec, task group, session, attempt) and a `superseded_by` column. Unresolved
critical and major findings are the highest-priority knowledge items — they
represent known quality issues that coders must address.

### 5.2 `drift_findings`

Spec-to-code discrepancies detected by drift-review sessions. Structured
identically to review findings with additional spec and artifact reference
fields.

### 5.3 `verification_results`

Per-requirement verdicts (PASS, FAIL, PARTIAL) from verifier sessions, with
evidence text. Only FAIL verdicts are surfaced at retrieval time — PASS
verdicts are not actionable knowledge.

### 5.4 `finding_injections`

Tracks which findings and verdicts were injected into which sessions. This is
the bookkeeping table that enables the supersession lifecycle. When a session
completes, this table is queried to identify which findings to retire.

Cross-group items and prior-run findings are informational and are not recorded
here — they are not subject to automatic supersession.

### 5.5 `session_summaries`

Append-only log of natural-language session summaries. Each record carries the
spec name, task group, archetype, attempt number, run ID, and summary text.
Used for two retrieval categories: same-spec context (what earlier groups did)
and cross-spec context (what related specs accomplished in the current run).

### 5.6 `adr_entries`

Architecture Decision Records parsed from `docs/adr/*.md` in MADR 4.0.0
format. Fields: file path, title, status, chosen option, justification,
considered options, summary, content hash, keywords, and spec references.
Queried by spec reference or keyword overlap.

### 5.7 `errata`

Spec divergence records indexed from `docs/errata/` markdown files. Each
record is keyed by spec name and carries a content hash for deduplication.
Errata are never automatically generated — they are registered explicitly when
a spec-to-code divergence is discovered and documented.

### 5.8 `audit_events`

Structured log of every significant operation: run start, session
start/complete/fail, git merge, config reload, preflight skip. Each event has
a type, severity, run ID, node ID, and a JSON payload.

---

## 6. Retrieval: Finding the Right Knowledge

Before each session, `FoxKnowledgeProvider.retrieve()` is called with the spec
name, a task description derived from subtask bullets, the task group number,
and the session ID. It queries eight categories from DuckDB using direct SQL
with keyword-based relevance scoring — no embeddings, no vector search:

| Category | Source | Prefix | Scope |
|---|---|---|---|
| Review findings | `review_findings` | `[REVIEW]` | Active critical/major for this spec and task group |
| Verification verdicts | `verification_results` | `[VERDICT]` | Active FAIL verdicts only |
| Errata | `errata` | `[ERRATA]` | All errata for this spec |
| ADR summaries | `adr_entries` | `[ADR]` | ADRs matching spec or task keywords |
| Cross-group findings | `review_findings` | `[CROSS-GROUP]` | Critical/major from other groups in the same spec |
| Same-spec summaries | `session_summaries` | `[CONTEXT]` | Summaries from earlier sessions on this spec |
| Cross-spec summaries | `session_summaries` | `[CROSS-SPEC]` | Summaries from sessions on other specs (current run) |
| Prior-run findings | `review_findings` + `verification_results` | `[PRIOR-RUN]` | Unresolved findings from previous orchestrator runs |

### Relevance Scoring

Within each category, results are sorted by keyword overlap between the task
description and the item text. Keywords are extracted as lowercased words from
the task description; each item is scored by counting substring matches. This
ensures the most relevant items appear first when the result cap is reached.

### Priority and Capping

Review findings and errata are never dropped — they represent critical
institutional knowledge. Other categories are capped at configurable maximums.
Cross-group and prior-run items have separate, typically smaller caps since
they are informational rather than actionable.

### Injection Tracking

When a `session_id` is provided, the IDs of all injected review findings and
verification verdicts are recorded in `finding_injections`. This enables
automatic supersession on session completion (Section 4.1). Cross-group items
and prior-run findings are not tracked — they are informational context that
does not create supersession obligations.

### Graceful Degradation

If any table does not exist (fresh database) or any query fails, that category
is silently skipped. The session proceeds with whatever knowledge is available.
The knowledge system never prevents a session from launching.

---

## 7. Context Injection: How Knowledge Enters a Session

When the orchestrator prepares a coding session, context assembly follows this
sequence:

1. **Extract subtask descriptions** from the task group in `tasks.md` to
   form the `task_description` passed to `retrieve()`.

2. **Call `KnowledgeProvider.retrieve()`** → returns prefixed text blocks.

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

8. **Converge multi-instance outputs** (if applicable) using mode-specific
   convergence strategies.

9. **Call `KnowledgeProvider.ingest()`** → supersede injected findings, store
   session summary, index any new ADR files.

10. **Record session outcome** in `session_outcomes`.

11. **Emit audit events** to the per-run JSONL file.

This cycle repeats for every session. Findings are created by review sessions,
injected into coder sessions, and superseded when the coder completes — a
closed loop that keeps the knowledge store current without manual intervention.

---

## 8. The Finding Lifecycle

Findings follow a closed-loop lifecycle that is central to how the knowledge
system operates:

```
Created (by reviewer/verifier session)
    ↓
Active (queryable by context assembly and knowledge retrieval)
    ↓
Injected (tracked in finding_injections when served to a coder session)
    ↓
Superseded (retired when the session that received them completes)
```

**Created.** Review and verifier sessions parse structured JSON output to
produce findings classified by severity. Findings are stored with full
provenance: spec name, task group, session ID, attempt number, archetype,
and mode.

**Active.** Findings in the active state are visible to three consumers:
context assembly (rendered as structured markdown in Layer 3 of the system
prompt), knowledge retrieval (returned as `[REVIEW]` or `[VERDICT]` items),
and retry context (prepended to coder task prompts on retry attempts).

**Injected.** When `retrieve()` serves a finding to a session, the finding ID
and session ID are recorded in `finding_injections`. This bookkeeping is what
enables automatic supersession — without it, the system would not know which
findings the coder actually saw.

**Superseded.** When a session completes successfully, `ingest()` queries
`finding_injections` for all findings served to that session and marks them
as superseded. Superseded findings retain their `superseded_by` reference for
audit trail purposes but are excluded from all active queries.

Findings from cross-group and prior-run sources are not tracked in the
injection table. They are informational — the coder may benefit from seeing
them, but they are not considered addressed merely because the session
completed.

---

## 9. Quality Assurance Layer

Beyond the knowledge protocol, agent-fox maintains a quality layer through its
archetype system. Multiple agent archetypes produce structured findings stored
in DuckDB:

### Review Findings

The reviewer archetype in pre-review and audit-review modes produces findings
classified by severity: critical, major, minor, and observation. Critical
security findings always block downstream coder tasks regardless of the
configured blocking threshold. Other critical findings block when they exceed
the threshold.

### Drift Findings

The reviewer archetype in drift-review mode compares spec assumptions against
the actual codebase and detects drift: places where existing code diverges from
what the spec assumes.

### Verification Results

The verifier archetype checks individual requirements against the
implementation, producing per-requirement pass/fail verdicts with evidence text.

### Multi-Instance Convergence

When reviewer or verifier nodes run with multiple instances, their outputs are
merged deterministically before persistence:

- **Pre-review and drift-review**: Union all findings, deduplicate, and
  majority-gate critical findings (a finding is only promoted to critical if
  a majority of instances flagged it).
- **Audit-review**: Worst-verdict-wins — if any instance flags an issue, it
  is included.
- **Verifier**: Majority-vote each requirement verdict across instances.

This prevents individual outlier sessions from producing spurious blocking
findings while ensuring genuine issues are still caught.

---

## 10. Audit and Observability

Every significant operation emits a structured audit event to the
`SinkDispatcher`. Events carry a type, severity, run ID, node ID, archetype,
and a JSON payload. The sink dispatcher forwards events to all registered
sinks — the DuckDB sink for persistence and a JSONL file sink for
human-readable logs.

Agent conversation traces are a specialized form of audit event. During
session execution, the backend emits structured trace events: `session.init`
(with prompts), `tool.use` (with tool input), `assistant.message` (with
response text), `tool.error` (with error details), and `session.result` (with
metrics). These traces can be reconstructed into full conversation transcripts
from the JSONL audit trail after the fact.

Completed spec audit files are cleaned up at end-of-run to avoid unbounded
growth. Audit retention is managed per-run: the oldest runs beyond a
configurable limit are pruned at the start of each new run.

---

## 11. Design Principles

**A clean protocol boundary.** The engine calls `retrieve()` and `ingest()` on
a `KnowledgeProvider` — it never imports knowledge internals. The implementation
can be replaced (or no-oped) without touching the engine.

**Spec-scoped, high-signal.** Retrieval is intentionally precise: findings and
verdicts are keyed by spec and task group, errata by spec name, ADRs by spec
reference or keyword overlap. This trades recall breadth for precision — the
agent gets a small number of directly relevant items rather than a large ranked
list of loosely related ones.

**No embeddings.** All retrieval uses direct column-filter SQL with keyword
scoring. This eliminates the computational overhead and operational complexity
of embedding generation and vector indexing. The tradeoff favors operational
simplicity over cross-spec semantic discovery.

**Closed-loop finding lifecycle.** Findings are not merely stored — they are
tracked through injection and retired on completion. This prevents resolved
issues from permanently consuming prompt space, while preserving full audit
history through supersession references.

**Cross-session continuity.** Session summaries bridge the context gap between
sessions. Same-spec summaries give later groups visibility into what earlier
groups accomplished. Cross-spec summaries connect related work across specs.
Prior-run findings surface issues that survived previous runs. Together, these
mechanisms provide continuity of purpose across the session boundary.

**Graceful degradation everywhere.** If knowledge retrieval fails, the session
proceeds without context. If ingestion fails, the session outcome is
unaffected. The knowledge system never blocks the coding lifecycle.

---

*Previous: [Night-Shift Mode](04-night-shift.md)*
