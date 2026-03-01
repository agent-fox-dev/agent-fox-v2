# PRD: Structured Memory

**Source:** `.specs/prd.md` -- Section 5 "Structured Memory" (REQ-060 through
REQ-063), Section 4 "Plan and Execute" workflow (step 5: extract learnings),
Section 6 (memory extraction model), Section 7 (Knowledge Base output).

## Overview

The structured memory system extracts facts from completed coding sessions,
categorizes them, stores them in JSONL, selects relevant facts for future
session context, compacts the knowledge base, and maintains a human-readable
summary. It is the mechanism by which agent-fox learns from experience and
avoids repeating mistakes.

## Problem Statement

Each coding session produces implicit knowledge: which approaches worked, which
failed, what conventions the project follows, where fragile code lives, and
what architectural decisions were made. Without a structured memory system,
this knowledge is lost between sessions. The agent repeats mistakes, ignores
conventions, and cannot benefit from prior experience.

## Goals

- Extract structured facts from completed session transcripts using an LLM
  (SIMPLE model tier)
- Categorize facts into six types: gotcha, pattern, decision, convention,
  anti_pattern, fragile_area
- Store facts in JSONL format at `.agent-fox/memory.jsonl` (one fact per line)
- Select relevant facts for upcoming sessions by matching spec name and keyword
  overlap, within a budget of 50 facts
- Compact the knowledge base on demand: deduplicate by content hash and remove
  superseded facts
- Generate a human-readable summary at `docs/memory.md` organized by category

## Non-Goals

- DuckDB dual-write of facts -- that is spec 11/12 (Fox Ball)
- Embedding generation or vector search -- that is spec 12 (Fox Ball)
- Causal link extraction between facts -- that is spec 13 (Time Vision)
- Automatic compaction triggered by knowledge base size -- manual only (see
  PRD open question 3)
- Real-time pattern detection during active sessions -- batch only

## Key Decisions

- **Six fact categories** cover the useful knowledge types extracted from
  coding sessions: gotchas (things that tripped up the agent), patterns
  (successful approaches), decisions (architectural choices), conventions
  (project style rules), anti-patterns (approaches to avoid), and fragile
  areas (code regions sensitive to change).
- **JSONL is the source of truth.** One fact per line, JSON-serialized.
  The file is git-tracked so knowledge travels with the repository.
- **UUID-based fact identity.** Each fact gets a UUID, enabling supersession
  chains (fact B supersedes fact A by referencing A's UUID).
- **Keyword + spec name matching for context selection.** Simple, explainable,
  and deterministic. No embedding dependency.
- **Budget of 50 facts per session.** Prevents context window bloat while
  providing meaningful prior knowledge.
- **SIMPLE model for extraction.** Haiku-class model keeps extraction cost
  low since it runs after every successful session.
- **Content hash for deduplication.** SHA-256 of the content string detects
  exact duplicates regardless of metadata differences.

## Dependencies

| Dependency | Spec | What This Spec Uses |
|------------|------|---------------------|
| Config system | 01 | `MemoryConfig` (model), `ModelConfig` (memory_extraction), `AgentFoxConfig`, `load_config()` |
| Error hierarchy | 01 | `AgentFoxError`, custom `MemoryError` subclass |
| Model registry | 01 | `resolve_model()`, `ModelEntry`, `ModelTier.SIMPLE` |
| Logging | 01 | Named loggers for memory modules |
| Session outcome | 03 | `SessionOutcome` dataclass (spec_name, task_group, transcript) -- extraction runs after successful sessions |
