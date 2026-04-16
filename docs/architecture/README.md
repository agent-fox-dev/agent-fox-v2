# Architecture Guide

This guide describes the internal architecture of agent-fox. It is written for
engineers who want to understand how the system works before reading the source
code. The documents stay at the conceptual level — no code snippets, no method
signatures, no class hierarchies. For API details, consult the source under
`agent_fox/`. For configuration specifics, see the
[configuration reference](../config-reference.md). For archetype details,
see [Part 3](03-execution-and-archetypes.md#agent-archetypes).

## Architectural Principles

Several design principles run through the entire system:

**Specs are contracts, not suggestions.** All work traces back to structured
specifications. Agents that deviate from specs are caught by review agents
before their code lands. This front-loads the human judgment and lets the
machine execute without improvisation.

**Planning is deterministic.** Given the same specs and configuration, the
planner produces the same task graph. There is no LLM inference in the
planning phase. The human can inspect the plan, predict what will happen,
and trust the execution order.

**The orchestrator is deterministic.** The orchestrator itself makes zero LLM
calls. Every dispatch, retry, and escalation decision is based on rules and
thresholds. LLM work happens inside sessions; the orchestrator only manages
them.

**Isolation by default.** Each coding session runs in its own git worktree on
its own feature branch. Multiple agents work simultaneously without stepping
on each other. Integration happens through a serializing merge lock.

**Separation of concerns through archetypes.** Four archetype entries (Coder,
Reviewer, Verifier, Maintainer) with a mode system divide labor. The Reviewer
archetype covers three distinct review roles (pre-review, drift-review,
audit-review) through modes that override injection points and tool
allowlists. Review modes cannot modify code. Implementation agents cannot
skip quality checks.

**Graceful degradation everywhere.** Every component handles failure
non-fatally. If embedding generation fails, facts are stored without
embeddings. If contradiction detection fails, facts are ingested unchecked.
If the database is locked, the system falls back to JSONL. The knowledge
system never blocks the coding session lifecycle.

## Document Map

The architecture is documented in five parts that follow the user's workflow.

### [Part 1: Spec Authoring and Spec Structure](01-spec-authoring.md)

How human intent enters the system. Covers the five-artifact spec model
(PRD, requirements, design, test spec, tasks), the traceability chain between
them, task groups and dependency declarations, spec discovery, the static and
AI validation pipeline, severity model, auto-fixers, and the lint command.

### [Part 2: Planning — From Specs to Task Graphs](02-planning.md)

How specs become an executable plan. Covers the four-phase graph construction
(base nodes, archetype injection, tag overrides, cross-spec edges),
topological sort with deterministic tie-breaking, fast mode, file impact
analysis, critical path analysis, graph persistence, runtime patching, and
hot-load discovery.

### [Part 3: Execution, Session Lifecycle, and Agent Archetypes](03-execution-and-archetypes.md)

How the plan is carried out. Covers the orchestrator's dispatch loop, the
four-phase session lifecycle (prepare, execute, harvest, assess), context
assembly, the four-entry archetype registry with mode system (coder, reviewer,
verifier, maintainer), multi-instance convergence strategies, the escalation
ladder, model routing, workspace isolation, merge integration, sync barriers,
and reset.

### [Part 4: Night-Shift Mode](04-night-shift.md)

How the system maintains itself. Covers the hunt-and-fix daemon, eight
hunt categories, the LLM critic for finding consolidation, fingerprint-based
deduplication, batch triage with dependency and supersession detection, the
two-agent fix pipeline, in-memory spec construction, cost limits, and
staleness detection.

### [Part 5: Knowledge System Architecture](05-knowledge-system-architecture.md)

How the system remembers. Covers fact extraction from session transcripts,
causal link discovery, external knowledge ingestion (ADRs, git history),
the DuckDB-backed knowledge store, the supersession model, lifecycle
management (deduplication, contradiction detection, confidence decay),
retrieval and context injection, the RAG query pipeline, temporal queries,
and the audit trail.

## Reading Order

Read in order for a complete picture, or jump to any part for a specific
topic. Each document is self-contained but cross-references the others where
concepts connect.
