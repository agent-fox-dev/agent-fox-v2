# Knowledge System Architecture

## Conceptual Overview

---

## 1. What the Knowledge System Is

The agent-fox knowledge system is the institutional memory of an autonomous coding orchestrator. It captures what the coding agent learns during sessions — patterns discovered, pitfalls encountered, architectural decisions made, conventions established — and makes that knowledge available to future sessions so the same mistakes are never repeated and the same discoveries never need to happen twice.

The system operates on a fundamental architectural principle: **every coding session starts with a fresh context window, but not a blank mind.** The orchestrator deliberately resets the LLM's context between sessions to prevent accumulated confusion, while the knowledge system provides curated, relevant prior knowledge to each new session. This separation of concerns — stateless execution with persistent knowledge — is what allows agent-fox to run autonomously across dozens or hundreds of sessions without context window degradation.

---

## 2. The Knowledge Lifecycle

Knowledge flows through five phases: **Extraction → Ingestion → Lifecycle Management → Retrieval → Injection.** Each phase has distinct responsibilities and failure modes.

```
     Coding Session                    External Sources
          │                             │          │
          │ transcript                  ADRs    git log
          ▼                             │          │
  ┌───────────────┐               ┌─────▼──────────▼─────┐
  │  EXTRACTION   │               │     INGESTION         │
  │  LLM-powered  │               │  Deterministic parse  │
  │  fact mining   │               │  of ADRs, commits     │
  └───────┬───────┘               └──────────┬────────────┘
          │ typed facts                      │ typed facts
          ▼                                  ▼
  ┌──────────────────────────────────────────────────────┐
  │              KNOWLEDGE STORE (DuckDB)                │
  │                                                      │
  │   memory_facts ──── memory_embeddings                │
  │        │                                             │
  │        └──── fact_causes (causal graph)               │
  │                                                      │
  │   review_findings ── drift_findings                  │
  │   verification_results ── blocking_decisions          │
  │   session_outcomes ── execution_outcomes              │
  │   complexity_assessments ── audit_events              │
  └──────────────────────┬───────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  LIFECYCLE MGMT     │
              │  • Deduplication    │
              │  • Contradiction    │
              │  • Decay & expiry   │
              │  • Compaction       │
              └──────────┬──────────┘
                         │ curated facts
              ┌──────────▼──────────┐
              │     RETRIEVAL       │
              │  • Keyword match    │
              │  • Vector search    │
              │  • Causal traversal │
              │  • Temporal query   │
              └──────────┬──────────┘
                         │ ranked, relevant
              ┌──────────▼──────────┐
              │  CONTEXT INJECTION  │
              │  Into session prompt│
              └─────────────────────┘
```

---

## 3. Extraction: Mining Knowledge from Sessions

### 3.1 Session Transcript Extraction

After every coding session completes, the knowledge harvester processes the full session transcript through an LLM to extract structured facts. This is the primary knowledge creation path.

The extraction prompt instructs the LLM to identify learnings from the transcript and classify each one as a structured fact with four attributes:

- **Content** — A concise 1-2 sentence description of the learning.
- **Category** — One of six types that define the nature of the knowledge:
  - **Gotcha** — A surprising or non-obvious behavior that tripped the agent up. "The pytest-asyncio plugin requires `mode='auto'` in pyproject.toml."
  - **Pattern** — A recurring approach that works well. "Wrapping DuckDB calls in try/except and falling back to JSONL prevents test isolation failures."
  - **Decision** — An architectural or design choice made and why. "Chose DuckDB over SQLite for the knowledge store because of native vector similarity support."
  - **Convention** — A coding standard or project norm. "All public API functions include a docstring with an Args section."
  - **Anti-pattern** — Something that was tried and should be avoided. "Don't use `subprocess.run` with `shell=True` for git commands — it breaks on paths with spaces."
  - **Fragile Area** — A part of the codebase that is known to be brittle or error-prone. "The migration runner is sensitive to table ordering due to foreign key constraints."
- **Confidence** — A float between 0.0 and 1.0 indicating how reliable the learning is (normalized from LLM-provided high/medium/low labels).
- **Keywords** — 2-5 terms for matching the fact to relevant future tasks.

The extraction output is a JSON array parsed and validated with defensive handling for malformed LLM responses (truncated fields, invalid categories, empty content). Each valid fact is assigned a UUID, timestamped, and annotated with provenance: the spec name, session ID, and git commit SHA.

### 3.2 Causal Link Extraction

Once a fact corpus reaches a minimum threshold (5 or more active facts), the harvester performs a second LLM pass to extract causal relationships between facts. This builds a directed causal graph where edges represent "this learning led to that learning" or "this decision caused this consequence."

