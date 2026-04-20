# PRD: Time Vision -- Temporal Reasoning

**Source:** `.specs/prd.md` -- REQ-160 through REQ-165.
`.specs/v2.md` -- Section 4 (Tail 2: Time Vision), causal graph design,
temporal queries, predictive pattern detection.

## Overview

Time Vision adds temporal reasoning to the agent-fox knowledge system. It
tracks causal links between facts, enables temporal queries ("what happened
last time we changed X?"), detects predictive patterns across sessions, and
enhances session context selection with causal graph data. Time Vision turns
historical data into actionable foresight -- the fox gets smarter about your
specific failure modes, not just general software development patterns.

## Problem Statement

agent-fox v1 extracts timestamped facts from sessions, but those facts exist in
isolation. "User.email became nullable" is a fact, but "User.email became
nullable because of spec 07, which was triggered by issue #34 about third-party
OAuth support, which caused spec 09 tests to break three weeks later" is a
causal chain that v1 cannot represent. Without causal links, the agent cannot
trace impact, predict breakage, or learn from recurring failure sequences.

## Goals

- Extract cause-effect relationships between facts during session harvest and
  store them in the `fact_causes` table in DuckDB
- Support causal graph traversal: given a fact, find its causes and effects,
  walk causal chains
- Enable temporal queries via the `ask` command that traverse the causal graph
  and return timeline-structured results
- Detect predictive patterns by analyzing historical co-occurrences (e.g.,
  "module X changes -> test Y breaks") as a batch computation
- Render timelines as indented text chains suitable for CLI display and piping
- Enhance pre-session context selection by prioritizing causally-linked facts
  alongside keyword-matched facts

## Non-Goals

- Real-time pattern detection during active sessions -- batch analysis only
- Interactive timeline visualization -- CLI text output only
- Causal link editing by humans -- read-only for now
- Automatic causal inference from code diffs -- causal links are extracted from
  session context by the extraction prompt
- Full causal graph validation or cycle detection at write time -- the graph is
  append-only and assumed acyclic

## Key Decisions

- **Causal links extracted at harvest time** -- the memory extraction prompt is
  enriched to identify cause-effect relationships with prior facts, keeping
  extraction cost within the existing session budget
- **`fact_causes` table** -- `(cause_id UUID, effect_id UUID)` directed acyclic
  graph, created by spec 11 and populated here
- **Pattern detection is batch, not streaming** -- computed on demand via the
  `agent-fox patterns` command or temporal `ask` queries, not during active
  sessions
- **Timelines rendered as indented text** -- suitable for CLI display and piping
  to other tools; no graphical visualization
- **Temporal queries routed through `ask`** -- same RAG pipeline from spec 12
  but augmented with causal graph traversal for timeline construction
- **Context enhancement is additive** -- causally-linked facts are added to
  the session context alongside existing keyword-matched facts (REQ-061), not
  replacing them

## Dependencies

| Dependency | Spec | What This Spec Uses |
|------------|------|---------------------|
| DuckDB knowledge store | 11 | `fact_causes` table, `session_outcomes` table, `memory_facts` table, `KnowledgeDB` connection manager |
| Fox Ball | 12 | Fact extraction pipeline (extended with causal metadata), embedding-based retrieval for temporal queries, `ask` command infrastructure |
| Config system | 01 | `KnowledgeConfig` for store path |
| Error hierarchy | 01 | `KnowledgeStoreError`, `AgentFoxError` |
| Logging | 01 | Named loggers for knowledge modules |