The causal extraction is context-bounded: when the total fact count exceeds a configurable limit, prior facts are ranked by embedding similarity to the newly extracted facts, and only the top-N most relevant prior facts are included in the causal prompt. This prevents the causal extraction prompt from growing unboundedly as the knowledge base scales.

Causal links are stored as directed edges in a `fact_causes` table with referential integrity — both the cause and effect fact IDs must exist in the fact store before a link can be created.

### 3.3 External Knowledge Ingestion

Beyond session transcripts, the knowledge system ingests two additional sources:

- **Architecture Decision Records (ADRs)** — Parsed from the project's `docs/adr/` directory. ADR content is converted into facts with category `decision` and ingested with full provenance.
- **Git commit messages** — Parsed from the repository's commit history. Significant commits (not fixups or merge commits) are converted into facts that capture what changed and why.

Both sources use deterministic parsing rather than LLM extraction, generating embeddings for vector search alongside the structured fact data.

---

## 4. The Knowledge Store

### 4.1 Storage Architecture

DuckDB serves as the primary knowledge store — chosen for its embedded operation (no server process), native vector similarity support via the VSS extension, and OLAP-friendly SQL for analytical queries over the knowledge base.

The schema is versioned through a forward-only migration system. The core tables are:

**Fact Tables:**
- `memory_facts` — The canonical fact store. Each row is a typed fact with content, category, confidence, timestamps, provenance (spec, session, commit), and a supersession chain (`superseded_by` column).
- `memory_embeddings` — Vector embeddings keyed by fact ID, used for similarity search. Dimensions are configurable (384, 768, or 1536).
- `fact_causes` — The causal graph: directed edges between fact UUIDs.

**Execution History:**
- `session_outcomes` — Cost, duration, status, and touched paths for every coding session.
- `execution_outcomes` — Aggregated outcomes per spec (joined with complexity assessments).
- `complexity_assessments` — Pre-session complexity estimates for task groups.
- `tool_calls` / `tool_errors` — Tool usage tracking per session.

**Quality Assurance:**
- `review_findings` — Issues found by the skeptic and oracle archetypes (severity-classified, with supersession).
- `drift_findings` — Spec-to-implementation drift detected during oracle review.
- `verification_results` — Requirement-level pass/fail verdicts with evidence.
- `blocking_decisions` — Records of when quality gates blocked a spec from proceeding, with outcome tracking for threshold learning.

**Operational:**
- `audit_events` — Structured audit trail with event types and severities.
- `schema_version` — Migration tracking.

A JSONL export of active facts is maintained alongside DuckDB for portability and as a fallback when the database file is locked by another process.

### 4.2 The Supersession Model

Facts are never deleted. Instead, they are superseded — marked with a reference to the fact that replaced them. This preserves full knowledge history while keeping the active fact set clean.

Supersession can happen through three mechanisms:
1. **Explicit supersession** — A new fact declares it replaces an older one (via the `supersedes` field set during extraction).
2. **Contradiction resolution** — The lifecycle manager detects that a new fact contradicts an existing one and marks the old fact as superseded.
3. **Decay expiry** — A fact's effective confidence decays below the minimum floor and it self-supersedes (superseded_by = own ID).

All queries that load "active" facts filter on `WHERE superseded_by IS NULL`, ensuring only current knowledge is used while historical knowledge remains auditable.

---

## 5. Lifecycle Management: Keeping Knowledge Healthy

Knowledge degrades over time. Code changes, decisions get reversed, patterns stop being patterns. The lifecycle management layer combats this through four mechanisms that run automatically during knowledge harvesting.

### 5.1 Embedding-Based Deduplication

When new facts are ingested, each one is compared against all existing active facts using vector cosine similarity. If an existing fact's embedding is within a configurable threshold (default: 0.92 similarity), the existing fact is superseded by the new one — effectively treating the new fact as an updated version of the old knowledge.

This catches semantically equivalent facts that are phrased differently: "Use `pytest.raises` for exception testing" and "Exception tests should use the `pytest.raises` context manager" would be detected as near-duplicates.

### 5.2 Contradiction Detection

After deduplication, surviving new facts are checked against the existing corpus for contradictions. This is an LLM-powered batch process: candidate pairs are identified by embedding proximity (facts that are similar enough to potentially contradict each other), then sent to the LLM in batches of 10 for classification.

When a contradiction is confirmed, the older fact is superseded by the newer one, with the LLM's reasoning recorded. This handles the case where a decision is reversed ("We switched from JWT to session cookies") or a gotcha is resolved ("The pytest-asyncio bug was fixed in v0.21").

### 5.3 Age-Based Confidence Decay

Every fact's effective confidence decays exponentially over time using a configurable half-life (default: 90 days). The formula is:

```
effective_confidence = stored_confidence × 0.5^(age_days / half_life_days)
```

When effective confidence falls below a configurable floor (default: 0.1), the fact is auto-superseded. This ensures that ancient knowledge doesn't crowd out fresh learnings. The stored confidence value is never modified — decay is computed at query time or during cleanup sweeps.

This mirrors how real codebases evolve: a convention established 6 months ago may no longer apply if the framework was upgraded, and a gotcha from early development may have been fixed in a subsequent refactor.

### 5.4 Compaction

Compaction is a full-corpus cleanup that runs on demand. It performs content-hash deduplication (catching exact duplicates missed by embedding similarity), resolves transitive supersession chains (if B supersedes A and C supersedes B, only C survives), removes orphaned records, and re-exports the clean fact set.

---

## 6. Retrieval: Finding the Right Knowledge

### 6.1 Pre-Session Fact Selection

Before each coding session, the orchestrator loads relevant facts to inject into the session context. The selection process has multiple stages:

**Stage 1: Confidence Filtering.** Facts whose confidence falls below a configurable threshold (default: 0.5) are excluded immediately. This prevents low-confidence or decayed facts from consuming context budget.

**Stage 2: Relevance Matching.** Two signals determine relevance:
- **Spec affinity** — Facts from the same specification as the current task are automatically relevant (they capture learnings from prior task groups within the same feature area).
- **Keyword overlap** — Facts whose keywords overlap with the current task's keywords are included, even if from different specs. This captures cross-cutting knowledge ("the auth middleware gotcha applies to any spec that touches authentication").

**Stage 3: Ranking.** Relevant facts are scored by a composite of keyword match count and recency bonus (normalized 0-1 based on fact age). This prioritizes facts that are both topically relevant and recently created.

**Stage 4: Budget Enforcement.** The top-N facts (default: 50) are selected from the ranked list. This prevents knowledge injection from consuming too much of the session's context window.

### 6.2 Causal Context Enhancement

After initial selection, the system enhances the fact set with causal context. For each selected fact, the causal graph is traversed to find causally linked facts that weren't in the initial selection. This surfaces important context like "this convention exists because of this earlier gotcha" or "this pattern was adopted after this anti-pattern caused failures."

The traversal uses breadth-first search on the `fact_causes` graph, following both cause and effect directions. This means if a selected fact is an effect, its root causes are included; if it's a cause, its downstream consequences are included.

The enhanced fact set — keyword-selected facts plus their causal neighbors — is what ultimately gets injected into the coding session prompt.

### 6.3 The Oracle (RAG Pipeline)

For interactive knowledge queries (the `agent-fox ask` command), the system provides a full retrieval-augmented generation pipeline:

1. The question is embedded using the configured embedding model.
2. Vector similarity search retrieves the top-k most relevant facts (default: 20).
3. Retrieved facts are assembled into a context block with full provenance (fact ID, source spec, session ID, commit SHA, similarity score).
4. The context and question are sent to a synthesis model with instructions to answer only from provided facts, cite sources, flag contradictions, and not hallucinate.
5. The response is parsed for the answer text, source citations, contradiction flags, and a confidence assessment (derived from result count and similarity scores).

### 6.4 Temporal Queries

For "what happened and why" questions, the system provides temporal query support. This combines vector search (to find seed facts relevant to the question) with causal graph traversal (to build a timeline of cause-and-effect from those seeds).

The result is a rendered timeline showing causal chains with timestamps, provenance, and relationship indicators (cause ← root → effect). This enables questions like "why did we change the auth strategy" or "what led to the test failures in spec 12."

---

## 7. Quality Assurance Layer

Beyond fact memory, agent-fox maintains a parallel quality knowledge layer through its archetype system. Multiple agent archetypes (coder, skeptic, oracle, verifier) operate on the same codebase, each producing different types of quality findings.

### 7.1 Review Findings

The skeptic archetype performs code review and produces findings classified by severity: critical, major, minor, and observation. These findings are stored with full provenance and support supersession — a finding can be marked as resolved when a subsequent session addresses the issue.

### 7.2 Drift Findings

The oracle archetype compares implemented code against the specification and detects drift: places where the implementation diverges from what was specified. Drift findings reference both the spec artifact and the code artifact, enabling precise traceability.

### 7.3 Verification Results

The verifier archetype checks individual requirements against the implementation, producing pass/fail verdicts with evidence. Verdicts that later become invalid (due to code changes) can be superseded by re-verification.

### 7.4 Blocking Decision Learning

When quality gates block a spec from proceeding (e.g., too many critical findings), the blocking decision and its outcome are recorded. Over time, this data enables threshold optimization: the system can compute the blocking thresholds that minimize false positives (blocking work that was actually fine) while maintaining an acceptable false negative rate (letting through work that should have been blocked).

This creates a feedback loop where the quality gate becomes more accurate with experience — a form of learned quality calibration.

---

## 8. The Nightshift Daemon

The nightshift is a background daemon that performs code quality analysis independent of the coding session lifecycle. It operates on its own schedule, hunting for issues that accumulate between sessions across eight categories: linter debt, dead code, test coverage, dependency freshness, deprecated API usage, documentation drift, TODO/FIXME tracking, and quality gate failures.

The nightshift uses its own triage system to prioritize findings, a deduplication layer to avoid re-reporting known issues, and a fix pipeline that can generate specifications for automated remediation. It also performs staleness checks across the project's knowledge, identifying areas where knowledge may have drifted from reality. For the full night-shift architecture, see [Part 4: Night-Shift Mode](04-night-shift.md).

---

## 9. The Project Model

The project model is a read-only aggregate view computed from execution history and quality data. It provides:

- **Spec-level metrics** — Average cost, duration, failure rate, and session count per specification.
- **Module stability scores** — Finding density (findings per session) per spec, indicating which areas of the codebase generate the most quality issues.
- **Archetype effectiveness** — Success rate per archetype type, showing which review strategies are producing actionable findings.
- **Knowledge staleness** — Days since the last session per spec, flagging areas where knowledge may be outdated.
- **Active drift areas** — Specs with recent oracle drift findings, highlighting implementation-specification misalignment.

This model informs orchestration decisions: specs with high failure rates may receive more pre-session context, areas with active drift may trigger re-verification, and stale knowledge areas may be flagged for review.

---

## 10. Audit and Observability

Every significant operation in the knowledge system emits a structured audit event. Events are typed (run.start, session.start, fact.extracted, fact.causal_links, harvest.complete, harvest.empty, fact.compacted) and severity-classified (info, warning, error, critical).

Audit events are stored both in DuckDB (for querying) and in JSONL sink files (for streaming and external consumption). The audit trail provides full traceability from session execution through knowledge extraction to fact storage, enabling forensic analysis of why the knowledge base contains what it contains.

---

## 11. Context Injection: How Knowledge Enters a Session

When the orchestrator prepares a coding session, context assembly follows this sequence:

1. **Load specification** — The task group's spec files from `.specs/` are read.
2. **Select memory facts** — Relevant facts are loaded via confidence filtering → keyword/spec matching → recency-weighted ranking → budget enforcement (Section 6.1).
3. **Enhance with causal context** — Selected facts are enriched with causally-linked facts from the causal graph (Section 6.2).
4. **Inject review findings** — For retry attempts, active critical/major review findings from prior sessions on the same spec are injected so the coder can address identified issues.
5. **Build system prompt** — All of the above is assembled with the archetype-specific template (coder, oracle, skeptic, verifier) into a system prompt.
6. **Build task prompt** — The specific task group instructions, with retry context if applicable, form the task prompt.
7. **Launch session** — The coding agent receives both prompts in a fresh context window inside an isolated git worktree.

After the session completes:

8. **Harvest knowledge** — The session transcript is processed through the extraction pipeline (Section 3).
9. **Run lifecycle management** — Dedup, contradiction detection, and decay cleanup run on the new facts (Section 5).
10. **Update rendering** — `docs/memory.md` is regenerated from the current active fact set.
11. **Record outcome** — Session metrics are written to the execution history tables.
12. **Emit audit events** — The harvest results are logged to the audit trail.

This cycle repeats for every session, continuously growing and refining the knowledge base while keeping it healthy through automated lifecycle management.

---

## 12. Design Principles

Several principles run through the architecture:

**Facts, not summaries.** The system stores discrete, typed, attributable facts — not narrative summaries of sessions. This makes knowledge individually addressable, queryable, and supersedable. A summary can't be partially invalidated; a fact can.

**Supersession, not deletion.** Knowledge is never destroyed. Old facts are marked as superseded, preserving the full historical record while keeping the active set clean. This supports both current relevance and historical auditability.

**Provenance is mandatory.** Every fact knows where it came from: which spec, which session, which git commit. This enables source verification, contradiction tracing, and trust assessment. A fact with no provenance is a fact that can't be validated.

**Graceful degradation.** Every component handles failure non-fatally. If embedding generation fails, facts are stored without embeddings. If contradiction detection fails, facts are ingested without contradiction checks. If DuckDB is locked, the system falls back to JSONL. The knowledge system never blocks the coding session lifecycle.

**The orchestrator stays deterministic.** The orchestrator itself makes zero LLM calls. All LLM usage is confined to fact extraction, causal analysis, contradiction detection, and synthesis. The scheduling, sequencing, and lifecycle decisions are entirely deterministic, ensuring reproducible behavior regardless of model variance.